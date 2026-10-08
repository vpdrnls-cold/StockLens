"""Rehearsal of the two January runs on already-used dates (CURRENT_STATUS item 88, pre-January 1-1).

    STOCKLENS_UNIVERSE=top50 PYTHONPATH=. .venv/bin/python scripts/rehearse_january_runs.py

Runs the exact code of
  A. scripts/evaluate_forward_holdout.py (``report_and_save``) on the intraday dev segment
     (2025-09-01 ~ 2026-06-30, report-only and already used in items 48/49), and
  B. scripts/run_next_cycle_grid.py (``run_grid``) on validation W3 (2020-01-01 ~ 2023-06-30,
     already used; the selection model trains to 2019-12-31), including the final M1
     retrain branch,
so that a crash, a missing column or a shape problem shows up now instead of after the
one real look.

Safety
  - The minute panel and the daily dataset are cut before FORWARD_START before anything
    is scored (``before_forward``); B reads bars only up to 2023-06-30 (no test dates, no lock).
  - No numbers are printed: only structural checks (row counts, NaNs, files, candidates x
    offsets). All output files go to a temporary folder that is deleted at the end
    (``--keep DIR`` keeps them, for debugging only).
  - Nothing is written to reports/forward_holdout, reports/next_cycle_grid or config/.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import tempfile
import time

import numpy as np
import pandas as pd

from scripts import evaluate_forward_holdout as fh
from scripts import run_next_cycle_grid as rg
from scripts.experiment_intraday_overlay_dev import add_beta, build_scores, load_intraday_panel
from scripts.run_ml_backtest import (
    STOCK_CODES,
    _load_priced_dataset,
    frozen_model_fingerprint,
    trading_calendar,
    train_frozen_model,
)
from src.data.dataset import TEST_START_DATE, VALIDATION_END_DATE, VALIDATION_START_DATE
from src.data.intraday_split import FORWARD_START, select_segment
from src.data.universe import get_universe
from src.eval import next_cycle as nc

CALLER = "rehearse_january_runs.py"
MINUTE_DIR = "data/raw/kiwoom/ka10080"
GRID_DEV_START, GRID_DEV_END = VALIDATION_START_DATE, VALIDATION_END_DATE  # W3


def before_forward(frame: pd.DataFrame, date_col: str = "trade_date") -> pd.DataFrame:
    """Rows dated before FORWARD_START only (applied before scoring)."""
    out = frame[pd.to_datetime(frame[date_col]) < pd.Timestamp(FORWARD_START)]
    if not out.empty and pd.to_datetime(out[date_col]).max() >= pd.Timestamp(FORWARD_START):
        raise AssertionError("forward rows survived the cut")
    return out


class Checks:
    def __init__(self) -> None:
        self.failed: list[str] = []

    def __call__(self, name: str, ok: bool) -> None:
        print(f"  [{'ok' if ok else 'FAIL'}] {name}")
        if not ok:
            self.failed.append(name)


def rehearse_forward(m0, out: Path, check: Checks) -> None:
    dataset = before_forward(add_beta(_load_priced_dataset()))
    panel = before_forward(load_intraday_panel(None, MINUTE_DIR))
    df = build_scores(dataset, panel, m0)
    check("A: nothing on or after FORWARD_START", pd.to_datetime(df["trade_date"]).max() < pd.Timestamp(FORWARD_START))
    calendar = [d for d in trading_calendar() if d < pd.Timestamp(FORWARD_START)]
    part = select_segment(df, "dev", caller=CALLER, horizon=5, calendar=calendar)
    check(f"A: dev segment selected ({part['trade_date'].nunique()} dates)", part["trade_date"].nunique() >= fh.FORWARD_MIN_DATES)
    result = fh.report_and_save(part, out, m0.best_iteration, run_name="rehearsal_forward_holdout",
                                show=False, runs_dir=out / "runs")
    for f in result["files"]:
        check(f"A: wrote {f.name}", f.exists() and f.stat().st_size > 0)
    res = result["results"].set_index("strategy")
    check("A: strategies daily/overlay/momentum/univ_ew", {"daily", "overlay", "momentum", "univ_ew"} <= set(res.index))
    check("A: IC and net return finite for daily/overlay",
          bool(np.isfinite(res.loc[["daily", "overlay"], ["ic", "net_cum", "mdd_daily"]].to_numpy(float)).all()))
    v = result["verdicts"]
    check("A: verdict keys", {"d2_not_rejected", "i6_status", "overlay_forward2_candidate"} <= set(v))
    phases = pd.read_csv(out / "forward_phase_sensitivity.csv")
    check("A: phase table 2 strategies x 5 offsets", len(phases) == 2 * len(fh.PHASE_OFFSETS))
    check("A: run log saved", any((out / "runs").iterdir()))


def rehearse_grid(m0, out: Path, check: Checks) -> None:
    check("B: rehearsal dev ends before the test period and the real dev",
          pd.Timestamp(GRID_DEV_END) < pd.Timestamp(TEST_START_DATE) and pd.Timestamp(GRID_DEV_END) < pd.Timestamp(nc.DEV_START))
    model_out = out / "next_cycle_model.json"
    r = rg.run_grid(m0, GRID_DEV_START, GRID_DEV_END, out, model_out, show=False, force_final_m1=True)
    phases = r["phases"]
    full = {(c, k) for c in nc.CANDIDATES for k in nc.PHASE_OFFSETS}
    check("B: 6 candidates x 5 offsets", set(zip(phases["candidate"], phases["offset"])) == full and len(phases) == len(full))
    cols = ["net_cum", "univ_ew_gross", "excess_vs_univ", "mdd", "mdd_daily", "net_cum_stale_zero"]
    check("B: phase numbers finite", bool(np.isfinite(phases[cols].to_numpy(float)).all()))
    check("B: point-in-time counters present",
          {"failed_entries", "locked_position_periods", "delisted_exits", "stale_at_end"} <= set(phases.columns))
    check("B: a decision for every candidate", list(r["decision"]["candidate"]) == list(nc.CANDIDATES))
    check("B: chosen is a candidate", r["chosen"] in nc.CANDIDATES)
    check("B: forward2 length is 125..500 or None",
          r["forward2_trading_days"] is None or r["forward2_trading_days"] in range(125, 501, 125))
    check("B: IC for M0 and M1 with a finite sd",
          len(r["ic"]) == 2 and bool(np.isfinite(r["ic"]["ic_sd"].to_numpy(float)).all()))
    check("B: diagnostics for M0 and M1", len(r["diagnostics"]) == 2)
    check(f"B: cleaning dropped rows ({r['rows_dropped_by_cleaning']})", r["rows_dropped_by_cleaning"] > 0)
    final = r["final"]
    check("B: final M1 retrain recorded (>= 100 trees)",
          final.get("train_end") == GRID_DEV_END and final.get("best_iteration", 0) >= nc.MIN_TREES - 1
          and len(final.get("fingerprint", "")) == 64)
    for name in ("phases.csv", "dev_ic.csv", "diagnostics.csv", rg.SUMMARY_FILE, model_out.name):
        check(f"B: wrote {name}", (out / name).exists() and (out / name).stat().st_size > 0)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--keep", default=None, help="keep the output files in this folder (debugging only)")
    args = ap.parse_args(argv)
    if set(STOCK_CODES) != set(get_universe("top50")):
        print("STOP: run with STOCKLENS_UNIVERSE=top50 (as both January runs).")
        return 2

    check = Checks()
    t0 = time.time()
    m0, _ = train_frozen_model(_load_priced_dataset())
    check("M0 is the pre-registered frozen model", fh.frozen_model_ok(m0.best_iteration, frozen_model_fingerprint(m0)))
    if check.failed:
        return 4
    tmp = Path(args.keep) if args.keep else Path(tempfile.mkdtemp(prefix="stocklens_rehearsal_"))
    try:
        print("A. forward evaluation code on the intraday dev segment (no numbers shown)")
        rehearse_forward(m0, tmp / "forward", check)
        print(f"   {time.time() - t0:.0f}s")
        print("B. next-cycle grid code on validation W3 (no numbers shown)")
        rehearse_grid(m0, tmp / "grid", check)
        print(f"   {time.time() - t0:.0f}s")
    finally:
        if not args.keep:
            shutil.rmtree(tmp, ignore_errors=True)
    print("\nREHEARSAL " + ("PASSED" if not check.failed else f"FAILED: {check.failed}"))
    return 0 if not check.failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
