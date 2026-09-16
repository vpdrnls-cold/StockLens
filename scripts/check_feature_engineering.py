import json
from pathlib import Path

from src.data.models import DailyBar
from src.features.engineering import FEATURE_COLUMNS, build_features


DATA_PATH = Path("data/processed/historical/005930.json")


def main() -> None:
    with DATA_PATH.open("r", encoding="utf-8") as f:
        raw_data = json.load(f)

    bars = [DailyBar(**row) for row in raw_data]

    print(f"Loaded bars: {len(bars)}")

    features = build_features(bars)

    print(f"Feature rows: {len(features)}")
    print(f"Feature columns: {len(FEATURE_COLUMNS)}")

    print("\nFeature columns:")
    for column in FEATURE_COLUMNS:
        print(f"  - {column}")

    print("\nLast 5 rows:")
    print(features.tail().to_string(index=False))

    print("\nNaN counts:")
    print(features[list(FEATURE_COLUMNS)].isna().sum())

    print("\nLatest feature row:")
    print(features.iloc[-1].to_string())


if __name__ == "__main__":
    main()