"""Tests for StockLens time-based splitting."""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import pytest

from src.data.splitting import split_by_date


def _make_data() -> pd.DataFrame:
    dates = [
        date(2024, 1, 1) + timedelta(days=index)
        for index in range(10)
    ]

    return pd.DataFrame(
        {
            "trade_date": dates,
            "value": range(10),
        }
    )


def test_split_is_chronological() -> None:
    data = _make_data()

    result = split_by_date(
        data,
        train_end=date(2024, 1, 4),
        validation_end=date(2024, 1, 7),
    )

    assert result.train["value"].tolist() == [0, 1, 2, 3]
    assert result.validation["value"].tolist() == [4, 5, 6]
    assert result.test["value"].tolist() == [7, 8, 9]


def test_splits_do_not_overlap() -> None:
    data = _make_data()

    result = split_by_date(
        data,
        train_end=date(2024, 1, 4),
        validation_end=date(2024, 1, 7),
    )

    train_dates = set(result.train["trade_date"])
    validation_dates = set(result.validation["trade_date"])
    test_dates = set(result.test["trade_date"])

    assert train_dates.isdisjoint(validation_dates)
    assert train_dates.isdisjoint(test_dates)
    assert validation_dates.isdisjoint(test_dates)


def test_empty_data_is_rejected() -> None:
    data = pd.DataFrame(columns=["trade_date"])

    with pytest.raises(ValueError, match="must not be empty"):
        split_by_date(
            data,
            train_end=date(2024, 1, 4),
            validation_end=date(2024, 1, 7),
        )


def test_unsorted_data_is_rejected() -> None:
    data = _make_data().iloc[::-1].reset_index(drop=True)

    with pytest.raises(ValueError, match="sorted"):
        split_by_date(
            data,
            train_end=date(2024, 1, 4),
            validation_end=date(2024, 1, 7),
        )


def test_invalid_boundaries_are_rejected() -> None:
    data = _make_data()

    with pytest.raises(ValueError, match="earlier"):
        split_by_date(
            data,
            train_end=date(2024, 1, 7),
            validation_end=date(2024, 1, 4),
        )