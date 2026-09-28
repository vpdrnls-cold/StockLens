from __future__ import annotations

import pandas as pd
import pytest

from src.data.intraday_split import (
    FORWARD_ENV_VAR,
    FORWARD_MIN_DATES,
    SEMI_HOLDOUT_ENV_VAR,
    IntradaySplitError,
    select_segment,
)
from src.eval.test_lock import TestSetLockedError


def _frame(start: str, end: str, stocks=("A", "B")) -> pd.DataFrame:
    dates = pd.bdate_range(start, end)
    return pd.DataFrame(
        [{"trade_date": d, "stock_code": s, "x": 1.0} for d in dates for s in stocks]
    )


@pytest.fixture(autouse=True)
def _locked(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(SEMI_HOLDOUT_ENV_VAR, raising=False)
    monkeypatch.delenv(FORWARD_ENV_VAR, raising=False)


def test_dev_rows_stay_inside_dev_and_are_purged_at_the_end() -> None:
    df = _frame("2025-09-01", "2026-08-31")
    out = select_segment(df, "dev", caller="t", horizon=5)
    dates = pd.bdate_range("2025-09-01", "2026-08-31")
    last_allowed = dates[dates.get_loc(pd.Timestamp("2026-06-30")) - 5]
    assert out["trade_date"].min() == pd.Timestamp("2025-09-01")
    assert out["trade_date"].max() == last_allowed  # label end must be <= 2026-06-30


def test_blocks_are_purged_at_their_own_end() -> None:
    df = _frame("2025-09-01", "2026-08-31")
    b1 = select_segment(df, "B1", caller="t", horizon=5)
    dates = pd.bdate_range("2025-09-01", "2026-08-31")
    assert b1["trade_date"].max() == dates[dates.get_loc(pd.Timestamp("2025-12-31")) - 5]


def test_semi_holdout_is_locked_by_default() -> None:
    df = _frame("2025-09-01", "2026-09-23")
    with pytest.raises(TestSetLockedError):
        select_segment(df, "semi_holdout", caller="t")


def test_semi_holdout_unlock_does_not_unlock_forward(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(SEMI_HOLDOUT_ENV_VAR, "1")
    df = _frame("2025-09-01", "2027-06-30")
    assert len(select_segment(df, "semi_holdout", caller="t")) > 0
    with pytest.raises(TestSetLockedError):
        select_segment(df, "forward", caller="t")


def test_forward_requires_minimum_dates(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(FORWARD_ENV_VAR, "1")
    short = _frame("2026-09-01", "2026-10-30")
    with pytest.raises(IntradaySplitError):
        select_segment(short, "forward", caller="t")
    long = _frame("2026-09-01", "2027-06-30")
    out = select_segment(long, "forward", caller="t")
    assert out["trade_date"].nunique() >= FORWARD_MIN_DATES
    assert out["trade_date"].min() == pd.Timestamp("2026-09-24")


def test_unknown_segment_rejected() -> None:
    with pytest.raises(ValueError):
        select_segment(_frame("2025-09-01", "2025-10-01"), "test", caller="t")


def test_calendar_keeps_dates_whose_label_ends_inside_the_segment() -> None:
    # dataset rows stop 5 bar dates before the data end (no target there)
    bars = pd.bdate_range("2026-06-01", "2026-09-23")
    rows = _frame("2026-06-01", str(bars[-6].date()))
    without = select_segment(rows, "dev", caller="t", horizon=5)
    with_cal = select_segment(rows, "dev", caller="t", horizon=5, calendar=bars)
    assert with_cal["trade_date"].max() == without["trade_date"].max()  # dev ends long before data end


def test_calendar_restores_the_last_dates_of_an_open_segment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(FORWARD_ENV_VAR, "1")
    bars = pd.bdate_range("2026-09-01", "2027-06-30")
    rows = _frame("2026-09-01", str(bars[-6].date()))  # last 5 bar dates have no row
    without = select_segment(rows, "forward", caller="t", horizon=5)
    with_cal = select_segment(rows, "forward", caller="t", horizon=5, calendar=bars)
    assert with_cal["trade_date"].max() == bars[-6]
    assert without["trade_date"].max() < bars[-6]  # conservative default drops valid dates
