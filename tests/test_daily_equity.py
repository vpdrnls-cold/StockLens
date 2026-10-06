"""Daily mark-to-market equity / drawdown (CURRENT_STATUS item 80)."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.backtest.baseline import BaselineConfig, calculate_performance, run_baseline_backtest
from src.backtest.buffered import BufferedBaselineConfig, run_buffered_backtest
from src.backtest.daily_equity import daily_equity, daily_max_drawdown, max_drawdown

COSTS = dict(buy_fee=0.00015, sell_fee=0.00015, sell_tax=0.002, buy_slippage=0.001, sell_slippage=0.001,
             allow_partial_universe=True)


def _data(n_stocks: int = 12, n_days: int = 160, seed: int = 0) -> dict[str, pd.DataFrame]:
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2024-01-01", periods=n_days)
    out = {}
    for i in range(n_stocks):
        close = 10_000 * np.exp(np.cumsum(rng.normal(0, 0.02, n_days)))
        open_ = close * np.exp(rng.normal(0, 0.005, n_days))
        out[f"{i:06d}"] = pd.DataFrame({"stock_code": f"{i:06d}", "trade_date": dates,
                                        "open_price": open_, "close_price": close})
    return out


@pytest.mark.parametrize("buffered", [False, True])
def test_period_ends_match_engine_and_daily_mdd_is_deeper(buffered: bool) -> None:
    data = _data()
    if buffered:
        trades = run_buffered_backtest(data, BufferedBaselineConfig(**COSTS, buffer_multiplier=3.0), top_n=3)
    else:
        trades = run_baseline_backtest(data, BaselineConfig(**COSTS), top_n=3)
    perf = calculate_performance(trades, initial_capital=1.0)
    eq = daily_equity(trades, data)
    exits = sorted({pd.Timestamp(t.exit_date) for t in trades})
    period_eq = (1.0 + pd.Series({pd.Timestamp(t.decision_date): 0.0 for t in trades})).sort_index()
    assert eq.loc[exits[-1]] == pytest.approx(1.0 + perf["total_return"], rel=1e-12)
    # every period-end value equals the compounded engine equity at that point
    df = pd.DataFrame([t.__dict__ for t in trades])
    rets = (df["weight"] * df["net_return"]).groupby(df["decision_date"]).sum().sort_index()
    ends = df.groupby("decision_date")["exit_date"].max().sort_index()
    np.testing.assert_allclose(eq.loc[pd.to_datetime(ends.values)].to_numpy(), (1.0 + rets).cumprod().to_numpy(), rtol=1e-12)
    assert daily_max_drawdown(trades, data) <= perf["max_drawdown"] + 1e-12
    assert len(eq) > len(period_eq)


def test_intra_period_dip_is_caught() -> None:
    dates = pd.bdate_range("2024-01-01", periods=12)
    close = np.array([100, 100, 100, 100, 100, 100, 60, 60, 100, 100, 100, 100], float)
    data = {"000001": pd.DataFrame({"stock_code": "000001", "trade_date": dates, "open_price": 100.0, "close_price": close})}
    trades = run_baseline_backtest(data, BaselineConfig(allow_partial_universe=True, buy_fee=0, sell_fee=0, sell_tax=0,
                                                        buy_slippage=0, sell_slippage=0), top_n=1)
    assert calculate_performance(trades, initial_capital=1.0)["max_drawdown"] == pytest.approx(0.0)
    assert daily_max_drawdown(trades, data) == pytest.approx(-0.4)


def test_cash_for_unused_weight_and_empty() -> None:
    assert daily_equity([], {}).empty and max_drawdown(pd.Series(dtype=float)) == 0.0
    eq = pd.Series([1.0, 0.9, 1.1, 0.88])
    assert max_drawdown(eq) == pytest.approx(0.88 / 1.1 - 1.0)
    assert max_drawdown(pd.Series([0.95, 1.0])) == pytest.approx(-0.05)  # first-day loss counts
