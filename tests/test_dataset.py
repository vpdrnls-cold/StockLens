from __future__ import annotations

import pandas as pd
import pytest

from src.data.dataset import (
    TARGET_COLUMN,
    build_combined_dataset,
    build_stock_dataset,
    split_by_time,
)
from src.data.models import DailyBar
from src.features.engineering import FEATURE_COLUMNS


def _make_bars(
    stock_code: str = "005930",
    count: int = 80,
) -> list[DailyBar]:
    """Create deterministic daily bars for dataset tests."""
    dates = pd.bdate_range("2026-01-02", periods=count)

    bars: list[DailyBar] = []

    for i, date in enumerate(dates):
        close = 100_000 + i * 1_000

        bars.append(
            DailyBar(
                stock_code=stock_code,
                trade_date=date.strftime("%Y-%m-%d"),
                open_price=close - 500,
                high_price=close + 1_000,
                low_price=close - 1_000,
                close_price=close,
                volume=1_000_000 + i * 10_000,
                trade_value_million_krw=100_000.0,
                previous_close_change=0.0,
                previous_close_change_sign=0,
                turnover_rate=1.0,
            )
        )

    return bars


def test_build_stock_dataset_contains_all_features_and_target() -> None:
    bars = _make_bars()

    dataset = build_stock_dataset(bars)

    expected_columns = [
        "trade_date",
        "stock_code",
        *FEATURE_COLUMNS,
        TARGET_COLUMN,
    ]

    assert list(dataset.columns) == expected_columns


def test_build_stock_dataset_removes_warmup_and_future_target_rows() -> None:
    bars = _make_bars(count=80)

    dataset = build_stock_dataset(bars)

    assert len(dataset) < len(bars)

    assert dataset["target_return_5d"].notna().all()
    assert dataset[list(FEATURE_COLUMNS)].notna().all().all()

    assert dataset["trade_date"].is_monotonic_increasing


def test_five_day_target_is_calculated_correctly() -> None:
    bars = _make_bars(count=80)

    dataset = build_stock_dataset(bars)

    first_row = dataset.iloc[0]

    current_close = float(
        next(
            bar.close_price
            for bar in bars
            if bar.trade_date == first_row["trade_date"]
        )
    )

    future_date = dataset.iloc[5]["trade_date"]

    future_close = float(
        next(
            bar.close_price
            for bar in bars
            if bar.trade_date == future_date
        )
    )

    expected_target = future_close / current_close - 1.0

    assert first_row[TARGET_COLUMN] == pytest.approx(expected_target)


def test_dataset_contains_only_one_stock() -> None:
    bars = _make_bars(stock_code="005930")

    dataset = build_stock_dataset(bars)

    assert dataset["stock_code"].nunique() == 1
    assert dataset["stock_code"].iloc[0] == "005930"


def test_mixed_stock_bars_are_rejected() -> None:
    bars = _make_bars(stock_code="005930", count=40)
    bars += _make_bars(stock_code="000660", count=40)

    with pytest.raises(ValueError, match="same stock"):
        build_stock_dataset(bars)


def test_invalid_target_horizon_is_rejected() -> None:
    bars = _make_bars()

    with pytest.raises(ValueError, match="positive"):
        build_stock_dataset(bars, target_horizon=0)


def test_custom_target_horizon_changes_target() -> None:
    bars = _make_bars(count=80)

    dataset = build_stock_dataset(
        bars,
        target_horizon=10,
    )

    first_row = dataset.iloc[0]

    current_close = float(
        next(
            bar.close_price
            for bar in bars
            if bar.trade_date == first_row["trade_date"]
        )
    )

    future_close = float(
        next(
            bar.close_price
            for bar in bars
            if bar.trade_date == dataset.iloc[10]["trade_date"]
        )
    )

    expected_target = future_close / current_close - 1.0

    assert first_row[TARGET_COLUMN] == pytest.approx(expected_target)

def test_build_combined_dataset_concatenates_multiple_stocks() -> None:
    stock_bars = {
        "000660": _make_bars(stock_code="000660", count=80),
        "005380": _make_bars(stock_code="005380", count=80),
        "005930": _make_bars(stock_code="005930", count=80),
        "035420": _make_bars(stock_code="035420", count=80),
        "035720": _make_bars(stock_code="035720", count=80),
    }

    dataset = build_combined_dataset(stock_bars)

    assert dataset["stock_code"].nunique() == 5

    for stock_code in stock_bars:
        assert (
            dataset.loc[
                dataset["stock_code"] == stock_code,
                "stock_code",
            ].count()
            == len(
                build_stock_dataset(stock_bars[stock_code])
            )
        )

    assert len(dataset) == sum(
        len(build_stock_dataset(bars))
        for bars in stock_bars.values()
    )


def test_build_combined_dataset_has_expected_columns() -> None:
    stock_bars = {
        "000660": _make_bars(stock_code="000660", count=80),
        "005930": _make_bars(stock_code="005930", count=80),
    }

    dataset = build_combined_dataset(stock_bars)

    expected_columns = [
        "trade_date",
        "stock_code",
        *FEATURE_COLUMNS,
        TARGET_COLUMN,
    ]

    assert list(dataset.columns) == expected_columns

    def test_split_by_time_uses_expected_date_ranges() -> None:
        stock_bars = {
            "000660": _make_bars(stock_code="000660", count=650),
            "005930": _make_bars(stock_code="005930", count=650),
        }

        dataset = build_combined_dataset(stock_bars)

        splits = split_by_time(dataset)

        assert splits.train["trade_date"].min() >= "2024-03-13"
        assert splits.train["trade_date"].max() <= "2025-12-31"

        assert splits.validation["trade_date"].min() >= "2026-01-01"
        assert splits.validation["trade_date"].max() <= "2026-06-30"

        assert splits.test["trade_date"].min() >= "2026-07-01"
        assert splits.test["trade_date"].max() <= "2026-09-01"


    def test_split_by_time_has_no_date_overlap() -> None:
        stock_bars = {
            "000660": _make_bars(stock_code="000660", count=650),
            "005930": _make_bars(stock_code="005930", count=650),
        }

        dataset = build_combined_dataset(stock_bars)

        splits = split_by_time(dataset)

        train_dates = set(splits.train["trade_date"])
        validation_dates = set(splits.validation["trade_date"])
        test_dates = set(splits.test["trade_date"])

        assert train_dates.isdisjoint(validation_dates)
        assert train_dates.isdisjoint(test_dates)
        assert validation_dates.isdisjoint(test_dates)


    def test_split_by_time_preserves_all_stocks() -> None:
        stock_bars = {
            "000660": _make_bars(stock_code="000660", count=650),
            "005380": _make_bars(stock_code="005380", count=650),
            "005930": _make_bars(stock_code="005930", count=650),
            "035420": _make_bars(stock_code="035420", count=650),
            "035720": _make_bars(stock_code="035720", count=650),
        }

        dataset = build_combined_dataset(stock_bars)

        splits = split_by_time(dataset)

        for split in (
            splits.train,
            splits.validation,
            splits.test,
        ):
            assert set(split["stock_code"]) == set(stock_bars)


def test_features_do_not_use_future_prices() -> None:
    bars = _make_bars(count=80)

    dataset = build_stock_dataset(bars)

    first_row = dataset.iloc[0]

    # 첫 번째 dataset row보다 미래의 가격을 극단적으로 변경한다.
    future_bars = bars.copy()

    first_trade_date = first_row["trade_date"]

    first_index = next(
        i
        for i, bar in enumerate(future_bars)
        if bar.trade_date == first_trade_date
    )

    for i in range(first_index + 1, len(future_bars)):
        future_bars[i] = DailyBar(
            stock_code=future_bars[i].stock_code,
            trade_date=future_bars[i].trade_date,
            open_price=future_bars[i].open_price * 100,
            high_price=future_bars[i].high_price * 100,
            low_price=future_bars[i].low_price * 100,
            close_price=future_bars[i].close_price * 100,
            volume=future_bars[i].volume * 100,
            trade_value_million_krw=future_bars[i].trade_value_million_krw,
            previous_close_change=future_bars[i].previous_close_change,
            previous_close_change_sign=future_bars[i].previous_close_change_sign,
            turnover_rate=future_bars[i].turnover_rate,
        )

    future_dataset = build_stock_dataset(future_bars)

    original_features = first_row[list(FEATURE_COLUMNS)]
    changed_features = future_dataset.iloc[0][list(FEATURE_COLUMNS)]

    pd.testing.assert_series_equal(
        original_features,
        changed_features,
        check_names=False,
    )