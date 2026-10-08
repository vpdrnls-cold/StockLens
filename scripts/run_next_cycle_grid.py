"""Next-cycle candidate grid on the selection dev period (CURRENT_STATUS item 84). Run once.

Pre-registered and confirmed (item 84, 2026-10-08) before any dev-period result was
seen. Rules live in ``src/eval/next_cycle.py``; this script only runs them.

When
  After the one forward evaluation (scripts/evaluate_forward_holdout.py, ~2027-01):
  the dev period runs from 2025-09-01 to ``--dev-end`` and includes the forward
  period, which may be read here only once ``reports/forward_holdout/forward_results.csv``
  exists. Until then the script stops before reading anything (no shorter early run either).

What it does (item 84 B~E)
  1. M0 = the frozen daily model (trained as in run_ml_backtest.py on top50, stops if
     its fingerprint does not match). M1 = same features and rank target, trained on
     the KOSPI200 (200 stocks) up to 2025-08-31 with at least 100 trees, early stopping
     on the last year of that range (purged).
  2. Both models score all 200 stocks on the dev dates; bars are cut at ``--dev-end``.
  3. Six candidates (M0/M1 x P0/P1/P2) through the buffered engine with real costs,
     5 rebalance start offsets each, excess over the same-holding equal-weight universe.
  4. Selection rule A-3 -> chosen candidate (baseline M0P0 if none passes).
  5. forward2 length from the chosen model's dev IC standard deviation (A-5).
  6. If M1 is chosen: one final M1 retrain through ``--dev-end`` and its fingerprint is
     written to ``--model-out``. The production path is NOT switched by this script.

Locks: the dev start (2025-09-01 ~ 2026-09-16) is the spent daily test period, so
``confirm_final_test_use`` must pass (STOCKLENS_CONFIRM_FINAL_TEST=1) -- turn it on only
after 재훈 confirms the run (item 84 "확정 시 남긴 실행 조건").

    STOCKLENS_UNIVERSE=top50 STOCKLENS_CONFIRM_FINAL_TEST=1 PYTHONPATH=. \\
        .venv/bin/python scripts/run_next_cycle_grid.py --dev-end YYYY-MM-DD
"""

from __future__ import annotations

import argparse
from dataclasses import replace
from datetime import date, datetime
import json
from pathlib import Path

import pandas as pd
import xgboost

from scripts import evaluate_forward_holdout as fh
from scripts.evaluate_cross_sectional_holdout import eligible, ic_block, load_holdout_dataset, period_rows
from scripts.run_ml_backtest import (
    BUFFERED_CONFIG,
    DETERMINISTIC_PARAMS,
    STOCK_CODES,
    _load_priced_dataset,
    _to_data_by_stock,
    frozen_model_fingerprint,
    train_frozen_model,
)
from scripts.walk_forward_backtest_compare import universe_average_gross
from src.backtest.baseline import calculate_performance
from src.backtest.buffered import run_buffered_backtest_with_turnover
from src.backtest.daily_equity import daily_max_drawdown
from src.data.universe import get_universe
from src.eval import next_cycle as nc
from src.eval.test_lock import TestSetLockedError, confirm_final_test_use
from src.ml.cross_section import rank_by_date
from src.ml.strategy import make_model_score_fn, predictions_for_dataset
from src.models.predict import TrainedModel, train_model

CALLER = "run_next_cycle_grid.py"
DEFAULT_OUT = "reports/next_cycle_grid"
DEFAULT_MODEL_OUT = "config/next_cycle_model.json"
FORWARD_RESULTS = Path("reports/forward_holdout/forward_results.csv")
SUMMARY_FILE = "summary.csv"


def gate(out: Path, dev_end: str, stock_codes, top50, forward_results: Path = FORWARD_RESULTS) -> tuple[int, str] | None:
    """Checks that need no data. Returns (exit code, message) to stop, or None to go on."""
    if (out / SUMMARY_FILE).exists():
        return 3, f"STOP: {out / SUMMARY_FILE} exists -- the grid runs once (item 84). Nothing was read."
    if set(stock_codes) != set(top50):
        return 2, "STOP: run with STOCKLENS_UNIVERSE=top50 (M0 is the frozen top50 model). Nothing was read."
    try:
        end = date.fromisoformat(dev_end)
    except ValueError:
        return 2, f"STOP: --dev-end must be YYYY-MM-DD, got {dev_end!r}."
    if end <= date.fromisoformat(nc.DEV_START):
        return 2, f"STOP: --dev-end must be after the dev start {nc.DEV_START}."
    if end > date.today():
        return 2, "STOP: --dev-end is in the future."
    if not forward_results.exists():
        return 6, (f"STOP: item 84 runs after the one forward evaluation ({forward_results} missing); "
                   "the forward period stays closed until then. Nothing was read.")
    if not nc.dev_needs_forward_evaluation(dev_end):
        return 2, "STOP: item 84's dev runs to the forward evaluation date -- --dev-end must be in the forward period."
    return None


def train_m1(dataset: pd.DataFrame, end_date: str) -> TrainedModel:
    fit, val = nc.m1_training_frames(dataset, end_date)
    return train_model(
        fit, rank_by_date(fit, "target_return_5d"), val, rank_by_date(val, "target_return_5d"),
        params=DETERMINISTIC_PARAMS, early_stopping_metric="ic", min_trees=nc.MIN_TREES,
    )


def candidate_phases(part: pd.DataFrame, candidate: str, score_col: str) -> pd.DataFrame:
    """Buffered engine, real costs, every start offset; excess over the same-holding universe."""
    _, p = nc.split_candidate(candidate)
    # 200 stocks with different listing histories -> partial-universe mode (as for top50).
    config = replace(BUFFERED_CONFIG, holding_days=p.holding_days, buffer_multiplier=p.buffer_multiplier,
                     allow_partial_universe=True)
    part = part.dropna(subset=["target_return_5d"])
    rows = []
    for k in nc.PHASE_OFFSETS:
        sub = fh.phase_offset_part(part, k)
        data = _to_data_by_stock(sub)
        scores = sub[["trade_date", "stock_code", score_col]].rename(columns={score_col: "predicted_return"})
        net, turnover = run_buffered_backtest_with_turnover(data, config, score_fn=make_model_score_fn(scores), top_n=p.top_n)
        perf = calculate_performance(net)
        univ = float((1.0 + universe_average_gross(data, holding=p.holding_days)).prod() - 1.0)
        rows.append({"candidate": candidate, "offset": k, "start": pd.to_datetime(sub["trade_date"]).min(),
                     "periods": int(perf["period_count"]), "net_cum": perf["total_return"],
                     "univ_ew_gross": univ, "excess_vs_univ": perf["total_return"] - univ,
                     "mdd": perf["max_drawdown"], "mdd_daily": daily_max_drawdown(net, data),
                     "entries_per_period": turnover["entries_per_period"]})
    return pd.DataFrame(rows)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dev-end", required=True, help="YYYY-MM-DD, last dev date (the forward evaluation date)")
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--model-out", default=DEFAULT_MODEL_OUT)
    args = ap.parse_args(argv)
    out = Path(args.out)

    stop = gate(out, args.dev_end, STOCK_CODES, get_universe("top50"))
    if stop:
        print(stop[1])
        return stop[0]

    m0, _ = train_frozen_model(_load_priced_dataset())
    if not fh.frozen_model_ok(m0.best_iteration, frozen_model_fingerprint(m0)):
        print("STOP: M0 is not the pre-registered frozen model. No dev data was read.")
        return 4
    try:
        confirm_final_test_use(CALLER)
    except TestSetLockedError as locked:
        print(f"STOP: {locked}\nNo dev data was read.")
        return 5

    codes = tuple(get_universe("kospi200"))
    dataset, skipped = load_holdout_dataset(codes, end=args.dev_end)
    print(f"KOSPI200: {len(codes) - len(skipped)} stocks built, skipped (history too short): {skipped or 'none'}")

    m1 = train_m1(dataset, nc.selection_train_end())
    print(f"M1 (selection): best_iteration={m1.best_iteration}, trained to {nc.selection_train_end()}")
    models = {"M0": m0, "M1": m1}
    df = dataset
    for name, model in models.items():
        preds = predictions_for_dataset(model, dataset).rename(columns={"predicted_return": f"score_{name}"})
        df = df.merge(preds, on=["trade_date", "stock_code"], how="left")

    dev_all = period_rows(df, nc.DEV_START, args.dev_end)
    ic_rows, ic_sd, diag = [], {}, []
    for name in nc.MODELS:
        part, dropped = eligible(dev_all.rename(columns={f"score_{name}": "score"}), nc.MIN_STOCKS)
        row, _ = ic_block(name, "report", part, dropped)
        ic_rows.append(row)
        ic_sd[name] = row["ic_sd"]
        diag.append({"model": name, "decile_spread_5d": nc.decile_spread(part, "score"),
                     "bottom20_avoid_excess_5d": nc.bottom_avoid_excess(part, "score"),
                     "distinct_scores_per_day": float(part.groupby("trade_date")["score"].nunique().mean())})

    phase_tables = []
    for c in nc.CANDIDATES:
        model, _ = nc.split_candidate(c)
        part, _ = eligible(dev_all.rename(columns={f"score_{model}": "score"}), nc.MIN_STOCKS)
        phase_tables.append(candidate_phases(part, c, "score"))
    phases = pd.concat(phase_tables, ignore_index=True)
    chosen, decision = nc.decide(phases)
    chosen_model, _ = nc.split_candidate(chosen)
    length = nc.forward2_length(ic_sd[chosen_model])

    out.mkdir(parents=True, exist_ok=True)
    final = {"candidate": chosen, "model": chosen_model, "dev_start": nc.DEV_START, "dev_end": args.dev_end,
             "forward2_trading_days": length, "forward2_mode": "verdict" if length else "harm_check_only",
             "dev_ic_sd": ic_sd[chosen_model], "created": datetime.now().isoformat(timespec="seconds"),
             "xgboost_version": xgboost.__version__}
    if chosen_model == "M1":
        m1_final = train_m1(dataset, args.dev_end)
        final.update(best_iteration=m1_final.best_iteration, fingerprint=frozen_model_fingerprint(m1_final),
                     train_end=args.dev_end)
    else:
        final.update(best_iteration=m0.best_iteration, fingerprint=frozen_model_fingerprint(m0),
                     note="M0 kept: the existing frozen model, no retrain")
    Path(args.model_out).write_text(json.dumps(final, ensure_ascii=False, indent=1), encoding="utf-8")

    phases.to_csv(out / "phases.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(ic_rows).to_csv(out / "dev_ic.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(diag).to_csv(out / "diagnostics.csv", index=False, encoding="utf-8-sig")
    decision.to_csv(out / SUMMARY_FILE, index=False, encoding="utf-8-sig")  # written last = the one-run marker

    print("\n" + "=" * 100)
    print(f"NEXT-CYCLE GRID (item 84, once)   dev {nc.DEV_START} ~ {args.dev_end}, KOSPI200")
    print("=" * 100)
    print(pd.DataFrame(ic_rows).to_string(index=False, float_format=lambda x: f"{x:+.4f}"))
    print("\ndiagnostics (not used for the decision):")
    print(pd.DataFrame(diag).to_string(index=False, float_format=lambda x: f"{x:+.4f}"))
    print("\nselection (A-3: beats baseline on >= 4 of 5 offsets and mean excess > 0):")
    print(decision.to_string(index=False, float_format=lambda x: f"{x:+.4f}"))
    print(f"\nCHOSEN: {chosen}   forward2: {length or 'harm check only (500 days not enough)'}"
          f" trading days (dev IC sd {ic_sd[chosen_model]:.4f})")
    print(f"model record: {args.model_out}   (production path not switched here)")
    print(f"saved: {out}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
