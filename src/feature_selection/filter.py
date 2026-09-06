import pandas as pd
from pathlib import Path

from .pearson import calculate_pearson, calculate_feature_correlation

from src.feature_selection.pearson import calculate_pearson


DATA_PATH = Path("data/processed/ml_dataset.csv")


def load_data():
    df = pd.read_csv(DATA_PATH)

    print("Shape:", df.shape)

    return df


def main():
    df = load_data()

    print(df.columns.tolist())
    target = df["target_return_5d"]

    features = df.drop(
        columns=["stock_code", "trade_date", "target_return_5d"]
    )

    # Pearson 계산
    pearson_result = calculate_pearson(features, target)

    print("\nPearson Correlation:")
    print(pearson_result)

    output_path = Path("data/processed/filter_pearson.csv")
    pearson_result.to_csv(output_path, index=False)

    print("Saved:", output_path)

    feature_correlation = calculate_feature_correlation(features)

    print("\nFeature-Feature Pearson Correlation:")
    print(feature_correlation)

    # Pearson: feature → target
    pearson_result = calculate_pearson(features, target)

    print("\nPearson Correlation:")
    print(pearson_result)


    # Pearson: feature ↔ feature
    feature_correlation = calculate_feature_correlation(features)

    print("\nFeature-Feature Pearson Correlation:")
    print(feature_correlation)


    # Save Pearson results
    output_dir = Path("data/processed/filter_results")
    output_dir.mkdir(parents=True, exist_ok=True)

    pearson_result.to_csv(
        output_dir / "pearson_target.csv",
        index=False
    )

    feature_correlation.to_csv(
        output_dir / "pearson_feature_correlation.csv"
    )

    print("\nPearson results saved.")


if __name__ == "__main__":
    main()