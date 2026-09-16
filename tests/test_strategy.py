from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.backtest.baseline import BaselineConfig, run_baseline_backtest
from src.features.engineering import SELECTED_FEATURES
from src.ml.strategy import make_model_score_fn, predictions_for_dataset
from src.models.predict import train_model


def _zero_cost_config() -> BaselineConfig:
    return BaselineConfig(
        lookback_days=5,
        holding_days=5,
        buy_fee=0.0,
        sell_fee=0.0,
        sell_tax=0.0,
        buy_slippage=0.0,
        sell_slippage=0.0,
    )


def _make_price_dataset() -> dict[str, pd.DataFrame]:
    dates = pd.bdate_range("2026-07-01", periods=16)
    codes = ["000660", "005380", "005930", "035420", "035720"]

    data_by_stock: dict[str, pd.DataFrame] = {}

    for code in codes:
        closes = [100.0 + i * 0.1 for i in range(len(dates))]
        data_by_stock[code] = pd.DataFrame(
            {
                "stock_code": code,
                "trade_date": dates,
                "open_price": closes,
                "close_price": closes,
            }
        )

    return data_by_stock


def test_make_model_score_fn_returns_prediction_for_key() -> None:
    predictions = pd.DataFrame(
        {
            "trade_date": pd.to_datetime(["2026-07-08", "2026-07-08"]),
            "stock_code": ["000660", "005380"],
            "predicted_return": [0.01, 0.05],
        }
    )

    score_fn = make_model_score_fn(predictions)

    universe = pd.DataFrame(
        {"trade_date": pd.to_datetime(["2026-07-01", "2026-07-08"])}
    )

    assert score_fn(universe, "005380", 1, lookback_days=5) == pytest.approx(0.05)
    assert score_fn(universe, "000660", 1, lookback_days=5) == pytest.approx(0.01)


def test_make_model_score_fn_raises_on_missing_prediction() -> None:
    predictions = pd.DataFrame(
        {
            "trade_date": pd.to_datetime(["2026-07-08"]),
            "stock_code": ["000660"],
            "predicted_return": [0.01],
        }
    )

    score_fn = make_model_score_fn(predictions)

    universe = pd.DataFrame(
        {"trade_date": pd.to_datetime(["2026-07-01", "2026-07-08"])}
    )

    with pytest.raises(KeyError):
        score_fn(universe, "005380", 1, lookback_days=5)


def test_make_model_score_fn_rejects_missing_columns() -> None:
    predictions = pd.DataFrame({"trade_date": [], "stock_code": []})

    with pytest.raises(ValueError, match="missing columns"):
        make_model_score_fn(predictions)


def test_predictions_for_dataset_shape_and_columns() -> None:
    rng = np.random.default_rng(0)
    n = 100

    train = pd.DataFrame(
        {feature: rng.normal(0, 1, n) for feature in SELECTED_FEATURES}
    )
    train["target_return_5d"] = rng.normal(0, 0.05, n)

    trained = train_model(
        train[list(SELECTED_FEATURES)],
        train["target_return_5d"],
        train[list(SELECTED_FEATURES)],
        train["target_return_5d"],
    )

    dataset = train.copy()
    dataset["trade_date"] = pd.bdate_range("2026-01-01", periods=n)
    dataset["stock_code"] = "000660"

    predictions = predictions_for_dataset(trained, dataset)

    assert list(predictions.columns) == [
        "trade_date",
        "stock_code",
        "predicted_return",
    ]
    assert len(predictions) == n


def test_model_score_fn_drives_a_different_pick_than_momentum() -> None:
    """End-to-end: wiring a model score_fn into run_baseline_backtest
    picks the stock the predictions favor, not the momentum winner."""

    data_by_stock = _make_price_dataset()

    # Every stock has identical price history (flat momentum), so the
    # momentum baseline has no real signal -- but the model score_fn
    # should still deterministically pick 005930.
    universe_dates = data_by_stock["000660"]["trade_date"]
    decision_dates = universe_dates.iloc[5::5]

    records = []
    for date in decision_dates:
        for code in data_by_stock:
            records.append(
                {
                    "trade_date": date,
                    "stock_code": code,
                    "predicted_return": 0.05 if code == "005930" else 0.0,
                }
            )

    predictions = pd.DataFrame(records)
    score_fn = make_model_score_fn(predictions)

    trades = run_baseline_backtest(
        data_by_stock, config=_zero_cost_config(), score_fn=score_fn
    )

    assert trades
    assert all(trade.stock_code == "005930" for trade in trades)
