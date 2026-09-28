"""Time split for intraday (ka10080) research -- CURRENT_STATUS item 46.

Why this is separate from ``src/data/dataset.py``
  ``ka10080`` only serves about one year of history (2025-09-01~), and that
  whole year sits inside the daily test period (2023-07-01~2026-09-16), which
  item 41 already consumed. The daily split therefore cannot be reused for
  intraday work. The daily model stays frozen (trained 2002-2019, early-stopped
  on 2020-2023H1), so its scores are out-of-sample everywhere in this range;
  only the intraday side needs its own partition.

Decision timing (item 46, option A)
  Decide after day T is final (20:00 KST, after the after-market session),
  enter at T+1's open, exit at T+h's close -- the same timing as the daily
  target (``entry="next_open"``) and the backtest engine. Features may use
  T's whole regular session (09:00-15:30). They may never use T+1 or later.

Segments (by decision date T)
  dev            2025-09-01 ~ 2026-06-30   feature choice, overlay weight
    B1           2025-09-01 ~ 2025-12-31   } sign-consistency blocks
    B2           2026-01-01 ~ 2026-03-31   } inside dev
    B3           2026-04-01 ~ 2026-06-30   }
  semi_holdout   2026-07-01 ~ 2026-09-23   already seen by the intraday IC
                                           diagnostic (Notion, 2026-09-24), so
                                           NOT clean: sign check only, once
  forward        2026-09-24 ~              the only clean holdout; locked until
                                           at least FORWARD_MIN_DATES dates exist

Label purge
  A row's label ``close(T+h) / open(T+1) - 1`` reaches h trading days past T.
  Rows whose label window crosses a segment's end are dropped, so no segment's
  labels use prices from the next segment (e.g. a 2026-06-29 decision would
  otherwise read July prices from the semi-holdout).

Locks
  ``semi_holdout`` needs STOCKLENS_CONFIRM_INTRADAY_SEMI_HOLDOUT=1 and
  ``forward`` needs STOCKLENS_CONFIRM_INTRADAY_FORWARD=1 for that run, the same
  mechanism as ``src/eval/test_lock.py``.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from src.eval.test_lock import confirm_holdout_use

SEMI_HOLDOUT_ENV_VAR = "STOCKLENS_CONFIRM_INTRADAY_SEMI_HOLDOUT"
FORWARD_ENV_VAR = "STOCKLENS_CONFIRM_INTRADAY_FORWARD"

INTRADAY_DATA_START = "2025-09-01"
FORWARD_START = "2026-09-24"
# Pre-registered: the forward holdout is evaluated once, after at least this
# many decision dates exist (about 3 months of trading days).
FORWARD_MIN_DATES = 60


@dataclass(frozen=True)
class Segment:
    name: str
    start: str
    end: str | None  # None = open-ended
    lock_env_var: str | None = None


DEV_BLOCKS = (
    Segment("B1", "2025-09-01", "2025-12-31"),
    Segment("B2", "2026-01-01", "2026-03-31"),
    Segment("B3", "2026-04-01", "2026-06-30"),
)
SEGMENTS = {
    "dev": Segment("dev", "2025-09-01", "2026-06-30"),
    **{b.name: b for b in DEV_BLOCKS},
    "semi_holdout": Segment("semi_holdout", "2026-07-01", "2026-09-23", SEMI_HOLDOUT_ENV_VAR),
    "forward": Segment("forward", FORWARD_START, None, FORWARD_ENV_VAR),
}


class IntradaySplitError(RuntimeError):
    """Raised when a segment cannot be served safely (e.g. forward holdout too short)."""


def _label_end_dates(dates: pd.Series, horizon: int) -> pd.Series:
    """Map each decision date to the date h trading days later (NaT if beyond the data)."""
    calendar = pd.Series(sorted(pd.to_datetime(dates).dropna().unique()))
    ahead = calendar.shift(-horizon)
    lookup = dict(zip(calendar, ahead))
    return pd.to_datetime(dates).map(lookup)


def select_segment(
    df: pd.DataFrame,
    segment: str,
    *,
    caller: str,
    horizon: int = 5,
    date_col: str = "trade_date",
) -> pd.DataFrame:
    """Rows of ``df`` whose decision date is in ``segment``, label-purged at its end.

    ``df`` must cover the whole trading calendar around the segment (the purge
    uses the dates present in ``df`` as the calendar). Locked segments raise
    unless their environment variable is set to 1 for this run.
    """
    if segment not in SEGMENTS:
        raise ValueError(f"unknown segment {segment!r}; choose from {sorted(SEGMENTS)}")
    if horizon < 1:
        raise ValueError("horizon must be >= 1")
    seg = SEGMENTS[segment]

    if seg.lock_env_var is not None:
        confirm_holdout_use(
            caller,
            env_var=seg.lock_env_var,
            what=f"the intraday '{segment}' segment ({seg.start}~{seg.end or ''})",
        )

    dates = pd.to_datetime(df[date_col])
    in_seg = dates >= pd.Timestamp(seg.start)
    if seg.end is not None:
        in_seg &= dates <= pd.Timestamp(seg.end)

    label_end = _label_end_dates(dates, horizon)
    purge_limit = pd.Timestamp(seg.end) if seg.end is not None else dates.max()
    keep = in_seg & label_end.notna() & (label_end <= purge_limit)
    out = df.loc[keep].copy()

    if segment == "forward":
        n_dates = pd.to_datetime(out[date_col]).nunique()
        if n_dates < FORWARD_MIN_DATES:
            raise IntradaySplitError(
                f"forward holdout has {n_dates} usable decision dates; the "
                f"pre-registered minimum is {FORWARD_MIN_DATES}. Keep collecting "
                f"(scripts/nightly_ingest.sh) and evaluate later."
            )
    return out
