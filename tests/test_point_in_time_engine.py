"""Point-in-time engine (CURRENT_STATUS item 87) -- synthetic data only."""
from __future__ import annotations

from dataclasses import replace

import numpy as np
import pandas as pd
import pytest

from scripts.walk_forward_backtest_compare import universe_average_gross
from src.backtest.baseline import calculate_performance
from src.backtest.daily_equity import daily_max_drawdown
from src.backtest.buffered import BufferedBaselineConfig, run_buffered_backtest_with_turnover
from src.backtest.point_in_time import (
    run_point_in_time_backtest,
    universe_average_gross_pit,
    zero_value_sensitivity,
)

CFG = BufferedBaselineConfig(lookback_days=5, holding_days=5, allow_partial_universe=True, buffer_multiplier=None)


def _data(n_stocks: int = 6, n_dates: int = 61, seed: int = 3) -> dict[str, pd.DataFrame]:
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2030-01-01", periods=n_dates)
    out = {}
    for k in range(n_stocks):
        close = 100 * np.cumprod(1 + rng.normal(0, 0.02, n_dates))
        out[f"{k:06d}"] = pd.DataFrame({"stock_code": f"{k:06d}", "trade_date": dates,
                                        "open_price": close * (1 + rng.normal(0, 0.003, n_dates)), "close_price": close})
    return out


def _random_scores(seed: int = 5):
    rng = np.random.default_rng(seed)
    table: dict[tuple[str, int], float] = {}

    def score_fn(universe, code, d, lb):
        return table.setdefault((code, d), float(rng.normal()))
    return score_fn


def _fixed_scores(order: list[str]):
    return lambda universe, code, d, lb: float(len(order) - order.index(code))


def _drop(data, code, idx):
    df = data[code]
    data[code] = df.drop(df.index[idx]).reset_index(drop=True)
    return data


@pytest.mark.parametrize("buffer,top_n,holding", [(None, 3, 5), (3.0, 2, 5), (3.0, 3, 10), (1.5, 1, 20)])
def test_identical_to_buffered_engine_on_complete_data(buffer, top_n, holding) -> None:
    data = _data(n_dates=101)
    cfg = replace(CFG, buffer_multiplier=buffer, holding_days=holding)
    old, old_stats = run_buffered_backtest_with_turnover(data, cfg, score_fn=_random_scores(), top_n=top_n)
    new, stats = run_point_in_time_backtest(data, cfg, _random_scores(), top_n)
    key = lambda t: (t.decision_date, t.stock_code)  # noqa: E731 -- the buffered engine lists a period's trades in set order
    assert sorted(new, key=key) == sorted(old, key=key)
    assert stats["entries_per_period"] == old_stats["entries_per_period"]
    assert (stats["failed_entries"], stats["locked_position_periods"], stats["delisted_exits"], stats["stale_at_end"]) == (0, 0, 0, [])


@pytest.mark.parametrize("holding", [5, 10, 20])
def test_benchmark_identical_on_complete_data(holding) -> None:
    data = _data(n_dates=101)
    pd.testing.assert_series_equal(universe_average_gross_pit(data, holding=holding),
                                   universe_average_gross(data, holding=holding))


def test_halted_holding_is_locked_not_dropped() -> None:
    order = ["000000", "000001", "000002", "000003", "000004", "000005"]
    data = _drop(_data(), "000000", [10])           # 000000 halted on the rebalance day (index 10)
    trades, stats = run_point_in_time_backtest(data, CFG, _fixed_scores(order), top_n=1)
    second = [t for t in trades if t.decision_date == data["000001"]["trade_date"].iloc[10]]
    assert [t.stock_code for t in second] == ["000000"]  # kept its slot, nothing else bought
    closes = data["000000"].set_index("trade_date")["close_price"]
    assert second[0].entry_price == closes.iloc[9]       # marked from its last valid close
    assert stats["locked_position_periods"] == 1
    old, _ = run_buffered_backtest_with_turnover(data, CFG, score_fn=_fixed_scores(order), top_n=1)
    assert "000001" in {t.stock_code for t in old}       # the old engine silently switched stocks


def test_pick_without_next_open_is_not_entered() -> None:
    order = ["000000", "000001", "000002", "000003", "000004", "000005"]
    data = _data()
    data["000000"].loc[11, "open_price"] = np.nan        # T+1 open missing for the decision at index 10
    trades, stats = run_point_in_time_backtest(data, CFG, _fixed_scores(order), top_n=1)
    d10 = data["000001"]["trade_date"].iloc[10]
    assert [t for t in trades if t.decision_date == d10] == [] and stats["failed_entries"] == 1


def test_delisted_holding_exits_at_its_last_close_with_costs() -> None:
    order = ["000000", "000001", "000002", "000003", "000004", "000005"]
    data = _data()
    data["000000"] = data["000000"].iloc[:13]            # last bar at index 12 (정리매매 close), others continue
    trades, stats = run_point_in_time_backtest(data, CFG, _fixed_scores(order), top_n=1)
    t = [t for t in trades if t.stock_code == "000000"][-1]
    assert t.exit_date == data["000000"]["trade_date"].iloc[12] and stats["delisted_exits"] == 1
    assert t.net_return < t.exit_price / t.entry_price - 1  # sell costs charged
    later = {x.stock_code for x in trades if x.decision_date > t.decision_date}
    assert "000000" not in later and later == {"000001"}


def test_stale_at_end_reported_and_zero_value_sensitivity() -> None:
    order = ["000000", "000001", "000002", "000003", "000004", "000005"]
    data = _drop(_data(n_dates=63), "000000", [55, 56, 57, 58, 59, 60])  # halted through the last exit (index 60)
    trades, stats = run_point_in_time_backtest(data, CFG, _fixed_scores(order), top_n=1)
    assert stats["stale_at_end"] == ["000000"]
    assert zero_value_sensitivity(trades, stats["stale_at_end"]) < calculate_performance(trades)["total_return"]
    assert zero_value_sensitivity(trades, []) == calculate_performance(trades)["total_return"]


def test_benchmark_keeps_a_halted_stock_at_its_last_price() -> None:
    data = _drop(_data(n_stocks=2), "000000", [12, 13, 14, 15])
    b_pit = universe_average_gross_pit(data)
    d10 = data["000001"]["trade_date"].iloc[10]
    c0 = data["000000"].set_index("trade_date")
    o0 = c0["open_price"].iloc[11]
    last0 = c0["close_price"].loc[:data["000001"]["trade_date"].iloc[11]].iloc[-1]
    c1 = data["000001"]
    expected = np.mean([last0 / o0 - 1, c1["close_price"].iloc[15] / c1["open_price"].iloc[11] - 1])
    assert b_pit.loc[d10] == pytest.approx(expected)
    assert universe_average_gross(data).loc[d10] != pytest.approx(expected)  # the old benchmark drops it


def test_position_halted_for_a_whole_period_keeps_dates_ordered() -> None:
    # found by the January rehearsal (item 88): halted from before a rebalance through the next one
    order = ["000000", "000001", "000002", "000003", "000004", "000005"]
    data = _drop(_data(), "000000", list(range(9, 17)))  # no bars 9..16: the whole period [10, 15] and its end
    trades, stats = run_point_in_time_backtest(data, CFG, _fixed_scores(order), top_n=1)
    assert all(t.entry_date <= t.exit_date for t in trades)
    assert stats["locked_position_periods"] >= 2
    assert np.isfinite(daily_max_drawdown(trades, data))
