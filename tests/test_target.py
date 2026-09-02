"""Tests for StockLens target construction."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from src.data.models import DailyBar
from src.features.target import (
    TARGET_COLUMN,
    TARGET_HORIZON,
    build_target,
)


def _make_bars(count: int = 10) -> list[DailyBar]:
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


def test_target_uses_five_day_forward_return() -> None:
    bars = _make_bars()

    result = build_target(bars)

    # t = 0:
    # close(t) = 100
    # close(t+5) = 105
    expected = 105.0 / 100.0 - 1.0

    assert result.loc[0, TARGET_COLUMN] == pytest.approx(expected)


def test_last_five_rows_have_no_future_target() -> None:
    bars = _make_bars()

    result = build_target(bars)

    assert result[TARGET_COLUMN].iloc[-5:].isna().all()
    assert result[TARGET_COLUMN].iloc[:-5].notna().all()


def test_target_rows_are_sorted_by_trade_date() -> None:
    bars = _make_bars()
    bars.reverse()

    result = build_target(bars)

    assert result["trade_date"].is_monotonic_increasing


def test_target_does_not_use_past_price() -> None:
    bars = _make_bars()

    result = build_target(bars)

    # At t=0, target must depend on close[5], not close[-5].
    expected = 105.0 / 100.0 - 1.0

    assert result.loc[0, TARGET_COLUMN] == pytest.approx(expected)


def test_empty_input_is_rejected() -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        build_target([])


def test_invalid_horizon_is_rejected() -> None:
    bars = _make_bars()

    with pytest.raises(ValueError, match="positive integer"):
        build_target(bars, horizon=0)


def test_duplicate_trade_dates_are_rejected() -> None:
    bars = _make_bars()

    bars.append(
        DailyBar(
            stock_code="005930",
            trade_date=bars[-1].trade_date,
            open_price=200.0,
            high_price=202.0,
            low_price=198.0,
            close_price=200.0,
            volume=1_000_000,
            trade_value_million_krw=1000.0,
            previous_close_change=0.0,
            previous_close_change_sign=0,
            turnover_rate=1.0,
        )
    )

    with pytest.raises(ValueError, match="duplicate trade dates"):
        build_target(bars)


def test_multiple_stocks_are_rejected() -> None:
    bars = _make_bars()

    bars.append(
        DailyBar(
            stock_code="000660",
            trade_date=bars[-1].trade_date + timedelta(days=1),
            open_price=200.0,
            high_price=202.0,
            low_price=198.0,
            close_price=200.0,
            volume=1_000_000,
            trade_value_million_krw=1000.0,
            previous_close_change=0.0,
            previous_close_change_sign=0,
            turnover_rate=1.0,
        )
    )

    with pytest.raises(ValueError, match="same stock"):
        build_target(bars)