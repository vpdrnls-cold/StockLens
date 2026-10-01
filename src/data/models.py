"""Provider-independent historical market-data models."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
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


@dataclass(frozen=True)
class IndexDailyBar:
    """One validated daily bar of a market index (e.g. KOSPI).

    Prices are index points with the provider's 100x integer encoding
    already undone (``690853`` -> ``Decimal("6908.53")``).
    ka20006 ``trde_qty`` is in THOUSANDS of shares even though the spec
    says "단위: 1주": on all 597 days of 2024-04~2026-09 the top-50
    universe's own share volume alone is 46~315x the index value, which is
    impossible in single shares (CURRENT_STATUS item 58). The field name
    carries the unit, like ``trade_value_million_krw``.
    ``is_complete`` is False when the bar was retrieved during the
    trading day it belongs to (an in-progress candle, AGENTS.md 2.3).
    """

    index_code: str
    trade_date: date
    open_price: Decimal
    high_price: Decimal
    low_price: Decimal
    close_price: Decimal
    volume_thousand_shares: int
    trade_value_million_krw: int
    retrieved_at: datetime
    is_complete: bool

    def to_dict(self) -> dict[str, str | int | bool]:
        return {
            "index_code": self.index_code,
            "trade_date": self.trade_date.isoformat(),
            "open_price": str(self.open_price),
            "high_price": str(self.high_price),
            "low_price": str(self.low_price),
            "close_price": str(self.close_price),
            "volume_thousand_shares": self.volume_thousand_shares,
            "trade_value_million_krw": self.trade_value_million_krw,
            "retrieved_at": self.retrieved_at.isoformat(),
            "is_complete": self.is_complete,
        }


# Investor categories whose daily net buys must sum to zero (every share
# bought is sold by someone). Institution is represented by its eight
# sub-categories, NOT the provider's reported institution total: before
# mid-2012 that total excluded the government category, after it included
# it (verified against 005930 ka10059 history, 2026-10-01).
INSTITUTION_SUBCATEGORIES = (
    "financial_investment",
    "insurance",
    "investment_trust",
    "other_financial",
    "bank",
    "pension_fund",
    "private_equity",
    "government",
)
INVESTOR_CATEGORIES = (
    "individual",
    "foreign",
    *INSTITUTION_SUBCATEGORIES,
    "other_corporation",
    "domestic_foreigner",
)


@dataclass(frozen=True)
class InvestorFlowDay:
    """One validated day of net buying by investor category for one stock.

    All flow values are net buy amounts in million KRW (negative = net
    sell). ``balance_residual`` is the sum over ``INVESTOR_CATEGORIES``;
    a completed day balances to zero up to per-field rounding, a
    provisional intraday (가집계) day does not. ``is_complete`` combines
    that check with the retrieval-time check used for index bars.
    """

    stock_code: str
    trade_date: date
    volume: int
    trade_value_million_krw: int
    individual: int
    foreign: int
    institution_reported: int
    financial_investment: int
    insurance: int
    investment_trust: int
    other_financial: int
    bank: int
    pension_fund: int
    private_equity: int
    government: int
    other_corporation: int
    domestic_foreigner: int
    retrieved_at: datetime
    is_complete: bool

    @property
    def institution_total(self) -> int:
        """Institution net buy with a definition that is consistent over time."""
        return sum(getattr(self, name) for name in INSTITUTION_SUBCATEGORIES)

    @property
    def balance_residual(self) -> int:
        return sum(getattr(self, name) for name in INVESTOR_CATEGORIES)

    def to_dict(self) -> dict[str, str | int | bool]:
        record: dict[str, str | int | bool] = {
            "stock_code": self.stock_code,
            "trade_date": self.trade_date.isoformat(),
            "volume": self.volume,
            "trade_value_million_krw": self.trade_value_million_krw,
            "institution_reported": self.institution_reported,
        }
        record.update({name: getattr(self, name) for name in INVESTOR_CATEGORIES})
        record.update(
            {
                "retrieved_at": self.retrieved_at.isoformat(),
                "is_complete": self.is_complete,
            }
        )
        return record
