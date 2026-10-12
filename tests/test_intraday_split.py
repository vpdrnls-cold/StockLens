from __future__ import annotations

import pandas as pd
import pytest

from src.data import intraday_split as isp
from src.data.intraday_split import (
    FORWARD2_ENV_VAR,
    FORWARD2_START,
    FORWARD_END,
    FORWARD_ENV_VAR,
    FORWARD_START,
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
    monkeypatch.delenv(FORWARD2_ENV_VAR, raising=False)


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
    # forward2 is the open-ended segment since item 94 (forward ends the day before it).
    monkeypatch.setenv(FORWARD2_ENV_VAR, "1")
    bars = pd.bdate_range("2027-01-01", "2027-06-30")
    rows = _frame("2027-01-01", str(bars[-6].date()))  # last 5 bar dates have no row
    without = select_segment(rows, "forward2", caller="t", horizon=5)
    with_cal = select_segment(rows, "forward2", caller="t", horizon=5, calendar=bars)
    assert with_cal["trade_date"].max() == bars[-6]
    assert without["trade_date"].max() < bars[-6]  # conservative default drops valid dates



# --- item 94: forward2 lock, forward end fixed ---------------------------------------

def test_forward_ends_the_day_before_forward2() -> None:
    assert FORWARD2_START == "2027-01-11"
    assert pd.Timestamp(FORWARD_END) == pd.Timestamp(FORWARD2_START) - pd.Timedelta(days=1)
    assert pd.Timestamp(FORWARD_START) < pd.Timestamp(FORWARD_END)
    assert isp.SEGMENTS["forward"].end == FORWARD_END
    assert isp.SEGMENTS["forward2"].start == FORWARD2_START and isp.SEGMENTS["forward2"].end is None


def test_forward2_is_locked_and_other_unlocks_do_not_open_it(monkeypatch: pytest.MonkeyPatch) -> None:
    df = _frame("2026-09-01", "2027-06-30")
    with pytest.raises(TestSetLockedError):
        select_segment(df, "forward2", caller="t")
    monkeypatch.setenv(FORWARD_ENV_VAR, "1")
    monkeypatch.setenv(SEMI_HOLDOUT_ENV_VAR, "1")
    with pytest.raises(TestSetLockedError):
        select_segment(df, "forward2", caller="t")
    monkeypatch.setenv(FORWARD2_ENV_VAR, "1")
    monkeypatch.delenv(FORWARD_ENV_VAR)
    assert select_segment(df, "forward2", caller="t")["trade_date"].min() == pd.Timestamp(FORWARD2_START)
    with pytest.raises(TestSetLockedError):  # forward2's flag does not open forward
        select_segment(df, "forward", caller="t")


def test_forward_and_forward2_never_share_a_row(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(FORWARD_ENV_VAR, "1")
    monkeypatch.setenv(FORWARD2_ENV_VAR, "1")
    bars = pd.bdate_range("2026-09-01", "2027-06-30")
    df = _frame("2026-09-01", "2027-06-30")
    fwd = select_segment(df, "forward", caller="t", calendar=bars)
    fwd2 = select_segment(df, "forward2", caller="t", calendar=bars)
    assert fwd["trade_date"].max() <= pd.Timestamp(FORWARD_END)
    assert set(fwd["trade_date"]).isdisjoint(set(fwd2["trade_date"]))


@pytest.mark.parametrize("last_bar", ["2027-01-08", "2026-12-30"])
def test_fixed_forward_end_selects_what_the_open_end_did(monkeypatch: pytest.MonkeyPatch, last_bar: str) -> None:
    # Item 94 condition 5: on the planned run (data through 2027-01-08, or earlier) the
    # fixed end changes nothing compared with the open-ended definition used before.
    monkeypatch.setenv(FORWARD_ENV_VAR, "1")
    bars = pd.bdate_range("2026-09-01", last_bar)
    rows = _frame("2026-09-01", str(bars[-6].date()))
    for calendar in (None, bars):
        fixed = select_segment(rows, "forward", caller="t", horizon=5, calendar=calendar)
        monkeypatch.setitem(isp.SEGMENTS, "forward", isp.Segment("forward", FORWARD_START, None, FORWARD_ENV_VAR))
        open_end = select_segment(rows, "forward", caller="t", horizon=5, calendar=calendar)
        monkeypatch.undo()
        monkeypatch.setenv(FORWARD_ENV_VAR, "1")
        pd.testing.assert_frame_equal(fixed, open_end)
        assert fixed["trade_date"].nunique() >= FORWARD_MIN_DATES
