"""Build leakage-safe machine-learning datasets."""

from __future__ import annotations

from collections.abc import Sequence

from dataclasses import dataclass

import pandas as pd

from src.data.models import DailyBar
from src.features.engineering import FEATURE_COLUMNS, build_features


DEFAULT_TARGET_HORIZON = 5
TARGET_COLUMN = "target_return_5d"

TRAIN_START_DATE = "2024-03-13"
TRAIN_END_DATE = "2025-12-31"

VALIDATION_START_DATE = "2026-01-01"
VALIDATION_END_DATE = "2026-06-30"

TEST_START_DATE = "2026-07-01"
TEST_END_DATE = "2026-09-01"


def build_stock_dataset(
    bars: Sequence[DailyBar],
    *,
    target_horizon: int = DEFAULT_TARGET_HORIZON,
) -> pd.DataFrame:
    """Build one stock's feature-and-target dataset.

    Features at time t use information available at or before t.
    The target is the forward return from t's close to t+horizon's close.
    """
    if not bars:
        raise ValueError("bars must not be empty.")

    if target_horizon <= 0:
        raise ValueError("target_horizon must be positive.")

    stock_codes = {bar.stock_code for bar in bars}
    if len(stock_codes) != 1:
        raise ValueError("All bars must belong to the same stock.")

    stock_code = next(iter(stock_codes))

    features = build_features(bars)

    close_prices = (
        pd.Series(
            [bar.close_price for bar in bars],
            index=[bar.trade_date for bar in bars],
            dtype="float64",
        )
    )

    target = (
        close_prices.shift(-target_horizon) / close_prices - 1.0
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