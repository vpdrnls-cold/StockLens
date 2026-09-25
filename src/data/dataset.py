"""Build leakage-safe machine-learning datasets."""

from __future__ import annotations

from collections.abc import Sequence

from dataclasses import dataclass

import pandas as pd

from src.data.models import DailyBar
from src.features.engineering import FEATURE_COLUMNS, build_features


DEFAULT_TARGET_HORIZON = 5
TARGET_COLUMN = "target_return_5d"

# Entry timing for the target (T-1 framing, Phase H):
#   "close"     : target = close(t+h) / close(t) - 1
#                 (legacy; assumes you can trade at t's close using t's
#                 close-derived features -- not actually executable)
#   "next_open" : target = close(t+h) / open(t+1) - 1
#                 (features use information through t's close; the
#                 position is entered at t+1's opening auction, which is
#                 executable. Intraday diagnostic 2026-09-24 used this.)
#
# DEFAULT = "next_open" (2026-09-24). src/backtest/baseline.py has always
# executed T+1 open entry -> T+holding_days close exit, so the legacy
# "close" target trained the model on a return the engine never
# realizes. "next_open" makes target_return_5d exactly the engine's
# gross trade return (before costs). Top-50 entry-timing IC check
# (scripts/entry_timing_ic.py, train/validation only): feature IC ranks
# nearly unchanged (rank corr 0.97 / 0.93), most |IC| larger, gap-based
# reversal only visible under next_open.
#
# Results recorded before this change (CURRENT_STATUS items up to the
# Phase H entry-timing check) used "close"; pass entry="close" to
# reproduce them.
ENTRY_MODES = ("close", "next_open")
DEFAULT_ENTRY_MODE = "next_open"

# Split boundaries cover the full 5-stock overlap window
# (2002-10-29 ~ 2026-09-16, confirmed via scripts/check_data_coverage.py
# -- bounded by 035420's 2002-10-29 listing date). Roughly 70/15/15 by
# calendar time. The old 2024-03-13 ~ 2026-09-01 boundaries only gave
# ~38 test days (6 non-overlapping 5-day decisions); this test window
# (~3.2 years) gives ~230, which is enough to tell a real strategy edge
# apart from noise.
TRAIN_START_DATE = "2002-10-29"
TRAIN_END_DATE = "2019-12-31"

VALIDATION_START_DATE = "2020-01-01"
VALIDATION_END_DATE = "2023-06-30"

TEST_START_DATE = "2023-07-01"
TEST_END_DATE = "2026-09-16"


def build_stock_dataset(
    bars: Sequence[DailyBar],
    *,
    target_horizon: int = DEFAULT_TARGET_HORIZON,
    entry: str = DEFAULT_ENTRY_MODE,
) -> pd.DataFrame:
    """Build one stock's feature-and-target dataset.

    Features at time t use information available at or before t's close.
    The target is the forward return to t+horizon's close, entered at
    t's close (``entry="close"``) or at t+1's open (``entry="next_open"``).
    """
    if not bars:
        raise ValueError("bars must not be empty.")

    if target_horizon <= 0:
        raise ValueError("target_horizon must be positive.")

    if entry not in ENTRY_MODES:
        raise ValueError(f"entry must be one of {ENTRY_MODES}.")

    stock_codes = {bar.stock_code for bar in bars}
    if len(stock_codes) != 1:
        raise ValueError("All bars must belong to the same stock.")

    stock_code = next(iter(stock_codes))

    features = build_features(bars)

    # Sort by date before shifting: build_features() sorts internally,
    # but the target series must follow the same chronological order or
    # shift(-h) would pair the wrong days.
    ordered_bars = sorted(bars, key=lambda bar: bar.trade_date)
    trade_dates = [bar.trade_date for bar in ordered_bars]

    close_prices = pd.Series(
        [bar.close_price for bar in ordered_bars],
        index=trade_dates,
        dtype="float64",
    )

    if entry == "close":
        entry_prices = close_prices
    else:  # "next_open"
        open_prices = pd.Series(
            [bar.open_price for bar in ordered_bars],
            index=trade_dates,
            dtype="float64",
        )
        entry_prices = open_prices.shift(-1)

    target = (
        close_prices.shift(-target_horizon) / entry_prices - 1.0
    )

    target.index.name = "trade_date"

    target_df = target.rename(TARGET_COLUMN).reset_index()

    dataset = features.merge(
        target_df,
        on="trade_date",
        how="left",
        validate="one_to_one",
    )

    dataset.insert(1, "stock_code", stock_code)

    # Feature warm-up rows and rows without a future target cannot
    # be used for model training.
    dataset = dataset.dropna(
        subset=[*FEATURE_COLUMNS, TARGET_COLUMN]
    ).reset_index(drop=True)

    return dataset

def build_combined_dataset(
    stock_bars: dict[str, Sequence[DailyBar]],
    *,
    target_horizon: int = DEFAULT_TARGET_HORIZON,
    entry: str = DEFAULT_ENTRY_MODE,
) -> pd.DataFrame:
    """Build and concatenate datasets for multiple stocks."""
    if not stock_bars:
        raise ValueError("stock_bars must not be empty.")

    datasets: list[pd.DataFrame] = []

    for stock_code, bars in stock_bars.items():
        if not bars:
            raise ValueError(
                f"bars must not be empty for stock {stock_code}."
            )

        actual_stock_codes = {bar.stock_code for bar in bars}

        if actual_stock_codes != {stock_code}:
            raise ValueError(
                f"Bars for {stock_code} contain inconsistent stock codes."
            )

        dataset = build_stock_dataset(
            bars,
            target_horizon=target_horizon,
            entry=entry,
        )

        datasets.append(dataset)

    combined = pd.concat(
        datasets,
        ignore_index=True,
    )

    combined = combined.sort_values(
        ["trade_date", "stock_code"]
    ).reset_index(drop=True)

    return combined

@dataclass(frozen=True)
class TimeSplit:
    """Time-based train, validation, and test datasets."""

    train: pd.DataFrame
    validation: pd.DataFrame
    test: pd.DataFrame


def split_by_time(
    dataset: pd.DataFrame,
    *,
    train_start: str = TRAIN_START_DATE,
    train_end: str = TRAIN_END_DATE,
    validation_start: str = VALIDATION_START_DATE,
    validation_end: str = VALIDATION_END_DATE,
    test_start: str = TEST_START_DATE,
    test_end: str = TEST_END_DATE,
) -> TimeSplit:
    """Split a combined dataset into chronological train/validation/test sets."""
    if dataset.empty:
        raise ValueError("dataset must not be empty.")

    if "trade_date" not in dataset.columns:
        raise ValueError("dataset must contain 'trade_date'.")

    dates = pd.to_datetime(dataset["trade_date"])

    boundaries = pd.to_datetime(
        [
            train_start,
            train_end,
            validation_start,
            validation_end,
            test_start,
            test_end,
        ]
    )

    (
        train_start_dt,
        train_end_dt,
        validation_start_dt,
        validation_end_dt,
        test_start_dt,
        test_end_dt,
    ) = boundaries

    if not (
        train_start_dt
        <= train_end_dt
        < validation_start_dt
        <= validation_end_dt
        < test_start_dt
        <= test_end_dt
    ):
        raise ValueError("Time split boundaries must be chronological.")

    train_mask = (
        (dates >= train_start_dt)
        & (dates <= train_end_dt)
    )

    validation_mask = (
        (dates >= validation_start_dt)
        & (dates <= validation_end_dt)
    )

    test_mask = (
        (dates >= test_start_dt)
        & (dates <= test_end_dt)
    )

    train = dataset.loc[train_mask].copy()
    validation = dataset.loc[validation_mask].copy()
    test = dataset.loc[test_mask].copy()

    if train.empty:
        raise ValueError("Train split is empty.")

    if validation.empty:
        raise ValueError("Validation split is empty.")

    if test.empty:
        raise ValueError("Test split is empty.")

    return TimeSplit(
        train=train.reset_index(drop=True),
        validation=validation.reset_index(drop=True),
        test=test.reset_index(drop=True),
    )