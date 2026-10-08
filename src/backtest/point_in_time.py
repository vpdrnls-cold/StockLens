"""Point-in-time variant of the buffered engine (CURRENT_STATUS item 87, decisions 1-3 = a).

``src.backtest.buffered`` only lets a stock be picked when its exit close (T+holding) is
already in the data, so a stock that will halt or delist is silently avoided, and a held
stock that stops trading drops out without its loss. Fine for comparing candidates on the
same data, but optimistic as a measure of what a user would have got. This engine uses
only what is known at the decision close T:

  - eligible at T: a valid close at T-lookback and at T, and a finite score
    (halted days are missing rows after item 86 cleaning, so a halted stock is not eligible);
  - a pick whose T+1 open is missing (halt starts next day) is not entered: that slot is cash;
  - a held stock with no valid close at a rebalance cannot be sold: it is carried
    ("locked"), keeps its slot, and is marked at its last valid close;
  - a stock whose bars end before the last date of the data is treated as delisted on its
    last bar: it exits at that close (including any 정리매매 price) with sell-side costs
    (decision 2);
  - at the end of the run every position is closed at its last valid close (decision 3);
    positions whose price is stale at that point are listed so a caller can also report
    them valued at zero (``zero_value_sensitivity``).

Same decision grid, ranking (score desc, stable on ``data_by_stock`` order), buffer rule
(``select_held``) and cost model as ``run_buffered_backtest``. On data without gaps the
trades are identical -- ``tests/test_point_in_time_engine.py`` pins that.
Not used by the frozen model, the forward evaluation or any earlier result (item 87 decision 4).
"""

from __future__ import annotations

from dataclasses import replace
import math

import numpy as np
import pandas as pd

from src.backtest.baseline import Trade, calculate_performance, prepare_universe
from src.backtest.buffered import BufferedBaselineConfig, buffer_rank_limit, select_held


def _valid(x: float) -> bool:
    return math.isfinite(x) and x > 0


def _last_valid_at_or_before(closes: np.ndarray, i: int) -> int | None:
    for k in range(i, -1, -1):
        if _valid(closes[k]):
            return k
    return None


def run_point_in_time_backtest(
    data_by_stock: dict[str, pd.DataFrame],
    config: BufferedBaselineConfig,
    score_fn,
    top_n: int,
) -> tuple[list[Trade], dict]:
    """Trades (same shape as ``run_buffered_backtest``) and a stats dict."""
    codes = list(data_by_stock.keys())
    if not (1 <= top_n <= len(codes)):
        raise ValueError(f"top_n must be between 1 and {len(codes)}, got {top_n}.")
    universe = prepare_universe(data_by_stock, how="outer")
    n, lb, h = len(universe), config.lookback_days, config.holding_days
    empty_stats = {"periods": 0.0, "entries_per_period": float("nan"), "avg_positions_held": float("nan"),
                   "failed_entries": 0, "locked_position_periods": 0, "delisted_exits": 0, "stale_at_end": []}
    if n < lb + 1 + h:
        return [], empty_stats
    opens = {c: universe[f"open_{c}"].to_numpy(dtype=float) for c in codes}
    closes = {c: universe[f"close_{c}"].to_numpy(dtype=float) for c in codes}
    dates = universe["trade_date"]
    last_bar = {c: _last_valid_at_or_before(closes[c], n - 1) for c in codes}
    delisted = {c for c in codes if last_bar[c] is not None and last_bar[c] < n - 1}
    buffer_rank = buffer_rank_limit(top_n, config.buffer_multiplier)
    decisions = list(range(lb, n - h, h))

    # pass 1: who is held in each period, and how each position starts
    periods = []  # (d, e, held, carried, entered, scores)
    held: set[str] = set()
    failed = locked_count = 0
    for d in decisions:
        e = d + h
        held = {c for c in held if not (c in delisted and last_bar[c] < d)}  # exited at delisting
        locked = {c for c in held if not _valid(closes[c][d])}
        tradable = held - locked
        scores: dict[str, float] = {}
        for c in codes:
            if _valid(closes[c][d - lb]) and _valid(closes[c][d]):
                try:
                    s = score_fn(universe, c, d, lb)
                except KeyError:
                    continue
                if math.isfinite(s):
                    scores[c] = s
        slots = top_n - len(locked)
        if len(scores) < top_n or slots <= 0:
            picked, carried = set(), set()
        else:
            ranked = sorted(scores, key=scores.get, reverse=True)
            picked, carried = select_held(tradable, ranked, slots, buffer_rank)
        new = picked - carried
        entered = {c for c in new if _valid(opens[c][d + 1])}
        failed += len(new - entered)
        locked_count += len(locked)
        held = locked | carried | entered
        periods.append((d, e, held, locked | carried, entered, scores))

    # pass 2: returns
    weight = 1.0 / top_n
    trades: list[Trade] = []
    delisted_exits = 0
    stale_at_end: list[str] = []
    for j, (d, e, held_j, carried_j, entered_j, scores) in enumerate(periods):
        next_carried = periods[j + 1][3] if j + 1 < len(periods) else set()
        for c in sorted(held_j, key=codes.index):
            delists_now = c in delisted and last_bar[c] < e
            end = last_bar[c] if delists_now else _last_valid_at_or_before(closes[c], e)
            is_exit = delists_now or c not in next_carried
            if c in entered_j:
                entry_price = opens[c][d + 1]
                effective_entry = entry_price * (1.0 + config.buy_slippage)
                buy_fee = config.buy_fee
            else:
                start = _last_valid_at_or_before(closes[c], d)
                entry_price = effective_entry = closes[c][start]
                buy_fee = 0.0
            exit_price = closes[c][end]
            if is_exit:
                effective_exit = exit_price * (1.0 - config.sell_slippage) * (1.0 - config.sell_tax)
                sell_fee = config.sell_fee
            else:
                effective_exit, sell_fee = exit_price, 0.0
            if delists_now:
                delisted_exits += 1
            if j == len(periods) - 1 and end < e:  # no price at the last exit (halted or gone): valued at last price
                stale_at_end.append(c)
            gross = effective_exit / effective_entry - 1.0
            trades.append(Trade(
                decision_date=dates.iloc[d], stock_code=c, score=float(scores.get(c, float("nan"))),
                # a position with no new price in this period (halted throughout, or delisted before T+1)
                # is dated at its last mark so entry_date <= exit_date (daily_equity reads that span)
                entry_date=dates.iloc[d + 1] if end >= d + 1 else dates.iloc[end], entry_price=float(entry_price),
                exit_date=dates.iloc[end], exit_price=float(exit_price),
                gross_return=float(gross), net_return=float(gross - buy_fee - sell_fee), weight=weight,
            ))

    active = [p for p in periods if p[2]]
    stats = {
        "periods": float(len(active)),
        "entries_per_period": float(np.mean([len(p[4]) for p in active])) if active else float("nan"),
        "avg_positions_held": float(np.mean([len(p[2]) for p in active])) if active else float("nan"),
        "failed_entries": failed,
        "locked_position_periods": locked_count,
        "delisted_exits": delisted_exits,
        "stale_at_end": stale_at_end,
    }
    return trades, stats


def zero_value_sensitivity(trades: list[Trade], stale_at_end: list[str]) -> float:
    """Total net return if the positions still stale at the end were worth nothing (decision 3, report only)."""
    if not trades or not stale_at_end:
        return calculate_performance(trades)["total_return"]
    last = max(t.decision_date for t in trades)
    adjusted = [
        replace(t, net_return=-1.0, gross_return=-1.0)
        if t.decision_date == last and t.stock_code in stale_at_end else t
        for t in trades
    ]
    return calculate_performance(adjusted)["total_return"]


def universe_average_gross_pit(data_by_stock: dict[str, pd.DataFrame], holding: int = 5, lookback: int = 5) -> pd.Series:
    """Equal-weight gross benchmark on the same point-in-time rule, per decision date.

    Every stock with a valid close at T-lookback and T and a valid open at T+1 is bought;
    it is valued at its last valid close up to T+holding (a stock that stops trading keeps
    its last price). No costs, like ``universe_average_gross``.
    """
    universe = prepare_universe(data_by_stock, how="outer")
    codes = list(data_by_stock)
    opens = {c: universe[f"open_{c}"].to_numpy(float) for c in codes}
    closes = {c: universe[f"close_{c}"].to_numpy(float) for c in codes}
    dates = universe["trade_date"]
    out: dict[pd.Timestamp, float] = {}
    for d in range(lookback, len(universe) - holding, holding):
        rets = []
        for c in codes:
            if _valid(closes[c][d - lookback]) and _valid(closes[c][d]) and _valid(opens[c][d + 1]):
                end = _last_valid_at_or_before(closes[c], d + holding)
                rets.append(closes[c][end] / opens[c][d + 1] - 1.0)
        if rets:
            out[dates.iloc[d]] = float(np.mean(rets))
    return pd.Series(out, dtype="float64")
