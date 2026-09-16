from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.features.engineering import SELECTED_FEATURES
from src.models.predict import TrainedModel, feature_importance, predict, train_model


def _make_learnable_dataset(n: int = 400, seed: int = 0) -> pd.DataFrame:
    """Synthetic data where the target is a noisy linear function of
    price_to_sma_5 and volatility_20, and the other 3 selected
    features are pure noise. Learnable enough that a real model
    should clearly beat a mean-only baseline, without requiring real
    market data.
    """
    rng = np.random.default_rng(seed)

    price_to_sma_5 = rng.normal(0, 1, n)
    price_to_sma_60 = rng.normal(0, 1, n)
    macd_hist_pct = rng.normal(0, 1, n)
    volatility_20 = rng.normal(0, 1, n)
    atr_pct = rng.normal(0, 1, n)

    noise = rng.normal(0, 0.05, n)
    target = 0.02 * price_to_sma_5 - 0.015 * volatility_20 + noise

    return pd.DataFrame(
        {
            "price_to_sma_5": price_to_sma_5,
            "price_to_sma_60": price_to_sma_60,
            "macd_hist_pct": macd_hist_pct,
            "volatility_20": volatility_20,
            "atr_pct": atr_pct,
            "target_return_5d": target,
        }
    )


def _split(df: pd.DataFrame, train_frac: float = 0.7):
    cut = int(len(df) * train_frac)
    train, val = df.iloc[:cut], df.iloc[cut:]

    X_train = train[list(SELECTED_FEATURES)]
    y_train = train["target_return_5d"]
    X_val = val[list(SELECTED_FEATURES)]
    y_val = val["target_return_5d"]

    return X_train, y_train, X_val, y_val


def test_train_model_returns_trained_model_with_expected_columns() -> None:
    X_train, y_train, X_val, y_val = _split(_make_learnable_dataset())

    trained = train_model(X_train, y_train, X_val, y_val)

    assert isinstance(trained, TrainedModel)
    assert trained.feature_columns == tuple(SELECTED_FEATURES)
    assert trained.best_iteration >= 0


def test_predict_beats_mean_baseline_on_learnable_signal() -> None:
    X_train, y_train, X_val, y_val = _split(_make_learnable_dataset())

    trained = train_model(X_train, y_train, X_val, y_val)
    predictions = predict(trained, X_val)

    model_rmse = float(np.sqrt(np.mean((y_val.to_numpy() - predictions) ** 2)))

    mean_pred = np.full_like(y_val.to_numpy(), y_train.mean())
    baseline_rmse = float(np.sqrt(np.mean((y_val.to_numpy() - mean_pred) ** 2)))

    assert model_rmse < baseline_rmse


def test_predict_output_shape_matches_input_rows() -> None:
    X_train, y_train, X_val, y_val = _split(_make_learnable_dataset())

    trained = train_model(X_train, y_train, X_val, y_val)
    predictions = predict(trained, X_val)

    assert predictions.shape == (len(X_val),)


def test_predict_ignores_extra_columns() -> None:
    X_train, y_train, X_val, y_val = _split(_make_learnable_dataset())

    trained = train_model(X_train, y_train, X_val, y_val)

    X_val_extra = X_val.copy()
    X_val_extra["some_unrelated_column"] = 0.0

    predictions = predict(trained, X_val_extra)

    assert predictions.shape == (len(X_val),)


def test_feature_importance_covers_every_selected_feature() -> None:
    X_train, y_train, X_val, y_val = _split(_make_learnable_dataset())

    trained = train_model(X_train, y_train, X_val, y_val)
    importances = feature_importance(trained)

    assert set(importances["feature"]) == set(SELECTED_FEATURES)
    assert importances["importance"].is_monotonic_decreasing


def test_train_model_rejects_missing_feature_columns() -> None:
    X_train, y_train, X_val, y_val = _split(_make_learnable_dataset())

    with pytest.raises(ValueError, match="missing required feature columns"):
        train_model(
            X_train.drop(columns=["price_to_sma_5"]),
            y_train,
            X_val,
            y_val,
        )


def test_predict_rejects_missing_feature_columns() -> None:
    X_train, y_train, X_val, y_val = _split(_make_learnable_dataset())

    trained = train_model(X_train, y_train, X_val, y_val)

    with pytest.raises(ValueError, match="missing required feature columns"):
        predict(trained, X_val.drop(columns=["atr_pct"]))


def test_train_model_rejects_empty_data() -> None:
    X_train, y_train, X_val, y_val = _split(_make_learnable_dataset())

    with pytest.raises(ValueError, match="must not be empty"):
        train_model(X_train.iloc[0:0], y_train.iloc[0:0], X_val, y_val)


def test_train_model_respects_custom_feature_subset() -> None:
    X_train, y_train, X_val, y_val = _split(_make_learnable_dataset())

    subset = ("price_to_sma_5", "volatility_20")

    trained = train_model(
        X_train, y_train, X_val, y_val, feature_columns=subset
    )

    assert trained.feature_columns == subset

    predictions = predict(trained, X_val)
    assert predictions.shape == (len(X_val),)
