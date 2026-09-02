import pandas as pd
import pytest

from src.ml.baseline import select_momentum_stock


def test_select_momentum_stock() -> None:
    data = pd.DataFrame(
        {
            "stock_code": [
                "000660",
                "005380",
                "005930",
            ],
            "return_5d": [
                0.02,
                0.08,
                -0.01,
            ],
        }
    )

    selected = select_momentum_stock(data)

    assert selected == "005380"


def test_select_momentum_stock_rejects_empty_data() -> None:
    data = pd.DataFrame(
        columns=[
            "stock_code",
            "return_5d",
        ]
    )

    with pytest.raises(ValueError):
        select_momentum_stock(data)


def test_select_momentum_stock_rejects_missing_columns() -> None:
    data = pd.DataFrame(
        {
            "stock_code": ["005930"],
        }
    )

    with pytest.raises(ValueError):
        select_momentum_stock(data)