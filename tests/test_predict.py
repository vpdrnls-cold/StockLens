from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.features.engineering import SELECTED_FEATURES
from src.models.predict import TrainedModel, feature_importance, predict, train_model


def _make_learnable_dataset(n: int = 400, seed: int = 0) -> pd.DataFrame:
    """Synthetic data where the target is a noisy linear function of
    price_to_sma_5 and volatility_20, and every other feature in
    SELECTED_FEATURES is pure noise. Learnable enough that a real model
    should clearly beat a mean-only baseline, without requiring real
    market data.

    Builds one noise column per current SELECTED_FEATURES entry (rather
    than hardcoding a fixed handful of column names) so this test stays
    valid regardless of how many features are currently selected.
    """
    rng = np.random.default_rng(seed)

    data = {
        feature: rng.normal(0, 1, n) for feature in SELECTED_FEATURES
    }

    noise = rng.normal(0, 0.05, n)
    target = 0.02 * data["price_to_sma_5"] - 0.015 * data["volatility_20"] + noise

    data["target_return_5d"] = target

    return pd.DataFrame(data)


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


def _make_cross_sectional_dataset(
    n_dates: int = 200, n_stocks: int = 10, seed: int = 0, shock_std: float = 0.3
) -> pd.DataFrame:
    """Cross-sectional data shaped like the real problem diagnosed in
    CURRENT_STATUS.md items 30-32: on each date, every stock shares a
    large common shock unrelated to any feature (unlearnable), plus a
    much smaller but genuinely learnable cross-sectional signal from
    ``price_to_sma_5``. RMSE is dominated by the common shock (it swamps
    small round-over-round improvements in the cross-sectional signal),
    while IC only looks at within-date ranking, where the common shock
    cancels out exactly because it is added equally to every stock on
    the date.
    """
    rng = np.random.default_rng(seed)

    dates = pd.date_range("2020-01-01", periods=n_dates, freq="B")
    rows = []
    for date in dates:
        common_shock = rng.normal(0, shock_std)
        signal = rng.normal(0, 1, n_stocks)
        noise_features = {
            feature: rng.normal(0, 1, n_stocks)
            for feature in SELECTED_FEATURES
            if feature != "price_to_sma_5"
        }
        target = common_shock + 0.01 * signal + rng.normal(0, 0.002, n_stocks)
        for i in range(n_stocks):
            row = {
                "trade_date": date,
                "stock_code": f"S{i}",
                "price_to_sma_5": signal[i],
                "target_return_5d": target[i],
            }
            for feature, values in noise_features.items():
                row[feature] = values[i]
            rows.append(row)

    return pd.DataFrame(rows)


def test_ic_early_stopping_requires_trade_date_column() -> None:
    X_train, y_train, X_val, y_val = _split(_make_learnable_dataset())

    with pytest.raises(ValueError, match="trade_date"):
        train_model(
            X_train, y_train, X_val, y_val, early_stopping_metric="ic"
        )


def test_train_model_rejects_unknown_early_stopping_metric() -> None:
    X_train, y_train, X_val, y_val = _split(_make_learnable_dataset())

    with pytest.raises(ValueError, match="early_stopping_metric"):
        train_model(
            X_train, y_train, X_val, y_val, early_stopping_metric="mae"
        )


def test_ic_early_stopping_achieves_at_least_as_good_validation_ic() -> None:
    from src.ml.cross_section import daily_rank_ic, summarize_ic

    df = _make_cross_sectional_dataset()
    cut = int(df["trade_date"].nunique() * 0.7)
    cutoff_date = df["trade_date"].unique()[cut]
    train = df[df["trade_date"] < cutoff_date]
    val = df[df["trade_date"] >= cutoff_date]

    rmse_model = train_model(
        train, train["target_return_5d"], val, val["target_return_5d"],
        early_stopping_metric="rmse",
    )
    ic_model = train_model(
        train, train["target_return_5d"], val, val["target_return_5d"],
        early_stopping_metric="ic",
    )

    def val_ic(trained) -> float:
        preds = predict(trained, val)
        frame = val.copy()
        frame["predicted"] = preds
        return summarize_ic(
            daily_rank_ic(frame, "predicted", "target_return_5d")
        ).mean_ic

    rmse_val_ic = val_ic(rmse_model)
    ic_val_ic = val_ic(ic_model)

    # best_iteration is not asserted here: per-round IC on a few hundred
    # cross-sectional dates is itself noisy, so IC-based early stopping
    # can legitimately stop earlier OR later than RMSE-based stopping
    # depending on the run. What must hold is the actual point of this
    # feature -- the model IC-based stopping actually lands on performs
    # at least as well, out of sample, on the metric that matters
    # (cross-sectional rank IC), which RMSE-based stopping was never
    # optimizing for in the first place.
    assert ic_val_ic >= rmse_val_ic - 1e-9
