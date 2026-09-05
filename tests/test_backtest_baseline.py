import pandas as pd
import pytest

from src.backtest.baseline import (
    BaselineConfig,
    calculate_net_return,
    calculate_score,
    run_baseline_backtest,
)


def make_stock_data(
    stock_code: str,
    closes: list[float],
    opens: list[float] | None = None,
) -> pd.DataFrame:
    if opens is None:
        opens = closes

    dates = pd.date_range(
        "2026-01-01",
        periods=len(closes),
        freq="B",
    )

    return pd.DataFrame(
        {
            "stock_code": stock_code,
            "trade_date": dates,
            "open_price": opens,
            "close_price": closes,
        }
    )


def test_calculate_score():
    df = pd.DataFrame(
        {
            "trade_date": pd.date_range(
                "2026-01-01",
                periods=6,
                freq="B",
            ),
            "close_A": [100, 100, 100, 100, 100, 110],
        }
    )

    score = calculate_score(
        df,
        "A",
        decision_index=5,
        lookback_days=5,
    )

    assert score == pytest.approx(0.10)


def test_calculate_net_return_applies_costs():
    config = BaselineConfig(
        buy_fee=0.001,
        sell_fee=0.001,
        sell_tax=0.002,
        buy_slippage=0.001,
        sell_slippage=0.001,
    )

    gross, net = calculate_net_return(
        entry_price=100.0,
        exit_price=110.0,
        config=config,
    )

    expected_entry = 100.0 * 1.001
    expected_exit = 110.0 * 0.999 * 0.998

    expected_gross = expected_exit / expected_entry - 1.0
    expected_net = expected_gross - 0.001 - 0.001

    assert gross == pytest.approx(expected_gross)
    assert net == pytest.approx(expected_net)


def test_baseline_selects_highest_five_day_momentum():
    stock_a = make_stock_data(
        "A",
        [100, 100, 100, 100, 100, 105, 105, 105, 105, 105, 105, 105],
    )

    stock_b = make_stock_data(
        "B",
        [100, 100, 100, 100, 100, 120, 120, 120, 120, 120, 120, 120],
    )

    stock_c = make_stock_data(
        "C",
        [100] * 12,
    )

    stock_d = make_stock_data(
        "D",
        [100] * 12,
    )

    stock_e = make_stock_data(
        "E",
        [100] * 12,
    )

    data = {
        "A": stock_a,
        "B": stock_b,
        "C": stock_c,
        "D": stock_d,
        "E": stock_e,
    }

    trades = run_baseline_backtest(
        data,
        BaselineConfig(
            buy_fee=0.0,
            sell_fee=0.0,
            sell_tax=0.0,
            buy_slippage=0.0,
            sell_slippage=0.0,
        ),
    )

    assert trades
    assert trades[0].stock_code == "B"


def test_rebalance_every_five_trading_days():
    stocks = {
        code: make_stock_data(
            code,
            [100 + i for i in range(20)],
        )
        for code in ["A", "B", "C", "D", "E"]
    }

    trades = run_baseline_backtest(
        stocks,
        BaselineConfig(
            buy_fee=0.0,
            sell_fee=0.0,
            sell_tax=0.0,
            buy_slippage=0.0,
            sell_slippage=0.0,
        ),
    )

    assert len(trades) >= 2

    for previous, current in zip(trades, trades[1:]):
        assert (
            current.decision_date - previous.decision_date
        ).days >= 5