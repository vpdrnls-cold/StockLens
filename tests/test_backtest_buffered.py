"""Tests for the turnover-reduction buffer engine (src/backtest/buffered.py)."""

from __future__ import annotations

import pandas as pd
import pytest

from src.backtest.baseline import (
    BaselineConfig,
    run_baseline_backtest,
    trades_to_dataframe,
)
from src.backtest.buffered import (
    BufferedBaselineConfig,
    run_buffered_backtest,
    run_buffered_backtest_with_turnover,
)


def _stock(code: str, closes: list[float]) -> pd.DataFrame:
    dates = pd.date_range("2026-01-01", periods=len(closes), freq="B")
    return pd.DataFrame(
        {
            "stock_code": code,
            "trade_date": dates,
            "open_price": closes,
            "close_price": closes,
        }
    )


def _zero_cost(**overrides) -> BufferedBaselineConfig:
    base = dict(
        buy_fee=0.0, sell_fee=0.0, sell_tax=0.0,
        buy_slippage=0.0, sell_slippage=0.0,
        allow_partial_universe=True,
    )
    base.update(overrides)
    return BufferedBaselineConfig(**base)


def _realistic_cost(**overrides) -> BufferedBaselineConfig:
    base = dict(
        buy_fee=0.00015, sell_fee=0.00015, sell_tax=0.0020,
        buy_slippage=0.0010, sell_slippage=0.0010,
        allow_partial_universe=True,
    )
    base.update(overrides)
    return BufferedBaselineConfig(**base)


def test_buffer_multiplier_rejects_below_one() -> None:
    stocks = {c: _stock(c, [100.0 + i for i in range(40)]) for c in "AB"}
    with pytest.raises(ValueError, match="buffer_multiplier"):
        run_buffered_backtest(
            stocks, _zero_cost(buffer_multiplier=0.5), top_n=1
        )


def test_no_buffer_matches_run_baseline_backtest_exactly() -> None:
    """buffer_multiplier=None must reproduce run_baseline_backtest bit for bit.

    This is the regression guard: it proves the new two-pass engine
    collapses to the old, already-trusted one when buffering is off.
    """
    stocks = {
        code: _stock(code, [100.0 + i * step + (i % 7) * (-1) ** i for i in range(60)])
        for code, step in zip("ABCDEF", (0.3, -0.2, 0.5, 0.1, -0.4, 0.2))
    }

    for top_n in (1, 2, 3):
        baseline_config = BaselineConfig(
            buy_fee=0.00015, sell_fee=0.00015, sell_tax=0.0020,
            buy_slippage=0.0010, sell_slippage=0.0010,
            allow_partial_universe=True,
        )
        buffered_config = BufferedBaselineConfig(
            buy_fee=0.00015, sell_fee=0.00015, sell_tax=0.0020,
            buy_slippage=0.0010, sell_slippage=0.0010,
            allow_partial_universe=True,
            buffer_multiplier=None,
        )

        baseline_trades = run_baseline_backtest(stocks, baseline_config, top_n=top_n)
        buffered_trades = run_buffered_backtest(stocks, buffered_config, top_n=top_n)

        baseline_df = trades_to_dataframe(baseline_trades)
        buffered_df = trades_to_dataframe(buffered_trades)

        pd.testing.assert_frame_equal(
            baseline_df.sort_values(["decision_date", "stock_code"]).reset_index(drop=True),
            buffered_df.sort_values(["decision_date", "stock_code"]).reset_index(drop=True),
        )


def test_buffer_keeps_a_persistently_top_ranked_stock_without_new_entry_cost() -> None:
    """A always outperforms B, so with any buffer >= 1.0 it is bought once
    and held to the end -- no repeated buy/sell fee for the periods in
    between, unlike the unbuffered engine which pays it every period.
    """
    n = 40
    stock_a = _stock("A", [100.0 * (1.01 ** i) for i in range(n)])
    stock_b = _stock("B", [100.0 * (0.999 ** i) for i in range(n)])
    stocks = {"A": stock_a, "B": stock_b}

    config = _realistic_cost(buffer_multiplier=2.0)
    trades = run_buffered_backtest(stocks, config, top_n=1)

    a_trades = sorted(
        (t for t in trades if t.stock_code == "A"), key=lambda t: t.decision_date
    )
    assert len(a_trades) >= 3, "expected several periods of A being held"

    first, *middle, last = a_trades

    # First period: a real entry -- entry_price is the raw open price,
    # not yesterday's close.
    assert first.entry_price == pytest.approx(
        stock_a.loc[stock_a["trade_date"] == first.entry_date, "open_price"].iloc[0]
    )

    # Interior periods: no transaction, so no fee drag -- net_return
    # equals gross_return exactly, and entry_price is a close price
    # (continuation), not an open price.
    for period in middle:
        assert period.net_return == pytest.approx(period.gross_return)
        assert period.entry_price != pytest.approx(
            stock_a.loc[stock_a["trade_date"] == period.entry_date, "open_price"].iloc[0]
        )

    # Last period: a real exit -- net_return reflects sell fee/tax/slippage,
    # so it must be strictly less than gross_return.
    assert last.net_return < last.gross_return

    # Unbuffered engine pays entry+exit cost on every single period for
    # the same always-best stock -- the buffered engine's total cost
    # drag over the run must be smaller.
    unbuffered_trades = run_buffered_backtest(
        stocks, _realistic_cost(buffer_multiplier=None), top_n=1
    )
    unbuffered_a = [t for t in unbuffered_trades if t.stock_code == "A"]
    buffered_drag = sum(t.gross_return - t.net_return for t in a_trades)
    unbuffered_drag = sum(t.gross_return - t.net_return for t in unbuffered_a)
    assert buffered_drag < unbuffered_drag


def test_turnover_diagnostic_shows_fewer_entries_with_a_buffer() -> None:
    n = 40
    stock_a = _stock("A", [100.0 * (1.01 ** i) for i in range(n)])
    stock_b = _stock("B", [100.0 * (0.999 ** i) for i in range(n)])
    stocks = {"A": stock_a, "B": stock_b}

    _, unbuffered_stats = run_buffered_backtest_with_turnover(
        stocks, _zero_cost(buffer_multiplier=None), top_n=1
    )
    _, buffered_stats = run_buffered_backtest_with_turnover(
        stocks, _zero_cost(buffer_multiplier=2.0), top_n=1
    )

    assert unbuffered_stats["entries_per_period"] == pytest.approx(1.0)
    assert buffered_stats["entries_per_period"] < unbuffered_stats["entries_per_period"]
    assert buffered_stats["avg_positions_held"] == pytest.approx(1.0)
