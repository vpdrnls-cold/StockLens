"""Buffered holdings for the paper-trading log (CURRENT_STATUS item 66).

``scripts/recommend.py`` ranks every stock on a decision date, but the strategy
that is backtested and forward-evaluated is buffered: a held stock is kept while
its rank stays within ``buffer_multiplier * top_n`` (item 47). Holdings therefore
depend on the previous holdings, which a single day's ranking cannot show.

No separate state file: every neutral log ``reports/daily_picks/<YYYYMMDD>.csv``
already stores the full ranking of its date, so the holdings are recomputed by
replaying the logged rankings in date order with the engine's own rule
(``src.backtest.buffered.select_held``). The replay starts from empty holdings at
the first logged date, like the engine's first period.

Limits: the log is written about once a week (Fridays, when daily bars are
refreshed), while the engine rebalances every 5 trading days; a holiday week or a
skipped run makes the two schedules differ. ``schedule_gaps`` reports such gaps.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from src.backtest.buffered import buffer_rank_limit, select_held

MAX_GAP_CALENDAR_DAYS = 9  # weekly log + one holiday; more means a missed rebalance


@dataclass(frozen=True)
class HoldingStep:
    trade_date: pd.Timestamp
    held: frozenset[str]
    carried: frozenset[str]  # kept by the buffer rule from the previous step

    @property
    def entered(self) -> frozenset[str]:
        return self.held - self.carried


def ranked_codes(log: pd.DataFrame) -> list[str]:
    """Stock codes of one log, best rank first (the log's rank already follows the engine's tie rule)."""
    return [str(c).zfill(6) for c in log.sort_values("rank")["stock_code"]]


def replay_holdings(
    rankings: list[tuple[pd.Timestamp, list[str]]],
    *,
    top_n: int,
    buffer_multiplier: float | None,
) -> list[HoldingStep]:
    """Apply the buffer rule over ``rankings`` (date, codes best-first) in date order."""
    limit = buffer_rank_limit(top_n, buffer_multiplier)
    held: set[str] = set()
    steps: list[HoldingStep] = []
    for trade_date, ranked in sorted(rankings, key=lambda x: x[0]):
        if len(ranked) < top_n:
            raise ValueError(f"{trade_date:%Y-%m-%d}: only {len(ranked)} ranked stocks (< top_n={top_n}).")
        held, carried = select_held(held, ranked, top_n, limit)
        steps.append(HoldingStep(pd.Timestamp(trade_date), frozenset(held), frozenset(carried)))
    return steps


def load_logged_rankings(log_dir: Path, before: pd.Timestamp) -> list[tuple[pd.Timestamp, list[str]]]:
    """Rankings from ``<log_dir>/<YYYYMMDD>.csv`` with a decision date strictly before ``before``."""
    out = []
    for path in sorted(Path(log_dir).glob("[0-9]" * 8 + ".csv")):
        log = pd.read_csv(path, dtype={"stock_code": str}, encoding="utf-8-sig")
        if log.empty or "rank" not in log.columns:
            continue
        trade_date = pd.Timestamp(log["trade_date"].iloc[0])
        if trade_date < before:
            out.append((trade_date, ranked_codes(log)))
    return out


def schedule_gaps(dates: list[pd.Timestamp], max_days: int = MAX_GAP_CALENDAR_DAYS) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    """Consecutive logged dates more than ``max_days`` calendar days apart."""
    ds = sorted(pd.Timestamp(d) for d in dates)
    return [(a, b) for a, b in zip(ds, ds[1:]) if (b - a).days > max_days]
