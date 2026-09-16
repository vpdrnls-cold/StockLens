"""ML-pipeline adapter for the canonical rule-based baseline backtest.

The canonical backtest implementation lives in ``src.backtest.baseline``.
It is the more complete implementation: T+1 open entry, T+holding_days
close exit, explicit buy/sell fees, sell tax, and slippage.

This module does NOT reimplement scoring or return-calculation logic.
It only reshapes the long-format ("tidy") dataset produced by the
StockLens feature pipeline -- one row per (trade_date, stock_code) --
into the per-stock dict shape ``src.backtest.baseline`` expects, calls
the canonical backtest, and reshapes the result back into the
``BacktestResult`` interface that ``scripts/run_backtest.py`` and the
ML pipeline already rely on.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from src.backtest.baseline import (
    BaselineConfig,
    calculate_score,
    prepare_universe,
    run_baseline_backtest as _run_canonical_backtest,
)

DEFAULT_HOLDING_PERIOD = 5


@dataclass(frozen=True)
class BacktestResult:
    """Backtest result containing trade-level records and summary metrics."""

    trades: pd.DataFrame
    rankings: pd.DataFrame
    equity_curve: pd.DataFrame
    cumulative_return: float
    average_return: float
    hit_rate: float
    max_drawdown: float


def run_baseline_backtest(
    dataset: pd.DataFrame,
    *,
    holding_period: int = DEFAULT_HOLDING_PERIOD,
    config: BaselineConfig | None = None,
) -> BacktestResult:
    """Run the canonical rule-based baseline on a long-format dataset.

    ``dataset`` must be in tidy form, with columns ``trade_date``,
    ``stock_code``, ``open_price``, ``close_price`` -- exactly five
    stock codes, matching ``src.backtest.baseline``'s requirement.

    ``holding_period`` sets both the lookback window used for scoring
    and the holding period, unless an explicit ``config`` is supplied
    (in which case ``config`` wins and ``holding_period`` is ignored).
    """

    _validate_input(dataset)

    config = config or BaselineConfig(
        lookback_days=holding_period,
        holding_days=holding_period,
    )

    data_by_stock = _to_data_by_stock(dataset)

    trades = _run_canonical_backtest(data_by_stock, config=config)

    if not trades:
        raise ValueError("Not enough dates to run the backtest.")

    trades_df = pd.DataFrame(
        [
            {
                "decision_date": trade.decision_date,
                "exit_date": trade.exit_date,
                "stock_code": trade.stock_code,
                "score": trade.score,
                "entry_price": trade.entry_price,
                "exit_price": trade.exit_price,
                "gross_return": trade.gross_return,
                "net_return": trade.net_return,
            }
            for trade in trades
        ]
    )

    rankings = _build_rankings(
        data_by_stock,
        decision_dates=trades_df["decision_date"],
        lookback_days=config.lookback_days,
    )

    trades_df = trades_df.merge(
        rankings[["decision_date", "stock_code", "rank"]],
        on=["decision_date", "stock_code"],
        how="left",
    )

    equity_curve = _build_equity_curve(trades_df)

    cumulative_return = float(equity_curve["equity"].iloc[-1]) - 1.0
    average_return = float(trades_df["net_return"].mean())
    hit_rate = float((trades_df["net_return"] > 0).mean())
    max_drawdown = _calculate_max_drawdown(equity_curve["equity"])

    return BacktestResult(
        trades=trades_df,
        rankings=rankings,
        equity_curve=equity_curve,
        cumulative_return=cumulative_return,
        average_return=average_return,
        hit_rate=hit_rate,
        max_drawdown=max_drawdown,
    )


def _validate_input(dataset: pd.DataFrame) -> None:
    if dataset.empty:
        raise ValueError("dataset must not be empty.")

    required_columns = {
        "trade_date",
        "stock_code",
        "open_price",
        "close_price",
    }

    missing = required_columns - set(dataset.columns)

    if missing:
        raise ValueError(f"Missing required columns: {sorted(missing)}")


def _to_data_by_stock(dataset: pd.DataFrame) -> dict[str, pd.DataFrame]:
    data = dataset.copy()
    data["trade_date"] = pd.to_datetime(data["trade_date"])

    data_by_stock: dict[str, pd.DataFrame] = {}

    for stock_code, group in data.groupby("stock_code"):
        data_by_stock[str(stock_code)] = (
            group[["stock_code", "trade_date", "open_price", "close_price"]]
            .sort_values("trade_date")
            .reset_index(drop=True)
        )

    return data_by_stock


def _build_rankings(
    data_by_stock: dict[str, pd.DataFrame],
    decision_dates: pd.Series,
    lookback_days: int,
) -> pd.DataFrame:
    """Rank every stock (not just the winner) at each decision date.

    Uses the same ``calculate_score`` the canonical backtest uses to
    pick the winner, so rankings are always consistent with trades.
    """

    universe = prepare_universe(data_by_stock)
    stock_codes = list(data_by_stock.keys())

    date_to_index = {
        date: index for index, date in enumerate(universe["trade_date"])
    }

    records = []

    for decision_date in decision_dates.drop_duplicates():
        decision_index = date_to_index[decision_date]

        scores = {
            stock_code: calculate_score(
                universe, stock_code, decision_index, lookback_days
            )
            for stock_code in stock_codes
        }

        ranked = sorted(
            scores.items(), key=lambda item: item[1], reverse=True
        )

        for rank, (stock_code, score) in enumerate(ranked, start=1):
            records.append(
                {
                    "decision_date": decision_date,
                    "stock_code": stock_code,
                    "score": score,
                    "rank": rank,
                }
            )

    return pd.DataFrame(records)


def _build_equity_curve(trades: pd.DataFrame) -> pd.DataFrame:
    equity = 1.0
    records = []

    for _, trade in trades.iterrows():
        equity *= 1.0 + float(trade["net_return"])

        records.append(
            {
                "date": trade["exit_date"],
                "equity": equity,
            }
        )

    return pd.DataFrame(records)


def _calculate_max_drawdown(equity: pd.Series) -> float:
    running_max = equity.cummax()
    drawdown = equity / running_max - 1.0
    return float(drawdown.min())
