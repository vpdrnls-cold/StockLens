"""Item 63: never decide on an unfinished daily bar."""
from __future__ import annotations

from datetime import date, datetime

import pytest

from src.data.normalization import KST
from src.data.session import intraday_bar_error


def test_today_before_final_time_is_refused() -> None:
    msg = intraday_bar_error(date(2026, 9, 28), datetime(2026, 9, 28, 12, 41, tzinfo=KST))
    assert msg is not None and "확정 전" in msg


def test_today_after_final_time_and_past_days_are_allowed() -> None:
    assert intraday_bar_error(date(2026, 9, 28), datetime(2026, 9, 28, 18, 0, tzinfo=KST)) is None
    assert intraday_bar_error(date(2026, 9, 25), datetime(2026, 9, 28, 9, 0, tzinfo=KST)) is None


def test_timezone_is_converted_to_kst() -> None:
    # 2026-09-28 03:41 UTC == 12:41 KST -> still intraday
    utc = datetime.fromisoformat("2026-09-28T03:41:00+00:00")
    assert intraday_bar_error(date(2026, 9, 28), utc) is not None


def test_future_date_and_naive_time() -> None:
    assert intraday_bar_error(date(2026, 9, 29), datetime(2026, 9, 28, 20, 0, tzinfo=KST)) is not None
    with pytest.raises(ValueError):
        intraday_bar_error(date(2026, 9, 28), datetime(2026, 9, 28, 20, 0))
