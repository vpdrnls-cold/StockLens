"""ML-scored strategy for the canonical backtest engine.

Builds a ``score_fn`` compatible with
``src.backtest.baseline.run_baseline_backtest`` that scores each stock
by the daily model's *predicted* target_return_5d, instead of past
5-day momentum. The trade-execution engine itself (T+1 open entry,
T+holding close exit, fees, tax, slippage) is unchanged and shared
with the rule-based baseline -- only the stock-picking rule differs,
so the two strategies' performance is directly comparable.
"""

from __future__ import annotations

import pandas as pd

from src.models.predict import TrainedModel, predict


def make_model_score_fn(
    predictions: pd.DataFrame,
) -> "callable":
    """Build a score_fn backed by precomputed model predictions.

    ``predictions`` must have columns ``trade_date``, ``stock_code``,
    ``predicted_return``, with one row per (trade_date, stock_code)
    that will ever be scored during the backtest.
    """
    required = {"trade_date", "stock_code", "predicted_return"}
    missing = required - set(predictions.columns)
    if missing:
        raise ValueError(f"predictions is missing columns: {sorted(missing)}")

    lookup = {
        (row.trade_date, row.stock_code): row.predicted_return
        for row in predictions.itertuples(index=False)
    }

    def score_fn(
        universe: pd.DataFrame,
        stock_code: str,
        decision_index: int,
        lookback_days: int,
    ) -> float:
        decision_date = universe.iloc[decision_index]["trade_date"]

        key = (decision_date, stock_code)

        if key not in lookup:
            raise KeyError(
                f"No prediction available for {stock_code} on "
                f"{decision_date.date()}."
            )

        return lookup[key]

    return score_fn


def predictions_for_dataset(
    trained: TrainedModel,
    dataset: pd.DataFrame,
) -> pd.DataFrame:
    """Predict target_return_5d for every row of a tidy feature dataset.

    ``dataset`` must contain ``trade_date``, ``stock_code``, and every
    column in ``trained.feature_columns``.
    """
    predicted_return = predict(trained, dataset)

    result = dataset[["trade_date", "stock_code"]].copy()
    result["trade_date"] = pd.to_datetime(result["trade_date"])
    result["predicted_return"] = predicted_return

    return result
