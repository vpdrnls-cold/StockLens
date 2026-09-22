"""Pre-Phase-H checklist item 3: does IC-based early stopping fix the
Window-3-style near-untrained-model problem?

CURRENT_STATUS.md items 18/20/24/30-33 keep hitting the same open issue:
some walk-forward windows (Window1 on core5, W3 on top50) train a model
with `best_iteration` of 0-8 -- essentially untrained -- because RMSE-based
early stopping plateaus almost immediately when the target's variance is
dominated by an unlearnable per-date common component (item 30's
diagnosis). `src.models.predict.train_model(..., early_stopping_metric="ic")`
(new) stops on cross-sectional rank IC instead, which cancels the common
component by construction. This script trains both variants on the same
3 walk-forward windows already used everywhere else in this project and
reports best_iteration and out-of-sample validation IC side by side.

Only train/validation dates are used -- the test period is never
touched (this script doesn't import src.eval.test_lock at all).

    STOCKLENS_UNIVERSE=top50 PYTHONPATH=. python3 scripts/compare_early_stopping_metric.py
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.data.dataset import (
    TEST_END_DATE,
    TEST_START_DATE,
    TRAIN_START_DATE,
    build_combined_dataset,
    split_by_time,
)
from src.data.storage import HistoricalStorage
from src.data.universe import get_universe
from src.features.engineering import FEATURE_COLUMNS
from src.ml.cross_section import daily_rank_ic, rank_by_date, summarize_ic
from src.models.predict import predict, train_model

RAW_SCALE_FEATURES = {
    "sma_5", "sma_20", "sma_60", "macd", "macd_signal", "macd_hist",
    "atr_14", "volume_sma_20",
}
ALL_19 = tuple(f for f in FEATURE_COLUMNS if f not in RAW_SCALE_FEATURES)
DETERMINISTIC_PARAMS = {"n_jobs": 1, "tree_method": "exact"}

WINDOWS = [
    ("W1 val 2012-2015", "2011-12-31", "2012-01-01", "2015-12-31"),
    ("W2 val 2016-2019", "2015-12-31", "2016-01-01", "2019-12-31"),
    ("W3 val 2020-2023H1", "2019-12-31", "2020-01-01", "2023-06-30"),
]

# Two target framings, since item 32 found the rank target more stable
# than the raw target -- worth knowing whether the early-stopping fix
# matters for both or mainly rescues the weaker (raw) framing.
TARGETS = {
    "raw": lambda df: df["target_return_5d"],
    "rank": lambda df: rank_by_date(df, "target_return_5d"),
}


def load_dataset() -> pd.DataFrame:
    storage = HistoricalStorage("data")
    stock_bars = {code: storage.load_daily_bars(code) for code in get_universe()}
    dataset = build_combined_dataset(stock_bars)
    dataset["trade_date"] = pd.to_datetime(dataset["trade_date"])
    dataset[list(FEATURE_COLUMNS)] = dataset[list(FEATURE_COLUMNS)].replace(
        [np.inf, -np.inf], np.nan
    )
    return dataset


def evaluate(splits, target_name: str, early_stopping_metric: str) -> dict:
    target_fn = TARGETS[target_name]
    trained = train_model(
        splits.train, target_fn(splits.train),
        splits.validation, target_fn(splits.validation),
        feature_columns=ALL_19,
        params=DETERMINISTIC_PARAMS,
        early_stopping_metric=early_stopping_metric,
    )
    val = splits.validation.copy()
    val["predicted"] = predict(trained, val)
    # Always evaluate against the RAW target's cross-sectional IC --
    # the point is real-world ranking usefulness, independent of which
    # target the model was trained on.
    summary = summarize_ic(daily_rank_ic(val, "predicted", "target_return_5d"))
    return {
        "target": target_name,
        "early_stopping": early_stopping_metric,
        "best_iteration": trained.best_iteration,
        "val_ic": summary.mean_ic,
        "pct_pos": summary.pct_pos,
        "coverage": summary.coverage,
        "n_days": summary.n_days,
    }


def run(dataset: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for label, train_end, val_start, val_end in WINDOWS:
        splits = split_by_time(
            dataset,
            train_start=TRAIN_START_DATE, train_end=train_end,
            validation_start=val_start, validation_end=val_end,
            test_start=TEST_START_DATE, test_end=TEST_END_DATE,
        )
        print(f"\n{label}: train n={len(splits.train)}  val n={len(splits.validation)}")
        for target_name in TARGETS:
            for early_stopping_metric in ("rmse", "ic"):
                row = evaluate(splits, target_name, early_stopping_metric)
                row["window"] = label
                rows.append(row)
    return pd.DataFrame(rows)


def _print_table(df: pd.DataFrame) -> None:
    header = (
        f"{'target':<7}{'stop_on':>9}{'best_iter':>11}{'val_ic':>9}"
        f"{'%days>0':>9}{'coverage':>10}{'n_days':>8}"
    )
    print(header)
    for r in df.itertuples():
        print(
            f"{r.target:<7}{r.early_stopping:>9}{r.best_iteration:>11}"
            f"{r.val_ic:>9.4f}{r.pct_pos:>9.2%}{r.coverage:>10.1%}{r.n_days:>8}"
        )


def main() -> None:
    results = run(load_dataset())

    for label in results["window"].unique():
        print("\n" + "=" * 80)
        print(label)
        print("=" * 80)
        _print_table(results[results["window"] == label])

    print("\n" + "=" * 80)
    print("How to read it: for each (target, window) pair, compare the 'rmse' row "
          "against the 'ic' row directly below it. A best_iteration that jumps well "
          "above single digits under 'ic', together with a val_ic that doesn't get "
          "worse, means IC-based early stopping is fixing a real early-stopping "
          "problem rather than just training longer for its own sake.")
    print("=" * 80)


if __name__ == "__main__":
    main()
