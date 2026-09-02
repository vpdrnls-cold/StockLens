from __future__ import annotations

from src.data.dataset import build_combined_dataset, split_by_time
from src.data.storage import HistoricalStorage


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

        print(
            f"{stock_code}: "
            f"{len(bars)} bars, "
            f"{bars[0].trade_date} ~ {bars[-1].trade_date}"
        )

    dataset = build_combined_dataset(stock_bars)

    print()
    print("=== Combined Dataset ===")
    print(f"rows: {len(dataset)}")
    print(f"columns: {len(dataset.columns)}")
    print(f"stocks: {dataset['stock_code'].nunique()}")
    print(
        f"date range: "
        f"{dataset['trade_date'].min()} ~ "
        f"{dataset['trade_date'].max()}"
    )

    print()
    print("Rows by stock:")
    print(dataset["stock_code"].value_counts().sort_index())

    splits = split_by_time(dataset)

    print()
    print("=== Time Split ===")

    for name, split in (
        ("Train", splits.train),
        ("Validation", splits.validation),
        ("Test", splits.test),
    ):
        print(
            f"{name}: "
            f"{len(split)} rows | "
            f"{split['trade_date'].min()} ~ "
            f"{split['trade_date'].max()}"
        )

        print(
            split["stock_code"]
            .value_counts()
            .sort_index()
            .to_dict()
        )


if __name__ == "__main__":
    main()