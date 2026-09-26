"""src/reporting/run_log.py + scripts/plot_run.py."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

from src.backtest.baseline import Trade, calculate_performance
from src.reporting.run_log import (
    RunRecorder,
    latest_run_dir,
    load_run,
    period_returns_from_trades,
)

ROOT = Path(__file__).resolve().parents[1]


def _trade(day: int, code: str, net: float, weight: float = 0.5) -> Trade:
    d = pd.Timestamp("2020-01-01") + pd.Timedelta(days=day)
    return Trade(
        decision_date=d, stock_code=code, score=0.0,
        entry_date=d + pd.Timedelta(days=1), entry_price=100.0,
        exit_date=d + pd.Timedelta(days=5), exit_price=100.0 * (1 + net),
        gross_return=net, net_return=net, weight=weight,
    )


TRADES = [
    _trade(0, "A", 0.04), _trade(0, "B", -0.02),
    _trade(5, "A", -0.10), _trade(5, "B", 0.00),
    _trade(10, "A", 0.06), _trade(10, "B", 0.02),
]


def test_period_returns_compound_to_calculate_performance():
    periods = period_returns_from_trades(TRADES)
    assert list(periods.round(10)) == [0.01, -0.05, 0.04]
    compounded = float((1 + periods).prod() - 1)
    assert compounded == pytest.approx(calculate_performance(TRADES)["total_return"])


def test_period_returns_empty():
    assert period_returns_from_trades([]).empty


def test_save_requires_trades(tmp_path):
    with pytest.raises(ValueError):
        RunRecorder("empty").save(tmp_path)


def test_save_and_load_roundtrip(tmp_path):
    recorder = RunRecorder("My Run: v1", meta={"top_n": 2})
    recorder.add_trades("W1", "ml", TRADES)
    recorder.add_trades("W1", "momentum", TRADES[:2])
    ic = pd.Series([0.1, None, -0.2], index=pd.to_datetime(["2020-01-01", "2020-01-02", "2020-01-03"]))
    recorder.add_ic("W1", "ml", ic)
    run_dir = recorder.save(tmp_path)

    assert run_dir.name.endswith("_my-run-v1")
    assert latest_run_dir(tmp_path) == run_dir

    run = load_run(run_dir)
    assert run.meta["run_name"] == "My Run: v1"
    assert run.meta["top_n"] == 2
    assert set(run.periods["series"]) == {"ml", "momentum"}
    assert len(run.periods[run.periods["series"] == "ml"]) == 3
    assert len(run.trades) == len(TRADES) + 2
    assert run.ic is not None and run.ic["ic"].isna().sum() == 1


def test_plot_run_writes_figures(tmp_path):
    sys.path.insert(0, str(ROOT / "scripts"))
    try:
        import plot_run
    finally:
        sys.path.pop(0)

    recorder = RunRecorder("plot smoke")
    recorder.add_trades("W1", "ml", TRADES)
    recorder.add_trades("W2", "ml", TRADES)
    ic = pd.Series(
        [0.05, -0.01, 0.02] * 10,
        index=pd.date_range("2020-01-01", periods=30, freq="B"),
    )
    recorder.add_ic("W1", "ml", ic)
    run_dir = recorder.save(tmp_path)

    out_dir = plot_run.main([str(run_dir), "--ic-window", "5"])
    for name in ("equity.png", "drawdown.png", "ic.png", "summary.csv"):
        assert (out_dir / name).stat().st_size > 0

    summary = pd.read_csv(out_dir / "summary.csv")
    w1 = summary[summary["panel"] == "W1"].iloc[0]
    assert w1["cum_return"] == pytest.approx(calculate_performance(TRADES)["total_return"])
    assert w1["mean_ic"] == pytest.approx(ic.mean())
