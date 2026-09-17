"""Walk-forward robustness check for the Wrapper feature-selection step.

Background: running scripts/feature_selection_ic_rerun.py on two different
machines (with n_jobs=1 forced on both, ruling out threading as the cause)
picked two different Wrapper winners from the same code and the same
data -- ('atr_pct', 'gap') on one machine, ('return_20d',) on the other
(roc_20 is a literal duplicate of return_20d, see engineering.py). Chasing
that exact cross-machine discrepancy further has diminishing returns.

The more useful question is: on ONE machine, does the Wrapper keep
finding roughly the same kind of signal if you give it different slices
of history to search over? This script runs the identical greedy
Wrapper search across three separate, non-overlapping train/validation
windows -- all strictly before the untouched test period (2023-07 on) --
and reports whether a stable winner (or family of winners) shows up.

Run this on a single machine only; comparing walk-forward results ACROSS
machines is a separate, harder problem this script does not attempt.

Run from the repo root:
    PYTHONPATH=. python3 scripts/walk_forward_wrapper.py

Runtime: a few minutes (3 windows x up to ~50 model fits each).
"""

from __future__ import annotations

from collections import Counter

import numpy as np
import pandas as pd
from scipy import stats

from src.data.dataset import (
    TEST_END_DATE,
    TEST_START_DATE,
    TRAIN_START_DATE,
    build_combined_dataset,
    split_by_time,
)
from src.data.storage import HistoricalStorage
from src.features.engineering import FEATURE_COLUMNS
from src.models.predict import train_model, predict

ALL_STOCKS = ("000660", "005380", "005930", "035420", "035720")

RAW_SCALE_FEATURES = {
    "sma_5", "sma_20", "sma_60",
    "macd", "macd_signal", "macd_hist",
    "atr_14", "volume_sma_20",
}
CANDIDATES = tuple(f for f in FEATURE_COLUMNS if f not in RAW_SCALE_FEATURES)

# Same fix as feature_selection_ic_rerun.py: single-threaded for
# reproducible re-runs on THIS machine.
DETERMINISTIC_PARAMS = {"n_jobs": 1}

MIN_DAYS = 300
MAX_WRAPPER_FEATURES = 6  # keep each window's search cheap

# Three sequential, non-overlapping expanding-window splits. Test period
# is never touched here -- these are all train/validation only, entirely
# before TEST_START_DATE (2023-07-01).
WINDOWS = [
    ("Window 1: train ..2011-12-31 / val 2012-2015", "2011-12-31", "2012-01-01", "2015-12-31"),
    ("Window 2: train ..2015-12-31 / val 2016-2019", "2015-12-31", "2016-01-01", "2019-12-31"),
    ("Window 3: train ..2019-12-31 / val 2020-2023.06 (current default)", "2019-12-31", "2020-01-01", "2023-06-30"),
]


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
) -> tuple[float, float, int]:
    ics = []
    for _, group in df.groupby("trade_date"):
        if group["stock_code"].nunique() < 3 or group[score_col].nunique() < 2:
            continue
        ic, _ = stats.spearmanr(group[score_col], group[target_col])
        if not np.isnan(ic):
            ics.append(ic)
    ics = np.array(ics)
    if len(ics) == 0:
        return float("nan"), float("nan"), 0
    return float(ics.mean()), float((ics > 0).mean()), len(ics)


def evaluate_feature_set(splits, feature_set: tuple[str, ...]) -> tuple[float, float, int]:
    if not feature_set:
        return float("-inf"), float("nan"), 0
    trained = train_model(
        splits.train, splits.train["target_return_5d"],
        splits.validation, splits.validation["target_return_5d"],
        feature_columns=feature_set,
        params=DETERMINISTIC_PARAMS,
    )
    val = splits.validation.copy()
    val["predicted_return"] = predict(trained, val)
    mean_ic, pct_pos, n = cross_sectional_ic(val, "predicted_return")
    if n < MIN_DAYS or np.isnan(mean_ic):
        return float("-inf"), pct_pos, n
    return mean_ic, pct_pos, n


def wrapper_sfs(splits, max_features: int = MAX_WRAPPER_FEATURES) -> tuple[tuple[str, ...], float]:
    selected: list[str] = []
    remaining = list(CANDIDATES)
    best_ic_so_far = float("-inf")

    while remaining and len(selected) < max_features:
        round_results = []
        for feat in remaining:
            trial = tuple(selected + [feat])
            mean_ic, pct_pos, n = evaluate_feature_set(splits, trial)
            round_results.append((feat, mean_ic, pct_pos, n))

        round_results.sort(key=lambda r: r[1], reverse=True)
        best_feat, best_mean_ic, best_pct, best_n = round_results[0]

        print(
            f"    round {len(selected) + 1}: best add = {best_feat:<20} "
            f"-> IC={best_mean_ic:+.4f} (%days>0={best_pct:.2%}, n={best_n})"
        )

        if best_mean_ic <= best_ic_so_far:
            print("    -- no further improvement, stopping.")
            break

        selected.append(best_feat)
        remaining.remove(best_feat)
        best_ic_so_far = best_mean_ic

    return tuple(selected), best_ic_so_far


def main() -> None:
    dataset = load_dataset()

    results = []
    for label, train_end, val_start, val_end in WINDOWS:
        print("\n" + "=" * 90)
        print(label)
        print("=" * 90)

        splits = split_by_time(
            dataset,
            train_start=TRAIN_START_DATE,
            train_end=train_end,
            validation_start=val_start,
            validation_end=val_end,
            test_start=TEST_START_DATE,
            test_end=TEST_END_DATE,
        )
        print(
            f"  train: {splits.train['trade_date'].min().date()} ~ "
            f"{splits.train['trade_date'].max().date()}  (n={len(splits.train)})"
        )
        print(
            f"  val:   {splits.validation['trade_date'].min().date()} ~ "
            f"{splits.validation['trade_date'].max().date()}  (n={len(splits.validation)})"
        )

        subset, ic = wrapper_sfs(splits)
        print(f"  >> winner: {subset}  IC={ic:+.4f}")
        results.append((label, subset, ic))

    print("\n" + "=" * 90)
    print("SUMMARY ACROSS WINDOWS")
    print("=" * 90)
    feature_votes = Counter()
    for label, subset, ic in results:
        print(f"  {label}")
        print(f"    -> {subset}  (IC={ic:+.4f})")
        feature_votes.update(subset)

    print("\n  Feature appearance count across the 3 windows (higher = more stable):")
    for feat, count in feature_votes.most_common():
        print(f"    {feat:<20} appeared in {count}/3 windows")

    print(
        "\n  Interpretation: a feature appearing in 2-3/3 windows is a much stronger "
        "candidate than one that only won in a single window (which is more likely "
        "noise specific to that period). If nothing recurs, treat all single-window "
        "Wrapper results (on any machine) as inconclusive."
    )


if __name__ == "__main__":
    main()
