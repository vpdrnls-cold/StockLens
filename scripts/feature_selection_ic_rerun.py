"""Re-run Feature Selection (Filter / Wrapper / Embedded) using
cross-sectional rank IC on the VALIDATION split, restricted to the 19
scale-free candidates (the 8 raw-price/volume-scale features are excluded
up front, same as the current SELECTED_FEATURES).

Background: SELECTED_FEATURES was widened from 5 to all 19 scale-free
candidates as a brute-force interim fix (see src/features/engineering.py
and CURRENT_STATUS.md section 14). That step never searched for a better
SUBSET -- it just used everything. This script does that search properly,
with the metric that actually matches a top-N ranking strategy
(cross-sectional rank IC, not pooled RMSE), and never touches the test
period except for one final confirmation at the end.

Run from the repo root:
    PYTHONPATH=. python3 scripts/feature_selection_ic_rerun.py

Runtime: a few minutes (the Wrapper step trains up to ~150 XGBoost models).

REPRODUCIBILITY NOTE (2026-09-17): the first version of this script used
XGBoost's default n_jobs=-1 (all available cores). XGBoost's histogram
tree builder sums per-thread partial results in parallel, and that
summation order depends on how many threads actually ran -- so the exact
floating-point result (and therefore which feature wins a near-tied race)
can differ between machines with different core counts, even with the
same random_state. This showed up concretely: one run picked
('atr_pct', 'gap') and another, on different hardware, picked
('return_20d',) alone -- both from the SAME code and SAME data. Forcing
DETERMINISTIC_PARAMS = {"n_jobs": 1} below removes that specific source of
cross-machine variance (single-threaded histogram building sums in a
fixed order), so re-runs of this exact script should now agree across
machines. It does not, by itself, make a weak/borderline-significant IC
result "correct" -- it only makes the number reproducible so that question
can be investigated on stable footing (e.g. via a walk-forward check
across several validation windows, not yet implemented here).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

from src.data.dataset import build_combined_dataset, split_by_time
from src.data.storage import HistoricalStorage
from src.data.universe import get_universe
from src.features.engineering import FEATURE_COLUMNS
from src.models.predict import train_model, predict

ALL_STOCKS = get_universe()  # core5 by default; STOCKLENS_UNIVERSE=top50 for 50 stocks

# Same exclusion as the current SELECTED_FEATURES: these mix raw price/
# volume level across differently-priced stocks and previously caused the
# model to learn "stock identity" instead of real time-varying signal.
RAW_SCALE_FEATURES = {
    "sma_5", "sma_20", "sma_60",
    "macd", "macd_signal", "macd_hist",
    "atr_14", "volume_sma_20",
}
CANDIDATES = tuple(f for f in FEATURE_COLUMNS if f not in RAW_SCALE_FEATURES)

# Force single-threaded XGBoost so results are reproducible across
# machines with different core counts (see REPRODUCIBILITY NOTE above).
# Every train_model() call in this script merges this in.
#
# UPDATE (CURRENT_STATUS.md item 23): n_jobs=1 alone did NOT fix this --
# it was later confirmed (this script's own REPRODUCIBILITY NOTE
# predates that finding) that the real cause is XGBoost's default
# tree_method="hist" summing histograms in an order that differs by CPU
# architecture, regardless of thread count. tree_method="exact" gave
# bit-identical predictions on two genuinely different real machines
# (Linux x86_64 vs macOS arm64) -- added here so a re-run of this
# script is actually reproducible, not just single-threaded.
DETERMINISTIC_PARAMS = {"n_jobs": 1, "tree_method": "exact"}

# Below this many valid cross-sectional decision-dates, predictions were
# too close to constant to trust the IC (see the "Top-5 by standalone IC"
# false-positive from the earlier validation scan: n=47 out of ~800).
MIN_DAYS = 300


def load_dataset() -> pd.DataFrame:
    storage = HistoricalStorage("data")
    stock_bars = {code: storage.load_daily_bars(code) for code in ALL_STOCKS}
    dataset = build_combined_dataset(stock_bars)
    dataset["trade_date"] = pd.to_datetime(dataset["trade_date"])
    dataset[list(FEATURE_COLUMNS)] = dataset[list(FEATURE_COLUMNS)].replace(
        [np.inf, -np.inf], np.nan
    )
    return dataset


def cross_sectional_ic(
    df: pd.DataFrame, score_col: str, target_col: str = "target_return_5d"
) -> tuple[float, float, int, float]:
    """Cross-sectional Spearman rank IC over ALL eligible decision dates.

    Returns ``(mean_ic, pct_pos, n_days, coverage)``.

    A date is eligible when at least 3 stocks are present. On an eligible
    date where the score is identical for every stock the IC is undefined
    (a tiny early-stopped tree model often puts every stock in the same
    leaf). Such a date is counted as IC = 0, NOT dropped: the model made
    no ranking call that day, and dropping those days lets a weak model
    report the IC of only the days on which it happened to discriminate --
    a selected, inflated subset (top50 run: a 4-feature Wrapper showed
    IC +0.0566 on n=343 of ~865 days).

    ``pct_pos`` is the share of ALL eligible days with IC > 0; ``coverage``
    is the share of eligible days on which the IC was defined.
    """
    ics: list[float] = []
    n_eligible = 0
    n_defined = 0
    for _, group in df.groupby("trade_date"):
        if group["stock_code"].nunique() < 3:
            continue
        n_eligible += 1
        if group[score_col].nunique() < 2:
            ics.append(0.0)
            continue
        ic, _ = stats.spearmanr(group[score_col], group[target_col])
        if np.isnan(ic):
            ics.append(0.0)
            continue
        ics.append(float(ic))
        n_defined += 1
    if n_eligible == 0:
        return float("nan"), float("nan"), 0, 0.0
    arr = np.array(ics)
    return float(arr.mean()), float((arr > 0).mean()), n_eligible, n_defined / n_eligible


def evaluate_feature_set(splits, feature_set: tuple[str, ...]) -> tuple[float, float, int, float]:
    """Train on train (early-stopped on validation), score cross-sectional
    IC on validation. Returns -inf for mean_ic if the result is unreliable
    (too few usable cross-sectional decision-dates)."""
    if not feature_set:
        return float("-inf"), float("nan"), 0, 0.0

    trained = train_model(
        splits.train, splits.train["target_return_5d"],
        splits.validation, splits.validation["target_return_5d"],
        feature_columns=feature_set,
        params=DETERMINISTIC_PARAMS,
    )
    val = splits.validation.copy()
    val["predicted_return"] = predict(trained, val)
    mean_ic, pct_pos, n, cov = cross_sectional_ic(val, "predicted_return")

    if n < MIN_DAYS or np.isnan(mean_ic):
        return float("-inf"), pct_pos, n, cov
    return mean_ic, pct_pos, n, cov


# ---------------------------------------------------------------------
# 1. FILTER -- rank candidates by their own standalone cross-sectional
#    IC (no model needed), then check top-K subsets as an actual model.
# ---------------------------------------------------------------------

def filter_method(splits) -> tuple[tuple[str, ...], float]:
    print("\n" + "=" * 90)
    print("1. FILTER -- standalone per-feature cross-sectional IC on validation")
    print("=" * 90)

    val = splits.validation
    scores = []
    for feat in CANDIDATES:
        mean_ic, pct_pos, n, cov = cross_sectional_ic(val, feat)
        scores.append((feat, mean_ic, pct_pos, n, cov))
    scores.sort(key=lambda r: -abs(r[1]) if not np.isnan(r[1]) else 0)

    print(f"{'feature':<20}{'mean_IC':>10}{'%days>0':>10}{'n_days':>8}{'coverage':>10}")
    for feat, mean_ic, pct_pos, n, cov in scores:
        print(f"{feat:<20}{mean_ic:>+10.4f}{pct_pos:>10.2%}{n:>8}{cov:>10.1%}")

    ranked_features = [f for f, *_ in scores]

    print("\n-- Evaluating top-K subsets as an actual trained model --")
    best_subset, best_ic = None, float("-inf")
    for k in sorted(set([3, 5, 8, 12, len(ranked_features)])):
        subset = tuple(ranked_features[:k])
        mean_ic, pct_pos, n, cov = evaluate_feature_set(splits, subset)
        note = "" if mean_ic > float("-inf") else "  [UNRELIABLE]"
        print(f"  top-{k:<3} val_xsec_IC={mean_ic:+.4f}  %days>0={pct_pos:.2%}  n={n}  coverage={cov:.1%}{note}")
        print(f"           {subset}")
        if mean_ic > best_ic:
            best_subset, best_ic = subset, mean_ic

    print(f"\n>> Filter best: {len(best_subset)} features, IC={best_ic:+.4f}")
    return best_subset, best_ic


# ---------------------------------------------------------------------
# 2. WRAPPER -- greedy sequential forward selection (SFS), scored by
#    cross-sectional IC on validation. Stops when adding anything more
#    stops helping.
# ---------------------------------------------------------------------

def wrapper_sfs(splits, max_features: int = 10) -> tuple[tuple[str, ...], float]:
    print("\n" + "=" * 90)
    print("2. WRAPPER -- sequential forward selection, scored by cross-sectional IC")
    print("=" * 90)

    selected: list[str] = []
    remaining = list(CANDIDATES)
    best_ic_so_far = float("-inf")

    while remaining and len(selected) < max_features:
        round_results = []
        for feat in remaining:
            trial = tuple(selected + [feat])
            mean_ic, pct_pos, n, cov = evaluate_feature_set(splits, trial)
            round_results.append((feat, mean_ic, pct_pos, n, cov))

        round_results.sort(key=lambda r: r[1], reverse=True)
        best_feat, best_mean_ic, best_pct, best_n, best_cov = round_results[0]

        print(
            f"  round {len(selected) + 1}: best add = {best_feat:<20} "
            f"-> IC={best_mean_ic:+.4f} (%days>0={best_pct:.2%}, n={best_n}, coverage={best_cov:.1%})  "
            f"[current best={best_ic_so_far:+.4f}]"
        )

        if best_mean_ic <= best_ic_so_far:
            print("  -- no further improvement, stopping.")
            break

        selected.append(best_feat)
        remaining.remove(best_feat)
        best_ic_so_far = best_mean_ic

    print(f"\n>> Wrapper best: {tuple(selected)}")
    print(f"   IC={best_ic_so_far:+.4f}")
    return tuple(selected), best_ic_so_far


# ---------------------------------------------------------------------
# 3. EMBEDDED -- fit once on all candidates, rank by the model's own
#    gain importance, then check top-K subsets by importance.
# ---------------------------------------------------------------------

def embedded_importance(splits) -> tuple[tuple[str, ...], float]:
    print("\n" + "=" * 90)
    print("3. EMBEDDED -- XGBoost gain importance (single fit on all candidates)")
    print("=" * 90)

    trained = train_model(
        splits.train, splits.train["target_return_5d"],
        splits.validation, splits.validation["target_return_5d"],
        feature_columns=CANDIDATES,
        params=DETERMINISTIC_PARAMS,
    )
    importances = trained.model.feature_importances_
    ranked = sorted(zip(CANDIDATES, importances), key=lambda x: -x[1])

    print("  Ranked by gain importance:")
    for feat, imp in ranked:
        print(f"    {feat:<20} {imp:.4f}")

    ranked_features = [f for f, _ in ranked]
    best_subset, best_ic = None, float("-inf")
    for k in sorted(set([3, 5, 8, 12, len(ranked_features)])):
        subset = tuple(ranked_features[:k])
        mean_ic, pct_pos, n, cov = evaluate_feature_set(splits, subset)
        note = "" if mean_ic > float("-inf") else "  [UNRELIABLE]"
        print(f"  top-{k:<3} val_xsec_IC={mean_ic:+.4f}  %days>0={pct_pos:.2%}  n={n}  coverage={cov:.1%}{note}")
        print(f"           {subset}")
        if mean_ic > best_ic:
            best_subset, best_ic = subset, mean_ic

    print(f"\n>> Embedded best: {len(best_subset)} features, IC={best_ic:+.4f}")
    return best_subset, best_ic


def main() -> None:
    dataset = load_dataset()
    splits = split_by_time(dataset)

    baseline_ic, _, baseline_n, baseline_cov = evaluate_feature_set(splits, CANDIDATES)
    print(
        f"BASELINE (current SELECTED_FEATURES = all {len(CANDIDATES)} scale-free "
        f"candidates): val_xsec_IC={baseline_ic:+.4f}  n={baseline_n}  coverage={baseline_cov:.1%}"
    )

    filter_subset, filter_ic = filter_method(splits)
    wrapper_subset, wrapper_ic = wrapper_sfs(splits)
    embedded_subset, embedded_ic = embedded_importance(splits)

    print("\n" + "=" * 90)
    print("SUMMARY (validation cross-sectional IC)")
    print("=" * 90)
    print(f"  Baseline (all {len(CANDIDATES)}):      {baseline_ic:+.4f}")
    print(f"  Filter   ({len(filter_subset):>2} feat):  {filter_ic:+.4f}  {filter_subset}")
    print(f"  Wrapper  ({len(wrapper_subset):>2} feat):  {wrapper_ic:+.4f}  {wrapper_subset}")
    print(f"  Embedded ({len(embedded_subset):>2} feat): {embedded_ic:+.4f}  {embedded_subset}")

    candidates = [
        ("Baseline (all 19)", CANDIDATES, baseline_ic),
        ("Filter", filter_subset, filter_ic),
        ("Wrapper", wrapper_subset, wrapper_ic),
        ("Embedded", embedded_subset, embedded_ic),
    ]
    winner_label, winner_subset, winner_ic = max(candidates, key=lambda c: c[2])
    print(f"\n>> OVERALL WINNER on validation: {winner_label} (IC={winner_ic:+.4f})")
    print(f"   features: {winner_subset}")

    print("\n" + "=" * 90)
    print("ONE-TIME TEST CONFIRMATION (test period touched exactly once, here)")
    print("=" * 90)
    trained = train_model(
        splits.train, splits.train["target_return_5d"],
        splits.validation, splits.validation["target_return_5d"],
        feature_columns=winner_subset,
        params=DETERMINISTIC_PARAMS,
    )
    test = splits.test.copy()
    test["predicted_return"] = predict(trained, test)
    mean_ic, pct_pos, n, cov = cross_sectional_ic(test, "predicted_return")
    print(f"  Test cross-sectional IC = {mean_ic:+.4f}  %days>0={pct_pos:.2%}  n={n}  coverage={cov:.1%}")
    print(
        "\n  Next: if this beats the current baseline, update SELECTED_FEATURES in "
        "src/features/engineering.py to this subset and re-run scripts/run_ml_backtest.py "
        "to see actual cumulative-return / hit-rate / drawdown numbers."
    )


if __name__ == "__main__":
    main()
