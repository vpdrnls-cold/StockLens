"""Historical backtesting for the rule-based StockLens baseline."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from src.ml.baseline import MOMENTUM_FEATURE, select_momentum_stock


DEFAULT_HOLDING_PERIOD = 5
DEFAULT_TRANSACTION_COST = 0.0
DEFAULT_SLIPPAGE = 0.0


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
    transaction_cost: float = DEFAULT_TRANSACTION_COST,
    slippage: float = DEFAULT_SLIPPAGE,
) -> BacktestResult:
    """Run the momentum baseline in chronological order.

    At each decision date, the stock with the highest 5-day return
    is selected. The position is held for ``holding_period`` trading
    days and evaluated using the forward close-to-close return.
    """

    _validate_input(dataset, holding_period)

    data = dataset.copy()
    data["trade_date"] = pd.to_datetime(data["trade_date"])

    data = data.sort_values(
        ["trade_date", "stock_code"]
    ).reset_index(drop=True)

    decision_dates = (
        data["trade_date"]
        .drop_duplicates()
        .sort_values()
        .tolist()
    )

    ranking_records: list[dict] = []
    records: list[dict] = []

    for index in range(
        0,
        len(decision_dates) - holding_period,
        holding_period,
    ):
        decision_date = decision_dates[index]
        exit_date = decision_dates[index + holding_period]

        decision_data = data.loc[
            data["trade_date"] == decision_date
        ].copy()

        selected_stock = select_momentum_stock(decision_data)

        selected_row = decision_data.loc[
            decision_data["stock_code"] == selected_stock
        ].iloc[0]

        exit_data = data.loc[
            (data["trade_date"] == exit_date)
            & (data["stock_code"] == selected_stock)
        ]

        if exit_data.empty:
            raise ValueError(
                f"Missing exit data for {selected_stock} "
                f"on {exit_date.date()}."
            )

        exit_row = exit_data.iloc[0]

        entry_price = float(selected_row["close_price"])
        exit_price = float(exit_row["close_price"])

        gross_return = exit_price / entry_price - 1.0

        net_return = (
            gross_return
            - transaction_cost
            - slippage
        )

        ranking = (
            decision_data[
                ["stock_code", MOMENTUM_FEATURE]
            ]
            .sort_values(
                MOMENTUM_FEATURE,
                ascending=False,
            )
            .reset_index(drop=True)
        )

        ranking["rank"] = ranking.index + 1

        rank_map = dict(
            zip(
                ranking["stock_code"],
                ranking["rank"],
            )
        )

        for _, row in ranking.iterrows():
            ranking_records.append(
                {
                    "decision_date": decision_date,
                    "stock_code": row["stock_code"],
                    "score": float(row[MOMENTUM_FEATURE]),
                    "rank": int(row["rank"]),
                }
            )

        records.append(
            {
                "decision_date": decision_date,
                "exit_date": exit_date,
                "stock_code": selected_stock,
                "score": float(
                    selected_row[MOMENTUM_FEATURE]
                ),
                "rank": int(rank_map[selected_stock]),
                "entry_price": entry_price,
                "exit_price": exit_price,
                "gross_return": gross_return,
                "net_return": net_return,
            }
        )

    trades = pd.DataFrame(records)

    if trades.empty:
        raise ValueError(
            "Not enough dates to run the backtest."
        )

    equity_curve = _build_equity_curve(trades)

    cumulative_return = (
        float(equity_curve["equity"].iloc[-1]) - 1.0
    )

    average_return = float(
        trades["net_return"].mean()
    )

    hit_rate = float(
        (trades["net_return"] > 0).mean()
    )

    max_drawdown = _calculate_max_drawdown(
        equity_curve["equity"]
    )

    rankings = pd.DataFrame(ranking_records)

    return BacktestResult(
        trades=trades,
        rankings=rankings,
        equity_curve=equity_curve,
        cumulative_return=cumulative_return,
        average_return=average_return,
        hit_rate=hit_rate,
        max_drawdown=max_drawdown,
    )


def _validate_input(
    dataset: pd.DataFrame,
    holding_period: int,
) -> None:
    if dataset.empty:
        raise ValueError("dataset must not be empty.")

    required_columns = {
        "trade_date",
        "stock_code",
        MOMENTUM_FEATURE,
        "close_price",
    }

    missing = required_columns - set(dataset.columns)

    if missing:
        raise ValueError(
            f"Missing required columns: {sorted(missing)}"
        )

    if holding_period <= 0:
        raise ValueError(
            "holding_period must be positive."
        )


def _build_equity_curve(
    trades: pd.DataFrame,
) -> pd.DataFrame:
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


def _calculate_max_drawdown(
    equity: pd.Series,
) -> float:
    running_max = equity.cummax()

    drawdown = equity / running_max - 1.0

    return float(drawdown.min())