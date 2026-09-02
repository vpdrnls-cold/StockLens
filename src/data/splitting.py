"""Time-based dataset splitting for StockLens."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pandas as pd


@dataclass(frozen=True)
class TimeSplit:
    """Container for train, validation, and test datasets."""

    train: pd.DataFrame
    validation: pd.DataFrame
    test: pd.DataFrame


def split_by_date(
    data: pd.DataFrame,
    *,
    train_end: date,
    validation_end: date,
) -> TimeSplit:
    """Split data chronologically without shuffling."""

    if data.empty:
        raise ValueError("data must not be empty.")

    if "trade_date" not in data.columns:
        raise ValueError("data must contain trade_date.")

    dates = pd.to_datetime(data["trade_date"]).dt.date

    if not dates.is_monotonic_increasing:
        raise ValueError("data must be sorted by trade_date.")

    if train_end >= validation_end:
        raise ValueError(
            "train_end must be earlier than validation_end."
        )

    train = data.loc[dates <= train_end].copy()

    validation = data.loc[
        (dates > train_end) & (dates <= validation_end)
    ].copy()

    test = data.loc[dates > validation_end].copy()

    if train.empty:
        raise ValueError("train split is empty.")

    if validation.empty:
        raise ValueError("validation split is empty.")

    if test.empty:
        raise ValueError("test split is empty.")

    return TimeSplit(
        train=train,
        validation=validation,
        test=test,
    )