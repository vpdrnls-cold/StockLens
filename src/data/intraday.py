"""Leakage-safe as-of cutoff for Kiwoom ``ka10080`` minute-chart rows.

Phase H decision-timestamp design (2026-09-22/23): a live check against
005930 (``scripts/check_kiwoom_minute_chart.py`` /
``scripts/ingest_kiwoom_minute_chart.py``) confirmed that ``ka10080``
returns NXT/pre-market/after-hours bars alongside the regular
09:00-15:30 KRX session -- 112 of 1866 rows (6.0%) over a 3-month pilot
window fell outside 09:00-15:30.

This matters for more than just "noise": the leakage rule for a fixed
intraday decision timestamp (e.g. 14:00 on trade date T) is NOT simply
"drop every bar timestamped after 14:00". It is two different rules
depending on which calendar date a bar falls on relative to T:

- Bars on T itself: only 09:00-14:00 may be used. Anything before 09:00
  (pre-market) or after 14:00 (including the as-yet-unknown rest of
  T's own regular session, and any of T's after-hours/NXT activity) was
  not knowable at the T 14:00 decision point and must be excluded.
- Bars on any date strictly before T: the full regular session
  (09:00-15:30) is fair game -- that day is already fully resolved
  history by the time T 14:00 arrives. Only the NXT/pre-market/
  after-hours noise on those prior days is excluded, and only because
  it is a different trading regime (thin liquidity, different price
  dynamics), not because of leakage.
- Bars on any date after T: always excluded (should not occur in a
  correctly time-bounded historical fetch, but guarded here
  defensively rather than trusted).

``as_of_snapshot()`` makes this structural -- the same
"don't rely on a comment, make it mechanically impossible" principle
``src/feature_selection/data_loading.py`` and ``src/eval/test_lock.py``
already use for other leakage risks in this project (see
learnings.md: "Data leakage is structurally prevented, not just
fixed"). Any future intraday feature-engineering code should filter
through this function rather than re-deriving the cutoff logic inline.
"""

from __future__ import annotations

import re
from typing import Any, Mapping, Sequence

REGULAR_SESSION_START = "0900"
REGULAR_SESSION_END = "1530"

_HHMM_PATTERN = re.compile(r"^\d{4}$")
_YYYYMMDD_PATTERN = re.compile(r"^\d{8}$")


class IntradayCutoffError(ValueError):
    """Raised when as_of_snapshot's inputs are malformed."""


def as_of_snapshot(
    rows: Sequence[Mapping[str, Any]],
    decision_date: str,
    cutoff_time: str,
    *,
    session_start: str = REGULAR_SESSION_START,
    session_end: str = REGULAR_SESSION_END,
) -> list[Mapping[str, Any]]:
    """Return only the ``ka10080`` rows knowable at ``decision_date`` ``cutoff_time``.

    ``decision_date`` is ``YYYYMMDD``. ``cutoff_time``/``session_start``/
    ``session_end`` are ``HHMM`` (24h, zero-padded, e.g. ``"1400"`` for
    14:00). Comparisons are inclusive at both ends. Rows missing or
    malformed ``cntr_tm`` (expected ``YYYYMMDDHHmmss``, per the
    documented ka10080 response schema) are dropped rather than raising,
    since a malformed timestamp cannot be placed relative to the cutoff
    safely either way.

    See the module docstring for why prior dates use
    ``[session_start, session_end]`` while ``decision_date`` itself uses
    ``[session_start, cutoff_time]``.
    """
    if not _YYYYMMDD_PATTERN.match(decision_date):
        raise IntradayCutoffError("decision_date must be YYYYMMDD.")
    for name, value in (
        ("cutoff_time", cutoff_time),
        ("session_start", session_start),
        ("session_end", session_end),
    ):
        if not _HHMM_PATTERN.match(value):
            raise IntradayCutoffError(f"{name} must be HHMM (4 digits).")
    if not (session_start <= cutoff_time <= session_end):
        raise IntradayCutoffError(
            "cutoff_time must be between session_start and session_end."
        )

    result: list[Mapping[str, Any]] = []
    for row in rows:
        cntr_tm = str(row.get("cntr_tm", ""))
        if len(cntr_tm) < 12 or not cntr_tm[:12].isdigit():
            continue
        row_date = cntr_tm[:8]
        row_time = cntr_tm[8:12]

        if row_date > decision_date:
            continue
        if row_date == decision_date:
            if session_start <= row_time <= cutoff_time:
                result.append(row)
        else:
            if session_start <= row_time <= session_end:
                result.append(row)

    return result
