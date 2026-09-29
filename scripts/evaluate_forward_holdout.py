"""Forward holdout evaluation -- the ONE final check of this cycle (items 46/50: D2 + I6).

Written and frozen BEFORE any forward date was looked at (2026-09-28). Run it
exactly once, when the forward period (2026-09-24~) has at least 60 usable
decision dates -- around early January 2027. Rerunning it later with more data
is a new look and needs a new pre-registered cycle.

Before running
  1. Refresh daily bars (the nightly job only fetches them on Fridays):
       STOCKLENS_NIGHTLY_DAILY=1 bash scripts/nightly_ingest.sh
  2. Make sure data/raw/kiwoom/ka10080 has every forward day (the intraday panel
     is rebuilt from raw here; the saved features_panel.csv stops at 2026-09-23):
       STOCKLENS_UNIVERSE=top50 PYTHONPATH=. python scripts/check_forward_minute_coverage.py
  3. Read the pre-registered follow-up table in CURRENT_STATUS item 53 BEFORE
     running -- what happens after each D2/I6 outcome is already decided there.
  The script stops before reading the forward period if the frozen model's
  best_iteration is not 9 (item 53).

    STOCKLENS_UNIVERSE=top50 STOCKLENS_CONFIRM_INTRADAY_FORWARD=1 PYTHONPATH=. \\
        python scripts/evaluate_forward_holdout.py

Strategies (all top_n=10, same fees/tax/slippage)
  daily       frozen daily ML score, buffer 3.0          (D2 -- items 46/47)
  overlay     z(daily) + 0.5 * z(intraday), buffer 3.0   (I6 -- items 48/49)
  momentum    past 5-day return, full turnover            (legacy reference)
  univ_ew     equal-weight universe, no costs             (long-only bar, item 48)

Pre-registered decisions (primary metric: daily rank IC vs the raw 5-day target)
  D2  daily track NOT REJECTED if IC(daily) > 0 on the forward period;
      otherwise rejected (no daily signal out of sample).
  I6  overlay NOT REJECTED if IC(overlay) - IC(daily) > 0; then w = 0.5 is
      carried into the production path. Otherwise the overlay is dropped.
  Everything else -- beta-neutral IC, net/gross return, MDD, hit rate, turnover,
  excess over univ_ew, monthly IC -- is reported for interpretation only.

Tie-break sensitivity (item 52, added 2026-09-28 before any forward date was seen)
  The frozen model (9 depth-2 trees) gives only ~8 distinct scores per date, so
  a large part of the top-10 is decided by the engine's tie rule (stable sort ->
  lower stock code first). That rule stays the reported strategy (it is part of
  the pre-registration). In addition, daily and overlay are re-run under
  TIE_PERMUTATIONS random stock orders (fixed TIE_SEED) and the net-return
  distribution is reported, with where the code-ascending result falls in it.
  Interpretation only -- NOT used by D2/I6. IC is unaffected (ties get average
  ranks), so the decisions cannot change.

Interpretation limit (item 46): ~60 decision dates are ~12 non-overlapping
5-day periods, SE(mean IC) ~ 0.06. "Not rejected" is the strongest possible
conclusion; nothing here proves an improvement, and results are limited to
data from 2025-09 on.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from scripts.experiment_intraday_overlay_dev import (
    CANDIDATE_W,
    GROSS_BUFFERED_CONFIG,
    add_beta,
    beta_neutral_target,
    build_scores,
    load_intraday_panel,
)
from scripts.run_ml_backtest import (
    BUFFER_MULTIPLIER,
    BUFFERED_CONFIG,
    PLAIN_CONFIG,
    STOCK_CODES,
    TOP_N,
    _load_priced_dataset,
    _to_data_by_stock,
    trading_calendar,
    train_frozen_model,
)
from scripts.walk_forward_backtest_compare import universe_average_gross
from src.backtest.baseline import calculate_performance, calculate_score, run_baseline_backtest
from src.backtest.buffered import run_buffered_backtest_with_turnover
from src.data.intraday_split import FORWARD_MIN_DATES, IntradaySplitError, select_segment
from src.eval.test_lock import TestSetLockedError
from src.ml.cross_section import daily_rank_ic, summarize_ic
from src.ml.strategy import make_model_score_fn
from src.reporting.run_log import RunRecorder

CALLER = "evaluate_forward_holdout.py"
OVERLAY_W = CANDIDATE_W  # 0.5, fixed by items 48/49
MIN_INTRADAY_COVERAGE = 0.80  # below this the overlay is mostly the daily score -> warn
STRATEGY_COLS = (("daily", "score_w0.0"), ("overlay", f"score_w{OVERLAY_W}"))
TIE_PERMUTATIONS = 20  # item 52, fixed before the forward look
TIE_SEED = 20260928
EXPECTED_BEST_ITERATION = 9  # item 53: a different frozen model is not the pre-registered one -> stop


def evaluate(part: pd.DataFrame) -> tuple[pd.DataFrame, dict, dict]:
    """Metrics per strategy on an already-selected, purged period."""
    part = part.dropna(subset=["target_return_5d"]).copy()
    part["target_bn"] = beta_neutral_target(part)
    data_by_stock = _to_data_by_stock(part)
    bench = universe_average_gross(data_by_stock)
    univ_cum = float((1.0 + bench).prod() - 1.0)

    rows, trades, ics = [], {}, {}
    for name, col in STRATEGY_COLS:
        scores = part[["trade_date", "stock_code", col]].rename(columns={col: "predicted_return"})
        score_fn = make_model_score_fn(scores)
        net, turnover = run_buffered_backtest_with_turnover(data_by_stock, BUFFERED_CONFIG, score_fn=score_fn, top_n=TOP_N)
        gross, _ = run_buffered_backtest_with_turnover(data_by_stock, GROSS_BUFFERED_CONFIG, score_fn=score_fn, top_n=TOP_N)
        ic = daily_rank_ic(part, col, "target_return_5d")
        ic_bn = daily_rank_ic(part.dropna(subset=["target_bn"]), col, "target_bn")
        perf = calculate_performance(net)
        s, s_bn = summarize_ic(ic), summarize_ic(ic_bn)
        rows.append({
            "strategy": name, "ic": s.mean_ic, "ic_pos": s.pct_pos, "ic_bn": s_bn.mean_ic, "days": s.n_days,
            "net_cum": perf["total_return"], "gross_cum": calculate_performance(gross)["total_return"],
            "mdd": perf["max_drawdown"], "hit": perf["win_rate"], "periods": int(perf["period_count"]),
            "entries": turnover["entries_per_period"],
        })
        trades[name], ics[name] = net, ic

    mom = run_baseline_backtest(data_by_stock, PLAIN_CONFIG, score_fn=calculate_score, top_n=TOP_N)
    perf = calculate_performance(mom)
    rows.append({"strategy": "momentum", "net_cum": perf["total_return"], "mdd": perf["max_drawdown"],
                 "hit": perf["win_rate"], "periods": int(perf["period_count"]), "entries": float(TOP_N)})
    rows.append({"strategy": "univ_ew", "gross_cum": univ_cum, "net_cum": univ_cum})
    trades["momentum"] = mom
    res = pd.DataFrame(rows)
    res["excess_vs_univ"] = res["net_cum"] - univ_cum
    return res, trades, ics


def verdicts(res: pd.DataFrame) -> dict[str, object]:
    ic = res.set_index("strategy")["ic"]
    diff = float(ic["overlay"] - ic["daily"])
    return {
        "ic_daily": float(ic["daily"]),
        "d2_not_rejected": bool(ic["daily"] > 0),
        "ic_diff": diff,
        "i6_not_rejected": bool(diff > 0),
    }


def frozen_model_ok(best_iteration: int) -> bool:
    """The forward look is valid only for the pre-registered frozen model (item 53)."""
    return int(best_iteration) == EXPECTED_BEST_ITERATION


def tie_orders(codes: list[str], n: int = TIE_PERMUTATIONS, seed: int = TIE_SEED) -> list[list[str]]:
    """``n`` random stock orders; the engine breaks score ties by dict order."""
    rng = np.random.default_rng(seed)
    return [[str(c) for c in rng.permutation(sorted(codes))] for _ in range(n)]


def tie_stats(part: pd.DataFrame, col: str, top_n: int = TOP_N) -> dict[str, float]:
    """Per-date mean of distinct scores and of stocks scoring >= the top_n-th score."""
    distinct, at_or_above = [], []
    for _, s in part.groupby("trade_date")[col]:
        s = s.dropna()
        if len(s) < top_n:
            continue
        distinct.append(s.nunique())
        at_or_above.append(int((s >= s.nlargest(top_n).iloc[-1]).sum()))
    return {
        "distinct_per_date": float(np.mean(distinct)) if distinct else float("nan"),
        "at_or_above_topn": float(np.mean(at_or_above)) if at_or_above else float("nan"),
    }


def tie_sensitivity(
    part: pd.DataFrame,
    strategies: tuple[tuple[str, str], ...] = STRATEGY_COLS,
    n: int = TIE_PERMUTATIONS,
    seed: int = TIE_SEED,
) -> pd.DataFrame:
    """Net results of each buffered strategy under ``n`` random tie-break orders."""
    part = part.dropna(subset=["target_return_5d"])
    data_by_stock = _to_data_by_stock(part)
    orders = tie_orders(list(data_by_stock), n, seed)
    rows = []
    for name, col in strategies:
        scores = part[["trade_date", "stock_code", col]].rename(columns={col: "predicted_return"})
        score_fn = make_model_score_fn(scores)
        for i, order in enumerate(orders):
            shuffled = {c: data_by_stock[c] for c in order}
            net, turnover = run_buffered_backtest_with_turnover(shuffled, BUFFERED_CONFIG, score_fn=score_fn, top_n=TOP_N)
            perf = calculate_performance(net)
            rows.append({"strategy": name, "perm": i, "net_cum": perf["total_return"], "mdd": perf["max_drawdown"],
                         "hit": perf["win_rate"], "entries": turnover["entries_per_period"]})
    return pd.DataFrame(rows)


def summarize_ties(
    sens: pd.DataFrame,
    res: pd.DataFrame,
    part: pd.DataFrame,
    strategies: tuple[tuple[str, str], ...] = STRATEGY_COLS,
) -> pd.DataFrame:
    """Distribution of net return over tie orders vs the code-ascending (reported) result."""
    base = res.set_index("strategy")
    rows = []
    for name, col in strategies:
        d = sens.loc[sens["strategy"] == name, "net_cum"]
        code_asc = float(base.loc[name, "net_cum"])
        rows.append({
            "strategy": name, **tie_stats(part, col), "code_asc": code_asc,
            "min": float(d.min()), "median": float(d.median()), "max": float(d.max()), "std": float(d.std()),
            "code_asc_pctile": float((d < code_asc).mean() + 0.5 * (d == code_asc).mean()),
            "mdd_worst": float(sens.loc[sens["strategy"] == name, "mdd"].min()),
        })
    return pd.DataFrame(rows)


def monthly_ic(ics: dict[str, pd.Series]) -> pd.DataFrame:
    return pd.DataFrame({k: v.groupby(v.index.to_period("M")).mean() for k, v in ics.items()})


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--panel", default=None, help="saved panel CSV (default: rebuild from raw -- needed for forward)")
    ap.add_argument("--minute-dir", default="data/raw/kiwoom/ka10080")
    ap.add_argument("--out", default="reports/forward_holdout")
    args = ap.parse_args()

    dataset = add_beta(_load_priced_dataset())
    trained, _ = train_frozen_model(dataset)
    print(f"frozen daily model: best_iteration={trained.best_iteration} (expected {EXPECTED_BEST_ITERATION})")
    if not frozen_model_ok(trained.best_iteration):
        print("STOP: this is not the pre-registered frozen model (library version or data changed). "
              "Fix the environment first -- the forward period was NOT read, so the one look is not spent.")
        return

    panel = load_intraday_panel(args.panel, args.minute_dir)
    df = build_scores(dataset, panel, trained)

    try:
        part = select_segment(df, "forward", caller=CALLER, horizon=5, calendar=trading_calendar())
    except (TestSetLockedError, IntradaySplitError) as locked:
        print(f"Forward holdout not evaluated: {locked}")
        return

    cov = float(part["has_intraday"].mean())
    print(f"forward period {part['trade_date'].min():%Y-%m-%d} ~ {part['trade_date'].max():%Y-%m-%d}, "
          f"{part['trade_date'].nunique()} decision dates (min {FORWARD_MIN_DATES}), intraday coverage {cov:.1%}")
    if cov < MIN_INTRADAY_COVERAGE:
        print(f"WARNING: intraday coverage below {MIN_INTRADAY_COVERAGE:.0%} -- check the nightly ingest logs "
              "before trusting the overlay comparison.")

    res, trades, ics = evaluate(part)
    v = verdicts(res)
    sens = tie_sensitivity(part)
    ties = summarize_ties(sens, res, part)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    res.to_csv(out / "forward_results.csv", index=False, encoding="utf-8-sig")
    monthly = monthly_ic(ics)
    monthly.to_csv(out / "forward_monthly_ic.csv", encoding="utf-8-sig")
    sens.to_csv(out / "forward_tie_permutations.csv", index=False, encoding="utf-8-sig")
    ties.to_csv(out / "forward_tie_sensitivity.csv", index=False, encoding="utf-8-sig")

    print("\n" + "=" * 112)
    print(f"FORWARD HOLDOUT (once)   top_n={TOP_N}, buffer={BUFFER_MULTIPLIER}, overlay w={OVERLAY_W}, "
          f"{len(STOCK_CODES)} stocks")
    print("=" * 112)
    print(res.to_string(index=False, float_format=lambda x: f"{x:+.4f}"))
    print("\nmonthly IC (info only):")
    print(monthly.to_string(float_format=lambda x: f"{x:+.4f}"))

    print(f"\ntie-break sensitivity (info only, not used by D2/I6): net_cum over {TIE_PERMUTATIONS} random "
          f"stock orders (seed {TIE_SEED}); code_asc = the reported rule")
    print(ties.to_string(index=False, float_format=lambda x: f"{x:+.4f}"))

    print("\n" + "=" * 112)
    print("PRE-REGISTERED DECISIONS")
    print("=" * 112)
    print(f"D2  IC(daily) = {v['ic_daily']:+.4f}  -> "
          + ("NOT REJECTED: daily signal present out of sample" if v["d2_not_rejected"] else "REJECTED: no daily signal"))
    print(f"I6  IC(overlay) - IC(daily) = {v['ic_diff']:+.4f}  -> "
          + ("NOT REJECTED: carry w=0.5 into the production path" if v["i6_not_rejected"] else "REJECTED: drop the overlay"))
    print("Limit: ~12 non-overlapping 5-day periods, SE(IC) ~ 0.06 -- 'not rejected' is not proof.")

    recorder = RunRecorder("forward_holdout", meta={
        "script": "scripts/evaluate_forward_holdout.py", "top_n": TOP_N, "buffer": BUFFER_MULTIPLIER,
        "overlay_w": OVERLAY_W, "best_iteration": trained.best_iteration, **v,
        "tie_permutations": TIE_PERMUTATIONS, "tie_seed": TIE_SEED,
    })
    for name, t in trades.items():
        recorder.add_trades("forward", name, t)
    for name, ic in ics.items():
        recorder.add_ic("forward", name, ic)
    recorder.save()
    print(f"\nsaved: {out / 'forward_results.csv'}, {out / 'forward_monthly_ic.csv'}, "
          f"{out / 'forward_tie_sensitivity.csv'}, {out / 'forward_tie_permutations.csv'}")


if __name__ == "__main__":
    main()
