"""Daily mark-to-market equity and drawdown for engine trades (CURRENT_STATUS item 80, item 78 A3).

The engines compound once per 5-day period, so ``calculate_performance()['max_drawdown']``
only sees period-end equity and misses drawdowns inside a holding period. This module
rebuilds a daily equity curve from the same ``Trade`` list -- reporting only; no engine,
rule or trade changes.

Definition (fixed here, item 80)
  For a period with start equity E and positions i (weight w_i = 1/top_n, unused weight
  stays in cash), the value on trading day d in [entry_date, exit_date] is

      E * (1 + sum_i w_i * v_i(d)),   v_i(d) = (1 + net_i) * close_i(d) / close_i(exit_date) - 1

  so on the exit date it equals the engine's period return exactly (costs included), and
  inside the period it follows each stock's close-to-close path. Between one period's exit
  close and the next period's entry the portfolio is flat (cash), as in the engine.
  The overnight gap from the exit close to the next entry is therefore not marked.
"""

from __future__ import annotations

import pandas as pd

from src.backtest.baseline import Trade, trades_to_dataframe


def _close_series(data_by_stock: dict[str, pd.DataFrame]) -> dict[str, pd.Series]:
    out = {}
    for code, df in data_by_stock.items():
        s = df[["trade_date", "close_price"]].copy()
        s["trade_date"] = pd.to_datetime(s["trade_date"])
        out[str(code)] = s.set_index("trade_date")["close_price"].astype(float).sort_index()
    return out


def daily_equity(
    trades: list[Trade],
    data_by_stock: dict[str, pd.DataFrame],
    initial_capital: float = 1.0,
) -> pd.Series:
    """Daily equity indexed by trading date (period-end values match calculate_performance)."""
    if not trades:
        return pd.Series(dtype="float64", name="equity")
    closes = _close_series(data_by_stock)
    df = trades_to_dataframe(trades)
    df["entry_date"] = pd.to_datetime(df["entry_date"])
    df["exit_date"] = pd.to_datetime(df["exit_date"])

    equity = float(initial_capital)
    values: dict[pd.Timestamp, float] = {}
    for _, group in df.sort_values("decision_date").groupby("decision_date", sort=True):
        cols = {}
        for row in group.itertuples():
            px = closes[str(row.stock_code)].loc[row.entry_date:row.exit_date]
            v = (1.0 + row.net_return) * px / float(px.loc[row.exit_date]) - 1.0
            cols[row.Index] = row.weight * v
        # a stock without a bar on some day keeps its last value (0 before its first bar)
        path = pd.DataFrame(cols).sort_index().ffill().fillna(0.0).sum(axis=1)
        for d, r in path.items():
            values[d] = equity * (1.0 + float(r))
        period_return = float((group["weight"] * group["net_return"]).sum())
        equity *= 1.0 + period_return
    return pd.Series(values, name="equity").sort_index()


def max_drawdown(equity: pd.Series, initial_capital: float = 1.0) -> float:
    """Most negative peak-to-trough fall of ``equity``.

    The starting peak is the initial capital, so a loss in the very first period counts.
    (``calculate_performance`` takes the running max of period-end equity only, so its
    first period cannot register as a drawdown -- one reason the two can differ.)
    """
    if equity.empty:
        return 0.0
    peak = equity.cummax().clip(lower=float(initial_capital))
    return float((equity / peak - 1.0).min())


def daily_max_drawdown(trades: list[Trade], data_by_stock: dict[str, pd.DataFrame]) -> float:
    return max_drawdown(daily_equity(trades, data_by_stock))
