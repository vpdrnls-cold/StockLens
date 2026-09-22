#HistoricalStorage -> 5개 종목 DailybBar 로드 -> build_combined_dataset 
# backtest용 close_price 연결 -> run_baseline_backtest -> 전체 test 기간 실행 -> 성과 출력

from __future__ import annotations

import pandas as pd

from src.backtest.baseline import BaselineConfig
from src.data.dataset import build_combined_dataset, split_by_time
from src.data.storage import HistoricalStorage
from src.data.universe import get_universe
from src.ml.backtest import run_baseline_backtest


# core5 by default; STOCKLENS_UNIVERSE=top50 selects the 50-stock universe
# (see src/data/universe.py).
STOCK_CODES = get_universe()


def main() -> None:
    storage = HistoricalStorage("data")

    stock_bars = {}

    for stock_code in STOCK_CODES:
        bars = storage.load_daily_bars(stock_code)
        stock_bars[stock_code] = bars

    dataset = build_combined_dataset(stock_bars)

    dataset["trade_date"] = pd.to_datetime(dataset["trade_date"])

    # Backtest requires open_price (T+1 entry) and close_price
    # (T+holding_days exit) for the canonical backtest.
    prices = []

    for stock_code, bars in stock_bars.items():
        for bar in bars:
            prices.append(
                {
                    "trade_date": pd.Timestamp(bar.trade_date),
                    "stock_code": stock_code,
                    "open_price": float(bar.open_price),
                    "close_price": float(bar.close_price),
                }
            )

    price_df = pd.DataFrame(prices)

    dataset = dataset.merge(
        price_df,
        on=["trade_date", "stock_code"],
        how="left",
        validate="one_to_one",
    )

    splits = split_by_time(dataset)

    print("=== Baseline Backtest ===")
    print(
        f"Test period: "
        f"{splits.test['trade_date'].min()} ~ "
        f"{splits.test['trade_date'].max()}"
    )

    config = BaselineConfig(
        lookback_days=5,
        holding_days=5,
        buy_fee=0.00015,
        sell_fee=0.00015,
        sell_tax=0.0020,
        buy_slippage=0.0010,
        sell_slippage=0.0010,
        allow_partial_universe=len(STOCK_CODES) != 5,
    )

    result = run_baseline_backtest(
        splits.test,
        config=config,
    )

    print()
    print("=== Performance ===")
    print(
        f"Cumulative Return: "
        f"{result.cumulative_return:.4%}"
    )
    print(
        f"Average Return: "
        f"{result.average_return:.4%}"
    )
    print(
        f"Hit Rate: "
        f"{result.hit_rate:.4%}"
    )
    print(
        f"Maximum Drawdown: "
        f"{result.max_drawdown:.4%}"
    )

    print()
    print("=== Trades ===")
    print(result.trades.to_string(index=False))

    print()
    print("=== Rankings ===")
    print(result.rankings.to_string(index=False))


if __name__ == "__main__":
    main()
