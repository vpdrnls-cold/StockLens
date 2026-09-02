"""Tests for StockLens feature engineering."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from src.data.models import DailyBar
from src.features.engineering import FEATURE_COLUMNS, build_features


def _make_bars(count: int = 80) -> list[DailyBar]:
    bars: list[DailyBar] = []

    for index in range(count):
        close = 100.0 + index

        bars.append(
            DailyBar(
                stock_code="005930",
                trade_date=date(2026, 1, 1) + timedelta(days=index),
                open_price=close - 1.0,
                high_price=close + 2.0,
                low_price=close - 2.0,
                close_price=close,
                volume=1_000_000 + index * 10_000,
                trade_value_million_krw=1000.0,
                previous_close_change=0.0,
                previous_close_change_sign=0,
                turnover_rate=1.0,
            )
        )

    return bars


def _replace_bar(
    bar: DailyBar,
    *,
    stock_code: str | None = None,
    trade_date: date | None = None,
    close_price: float | None = None,
) -> DailyBar:
    return DailyBar(
        stock_code=stock_code or bar.stock_code,
        trade_date=trade_date or bar.trade_date,
        open_price=bar.open_price,
        high_price=bar.high_price,
        low_price=bar.low_price,
        close_price=(
            close_price if close_price is not None else bar.close_price
        ),
        volume=bar.volume,
        trade_value_million_krw=bar.trade_value_million_krw,
        previous_close_change=bar.previous_close_change,
        previous_close_change_sign=bar.previous_close_change_sign,
        turnover_rate=bar.turnover_rate,
    )


def test_build_features_returns_25_features() -> None:
    bars = _make_bars()

    result = build_features(bars)

    assert list(result.columns) == [
        "trade_date",
        *FEATURE_COLUMNS,
    ]
    assert len(FEATURE_COLUMNS) == 25


def test_features_are_sorted_by_trade_date() -> None:
    bars = _make_bars()
    bars.reverse()

    result = build_features(bars)

    assert result["trade_date"].is_monotonic_increasing


def test_return_1d_is_calculated_correctly() -> None:
    bars = _make_bars()

    result = build_features(bars)

    expected = 101.0 / 100.0 - 1.0

    assert result.loc[1, "return_1d"] == pytest.approx(expected)


def test_return_5d_is_calculated_correctly() -> None:
    bars = _make_bars()

    result = build_features(bars)

    expected = 105.0 / 100.0 - 1.0

    assert result.loc[5, "return_5d"] == pytest.approx(expected)


def test_sma_5_is_calculated_correctly() -> None:
    bars = _make_bars()

    result = build_features(bars)

    expected = (100 + 101 + 102 + 103 + 104) / 5

    assert result.loc[4, "sma_5"] == pytest.approx(expected)


def test_warmup_period_contains_nan() -> None:
    bars = _make_bars()

    result = build_features(bars)

    assert result.loc[19, "return_20d"] != result.loc[19, "return_20d"]
    assert result.loc[20, "return_20d"] == pytest.approx(
        120.0 / 100.0 - 1.0
    )

    assert result.loc[18, "sma_20"] != result.loc[18, "sma_20"]
    assert result.loc[19, "sma_20"] == pytest.approx(
        sum(range(100, 120)) / 20
    )

    assert result.loc[58, "sma_60"] != result.loc[58, "sma_60"]
    assert result.loc[59, "sma_60"] == pytest.approx(
        sum(range(100, 160)) / 60
    )


def test_changing_future_bar_does_not_change_past_features() -> None:
    bars = _make_bars()

    original = build_features(bars)

    modified_bars = list(bars)
    last = modified_bars[-1]

    modified_bars[-1] = _replace_bar(
        last,
        close_price=last.close_price * 10,
    )

    modified = build_features(modified_bars)

    for column in FEATURE_COLUMNS:
        assert original.loc[:78, column].equals(
            modified.loc[:78, column]
        )


def test_duplicate_trade_dates_are_rejected() -> None:
    bars = _make_bars()

    bars.append(
        _replace_bar(
            bars[-1],
            trade_date=bars[-2].trade_date,
        )
    )

    with pytest.raises(ValueError, match="duplicate trade dates"):
        build_features(bars)


def test_multiple_stocks_are_rejected() -> None:
    bars = _make_bars()

    bars.append(
        _replace_bar(
            bars[-1],
            stock_code="000660",
            trade_date=bars[-1].trade_date + timedelta(days=1),
        )
    )

    with pytest.raises(ValueError, match="same stock"):
        build_features(bars)


def test_empty_input_is_rejected() -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        build_features([])