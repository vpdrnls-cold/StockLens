"""Turnover-reduction ("buffer") variant of the baseline backtest.

Pre-Phase-H checklist item 2 (CURRENT_STATUS.md item 34's next-step
list, first candidate from item 33): does cutting unnecessary round
trips let an already-mildly-profitable gross signal (reversal / ML --
see item 33) survive after realistic costs?
``src.backtest.baseline.run_baseline_backtest`` closes and reopens
every position every rebalance, even when the exact same stock is
still top-ranked -- that pays a full round trip (~0.43% for the
current cost assumptions) for zero actual change in the portfolio.

This module keeps the same decision timing as
``src.backtest.baseline`` (score at T close, entry at T+1 open, exit
at T+holding_days close) and the same cost model (buy/sell fee, sell
tax, slippage), but a currently held stock that is still within a
``buffer_multiplier * top_n``-sized rank band is *kept* instead of
being sold and immediately rebought. Costs are then only ever charged
at the real entry and the real exit of a contiguous holding span --
periods in between are a pure close-to-close mark-to-market return
with zero fee/slippage/tax, because nothing was actually traded.

``buffer_multiplier=None`` disables buffering: every stock is closed
and reopened every period, identical to ``run_baseline_backtest``.
``tests/test_backtest_buffered.py`` checks the two engines produce
bit-identical trades in that mode -- that is the regression guard that
this refactor didn't change the reference case.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import pandas as pd

from src.backtest.baseline import (
    BaselineConfig,
    Trade,
    _eligible_scores,
    calculate_score,
    prepare_universe,
)


@dataclass(frozen=True)
class BufferedBaselineConfig(BaselineConfig):
    """``BaselineConfig`` plus a turnover-reduction buffer.

    buffer_multiplier:
        ``None`` (default): no buffering, behaves exactly like
        ``BaselineConfig`` / ``run_baseline_backtest``.

        A float >= 1.0: a stock already held is kept for another
        period if its rank today (1 = best score) is
        ``<= floor(buffer_multiplier * top_n)``, instead of being sold
        just because some other name is now strictly better-ranked.
    """

    buffer_multiplier: float | None = None


def _build_held_timeline(
    data_by_stock: dict[str, pd.DataFrame],
    config: BufferedBaselineConfig,
    score_fn,
    top_n: int,
):
    """Shared pass-1 logic: decide the held set for every rebalance date.

    Returns ``(universe, decision_indices, held_over_time,
    carried_over_time, meta_over_time, open_arrays, close_arrays)``.
    ``meta_over_time[j]`` is ``None`` for a period skipped for lack of
    ``top_n`` tradable names (the engine goes to cash and
    force-closes everything).

    ``carried_over_time[j]`` is the subset of ``held_over_time[j]``
    that is held *because the buffer rule kept it*, as opposed to
    being freshly picked this period. This is tracked explicitly,
    separately from "is this stock code already in the previous
    held set", because with ``buffer_multiplier=None`` the same stock
    can legitimately be re-picked from scratch in back-to-back
    periods by coincidence (it is still the single best-ranked name)
    -- that must still be charged a full round trip, unlike a real
    buffer-driven carry-over. Conflating the two was an actual bug
    caught by ``tests/test_backtest_buffered.py`` while building this
    module: with no buffer, `top_n=1` and a stock that stays the best
    pick for the whole run, treating "already held" as "carried" made
    every period after the first look like a free continuation --
    silently reproducing the exact turnover-reduction effect this
    module exists to *measure*, even with buffering switched off.

    Split out from ``run_buffered_backtest`` so both the trade-level
    backtest and the turnover diagnostic in
    ``run_buffered_backtest_with_turnover`` compute the held-set
    timeline exactly once, the same way.
    """
    stock_codes = list(data_by_stock.keys())
    partial = config.allow_partial_universe

    if not partial and len(stock_codes) != 5:
        raise ValueError(
            f"Baseline expects five stocks, got {len(stock_codes)}. "
            "Set allow_partial_universe=True for a larger universe."
        )
    if not (1 <= top_n <= len(stock_codes)):
        raise ValueError(
            f"top_n must be between 1 and {len(stock_codes)}, got {top_n}."
        )
    if config.buffer_multiplier is not None and config.buffer_multiplier < 1.0:
        raise ValueError(
            "buffer_multiplier must be None or >= 1.0, got "
            f"{config.buffer_multiplier}."
        )

    universe = prepare_universe(
        data_by_stock, how="outer" if partial else "inner"
    )

    required_rows = config.lookback_days + 1 + config.holding_days
    if len(universe) < required_rows:
        return universe, [], [], [], [], {}, {}

    open_arrays = {
        c: universe[f"open_{c}"].to_numpy(dtype=float) for c in stock_codes
    }
    close_arrays = {
        c: universe[f"close_{c}"].to_numpy(dtype=float) for c in stock_codes
    }

    first_decision_index = config.lookback_days
    last_decision_index = len(universe) - config.holding_days - 1
    decision_indices = list(
        range(first_decision_index, last_decision_index + 1, config.holding_days)
    )

    buffer_rank = None
    if config.buffer_multiplier is not None:
        buffer_rank = max(top_n, math.floor(config.buffer_multiplier * top_n))

    held_over_time: list[set[str]] = []
    carried_over_time: list[set[str]] = []
    meta_over_time: list[dict | None] = []
    held: set[str] = set()

    for decision_index in decision_indices:
        entry_index = decision_index + 1
        exit_index = decision_index + config.holding_days

        scores = _eligible_scores(
            universe, stock_codes, decision_index, entry_index, exit_index,
            config.lookback_days, score_fn, open_arrays, close_arrays,
        )

        if len(scores) < top_n:
            held_over_time.append(set())
            carried_over_time.append(set())
            meta_over_time.append(None)
            held = set()
            continue

        ranked = sorted(scores, key=scores.get, reverse=True)
        rank_of = {code: i + 1 for i, code in enumerate(ranked)}

        if buffer_rank is None:
            # No buffering: every period is a fresh top_n pick, full
            # stop. Nothing is ever "carried" -- even if the same
            # stock code happens to be picked again next period, that
            # is a coincidence of the ranking, not a decision to hold,
            # and must still be charged a full round trip (see the
            # docstring above for why this distinction is load-bearing).
            new_held = set(ranked[:top_n])
            carried = set()
        else:
            keep = sorted(
                (c for c in held if rank_of.get(c, math.inf) <= buffer_rank),
                key=lambda c: rank_of[c],
            )[:top_n]
            keep_set = set(keep)
            fill = [c for c in ranked if c not in keep_set][
                : top_n - len(keep_set)
            ]
            new_held = keep_set | set(fill)
            carried = keep_set

        held_over_time.append(new_held)
        carried_over_time.append(carried)
        meta_over_time.append(
            {
                "decision_date": universe.iloc[decision_index]["trade_date"],
                "entry_date": universe.iloc[entry_index]["trade_date"],
                "exit_date": universe.iloc[exit_index]["trade_date"],
                "decision_index": decision_index,
                "entry_index": entry_index,
                "exit_index": exit_index,
                "rank_of": rank_of,
                "scores": scores,
            }
        )
        held = new_held

    return (
        universe,
        decision_indices,
        held_over_time,
        carried_over_time,
        meta_over_time,
        open_arrays,
        close_arrays,
    )


def run_buffered_backtest(
    data_by_stock: dict[str, pd.DataFrame],
    config: BufferedBaselineConfig | None = None,
    score_fn=calculate_score,
    top_n: int = 1,
) -> list[Trade]:
    """Same decision engine as ``run_baseline_backtest``, with an optional turnover buffer.

    Returns one ``Trade`` per (period, held stock) -- the same shape as
    ``run_baseline_backtest``'s output, so ``trades_to_dataframe`` /
    ``calculate_performance`` work unchanged. A stock held across
    several consecutive periods produces several ``Trade`` records
    (one per period): only the first (a real entry) pays buy-side
    cost, only the last (a real exit -- it drops out of the held set
    the following period, or the backtest ends) pays sell-side cost.
    Periods in between are a pure close-to-close mark-to-market return
    with zero fee/slippage/tax, since nothing was actually bought or
    sold that period.
    """
    config = config or BufferedBaselineConfig()

    (
        universe,
        decision_indices,
        held_over_time,
        carried_over_time,
        meta_over_time,
        open_arrays,
        close_arrays,
    ) = _build_held_timeline(data_by_stock, config, score_fn, top_n)

    if not decision_indices:
        return []

    weight = 1.0 / top_n
    trades: list[Trade] = []
    n_periods = len(held_over_time)

    for j in range(n_periods):
        meta = meta_over_time[j]
        if meta is None:
            continue

        next_carried = carried_over_time[j + 1] if j + 1 < n_periods else set()

        for stock_code in held_over_time[j]:
            # A real entry unless the buffer rule explicitly carried
            # this position over from the previous period.
            is_entry = stock_code not in carried_over_time[j]
            # A real exit unless the buffer rule will explicitly carry
            # it into the next period.
            is_exit = stock_code not in next_carried

            close_at_decision = close_arrays[stock_code][meta["decision_index"]]
            raw_exit_price = close_arrays[stock_code][meta["exit_index"]]

            if is_entry:
                entry_price = open_arrays[stock_code][meta["entry_index"]]
                effective_entry = entry_price * (1.0 + config.buy_slippage)
                buy_fee = config.buy_fee
            else:
                entry_price = close_at_decision
                effective_entry = close_at_decision
                buy_fee = 0.0

            exit_price = raw_exit_price
            if is_exit:
                effective_exit = (
                    exit_price
                    * (1.0 - config.sell_slippage)
                    * (1.0 - config.sell_tax)
                )
                sell_fee = config.sell_fee
            else:
                effective_exit = exit_price
                sell_fee = 0.0

            gross_return = effective_exit / effective_entry - 1.0
            net_return = gross_return - buy_fee - sell_fee

            trades.append(
                Trade(
                    decision_date=meta["decision_date"],
                    stock_code=stock_code,
                    score=float(meta["scores"][stock_code]),
                    entry_date=meta["entry_date"],
                    entry_price=float(entry_price),
                    exit_date=meta["exit_date"],
                    exit_price=float(exit_price),
                    gross_return=float(gross_return),
                    net_return=float(net_return),
                    weight=weight,
                )
            )

    return trades


def run_buffered_backtest_with_turnover(
    data_by_stock: dict[str, pd.DataFrame],
    config: BufferedBaselineConfig | None = None,
    score_fn=calculate_score,
    top_n: int = 1,
) -> tuple[list[Trade], dict[str, float]]:
    """``run_buffered_backtest`` plus a turnover diagnostic.

    ``entries_per_period`` is exactly ``top_n`` when
    ``buffer_multiplier=None`` (every position closed and reopened
    every period, same as ``run_baseline_backtest``). A value below
    ``top_n`` is the number of round trips per period the buffer
    actually avoided -- multiplied by the round-trip cost, that is the
    saving this whole experiment is trying to measure.
    """
    config = config or BufferedBaselineConfig()

    (
        _universe,
        decision_indices,
        held_over_time,
        carried_over_time,
        meta_over_time,
        open_arrays,
        close_arrays,
    ) = _build_held_timeline(data_by_stock, config, score_fn, top_n)

    if not decision_indices:
        return [], {
            "periods": 0.0,
            "entries_per_period": float("nan"),
            "avg_positions_held": float("nan"),
        }

    trades = run_buffered_backtest(data_by_stock, config, score_fn, top_n)

    active_periods = [j for j, m in enumerate(meta_over_time) if m is not None]
    entry_counts = []
    held_counts = []
    for j in active_periods:
        # A real entry is anything held this period that wasn't
        # explicitly carried over by the buffer rule -- see the
        # is_entry/carried_over_time discussion in run_buffered_backtest.
        entries = len(held_over_time[j] - carried_over_time[j])
        entry_counts.append(entries)
        held_counts.append(len(held_over_time[j]))

    stats = {
        "periods": float(len(active_periods)),
        "entries_per_period": (
            float(sum(entry_counts)) / len(entry_counts) if entry_counts else float("nan")
        ),
        "avg_positions_held": (
            float(sum(held_counts)) / len(held_counts) if held_counts else float("nan")
        ),
    }
    return trades, stats
