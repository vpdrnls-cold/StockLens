"""Does a cross-sectional training target make the model rank better?

Compares, on the same three walk-forward windows as
scripts/walk_forward_wrapper.py (train/validation only -- the test period is
never touched):

  raw       target_return_5d as is (current setup)
  demeaned  minus the per-date mean over stocks (removes the market move)
  rank      per-date percentile rank in (-0.5, 0.5)

for two feature sets: all 19 scale-free candidates, and a small
"reversal family" (return_5d, rsi_14, return_20d, price_to_sma_20) -- the
features that won the Wrapper in the walk-forward windows of CURRENT_STATUS
item 30. IC is always measured against the ORIGINAL target (the per-date
rank IC is unchanged by a per-date monotone transform, so this is exact).

Output per fit: IC (undefined days = 0), %days>0, coverage (share of days
on which the model produced a non-constant ranking), best_iteration.

    STOCKLENS_UNIVERSE=top50 PYTHONPATH=. python3 scripts/experiment_target_transform.py
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
from src.ml.cross_section import daily_rank_ic, demean_by_date, rank_by_date, summarize_ic
from src.models.predict import predict, train_model

RAW_SCALE_FEATURES = {
    "sma_5", "sma_20", "sma_60", "macd", "macd_signal", "macd_hist",
    "atr_14", "volume_sma_20",
}
ALL_19 = tuple(f for f in FEATURE_COLUMNS if f not in RAW_SCALE_FEATURES)
REVERSAL_FAMILY = ("return_5d", "rsi_14", "return_20d", "price_to_sma_20")
FEATURE_SETS = {"all19": ALL_19, "reversal4": REVERSAL_FAMILY}

DETERMINISTIC_PARAMS = {"n_jobs": 1, "tree_method": "exact"}

WINDOWS = [
    ("W1 val 2012-2015", "2011-12-31", "2012-01-01", "2015-12-31"),
    ("W2 val 2016-2019", "2015-12-31", "2016-01-01", "2019-12-31"),
    ("W3 val 2020-2023H1", "2019-12-31", "2020-01-01", "2023-06-30"),
]

TARGETS = {
    "raw": lambda df: df["target_return_5d"],
    "demeaned": lambda df: demean_by_date(df, "target_return_5d"),
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


def run(dataset: pd.DataFrame, windows=WINDOWS) -> pd.DataFrame:
    records = []
    for label, train_end, val_start, val_end in windows:
        splits = split_by_time(
            dataset,
            train_start=TRAIN_START_DATE,
            train_end=train_end,
            validation_start=val_start,
            validation_end=val_end,
            test_start=TEST_START_DATE,
            test_end=TEST_END_DATE,
        )
        print(f"\n{label}: train n={len(splits.train)}  val n={len(splits.validation)}")

        for set_name, features in FEATURE_SETS.items():
            for target_name, transform in TARGETS.items():
                trained = train_model(
                    splits.train, transform(splits.train),
                    splits.validation, transform(splits.validation),
                    feature_columns=features,
                    params=DETERMINISTIC_PARAMS,
                )
                val = splits.validation.copy()
                val["predicted"] = predict(trained, val)
                summary = summarize_ic(daily_rank_ic(val, "predicted"))
                records.append(
                    {
                        "window": label,
                        "features": set_name,
                        "target": target_name,
                        "ic": summary.mean_ic,
                        "pct_pos": summary.pct_pos,
                        "coverage": summary.coverage,
                        "best_iter": trained.best_iteration,
                    }
                )
                print(
                    f"  {set_name:<10}{target_name:<10}IC={summary.mean_ic:+.4f}  "
                    f"%days>0={summary.pct_pos:.1%}  coverage={summary.coverage:.1%}  "
                    f"best_iteration={trained.best_iteration}"
                )
    return pd.DataFrame(records)


def main() -> None:
    results = run(load_dataset())

    print("\n" + "=" * 90)
    print("AVERAGE ACROSS THE 3 WINDOWS")
    print("=" * 90)
    summary = (
        results.groupby(["features", "target"])[["ic", "pct_pos", "coverage", "best_iter"]]
        .mean()
        .round(4)
    )
    print(summary.to_string())
    wins = results.pivot_table(index=["features", "window"], columns="target", values="ic")
    print("\nIC by window:")
    print(wins.round(4).to_string())
    print(
        "\nInterpretation: only trust a target/feature-set combination that is "
        "positive in all three windows (or at least the two windows before 2020) "
        "with coverage near 100%. A better window-3 number alone is the same "
        "kind of single-window result as CURRENT_STATUS items 15/18/20."
    )


if __name__ == "__main__":
    main()
