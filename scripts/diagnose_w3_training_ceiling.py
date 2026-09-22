"""Pre-Phase-H checklist item 4 (final confirmatory experiment): does letting
W3 train all the way to the production n_estimators cap, with early stopping
turned off entirely, ever reach a validation cross-sectional rank IC that is
materially better than what early stopping (rmse- or ic-based, see
``scripts/compare_early_stopping_metric.py``) already found?

Background (CURRENT_STATUS.md items 32/33/35/36): W3 (top50, val
2020-2023H1) consistently trains very few rounds (best_iteration 4-55
depending on target/stopping metric) and its validation IC stays low
(0.0024-0.0154) compared to W1/W2. Item 36 already showed IC-based early
stopping doesn't help much here specifically (it stops even earlier than
RMSE-based stopping and still gets a similar-or-better IC) -- consistent
with "there just isn't much more learnable signal in this window" rather
than "early stopping gave up too soon". This script tests that directly:
train with n_estimators=1000 (the project's own production cap, from
``src.models.predict.DEFAULT_PARAMS`` -- not a new number picked for this
experiment) and no early stopping at all, then look at the validation IC
at every round of that full run.

IMPORTANT IMPLEMENTATION NOTE: an earlier version of this script tried to
read the round-by-round IC off XGBoost's own ``model.evals_result()``,
using a custom ``eval_metric`` callable (the same one
``src.models.predict._make_ic_eval_metric`` builds for IC-based early
stopping). That produced clearly wrong numbers (e.g. implying IC around
-0.32 at round 0 for a toy dataset where the actual round-0 model's IC,
verified independently via ``model.predict(..., iteration_range=(0, 1))``
+ ``daily_rank_ic``, is +0.10). XGBoost's custom-eval-metric callback
appears to receive different predictions internally when
``early_stopping_rounds`` is not driving a stop, at least in the installed
version (3.2.0) -- this was NOT a sign-convention bug in
``_make_ic_eval_metric`` itself (that function is independently verified
correct via the existing ``tests/test_predict.py`` IC early-stopping
tests, which DO pass early_stopping_rounds). Rather than depend on that
internal callback at all, this script trains once with no eval_metric,
then computes IC at each checkpoint round itself by calling
``model.predict(X_val, iteration_range=(0, k))`` and running the same
verified ``daily_rank_ic``/``summarize_ic`` functions used everywhere else
in this project. This is slower (one predict per checkpoint) but
trustworthy.

What this experiment can and cannot conclude: the curve's best round is an
*oracle* (chosen with knowledge of the entire training run's performance
against this exact validation set). If the oracle is not much better than
what real early stopping already achieves, that's strong evidence the
ceiling is genuinely low here (not a stopping-rule artifact). If the
oracle is much better, that does NOT mean "just train longer" is a safe
fix -- picking the single best round out of many by looking at validation
performance is itself a form of overfitting to validation and would need
separate out-of-sample validation before being adopted. No decision is
made directly from this script's output; it only informs the item 4
root-cause conclusion.

Only train/validation dates are used -- the test period is never touched
(this script doesn't import src.eval.test_lock at all).

    STOCKLENS_UNIVERSE=top50 PYTHONPATH=. python3 scripts/diagnose_w3_training_ceiling.py
"""

from __future__ import annotations

import time

import numpy as np
import pandas as pd
from xgboost import XGBRegressor

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
from src.models.predict import DEFAULT_PARAMS

RAW_SCALE_FEATURES = {
    "sma_5", "sma_20", "sma_60", "macd", "macd_signal", "macd_hist",
    "atr_14", "volume_sma_20",
}
ALL_19 = tuple(f for f in FEATURE_COLUMNS if f not in RAW_SCALE_FEATURES)
DETERMINISTIC_PARAMS = {"n_jobs": 1, "tree_method": "exact"}

# W3 only -- W1/W2 already train well past double digits of rounds under
# ordinary early stopping, so they aren't under suspicion of stopping too
# early (item 36).
WINDOW = ("W3 val 2020-2023H1", "2019-12-31", "2020-01-01", "2023-06-30")

TARGETS = {
    "raw": lambda df: df["target_return_5d"],
    "rank": lambda df: rank_by_date(df, "target_return_5d"),
}

# Checkpoints to evaluate: dense where it matters (the previously observed
# best_iteration values are all under 60), sparse afterward just to confirm
# no late resurgence all the way to the production n_estimators cap.
CHECKPOINTS = list(range(1, 101)) + list(range(125, 1001, 25))

# Previously observed early-stopped results (item 36), for direct
# side-by-side comparison. Not recomputed here -- copied from
# CURRENT_STATUS.md item 36's table.
PRIOR_RESULTS = {
    "raw": {"rmse": (55, 0.0024), "ic": (48, 0.0046)},
    "rank": {"rmse": (8, 0.0130), "ic": (4, 0.0154)},
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


def _val_ic_at(model: XGBRegressor, X_val: pd.DataFrame, n_trees: int) -> float:
    """Cross-sectional rank IC of predictions using only the first
    ``n_trees`` boosting rounds, always measured against the raw target
    (Spearman IC is invariant to a same-date monotonic transform of the
    target, so this is identical whether the model was trained on raw or
    rank -- matches the convention in compare_early_stopping_metric.py).
    """
    preds = model.predict(X_val[list(ALL_19)], iteration_range=(0, n_trees))
    frame = X_val[["trade_date", "target_return_5d"]].copy()
    frame["predicted"] = preds
    return summarize_ic(daily_rank_ic(frame, "predicted", "target_return_5d")).mean_ic


def run_full_curve(splits, target_name: str) -> dict:
    target_fn = TARGETS[target_name]
    X_train, y_train = splits.train, target_fn(splits.train)
    X_val = splits.validation

    resolved_params = {**DEFAULT_PARAMS, **DETERMINISTIC_PARAMS}
    model = XGBRegressor(**resolved_params)  # no eval_set/eval_metric/early stopping at all

    t0 = time.time()
    model.fit(X_train[list(ALL_19)], y_train, verbose=False)
    fit_elapsed = time.time() - t0

    t1 = time.time()
    curve = {k: _val_ic_at(model, X_val, k) for k in CHECKPOINTS}
    eval_elapsed = time.time() - t1

    oracle_round = max(curve, key=curve.get)
    oracle_ic = curve[oracle_round]

    return {
        "target": target_name,
        "curve": curve,
        "oracle_round": oracle_round,
        "oracle_ic": oracle_ic,
        "fit_elapsed": fit_elapsed,
        "eval_elapsed": eval_elapsed,
    }


def _print_curve_samples(curve: dict) -> None:
    checkpoints = sorted(
        set([1, 4, 8, 25, 48, 55, 100, 200, 300, 500, 750, 1000]) & set(curve)
    )
    print("  round-by-round samples:")
    for c in checkpoints:
        print(f"    round {c:>4}: ic={curve[c]:+.4f}")


def main() -> None:
    label, train_end, val_start, val_end = WINDOW
    dataset = load_dataset()
    splits = split_by_time(
        dataset,
        train_start=TRAIN_START_DATE, train_end=train_end,
        validation_start=val_start, validation_end=val_end,
        test_start=TEST_START_DATE, test_end=TEST_END_DATE,
    )
    print(f"{label}: train n={len(splits.train)}  val n={len(splits.validation)}")

    for target_name in TARGETS:
        print("\n" + "=" * 80)
        print(f"target={target_name}")
        print("=" * 80)
        result = run_full_curve(splits, target_name)
        print(
            f"fit 1000 rounds (no early stopping) in {result['fit_elapsed']:.1f}s, "
            f"evaluated {len(CHECKPOINTS)} checkpoints in {result['eval_elapsed']:.1f}s"
        )
        print(
            f"oracle best round: {result['oracle_round']} "
            f"(val_ic={result['oracle_ic']:+.4f})"
        )
        prior = PRIOR_RESULTS[target_name]
        for stop_on, (best_iter, val_ic) in prior.items():
            gap = result["oracle_ic"] - val_ic
            print(
                f"  vs early-stopped ({stop_on}): "
                f"best_iteration={best_iter}, val_ic={val_ic:+.4f}  "
                f"(oracle - this = {gap:+.4f})"
            )
        _print_curve_samples(result["curve"])

    print("\n" + "=" * 80)
    print(
        "How to read it: if the oracle val_ic is only marginally better "
        "than what rmse-/ic-based early stopping already found (say, "
        "within a few thousandths of IC), that confirms the low "
        "best_iteration in W3 reflects a genuinely shallow ceiling on "
        "learnable cross-sectional signal in this window, not a stopping "
        "rule that gave up too soon. A much higher oracle value would mean "
        "there IS more learnable signal later in training that current "
        "early stopping (either metric) is missing -- but note the oracle "
        "itself is not a deployable stopping rule (see module docstring)."
    )
    print("=" * 80)


if __name__ == "__main__":
    main()
