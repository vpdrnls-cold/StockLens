from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable
import json
import math

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class BaselineConfig:
    """Baseline backtest assumptions."""

    lookback_days: int = 5
    holding_days: int = 5

    buy_fee: float = 0.00015
    sell_fee: float = 0.00015
    sell_tax: float = 0.0020

    buy_slippage: float = 0.0010
    sell_slippage: float = 0.0010

    # False (default): the original five-stock behavior -- every stock
    # must have a bar on every date the engine uses (inner join), and
    # exactly five stocks are required. Every result recorded in
    # CURRENT_STATUS.md items 14~26 was produced this way.
    #
    # True: any number of stocks with different listing dates. The
    # calendar is the union of all stocks' dates, and each decision date
    # only ranks the stocks that actually have the prices needed for
    # that trade (see ``run_baseline_backtest``). Without this, an
    # inner join over ~50 stocks would shrink the usable history to that
    # of the most recently listed stock.
    allow_partial_universe: bool = False


@dataclass(frozen=True)
class Trade:
    """One completed baseline trade.

    ``weight`` is the fraction of capital allocated to this trade for
    its holding period. Single-winner-takes-all backtests (top_n=1)
    always have weight=1.0; diversified backtests (top_n>1) split
    capital equally across the top_n picks for that decision date, so
    weight=1/top_n for each.
    """

    decision_date: pd.Timestamp
    stock_code: str

    score: float

    entry_date: pd.Timestamp
    entry_price: float

    exit_date: pd.Timestamp
    exit_price: float

    gross_return: float
    net_return: float

    weight: float = 1.0


def load_historical_data(path: str | Path) -> pd.DataFrame:
    """
    Load normalized historical daily bars.

    Expected schema:
        stock_code
        trade_date
        open_price
        close_price
    """
    path = Path(path)

    data = json.loads(path.read_text(encoding="utf-8"))

    if not isinstance(data, list):
        raise ValueError(f"Expected a list of daily bars: {path}")

    df = pd.DataFrame(data)

    required = {
        "stock_code",
        "trade_date",
        "open_price",
        "close_price",
    }

    missing = required - set(df.columns)

    if missing:
        raise ValueError(
            f"Missing required columns in {path}: {sorted(missing)}"
        )

    df["trade_date"] = pd.to_datetime(df["trade_date"])

    for column in ("open_price", "close_price"):
        df[column] = pd.to_numeric(df[column], errors="raise")

    df = df.sort_values("trade_date").reset_index(drop=True)

    if df["trade_date"].duplicated().any():
        raise ValueError(f"Duplicate trade dates found: {path}")

    return df


def prepare_universe(
    data_by_stock: dict[str, pd.DataFrame],
    *,
    how: str = "inner",
) -> pd.DataFrame:
    """
    Build the wide (one column pair per stock) price universe.

    ``how="inner"`` (default): only dates present for every stock are
    retained -- the original five-stock behavior.

    ``how="outer"``: the union of all stocks' dates is kept; a stock
    without a bar on a date has NaN there. Used with
    ``BaselineConfig.allow_partial_universe`` for larger universes whose
    members were listed at different times.
    """
    if how not in {"inner", "outer"}:
        raise ValueError(f"how must be 'inner' or 'outer', got {how!r}.")

    if not data_by_stock:
        raise ValueError("No historical data supplied.")

    frames = []

    for stock_code, df in data_by_stock.items():
        current = df.copy()

        if "stock_code" in current.columns:
            codes = current["stock_code"].astype(str).unique()

            if len(codes) != 1 or codes[0] != stock_code:
                raise ValueError(
                    f"Stock-code mismatch for {stock_code}: {codes}"
                )

        current = current[
            ["trade_date", "open_price", "close_price"]
        ].copy()

        current = current.rename(
            columns={
                "open_price": f"open_{stock_code}",
                "close_price": f"close_{stock_code}",
            }
        )

        frames.append(current)

    universe = frames[0]

    for frame in frames[1:]:
        universe = universe.merge(
            frame,
            on="trade_date",
            how=how,
            validate="one_to_one",
        )

    return universe.sort_values("trade_date").reset_index(drop=True)


def calculate_score(
    universe: pd.DataFrame,
    stock_code: str,
    decision_index: int,
    lookback_days: int = 5,
) -> float:
    """Calculate T-day 5-day momentum score."""

    if decision_index < lookback_days:
        raise ValueError("Not enough history for score calculation.")

    current_close = universe.iloc[decision_index][f"close_{stock_code}"]
    previous_close = universe.iloc[
        decision_index - lookback_days
    ][f"close_{stock_code}"]

    if previous_close <= 0:
        raise ValueError("Previous close must be positive.")

    return float(current_close / previous_close - 1.0)


def calculate_net_return(
    entry_price: float,
    exit_price: float,
    config: BaselineConfig,
) -> tuple[float, float]:
    """
    Calculate gross and cost-adjusted return.

    Entry:
        open * (1 + buy_slippage)

    Exit:
        close * (1 - sell_slippage)

    Fees/tax:
        buy_fee
        sell_fee
        sell_tax
    """

    effective_entry = entry_price * (1.0 + config.buy_slippage)

    effective_exit = (
        exit_price
        * (1.0 - config.sell_slippage)
        * (1.0 - config.sell_tax)
    )

    gross_return = effective_exit / effective_entry - 1.0

    net_return = (
        gross_return
        - config.buy_fee
        - config.sell_fee
    )

    return gross_return, net_return


def _eligible_scores(
    universe: pd.DataFrame,
    stock_codes: list[str],
    decision_index: int,
    entry_index: int,
    exit_index: int,
    lookback_days: int,
    score_fn: Callable[[pd.DataFrame, str, int, int], float],
    open_arrays: dict[str, np.ndarray],
    close_arrays: dict[str, np.ndarray],
) -> dict[str, float]:
    """Score only the stocks that can actually be traded on this date.

    A stock is eligible when it has a positive price for every value
    the trade needs (close at T-lookback and T for the score, open at
    T+1, close at T+holding) and ``score_fn`` can produce a finite
    score for it (a model score_fn raises ``KeyError`` where the
    feature warm-up left no prediction).
    """
    scores: dict[str, float] = {}

    for stock_code in stock_codes:
        closes = close_arrays[stock_code]
        needed = (
            closes[decision_index - lookback_days],
            closes[decision_index],
            open_arrays[stock_code][entry_index],
            closes[exit_index],
        )
        if not all(math.isfinite(value) and value > 0 for value in needed):
            continue

        try:
            score = score_fn(universe, stock_code, decision_index, lookback_days)
        except KeyError:
            continue

        if math.isfinite(score):
            scores[stock_code] = score

    return scores


def run_baseline_backtest(
    data_by_stock: dict[str, pd.DataFrame],
    config: BaselineConfig | None = None,
    score_fn: Callable[[pd.DataFrame, str, int, int], float] = calculate_score,
    top_n: int = 1,
) -> list[Trade]:
    """
    Run the rule-based baseline backtest.

    Decision:
        T-day after close / 15:30

    Score:
        ``score_fn(universe, stock_code, decision_index, lookback_days)``.
        Defaults to ``calculate_score`` (5-day momentum ending at T).
        Pass a different ``score_fn`` (e.g. one backed by model
        predictions) to reuse this same execution engine -- entry/exit
        timing, fees, tax, slippage -- for a different stock-picking
        rule.

    Entry:
        T+1 open

    Exit:
        T+5 close

    Rebalance:
        Every 5 trading days

    Allocation:
        ``top_n=1`` (default) goes all-in on the single highest-scored
        stock, as before. ``top_n>1`` equal-weights the top ``top_n``
        scored stocks (1/top_n capital each) for that decision date --
        one Trade per stock, each carrying its ``weight``. Use
        ``calculate_performance`` to combine same-date trades into a
        single portfolio-level return per period; treating each Trade
        as its own period would double-count capital.

    Universe size:
        By default exactly five stocks, all required to have a bar on
        every used date. With ``config.allow_partial_universe=True`` any
        number of stocks is accepted; each decision date then ranks only
        the stocks with valid prices for that whole trade, and a date
        with fewer than ``top_n`` such stocks is skipped (cash).
    """

    config = config or BaselineConfig()

    stock_codes = list(data_by_stock.keys())
    partial = config.allow_partial_universe

    if not partial and len(stock_codes) != 5:
        raise ValueError(
            f"Baseline expects five stocks, got {len(stock_codes)}. "
            "Set BaselineConfig(allow_partial_universe=True) for a "
            "larger universe."
        )

    if not (1 <= top_n <= len(stock_codes)):
        raise ValueError(
            f"top_n must be between 1 and {len(stock_codes)}, got {top_n}."
        )

    universe = prepare_universe(
        data_by_stock, how="outer" if partial else "inner"
    )

    required_rows = (
        config.lookback_days
        + 1
        + config.holding_days
    )

    if len(universe) < required_rows:
        return []

    if partial:
        open_arrays = {
            code: universe[f"open_{code}"].to_numpy(dtype=float)
            for code in stock_codes
        }
        close_arrays = {
            code: universe[f"close_{code}"].to_numpy(dtype=float)
            for code in stock_codes
        }

    trades: list[Trade] = []

    # T must have:
    #   T-lookback_days
    #   T+1
    #   T+holding_days
    #
    # We move the decision point by holding_days so that
    # positions do not overlap.
    first_decision_index = config.lookback_days
    last_decision_index = (
        len(universe) - config.holding_days - 1
    )

    weight = 1.0 / top_n

    for decision_index in range(
        first_decision_index,
        last_decision_index + 1,
        config.holding_days,
    ):
        decision_date = universe.iloc[decision_index]["trade_date"]

        entry_index = decision_index + 1
        exit_index = decision_index + config.holding_days

        if partial:
            scores = _eligible_scores(
                universe,
                stock_codes,
                decision_index,
                entry_index,
                exit_index,
                config.lookback_days,
                score_fn,
                open_arrays,
                close_arrays,
            )
            # Not enough tradable stocks on this date -> stay in cash
            # for this period instead of holding fewer than top_n names.
            if len(scores) < top_n:
                continue
        else:
            scores = {
                stock_code: score_fn(
                    universe,
                    stock_code,
                    decision_index,
                    config.lookback_days,
                )
                for stock_code in stock_codes
            }

        selected_stocks = sorted(
            scores, key=scores.get, reverse=True
        )[:top_n]

        entry_date = universe.iloc[entry_index]["trade_date"]
        exit_date = universe.iloc[exit_index]["trade_date"]

        for selected_stock in selected_stocks:
            entry_price = float(
                universe.iloc[entry_index][f"open_{selected_stock}"]
            )

            exit_price = float(
                universe.iloc[exit_index][f"close_{selected_stock}"]
            )

            if entry_price <= 0 or exit_price <= 0:
                raise ValueError(
                    f"Invalid entry/exit price for {selected_stock}"
                )

            gross_return, net_return = calculate_net_return(
                entry_price,
                exit_price,
                config,
            )

            trades.append(
                Trade(
                    decision_date=decision_date,
                    stock_code=selected_stock,
                    score=scores[selected_stock],
                    entry_date=entry_date,
                    entry_price=entry_price,
                    exit_date=exit_date,
                    exit_price=exit_price,
                    gross_return=gross_return,
                    net_return=net_return,
                    weight=weight,
                )
            )

    return trades


def trades_to_dataframe(trades: list[Trade]) -> pd.DataFrame:
    """Convert trades into a DataFrame for analysis/export."""

    if not trades:
        return pd.DataFrame(
            columns=[
                "decision_date",
                "stock_code",
                "score",
                "entry_date",
                "entry_price",
                "exit_date",
                "exit_price",
                "gross_return",
                "net_return",
                "weight",
            ]
        )

    return pd.DataFrame(
        [
            {
                "decision_date": trade.decision_date,
                "stock_code": trade.stock_code,
                "score": trade.score,
                "entry_date": trade.entry_date,
                "entry_price": trade.entry_price,
                "exit_date": trade.exit_date,
                "exit_price": trade.exit_price,
                "gross_return": trade.gross_return,
                "net_return": trade.net_return,
                "weight": trade.weight,
            }
            for trade in trades
        ]
    )


def calculate_performance(
    trades: list[Trade],
    initial_capital: float = 10_000_000.0,
) -> dict[str, float]:
    """Calculate basic baseline performance metrics.

    Trades are grouped by ``decision_date`` first, and each period's
    portfolio return is the weight-averaged net_return of that
    period's trades (weights sum to 1.0 within a period by
    construction -- see ``run_baseline_backtest``). Equity compounds
    once per period, not once per individual trade -- with
    ``top_n>1`` a single period holds multiple simultaneous
    positions, and treating each as its own compounding step would
    double- (or triple-, or ...-) count capital.
    """

    if initial_capital <= 0:
        raise ValueError("Initial capital must be positive.")

    if not trades:
        return {
            "trade_count": 0.0,
            "period_count": 0.0,
            "total_return": 0.0,
            "win_rate": 0.0,
            "average_trade_return": 0.0,
            "max_drawdown": 0.0,
        }

    trades_df = trades_to_dataframe(trades)

    period_returns = (
        trades_df.groupby("decision_date")
        .apply(
            lambda group: float(
                (group["weight"] * group["net_return"]).sum()
            )
        )
        .sort_index()
    )

    equity = initial_capital * (1.0 + period_returns).cumprod()

    total_return = float(equity.iloc[-1] / initial_capital - 1.0)

    win_rate = float((period_returns > 0).mean())

    average_trade_return = float(period_returns.mean())

    running_max = equity.cummax()
    drawdown = equity / running_max - 1.0
    max_drawdown = float(drawdown.min())

    return {
        "trade_count": float(len(trades)),
        "period_count": float(len(period_returns)),
        "total_return": total_return,
        "win_rate": win_rate,
        "average_trade_return": average_trade_return,
        "max_drawdown": max_drawdown,
    }