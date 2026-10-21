"""Item 63: never decide on an unfinished daily bar."""
from __future__ import annotations

from datetime import date, datetime

import pytest

from src.data.normalization import KST
from src.data.session import daily_fetch_error, intraday_bar_error


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


# Item 98: the ka10081 fetch itself refuses to store today's unfinished bar.
WEDNESDAY_MORNING = datetime(2026, 10, 14, 10, 47, tzinfo=KST)


def test_daily_fetch_before_final_time_on_a_weekday_is_refused() -> None:
    msg = daily_fetch_error(date(2026, 10, 14), WEDNESDAY_MORNING)
    assert msg is not None and "--force" in msg and "10:47" in msg
    assert daily_fetch_error(date(2026, 10, 15), WEDNESDAY_MORNING) is not None  # later base date still returns today


def test_daily_fetch_after_final_time_past_base_date_or_weekend_is_allowed() -> None:
    assert daily_fetch_error(date(2026, 10, 14), datetime(2026, 10, 14, 19, 59, tzinfo=KST)) is not None  # NXT open (item 99)
    assert daily_fetch_error(date(2026, 10, 14), datetime(2026, 10, 14, 20, 0, tzinfo=KST)) is None
    assert daily_fetch_error(date(2026, 10, 13), WEDNESDAY_MORNING) is None
    assert daily_fetch_error(date(2026, 10, 17), datetime(2026, 10, 17, 10, 0, tzinfo=KST)) is None  # Saturday


def test_daily_fetch_naive_time_is_rejected() -> None:
    with pytest.raises(ValueError):
        daily_fetch_error(date(2026, 10, 14), datetime(2026, 10, 14, 10, 0))
