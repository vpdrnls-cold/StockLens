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


def train_model(
    X_train: pd.DataFrame,
    y_train: pd.Series,
    X_val: pd.DataFrame,
    y_val: pd.Series,
    *,
    feature_columns: tuple[str, ...] = SELECTED_FEATURES,
    params: dict | None = None,
) -> TrainedModel:
    """Train the daily XGBoost model with early stopping on validation.

    ``X_val``/``y_val`` are used only for early stopping (to pick the
    number of boosting rounds) -- never for fitting tree splits. This
    is not the same as touching the test set: validation is exactly
    the split Feature Selection already used for model comparison.
    """
    _validate_columns(X_train, feature_columns, name="X_train")
    _validate_columns(X_val, feature_columns, name="X_val")

    if y_train.empty or y_val.empty:
        raise ValueError("y_train and y_val must not be empty.")

    resolved_params = {**DEFAULT_PARAMS, **(params or {})}

    model = XGBRegressor(
        **resolved_params,
        eval_metric="rmse",
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
