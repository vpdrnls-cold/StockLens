"""Target construction for StockLens."""

from __future__ import annotations

from collections.abc import Sequence

import pandas as pd

from src.data.models import DailyBar


TARGET_COLUMN = "target_return_5d"
TARGET_HORIZON = 5


def build_target(
    bars: Sequence[DailyBar],
    *,
    horizon: int = TARGET_HORIZON,
) -> pd.DataFrame:
    """Build the forward return target for the requested horizon.

    The target at time t is the simple return from the close at t
    to the close at t + horizon.
    """
    if not bars:
        raise ValueError("bars must not be empty.")

    if horizon <= 0:
        raise ValueError("horizon must be a positive integer.")

    stock_codes = {bar.stock_code for bar in bars}
    if len(stock_codes) != 1:
        raise ValueError("All bars must belong to the same stock.")

    dates = [bar.trade_date for bar in bars]

    if len(dates) != len(set(dates)):
        raise ValueError("bars contains duplicate trade dates.")

    df = pd.DataFrame(
        {
            "stock_code": [bar.stock_code for bar in bars],
            "trade_date": [bar.trade_date for bar in bars],
            "close_price": [bar.close_price for bar in bars],
        }
    )

    df = df.sort_values("trade_date").reset_index(drop=True)

    close = df["close_price"].astype(float)

    if (close <= 0).any():
        raise ValueError("close_price must be positive.")

    df[TARGET_COLUMN] = (
        close.shift(-horizon) / close - 1.0
    )

    return df[
        [
            "stock_code",
            "trade_date",
            TARGET_COLUMN,
        ]
    ]