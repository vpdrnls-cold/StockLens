from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json

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


@dataclass(frozen=True)
class Trade:
    """One completed baseline trade."""

    decision_date: pd.Timestamp
    stock_code: str

    score: float

    entry_date: pd.Timestamp
    entry_price: float

    exit_date: pd.Timestamp
    exit_price: float

    gross_return: float
    net_return: float


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
) -> pd.DataFrame:
    """
    Build a common-date universe for the five stocks.

    Only dates present for every stock are retained.
    """
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
            how="inner",
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


def run_baseline_backtest(
    data_by_stock: dict[str, pd.DataFrame],
    config: BaselineConfig | None = None,
) -> list[Trade]:
    """
    Run the rule-based baseline backtest.

    Decision:
        T-day after close / 15:30

    Score:
        5-day return ending at T

    Entry:
        T+1 open

    Exit:
        T+5 close

    Rebalance:
        Every 5 trading days
    """

    config = config or BaselineConfig()

    stock_codes = list(data_by_stock.keys())

    if len(stock_codes) != 5:
        raise ValueError(
            f"Baseline expects five stocks, got {len(stock_codes)}."
        )

    universe = prepare_universe(data_by_stock)

    required_rows = (
        config.lookback_days
        + 1
        + config.holding_days
    )

    if len(universe) < required_rows:
        return []

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

    for decision_index in range(
        first_decision_index,
        last_decision_index + 1,
        config.holding_days,
    ):
        decision_date = universe.iloc[decision_index]["trade_date"]

        scores = {
            stock_code: calculate_score(
                universe,
                stock_code,
                decision_index,
                config.lookback_days,
            )
            for stock_code in stock_codes
        }

        selected_stock = max(scores, key=scores.get)

        entry_index = decision_index + 1
        exit_index = decision_index + config.holding_days

        entry_date = universe.iloc[entry_index]["trade_date"]
        exit_date = universe.iloc[exit_index]["trade_date"]

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
            }
            for trade in trades
        ]
    )


def calculate_performance(
    trades: list[Trade],
    initial_capital: float = 10_000_000.0,
) -> dict[str, float]:
    """Calculate basic baseline performance metrics."""

    if initial_capital <= 0:
        raise ValueError("Initial capital must be positive.")

    if not trades:
        return {
            "trade_count": 0.0,
            "total_return": 0.0,
            "win_rate": 0.0,
            "average_trade_return": 0.0,
            "max_drawdown": 0.0,
        }

    returns = pd.Series(
        [trade.net_return for trade in trades],
        dtype=float,
    )

    equity = initial_capital * (1.0 + returns).cumprod()

    total_return = float(equity.iloc[-1] / initial_capital - 1.0)

    win_rate = float((returns > 0).mean())

    average_trade_return = float(returns.mean())

    running_max = equity.cummax()
    drawdown = equity / running_max - 1.0
    max_drawdown = float(drawdown.min())

    return {
        "trade_count": float(len(trades)),
        "total_return": total_return,
        "win_rate": win_rate,
        "average_trade_return": average_trade_return,
        "max_drawdown": max_drawdown,
    }