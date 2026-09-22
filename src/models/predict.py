"""Daily return-prediction model for StockLens (Phase G).

Trains and serves predictions for ``target_return_5d`` using the
Phase F-selected feature set (``src.features.engineering.SELECTED_FEATURES``).

Per AGENTS.md section 31, this is the *daily* model -- a building
block / medium-horizon signal for the eventual integrated
recommendation system, not a standalone trading system. Predicting a
return is not the same as recommending a stock (AGENTS.md section 10);
this module only produces the prediction/signal layer.

Early stopping is used deliberately, not as a default habit: Phase F's
Embedded-track experiments showed a fixed ``n_estimators`` overfits
this noisy target, while early stopping against a real (never-trained-
on) validation set reliably improves over the mean-predictor baseline.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from xgboost import XGBRegressor

from src.features.engineering import SELECTED_FEATURES
from src.ml.cross_section import daily_rank_ic, summarize_ic

DEFAULT_PARAMS: dict = {
    "max_depth": 2,
    "learning_rate": 0.03,
    "subsample": 1.0,
    "colsample_bytree": 1.0,
    "n_estimators": 1000,
    "random_state": 42,
    "n_jobs": -1,
}

EARLY_STOPPING_ROUNDS = 30


@dataclass
class TrainedModel:
    """A fitted model plus the exact feature columns/order it expects."""

    model: XGBRegressor
    feature_columns: tuple[str, ...]
    best_iteration: int


def _make_ic_eval_metric(trade_dates: np.ndarray, min_stocks: int = 3):
    """Build a custom XGBoost eval metric: negative mean cross-sectional rank IC.

    Why this exists (CURRENT_STATUS.md items 18/20/24/30-33): the model
    is fit to raw ``target_return_5d`` with RMSE, but most of that
    target's variance is a market-wide common component shared by every
    stock on a given date -- unlearnable from stock-level features, and
    it swamps the much smaller cross-sectional signal the model is
    actually meant to learn (which stock beats the others). RMSE-based
    early stopping plateaus almost immediately in that situation
    (``best_iteration`` of 0-8 in some walk-forward windows) even when
    the cross-sectional ranking is still improving round over round.
    Early-stopping on the same metric the strategy is actually judged
    by (cross-sectional rank IC, AGENTS.md section 22) instead directly
    tests whether that plateau is a real ceiling or an artifact of the
    wrong stopping criterion.

    Returns a plain float, not the historical ``(name, value)`` tuple
    -- this was verified empirically against the installed XGBoost
    version rather than assumed (see AGENTS.md section 25's
    reproducibility note for why "assumed from memory" has bitten this
    project before): a callable ``eval_metric`` here must return a
    single float, named after the callable's own ``__name__``, and
    smaller is always better, matching every built-in metric's
    convention (including "rmse"). IC is therefore negated: a model
    that improves cross-sectional rank IC drives this metric down.

    Undefined-IC days (a day with a near-constant prediction, e.g. an
    under-trained model in early rounds) count as IC=0 via
    ``summarize_ic``, the same coverage-aware convention item 30
    established for reporting IC elsewhere -- otherwise a model that
    is only confidently ranking a handful of days could look
    artificially good.
    """

    def ic_eval_metric(y_true: np.ndarray, y_pred: np.ndarray) -> float:
        frame = pd.DataFrame(
            {
                "trade_date": trade_dates,
                "score": np.asarray(y_pred),
                "target_return_5d": np.asarray(y_true),
            }
        )
        summary = summarize_ic(
            daily_rank_ic(
                frame, "score", "target_return_5d", min_stocks=min_stocks
            )
        )
        if summary.n_days == 0:
            return 0.0
        return -summary.mean_ic

    return ic_eval_metric


def train_model(
    X_train: pd.DataFrame,
    y_train: pd.Series,
    X_val: pd.DataFrame,
    y_val: pd.Series,
    *,
    feature_columns: tuple[str, ...] = SELECTED_FEATURES,
    params: dict | None = None,
    early_stopping_metric: str = "rmse",
) -> TrainedModel:
    """Train the daily XGBoost model with early stopping on validation.

    ``X_val``/``y_val`` are used only for early stopping (to pick the
    number of boosting rounds) -- never for fitting tree splits. This
    is not the same as touching the test set: validation is exactly
    the split Feature Selection already used for model comparison.

    ``early_stopping_metric``:
        ``"rmse"`` (default): unchanged behavior, identical to every
        existing caller of this function.

        ``"ic"``: stop on cross-sectional rank IC instead (see
        ``_make_ic_eval_metric``). Requires ``X_val`` to include a
        ``trade_date`` column -- pass the full validation frame (e.g.
        ``splits.validation``), not the feature-only output of
        ``src.feature_selection.data_loading.load_split``, which
        strips it.
    """
    _validate_columns(X_train, feature_columns, name="X_train")
    _validate_columns(X_val, feature_columns, name="X_val")

    if y_train.empty or y_val.empty:
        raise ValueError("y_train and y_val must not be empty.")

    if early_stopping_metric == "rmse":
        eval_metric = "rmse"
    elif early_stopping_metric == "ic":
        if "trade_date" not in X_val.columns:
            raise ValueError(
                "early_stopping_metric='ic' requires X_val to include a "
                "'trade_date' column (pass the full validation frame, "
                "not a feature-only DataFrame)."
            )
        eval_metric = _make_ic_eval_metric(X_val["trade_date"].to_numpy())
    else:
        raise ValueError(
            "early_stopping_metric must be 'rmse' or 'ic', got "
            f"{early_stopping_metric!r}."
        )

    resolved_params = {**DEFAULT_PARAMS, **(params or {})}

    model = XGBRegressor(
        **resolved_params,
        eval_metric=eval_metric,
        early_stopping_rounds=EARLY_STOPPING_ROUNDS,
    )

    model.fit(
        X_train[list(feature_columns)],
        y_train,
        eval_set=[(X_val[list(feature_columns)], y_val)],
        verbose=False,
    )

    return TrainedModel(
        model=model,
        feature_columns=tuple(feature_columns),
        best_iteration=int(model.best_iteration),
    )


def predict(trained: TrainedModel, X: pd.DataFrame) -> np.ndarray:
    """Predict ``target_return_5d`` for new rows.

    ``X`` may contain extra columns (e.g. the full 25-feature matrix);
    only ``trained.feature_columns`` are used, in the order the model
    was fit with.
    """
    _validate_columns(X, trained.feature_columns, name="X")

    return trained.model.predict(X[list(trained.feature_columns)])


def feature_importance(trained: TrainedModel) -> pd.DataFrame:
    """Return gain-based feature importance, sorted descending.

    For the explanation layer (AGENTS.md section 24): every
    recommendation should eventually be traceable to actual
    calculations, not just a bare prediction number.
    """
    importances = trained.model.feature_importances_

    return (
        pd.DataFrame(
            {
                "feature": trained.feature_columns,
                "importance": importances,
            }
        )
        .sort_values("importance", ascending=False)
        .reset_index(drop=True)
    )


def _validate_columns(
    data: pd.DataFrame,
    feature_columns: tuple[str, ...],
    *,
    name: str,
) -> None:
    if data.empty:
        raise ValueError(f"{name} must not be empty.")

    missing = set(feature_columns) - set(data.columns)

    if missing:
        raise ValueError(
            f"{name} is missing required feature columns: {sorted(missing)}"
        )
