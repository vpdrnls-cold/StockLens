"""Data quality audit (CURRENT_STATUS item 86) -- synthetic bars only, no API."""
from __future__ import annotations

from datetime import date, timedelta
from types import SimpleNamespace

from scripts import audit_universe_data as au


def _bar(d: date, close: int, volume: int = 100, flat: bool = False):
    o, h, l = (close, close, close) if flat else (close, close + 1, close - 1)
    return SimpleNamespace(trade_date=d, open_price=o, high_price=h, low_price=l, close_price=close, volume=volume)


def test_audit_counts_each_issue() -> None:
    days = [date(2014, 1, 6) + timedelta(days=i) for i in range(10)]
    bars = [_bar(d, 1000) for d in days]
    del bars[3]                                   # one missing trading day
    bars[5] = _bar(bars[5].trade_date, 1000, volume=0, flat=True)  # halt
    bars[7] = _bar(bars[7].trade_date, 1200)      # +20% before 2015-06-15 -> over the 15% limit
    row = au.audit_stock("000001", bars, days, date(2014, 1, 8), end=days[-1], start=days[0])
    assert row["missing_trading_days"] == 1 and row["longest_missing_run"] == 1
    assert row["zero_volume_days"] == 1 and row["bars_before_listing"] == 2
    assert row["limit_breaches"] == 2  # up 20% and back down 16.7%
    assert row["nonpositive_price"] == 0 and row["ohlc_violation"] == 0


def test_limit_and_window() -> None:
    assert au.price_limit(date(2015, 6, 12)) == 0.15 and au.price_limit(date(2015, 6, 15)) == 0.30
    days = [date(2016, 1, 4) + timedelta(days=i) for i in range(4)]
    bars = [_bar(days[0], 1000), _bar(days[1], 1250), _bar(days[2], 1000), _bar(days[3], 5000)]
    row = au.audit_stock("000001", bars, days, None, end=days[2], start=days[0])
    assert row["limit_breaches"] == 0 and row["n_bars"] == 3  # 25% is inside the 30% limit; the jump after `end` is ignored


def test_audit_never_reaches_the_forward_period() -> None:
    assert au.audit_end() < date.fromisoformat(au.FORWARD_START)


def test_listing_dates_parsing() -> None:
    rows = [{"code": "018260", "name": "삼성에스디에스", "regDay": "20141114"}, {"code": "005930", "regDay": ""}]
    assert au.listing_dates(rows, ["018260", "005930", "000660"]) == {
        "018260": {"name": "삼성에스디에스", "reg_day": "2014-11-14"}}
