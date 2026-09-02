import json
from pathlib import Path

from src.data.models import DailyBar
from src.features.target import TARGET_COLUMN, build_target


DATA_PATH = Path("data/processed/historical/005930.json")


def main() -> None:
    with DATA_PATH.open("r", encoding="utf-8") as f:
        raw_data = json.load(f)

    bars = [DailyBar(**row) for row in raw_data]

    target = build_target(bars)

    print(f"Loaded bars: {len(bars)}")
    print(f"Target rows: {len(target)}")
    print(f"Target column: {TARGET_COLUMN}")

    print("\nFirst 5 rows:")
    print(target.head().to_string(index=False))

    print("\nLast 10 rows:")
    print(target.tail(10).to_string(index=False))

    print("\nNaN count:")
    print(target[TARGET_COLUMN].isna().sum())

    print("\nTarget statistics:")
    print(target[TARGET_COLUMN].describe())


if __name__ == "__main__":
    main()