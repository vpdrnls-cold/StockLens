"""Pre-Phase-H checklist item 5a: does reframing the target as cross-sectional
binary classification ("will this stock beat the same-date median 5-day
return?") do any better than the rank-regression target already adopted in
items 32/36/37?

Rationale for even checking (kept deliberately light -- one binary
threshold, no hyperparameter search): items 32/33/37 already show the
underlying price-based cross-sectional signal is weak and decays toward
the most recent window (W3), and that finding shouldn't depend on the
model being a regressor vs a classifier. But the checklist explicitly
asks the rank/classification target question, so this is answered with
evidence rather than assumption.

Label: per date, 1 if a stock's target_return_5d is above that date's
OWN median (across the same universe/date used everywhere else in this
project), else 0 -- computed independently within each split's own dates,
exactly the same "same-date peer group" transform src.ml.cross_section's
rank_by_date already uses for the regression target (not a new source of
leakage: it only uses other stocks' forward returns over the same forward
window, on the same decision date, never a future decision date).

Score for IC purposes: predicted P(class=1). Rank correlation is
invariant to monotonic transforms, so this is the natural classification
analogue of a predicted score. Always measured against the RAW target
(same convention as compare_early_stopping_metric.py) so it's directly
comparable to the rank-regression numbers already in CURRENT_STATUS.md
items 32/36.

Only train/validation dates are used -- the test period is never touched
(this script doesn't import src.eval.test_lock at all).

    STOCKLENS_UNIVERSE=top50 PYTHONPATH=. python3 scripts/experiment_classification_target.py
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from xgboost import XGBClassifier

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
from src.ml.cross_section import daily_rank_ic, summarize_ic
from src.models.predict import DEFAULT_PARAMS, EARLY_STOPPING_ROUNDS

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

# Prior rank-regression results (items 32/36) for the same windows, for
# direct side-by-side comparison. Not recomputed here.
PRIOR_RANK_REGRESSION = {
    "W1 val 2012-2015": {"rmse": 0.0635, "ic": 0.0626},
    "W2 val 2016-2019": {"rmse": 0.0413, "ic": 0.0417},
    "W3 val 2020-2023H1": {"rmse": 0.0130, "ic": 0.0154},
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


def _above_median_label(df: pd.DataFrame, col: str = "target_return_5d") -> pd.Series:
    """1 if col is above this row's OWN date's median, else 0.

    Same-date peer group only (see module docstring) -- mirrors
    src.ml.cross_section.rank_by_date's leakage-safety, just discretized.
    """
    median_by_date = df.groupby("trade_date")[col].transform("median")
    return (df[col] > median_by_date).astype(int)


def run_window(dataset: pd.DataFrame, label: str, train_end: str, val_start: str, val_end: str) -> dict:
    splits = split_by_time(
        dataset,
        train_start=TRAIN_START_DATE, train_end=train_end,
        validation_start=val_start, validation_end=val_end,
        test_start=TEST_START_DATE, test_end=TEST_END_DATE,
    )
    y_train = _above_median_label(splits.train)
    y_val = _above_median_label(splits.validation)

    resolved_params = {**DEFAULT_PARAMS, **DETERMINISTIC_PARAMS}
    model = XGBClassifier(
        **resolved_params,
        eval_metric="logloss",
        early_stopping_rounds=EARLY_STOPPING_ROUNDS,
    )
    model.fit(
        splits.train[list(ALL_19)], y_train,
        eval_set=[(splits.validation[list(ALL_19)], y_val)],
        verbose=False,
    )

    proba = model.predict_proba(splits.validation[list(ALL_19)])[:, 1]
    frame = splits.validation[["trade_date", "target_return_5d"]].copy()
    frame["predicted"] = proba
    summary = summarize_ic(daily_rank_ic(frame, "predicted", "target_return_5d"))

    # Sanity metric: classification accuracy on the (balanced-by-construction)
    # binary label itself, just to confirm the model is doing something
    # non-trivial, not just to judge ranking usefulness (that's val_ic).
    preds_binary = (proba > 0.5).astype(int)
    accuracy = float((preds_binary == y_val.to_numpy()).mean())

    return {
        "window": label,
        "best_iteration": int(model.best_iteration),
        "val_ic": summary.mean_ic,
        "pct_pos": summary.pct_pos,
        "coverage": summary.coverage,
        "n_days": summary.n_days,
        "val_accuracy": accuracy,
    }


def main() -> None:
    dataset = load_dataset()
    rows = [run_window(dataset, *w) for w in WINDOWS]

    header = (
        f"{'window':<22}{'best_iter':>10}{'val_ic':>9}{'%days>0':>9}"
        f"{'coverage':>10}{'n_days':>8}{'accuracy':>10}"
    )
    print(header)
    for r in rows:
        print(
            f"{r['window']:<22}{r['best_iteration']:>10}{r['val_ic']:>9.4f}"
            f"{r['pct_pos']:>9.2%}{r['coverage']:>10.1%}{r['n_days']:>8}"
            f"{r['val_accuracy']:>10.2%}"
        )

    print("\n" + "=" * 90)
    print("vs prior rank-regression val_ic (items 32/36, same windows):")
    for r in rows:
        prior = PRIOR_RANK_REGRESSION[r["window"]]
        print(
            f"  {r['window']}: classification={r['val_ic']:+.4f}  "
            f"rank-regression(rmse-stop)={prior['rmse']:+.4f}  "
            f"rank-regression(ic-stop)={prior['ic']:+.4f}"
        )
    print("=" * 90)


if __name__ == "__main__":
    main()
