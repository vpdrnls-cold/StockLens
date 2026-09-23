"""Tests for the ka10080 as-of cutoff (src/data/intraday.py).

Phase H decision-timestamp design, 2026-09-22/23: real ka10080 data for
005930 confirmed NXT/pre-market/after-hours bars are mixed in with the
regular 09:00-15:30 session (112/1866 rows, 6.0%, in a 3-month pilot
window). These tests pin down the resulting two-part cutoff rule --
see the src/data/intraday.py module docstring for the full rationale.
"""

from __future__ import annotations

import pytest

from src.data.intraday import IntradayCutoffError, as_of_snapshot


def _row(cntr_tm: str) -> dict:
    return {"cntr_tm": cntr_tm, "cur_prc": "+100000"}


def test_prior_date_keeps_full_regular_session_but_excludes_after_hours() -> None:
    rows = [
        _row("20260810083000"),  # prior date, pre-market -- excluded
        _row("20260810090000"),  # prior date, session open -- kept
        _row("20260810141500"),  # prior date, mid-session -- kept
        _row("20260810153000"),  # prior date, session close -- kept
        _row("20260810180000"),  # prior date, after-hours/NXT -- excluded
    ]

    result = as_of_snapshot(rows, decision_date="20260811", cutoff_time="1400")

    assert [row["cntr_tm"] for row in result] == [
        "20260810090000",
        "20260810141500",
        "20260810153000",
    ]


def test_decision_date_is_capped_at_cutoff_not_session_end() -> None:
    """The whole point of a 14:00 decision timestamp: T's own bars after
    14:00 were not knowable yet, even though they're still well within
    the 09:00-15:30 regular session."""
    rows = [
        _row("20260811083000"),  # decision date, pre-market -- excluded
        _row("20260811090000"),  # decision date, session open -- kept
        _row("20260811140000"),  # decision date, exactly at cutoff -- kept
        _row("20260811141500"),  # decision date, after cutoff -- excluded
        _row("20260811153000"),  # decision date, session close -- excluded
    ]

    result = as_of_snapshot(rows, decision_date="20260811", cutoff_time="1400")

    assert [row["cntr_tm"] for row in result] == [
        "20260811090000",
        "20260811140000",
    ]


def test_rows_after_decision_date_are_excluded_defensively() -> None:
    rows = [_row("20260812100000")]

    result = as_of_snapshot(rows, decision_date="20260811", cutoff_time="1400")

    assert result == []


def test_malformed_or_missing_cntr_tm_is_dropped_not_raised() -> None:
    rows = [
        {"cur_prc": "+100000"},  # missing cntr_tm entirely
        _row("2026081109"),  # too short
        _row("2026081abcdefg"),  # non-digit
        _row("20260810090000"),  # valid, prior date
    ]

    result = as_of_snapshot(rows, decision_date="20260811", cutoff_time="1400")

    assert [row["cntr_tm"] for row in result] == ["20260810090000"]


def test_custom_session_bounds_are_respected() -> None:
    rows = [
        _row("20260810084500"),  # prior date, before custom session_start
        _row("20260810090500"),  # prior date, within custom bounds
    ]

    result = as_of_snapshot(
        rows,
        decision_date="20260811",
        cutoff_time="1400",
        session_start="0900",
    )

    assert [row["cntr_tm"] for row in result] == ["20260810090500"]


def test_rejects_malformed_decision_date() -> None:
    with pytest.raises(IntradayCutoffError, match="decision_date"):
        as_of_snapshot([], decision_date="2026-08-11", cutoff_time="1400")


def test_rejects_malformed_cutoff_time() -> None:
    with pytest.raises(IntradayCutoffError, match="cutoff_time"):
        as_of_snapshot([], decision_date="20260811", cutoff_time="14:00")


def test_rejects_cutoff_time_outside_session_bounds() -> None:
    with pytest.raises(IntradayCutoffError, match="between session_start and session_end"):
        as_of_snapshot([], decision_date="20260811", cutoff_time="0830")
