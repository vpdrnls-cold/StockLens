import pandas as pd
from pathlib import Path

from .pearson import calculate_pearson, calculate_feature_correlation
from .spearman import (
    calculate_spearman,
    calculate_feature_correlation as calculate_spearman_feature_correlation,
)


DATA_PATH = Path("data/processed/ml_dataset.csv")
OUTPUT_DIR = Path("data/processed/filter_results")


def load_data():
    df = pd.read_csv(DATA_PATH)

    print("Shape:", df.shape)

    return df


def main():
    df = load_data()

    target = df["target_return_5d"]

    features = df.drop(
        columns=["stock_code", "trade_date", "target_return_5d"]
    )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Pearson: feature → target
    pearson_result = calculate_pearson(features, target)

    print("\nPearson Correlation:")
    print(pearson_result)

    pearson_result.to_csv(
        OUTPUT_DIR / "pearson_target.csv",
        index=False,
    )

    # Pearson: feature ↔ feature
    pearson_feature_correlation = calculate_feature_correlation(features)

    print("\nFeature-Feature Pearson Correlation:")
    print(pearson_feature_correlation)

    pearson_feature_correlation.to_csv(
        OUTPUT_DIR / "pearson_feature_correlation.csv"
    )

    # Spearman: feature → target
    spearman_result = calculate_spearman(features, target)

    print("\nSpearman Correlation:")
    print(spearman_result)

    spearman_result.to_csv(
        OUTPUT_DIR / "spearman_target.csv",
        index=False,
    )

    # Spearman: feature ↔ feature
    spearman_feature_correlation = calculate_spearman_feature_correlation(
        features
    )

    print("\nFeature-Feature Spearman Correlation:")
    print(spearman_feature_correlation)

    spearman_feature_correlation.to_csv(
        OUTPUT_DIR / "spearman_feature_correlation.csv"
    )

    print("\nFilter correlation results saved.")


if __name__ == "__main__":
    main()