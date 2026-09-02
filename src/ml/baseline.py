"""Rule-based baselines for StockLens."""

from __future__ import annotations

import pandas as pd

#from src.features.engineering import FEATURE_COLUMNS


MOMENTUM_FEATURE = "return_5d"


def select_momentum_stock(
    data: pd.DataFrame,
) -> str:
    """Select the stock with the highest recent 5-day return."""

    required_columns = {
        "stock_code",
        MOMENTUM_FEATURE,
    }

    missing = required_columns - set(data.columns)

    if missing:
        raise ValueError(
            f"Missing required columns: {sorted(missing)}"
        )

    if data.empty:
        raise ValueError("data must not be empty.")

    ranked = data.sort_values(
        MOMENTUM_FEATURE,
        ascending=False,
    )

    return str(ranked.iloc[0]["stock_code"])