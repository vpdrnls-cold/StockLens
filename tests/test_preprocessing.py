import pandas as pd

from src.features.engineering import FEATURE_COLUMNS
from src.ml.preprocessing import create_preprocessor


def _make_dataset(
    rows: int,
    *,
    feature_value: float,
) -> pd.DataFrame:
    data = {
        column: [feature_value] * rows
        for column in FEATURE_COLUMNS
    }

    data["stock_code"] = ["005930"] * rows
    data["trade_date"] = pd.date_range(
        "2025-01-01",
        periods=rows,
        freq="D",
    )
    data["target_return_5d"] = [0.01] * rows

    return pd.DataFrame(data)


def test_preprocessor_fits_on_train_only() -> None:
    train = _make_dataset(10, feature_value=10.0)
    validation = _make_dataset(10, feature_value=1000.0)

    preprocessor = create_preprocessor()

    transformed_train = preprocessor.fit_transform(train)
    transformed_validation = preprocessor.transform(validation)

    # Train 기준으로 standardization되므로 train 평균은 0이어야 한다.
    for column in FEATURE_COLUMNS:
        assert abs(transformed_train[column].mean()) < 1e-9

    # Validation의 값으로 scaler를 다시 fit하지 않았으므로
    # validation 값은 train 기준으로 크게 변환된다.
    for column in FEATURE_COLUMNS:
        assert transformed_validation[column].abs().mean() > 1.0


def test_transform_does_not_change_target() -> None:
    train = _make_dataset(10, feature_value=10.0)

    preprocessor = create_preprocessor()
    transformed = preprocessor.fit_transform(train)

    pd.testing.assert_series_equal(
        transformed["target_return_5d"],
        train["target_return_5d"],
    )


def test_transform_does_not_change_metadata() -> None:
    train = _make_dataset(10, feature_value=10.0)

    preprocessor = create_preprocessor()
    transformed = preprocessor.fit_transform(train)

    pd.testing.assert_series_equal(
        transformed["stock_code"],
        train["stock_code"],
    )

    pd.testing.assert_series_equal(
        transformed["trade_date"],
        train["trade_date"],
    )