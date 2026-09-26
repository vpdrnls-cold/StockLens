"""Save experiment time series in one standard layout so they can be plotted.

Every experiment script used to print its results to the terminal only, so
the per-period return path, the drawdown path and the daily IC -- the parts
that show *when* a strategy won or lost -- were gone once the terminal
closed. Summary numbers live in Notion; this module keeps the time series.

Layout written by ``save_run`` (one directory per script invocation):

    reports/runs/<YYYYmmdd-HHMMSS>_<run_name>/
        meta.json        run name, creation time, universe, free-form config
        periods.csv      panel, series, decision_date, period_return
        trades.csv       panel, series, + every Trade field
        ic_daily.csv     panel, series, trade_date, ic          (optional)

``panel`` groups series that belong on the same subplot (e.g. a walk-forward
window, or "test"); ``series`` names one line on it (e.g. "ml top_n=10").
``scripts/plot_run.py`` turns a run directory into PNG figures.

Nothing here reads data or decides which split is used -- callers pass in
what they already computed, so this cannot widen access to the test split.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from src.backtest.baseline import Trade, trades_to_dataframe

DEFAULT_RUNS_DIR = Path("reports/runs")

PERIODS_FILE = "periods.csv"
TRADES_FILE = "trades.csv"
IC_FILE = "ic_daily.csv"
META_FILE = "meta.json"


def period_returns_from_trades(trades: list[Trade]) -> pd.Series:
    """Weight-averaged net return per decision date.

    Same aggregation as ``calculate_performance`` (one compounding step per
    rebalance period, not per trade), so an equity curve built from this
    series ends exactly at that function's ``total_return``.
    """
    df = trades_to_dataframe(trades)
    if df.empty:
        return pd.Series(dtype="float64", name="period_return")
    df["contribution"] = df["weight"] * df["net_return"]
    series = df.groupby("decision_date")["contribution"].sum().sort_index()
    series.index = pd.to_datetime(series.index)
    series.name = "period_return"
    return series


@dataclass
class RunRecorder:
    """Collect trades / IC series during a script, then ``save()`` once."""

    run_name: str
    meta: dict[str, Any] = field(default_factory=dict)
    _trades: list[pd.DataFrame] = field(default_factory=list, repr=False)
    _periods: list[pd.DataFrame] = field(default_factory=list, repr=False)
    _ics: list[pd.DataFrame] = field(default_factory=list, repr=False)

    def add_trades(self, panel: str, series: str, trades: list[Trade]) -> None:
        trades_df = trades_to_dataframe(trades)
        trades_df.insert(0, "series", series)
        trades_df.insert(0, "panel", panel)
        self._trades.append(trades_df)

        periods = period_returns_from_trades(trades).rename_axis("decision_date").reset_index()
        periods.insert(0, "series", series)
        periods.insert(0, "panel", panel)
        self._periods.append(periods)

    def add_ic(self, panel: str, series: str, ic: pd.Series) -> None:
        ic_df = ic.rename("ic").rename_axis("trade_date").reset_index()
        ic_df["trade_date"] = pd.to_datetime(ic_df["trade_date"])
        ic_df.insert(0, "series", series)
        ic_df.insert(0, "panel", panel)
        self._ics.append(ic_df)

    def save(self, runs_dir: str | Path = DEFAULT_RUNS_DIR) -> Path:
        if not self._periods:
            raise ValueError("Nothing to save: call add_trades() at least once.")

        created = datetime.now()
        run_dir = Path(runs_dir) / f"{created:%Y%m%d-%H%M%S}_{_slug(self.run_name)}"
        run_dir.mkdir(parents=True, exist_ok=False)

        pd.concat(self._periods, ignore_index=True).to_csv(run_dir / PERIODS_FILE, index=False)
        pd.concat(self._trades, ignore_index=True).to_csv(run_dir / TRADES_FILE, index=False)
        if self._ics:
            pd.concat(self._ics, ignore_index=True).to_csv(run_dir / IC_FILE, index=False)

        meta = {"run_name": self.run_name, "created_at": created.isoformat(timespec="seconds"), **self.meta}
        (run_dir / META_FILE).write_text(
            json.dumps(meta, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
        )
        print(f"[run_log] saved -> {run_dir}")
        return run_dir


@dataclass(frozen=True)
class LoadedRun:
    run_dir: Path
    meta: dict[str, Any]
    periods: pd.DataFrame
    trades: pd.DataFrame
    ic: pd.DataFrame | None


def load_run(run_dir: str | Path) -> LoadedRun:
    run_dir = Path(run_dir)
    meta = json.loads((run_dir / META_FILE).read_text(encoding="utf-8"))
    periods = pd.read_csv(run_dir / PERIODS_FILE, parse_dates=["decision_date"])
    trades = pd.read_csv(run_dir / TRADES_FILE, parse_dates=["decision_date", "entry_date", "exit_date"])
    ic_path = run_dir / IC_FILE
    ic = pd.read_csv(ic_path, parse_dates=["trade_date"]) if ic_path.exists() else None
    return LoadedRun(run_dir, meta, periods, trades, ic)


def latest_run_dir(runs_dir: str | Path = DEFAULT_RUNS_DIR) -> Path:
    candidates = sorted(p for p in Path(runs_dir).iterdir() if (p / META_FILE).exists())
    if not candidates:
        raise FileNotFoundError(f"No saved runs under {runs_dir}")
    return candidates[-1]


def _slug(name: str) -> str:
    slug = re.sub(r"[^0-9A-Za-z_-]+", "-", name).strip("-").lower()
    return slug or "run"
