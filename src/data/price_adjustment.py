"""Detect adjusted-price recalculations in stored daily bars (CURRENT_STATUS item 82).

The nightly job overwrites ``data/processed/historical/<code>.json`` with the full
adjusted history from ka10081, so when Kiwoom recomputes past prices after a
corporate action (item 62: 207940, every bar up to 2026-10-01 x0.99230) nothing
records it. This module compares the previously seen bars with the current ones
and classifies the change. Pure functions only -- no file access, no returns,
features or scores; the script ``scripts/monitor_price_adjustments.py`` does the IO.

Bars are ``{trade_date (ISO str): (open, high, low, close, volume)}``. Only dates
present in both versions are compared; newly appended recent bars are ignored.

Classes
  unchanged        no overlapping bar changed and no date was removed
  rows_removed     a previously seen date is gone (checked first)
  uniform_rescale  >= 95% of overlapping dates have close_new/close_old equal to one
                   ratio r (within tolerance) and r != 1 -- an adjustment of the
                   whole past (item 62). ``last_date`` = last date on that ratio;
                   up to 5% of dates may differ (e.g. a replaced intraday bar, item 62)
  partial_change   anything else that changed (data corrections, a replaced
                   intraday bar)

Tolerance: prices are integer won. With old = round(T) and new = round(r*T), rounding
alone moves new/old/r by up to (0.5/r + 0.5)/close_old (005930 has closes down to
116 won before its 50:1 split). The per-row tolerance is therefore
max(1e-4, that bound) instead of a flat 1e-4, which would call a real rescale of a
stock with a long low-priced history ``partial_change``.
"""

from __future__ import annotations

from dataclasses import dataclass
from statistics import median
from typing import Iterable, Mapping

from src.data.models import DailyBar

FIELDS: tuple[str, ...] = ("open", "high", "low", "close", "volume")
_CLOSE = FIELDS.index("close")
_VOLUME = FIELDS.index("volume")

RATIO_REL_TOL = 1e-4
UNIFORM_MIN_SHARE = 0.95
RATIO_DECIMALS = 6
_FLOAT_SLACK = 1e-9

UNCHANGED = "unchanged"
UNIFORM_RESCALE = "uniform_rescale"
PARTIAL_CHANGE = "partial_change"
ROWS_REMOVED = "rows_removed"

Bar = tuple[int, int, int, int, int]
Bars = Mapping[str, Bar]


@dataclass(frozen=True)
class PriceChange:
    """Result of comparing two versions of one stock's bars. Holds ratios and
    dates only -- never price values (the event log is committed to a public repo)."""

    classification: str
    n_overlap: int
    n_changed: int = 0
    n_removed: int = 0
    n_matched: int = 0  # uniform_rescale: dates on the common ratio (n_changed - n_matched = off-ratio)
    close_ratio: float | None = None
    volume_ratio: float | None = None
    first_date: str | None = None
    last_date: str | None = None
    fields: tuple[str, ...] = ()

    @property
    def is_change(self) -> bool:
        return self.classification != UNCHANGED


def bars_from_daily(bars: Iterable[DailyBar]) -> dict[str, Bar]:
    """``DailyBar`` list -> comparison mapping."""
    return {
        bar.trade_date.isoformat(): (
            bar.open_price,
            bar.high_price,
            bar.low_price,
            bar.close_price,
            bar.volume,
        )
        for bar in bars
    }


def classify_change(old: Bars, new: Bars) -> PriceChange:
    """Classify how ``new`` differs from ``old`` on the dates ``old`` already had."""
    overlap = sorted(set(old) & set(new))
    removed = sorted(set(old) - set(new))
    changed = [day for day in overlap if tuple(old[day]) != tuple(new[day])]

    if removed:
        return PriceChange(
            classification=ROWS_REMOVED,
            n_overlap=len(overlap),
            n_changed=len(changed),
            n_removed=len(removed),
            first_date=removed[0],
            last_date=removed[-1],
            fields=_changed_fields(old, new, changed),
        )
    if not changed:
        return PriceChange(classification=UNCHANGED, n_overlap=len(overlap))

    rescale = _uniform_rescale(old, new, overlap, changed)
    if rescale is not None:
        return rescale
    return PriceChange(
        classification=PARTIAL_CHANGE,
        n_overlap=len(overlap),
        n_changed=len(changed),
        first_date=changed[0],
        last_date=changed[-1],
        fields=_changed_fields(old, new, changed),
    )


def _uniform_rescale(
    old: Bars, new: Bars, overlap: list[str], changed: list[str]
) -> PriceChange | None:
    close_changed = [
        day for day in changed if old[day][_CLOSE] > 0 and old[day][_CLOSE] != new[day][_CLOSE]
    ]
    if not close_changed:
        return None
    ratio = median(new[day][_CLOSE] / old[day][_CLOSE] for day in close_changed)
    if abs(ratio - 1.0) <= RATIO_REL_TOL:
        return None
    matched = [day for day in overlap if _close_matches(old[day], new[day], ratio)]
    if len(matched) < UNIFORM_MIN_SHARE * len(overlap):
        return None
    volume_ratios = [
        new[day][_VOLUME] / old[day][_VOLUME] for day in matched if old[day][_VOLUME] > 0
    ]
    return PriceChange(
        classification=UNIFORM_RESCALE,
        n_overlap=len(overlap),
        n_changed=len(changed),
        n_matched=len(matched),
        close_ratio=round(ratio, RATIO_DECIMALS),
        volume_ratio=round(median(volume_ratios), RATIO_DECIMALS) if volume_ratios else None,
        first_date=matched[0],
        last_date=matched[-1],
        fields=_changed_fields(old, new, changed),
    )


def _close_matches(old_bar: Bar, new_bar: Bar, ratio: float) -> bool:
    old_close = old_bar[_CLOSE]
    if old_close <= 0:
        return False
    rounding = (0.5 / ratio + 0.5) / old_close * (1.0 + _FLOAT_SLACK)
    tolerance = max(RATIO_REL_TOL, rounding)
    return abs(new_bar[_CLOSE] / old_close / ratio - 1.0) <= tolerance


def _changed_fields(old: Bars, new: Bars, days: Iterable[str]) -> tuple[str, ...]:
    hit = {
        FIELDS[i]
        for day in days
        if day in new
        for i in range(len(FIELDS))
        if old[day][i] != new[day][i]
    }
    return tuple(name for name in FIELDS if name in hit)
