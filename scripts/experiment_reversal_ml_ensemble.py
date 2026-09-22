"""Pre-Phase-H checklist item 5b: does blending the rule-based REVERSAL
score with the ML model add anything over either alone?

Named "momentum+ML ensemble" in the original checklist, but item 33
already found plain momentum (src.backtest.baseline.calculate_score)
runs BACKWARDS in this universe/period (consistently negative excess
return, e.g. W2 t=-3.03) while its sign-flipped version, reversal
(score = -momentum = -return_5d), is what actually carried positive
gross/excess returns alongside ML (items 33/35). Blending in literal
momentum would mean deliberately mixing in a signal already shown to
hurt, so this experiment blends REVERSAL + ML instead -- the two
signals this project has actual validation-only evidence for.

ML side uses the configuration adopted in items 36/38 (rank_by_date
target, early_stopping_metric="ic", deterministic params) -- the same
setup scripts/run_ml_backtest.py now uses.

Method: per date, z-score each signal across that date's universe
(neutralizes the two signals' very different raw scales -- reversal is
a raw 5-day return, ML's score is rank-scale), then blend

    blended = alpha * z(reversal) + (1 - alpha) * z(ml)

for a pre-registered alpha grid, and report cross-sectional rank IC
(against the raw target, same convention as items 32/36/37) for each
(window, alpha). alpha=1.0 is pure reversal, alpha=0.0 is pure ML.

Only train/validation dates are used -- the test period is never
touched (this script doesn't import src.eval.test_lock at all).

    STOCKLENS_UNIVERSE=top50 PYTHONPATH=. python3 scripts/experiment_reversal_ml_ensemble.py
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

# alpha=1.0 -> pure reversal, alpha=0.0 -> pure ML. Pre-registered before
# looking at any window's results.
ALPHAS = (0.0, 0.25, 0.5, 0.75, 1.0)


def load_dataset() -> pd.DataFrame:
    storage = HistoricalStorage("data")
    stock_bars = {code: storage.load_daily_bars(code) for code in get_universe()}
    dataset = build_combined_dataset(stock_bars)
    dataset["trade_date"] = pd.to_datetime(dataset["trade_date"])
    dataset[list(FEATURE_COLUMNS)] = dataset[list(FEATURE_COLUMNS)].replace(
        [np.inf, -np.inf], np.nan
    )
    return dataset


def _zscore_by_date(df: pd.DataFrame, col: str) -> pd.Series:
    grouped = df.groupby("trade_date")[col]
    mean = grouped.transform("mean")
    std = grouped.transform("std")
    z = (df[col] - mean) / std
    # A date where every stock has the identical raw value (std == 0,
    # e.g. a data gap) carries no cross-sectional information -- treat
    # as neutral (0) rather than propagating inf/NaN into the blend.
    return z.fillna(0.0).replace([np.inf, -np.inf], 0.0)


def run_window(dataset: pd.DataFrame, label: str, train_end: str, val_start: str, val_end: str) -> list[dict]:
    splits = split_by_time(
        dataset,
        train_start=TRAIN_START_DATE, train_end=train_end,
        validation_start=val_start, validation_end=val_end,
        test_start=TEST_START_DATE, test_end=TEST_END_DATE,
    )

    trained = train_model(
        splits.train,
        rank_by_date(splits.train, "target_return_5d"),
        splits.validation,
        rank_by_date(splits.validation, "target_return_5d"),
        feature_columns=ALL_19,
        params=DETERMINISTIC_PARAMS,
        early_stopping_metric="ic",
    )

    val = splits.validation.copy()
    val["reversal_score"] = -val["return_5d"]
    val["ml_score"] = predict(trained, val)
    val["z_reversal"] = _zscore_by_date(val, "reversal_score")
    val["z_ml"] = _zscore_by_date(val, "ml_score")

    rows = []
    for alpha in ALPHAS:
        val["blended"] = alpha * val["z_reversal"] + (1 - alpha) * val["z_ml"]
        summary = summarize_ic(daily_rank_ic(val, "blended", "target_return_5d"))
        rows.append(
            {
                "window": label,
                "alpha": alpha,
                "best_iteration": trained.best_iteration,
                "val_ic": summary.mean_ic,
                "pct_pos": summary.pct_pos,
                "coverage": summary.coverage,
                "n_days": summary.n_days,
            }
        )
    return rows


def main() -> None:
    dataset = load_dataset()
    rows = [row for w in WINDOWS for row in run_window(dataset, *w)]
    results = pd.DataFrame(rows)

    for label in results["window"].unique():
        print("\n" + "=" * 80)
        sub = results[results["window"] == label]
        print(f"{label}  (best_iteration={int(sub['best_iteration'].iloc[0])})")
        print("=" * 80)
        header = f"{'alpha':>7}{'val_ic':>9}{'%days>0':>9}{'coverage':>10}{'n_days':>8}"
        print(header)
        for r in sub.itertuples():
            label_alpha = "1.0(reversal)" if r.alpha == 1.0 else ("0.0(ML)" if r.alpha == 0.0 else f"{r.alpha:.2f}")
            print(f"{label_alpha:>7}{r.val_ic:>9.4f}{r.pct_pos:>9.2%}{r.coverage:>10.1%}{r.n_days:>8}")

    print("\n" + "=" * 80)
    print(
        "How to read it: alpha=0.0 is pure ML, alpha=1.0 is pure reversal. "
        "If some intermediate alpha's val_ic clearly beats BOTH endpoints "
        "in most/all windows, the two signals are complementary and "
        "blending helps. If the best alpha is always (near) 0 or 1, or "
        "the intermediate values are just an interpolation between the "
        "two endpoints with no bump, blending isn't adding anything -- "
        "just use whichever endpoint is better."
    )
    print("=" * 80)


if __name__ == "__main__":
    main()
