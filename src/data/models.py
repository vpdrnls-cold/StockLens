"""Provider-independent historical market-data models."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True)
class DailyBar:
    """One validated daily price and trading-activity observation."""

    stock_code: str
    trade_date: date
    open_price: int
    high_price: int
    low_price: int
    close_price: int
    volume: int
    trade_value_million_krw: int
    previous_close_change: int
    previous_close_change_sign: int
    turnover_rate: Decimal

    def to_dict(self) -> dict[str, str | int]:
        """Serialize with standard StockLens field names for JSON storage."""
        return {
            "stock_code": self.stock_code,
            "trade_date": self.trade_date.isoformat(),
            "open_price": self.open_price,
            "high_price": self.high_price,
            "low_price": self.low_price,
            "close_price": self.close_price,
            "volume": self.volume,
            "trade_value_million_krw": self.trade_value_million_krw,
            "previous_close_change": self.previous_close_change,
            "previous_close_change_sign": self.previous_close_change_sign,
            "turnover_rate": str(self.turnover_rate),
        }
