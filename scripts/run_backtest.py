#HistoricalStorage -> 5개 종목 DailybBar 로드 -> build_combined_dataset 
# backtest용 close_price 연결 -> run_baseline_backtest -> 전체 test 기간 실행 -> 성과 출력

from __future__ import annotations

import pandas as pd

from src.data.dataset import build_combined_dataset, split_by_time
from src.data.storage import HistoricalStorage
from src.ml.backtest import run_baseline_backtest


STOCK_CODES = (
    "000660",
    "005380",
    "005930",
    "035420",
    "035720",
)


def main() -> None:
    storage = HistoricalStorage("data")

    stock_bars = {}

    for stock_code in STOCK_CODES:
        bars = storage.load_daily_bars(stock_code)
        stock_bars[stock_code] = bars

    dataset = build_combined_dataset(stock_bars)

    dataset = build_combined_dataset(stock_bars)

    dataset["trade_date"] = pd.to_datetime(dataset["trade_date"])

    # Backtest requires the closing price used for
    # T -> T+5 return calculation.
    close_prices = []

    for stock_code, bars in stock_bars.items():
        for bar in bars:
            close_prices.append(
                {
                    "trade_date": pd.Timestamp(bar.trade_date),
                    "stock_code": stock_code,
                    "close_price": float(bar.close_price),
                }
            )

    price_df = pd.DataFrame(close_prices)

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

    result = run_baseline_backtest(
        splits.test,
        holding_period=5,
        transaction_cost=0.0,
        slippage=0.0,
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
