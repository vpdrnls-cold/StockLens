"""Feature engineering pipeline."""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import pandas as pd

from src.data.models import DailyBar

#features 25개 
FEATURE_COLUMNS = (
    "return_1d",
    "return_5d",
    "return_10d",
    "return_20d",
    "intraday_return",
    "high_low_range",
    "gap",
    "sma_5",
    "sma_20",
    "sma_60",
    "price_to_sma_5",
    "price_to_sma_20",
    "price_to_sma_60",
    "rsi_14",
    "roc_10",
    "roc_20",
    "macd",
    "macd_signal",
    "macd_hist",
    "volatility_5",
    "volatility_20",
    "atr_14",
    "volume_change_1d",
    "volume_sma_20",
    "volume_ratio_20",
)


def build_features(bars: Sequence[DailyBar]) -> pd.DataFrame:
    """Build the first-pass 25 technical features from normalized daily bars."""
    if not bars:
        raise ValueError("bars must not be empty.")

    stock_codes = {bar.stock_code for bar in bars}
    if len(stock_codes) != 1:
        raise ValueError("All bars must belong to the same stock.")

    dates = [bar.trade_date for bar in bars]
    if len(dates) != len(set(dates)):
        raise ValueError("bars contains duplicate trade dates.")

    df = pd.DataFrame(
        {
            "trade_date": [bar.trade_date for bar in bars],
            "open_price": [bar.open_price for bar in bars],
            "high_price": [bar.high_price for bar in bars],
            "low_price": [bar.low_price for bar in bars],
            "close_price": [bar.close_price for bar in bars],
            "volume": [bar.volume for bar in bars],
        }
    )

    df = df.sort_values("trade_date").reset_index(drop=True)

    close = df["close_price"].astype(float)
    open_price = df["open_price"].astype(float)
    high = df["high_price"].astype(float)
    low = df["low_price"].astype(float)
    volume = df["volume"].astype(float)

    if (close <= 0).any():
        raise ValueError("close_price must be positive.")
    if (open_price <= 0).any():
        raise ValueError("open_price must be positive.")
    if (high <= 0).any() or (low <= 0).any():
        raise ValueError("high_price and low_price must be positive.")
    if (volume < 0).any():
        raise ValueError("volume must not be negative.")

    features = pd.DataFrame(index=df.index)

    # ---------------------------------------------------------
    # 1. Price / Return
    # ---------------------------------------------------------

    features["return_1d"] = close.pct_change(1)
    features["return_5d"] = close.pct_change(5)
    features["return_10d"] = close.pct_change(10)
    features["return_20d"] = close.pct_change(20)

    features["intraday_return"] = close / open_price - 1.0
    features["high_low_range"] = high / low - 1.0

    previous_close = close.shift(1)
    features["gap"] = open_price / previous_close - 1.0

    # ---------------------------------------------------------
    # 2. Trend
    # ---------------------------------------------------------

    features["sma_5"] = close.rolling(
        window=5,
        min_periods=5,
    ).mean()

    features["sma_20"] = close.rolling(
        window=20,
        min_periods=20,
    ).mean()

    features["sma_60"] = close.rolling(
        window=60,
        min_periods=60,
    ).mean()

    features["price_to_sma_5"] = close / features["sma_5"] - 1.0
    features["price_to_sma_20"] = close / features["sma_20"] - 1.0
    features["price_to_sma_60"] = close / features["sma_60"] - 1.0

    # ---------------------------------------------------------
    # 3. Momentum
    # ---------------------------------------------------------

    delta = close.diff()

    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)

    # Wilder-style RSI
    avg_gain = gain.ewm(
        alpha=1 / 14,
        adjust=False,
        min_periods=14,
    ).mean()

    avg_loss = loss.ewm(
        alpha=1 / 14,
        adjust=False,
        min_periods=14,
    ).mean()

    rs = avg_gain / avg_loss.replace(0.0, np.nan)

    features["rsi_14"] = 100.0 - (100.0 / (1.0 + rs))

    features.loc[
        (avg_loss == 0) & (avg_gain > 0),
        "rsi_14",
    ] = 100.0

    features.loc[
        (avg_gain == 0) & (avg_loss > 0),
        "rsi_14",
    ] = 0.0

    features["roc_10"] = close.pct_change(10)
    features["roc_20"] = close.pct_change(20)

    # MACD = EMA(12) - EMA(26)
    ema_12 = close.ewm(
        span=12,
        adjust=False,
        min_periods=12,
    ).mean()

    ema_26 = close.ewm(
        span=26,
        adjust=False,
        min_periods=26,
    ).mean()

    features["macd"] = ema_12 - ema_26

    features["macd_signal"] = features["macd"].ewm(
        span=9,
        adjust=False,
        min_periods=9,
    ).mean()

    features["macd_hist"] = (
        features["macd"] - features["macd_signal"]
    )

    # ---------------------------------------------------------
    # 4. Volatility
    # ---------------------------------------------------------

    features["volatility_5"] = features["return_1d"].rolling(
        window=5,
        min_periods=5,
    ).std()

    features["volatility_20"] = features["return_1d"].rolling(
        window=20,
        min_periods=20,
    ).std()

    # True Range
    true_range = pd.concat(
        [
            high - low,
            (high - previous_close).abs(),
            (low - previous_close).abs(),
        ],
        axis=1,
    ).max(axis=1)

    # Wilder-style ATR
    features["atr_14"] = true_range.ewm(
        alpha=1 / 14,
        adjust=False,
        min_periods=14,
    ).mean()

    # ---------------------------------------------------------
    # 5. Volume
    # ---------------------------------------------------------

    features["volume_change_1d"] = volume.pct_change(1)

    features["volume_sma_20"] = volume.rolling(
        window=20,
        min_periods=20,
    ).mean()

    features["volume_ratio_20"] = (
        volume / features["volume_sma_20"]
    )

    return pd.concat(
        [
            df[["trade_date"]],
            features.loc[:, FEATURE_COLUMNS],
        ],
        axis=1,
    )