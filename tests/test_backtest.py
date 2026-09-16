from __future__ import annotations

import pandas as pd
import pytest

from src.backtest.baseline import BaselineConfig
from src.ml.backtest import run_baseline_backtest


def _make_dataset() -> pd.DataFrame:
    """Deterministic 5-stock tidy dataset.

    005380 always has the strongest lookback momentum, so it should
    always be selected. open_price == close_price so entry/exit math
    is easy to hand-check.
    """

    dates = pd.bdate_range("2026-07-01", periods=16)

    codes = ["000660", "005380", "005930", "035420", "035720"]

    rows = []

    for i, date in enumerate(dates):
        for code in codes:
            if code == "005380":
                close = 100.0 + i * 2
            elif code == "000660":
                close = 100.0 + i
            else:
                close = 100.0 - i * 0.1

            rows.append(
                {
                    "trade_date": date,
                    "stock_code": code,
                    "open_price": close,
                    "close_price": close,
                }
            )

    return pd.DataFrame(rows)


def _zero_cost_config(holding_period: int = 5) -> BaselineConfig:
    return BaselineConfig(
        lookback_days=holding_period,
        holding_days=holding_period,
        buy_fee=0.0,
        sell_fee=0.0,
        sell_tax=0.0,
        buy_slippage=0.0,
        sell_slippage=0.0,
    )


def test_backtest_selects_highest_momentum_stock() -> None:
    dataset = _make_dataset()

    result = run_baseline_backtest(dataset, config=_zero_cost_config())

    assert not result.trades.empty
    assert set(result.trades["stock_code"]) == {"005380"}


def test_backtest_rankings_cover_every_stock_every_date() -> None:
    dataset = _make_dataset()

    result = run_baseline_backtest(dataset, config=_zero_cost_config())

    n_decisions = result.trades["decision_date"].nunique()

    assert len(result.rankings) == n_decisions * 5
    assert result.rankings["rank"].max() == 5

    # The winner in trades must be rank 1.
    assert (result.trades["rank"] == 1).all()


def test_transaction_costs_reduce_net_return() -> None:
    dataset = _make_dataset()

    free = run_baseline_backtest(dataset, config=_zero_cost_config())

    costly_config = BaselineConfig(
        lookback_days=5,
        holding_days=5,
        buy_fee=0.00015,
        sell_fee=0.00015,
        sell_tax=0.0020,
        buy_slippage=0.0010,
        sell_slippage=0.0010,
    )
    costly = run_baseline_backtest(dataset, config=costly_config)

    assert (
        costly.trades["net_return"].iloc[0]
        < free.trades["net_return"].iloc[0]
    )


def test_equity_curve_compounds_trade_returns() -> None:
    dataset = _make_dataset()

    result = run_baseline_backtest(dataset, config=_zero_cost_config())

    first_return = result.trades.iloc[0]["net_return"]
    second_return = result.trades.iloc[1]["net_return"]

    expected_first_equity = 1.0 * (1.0 + first_return)
    expected_second_equity = expected_first_equity * (1.0 + second_return)

    assert result.equity_curve.iloc[0]["equity"] == pytest.approx(
        expected_first_equity
    )
    assert result.equity_curve.iloc[1]["equity"] == pytest.approx(
        expected_second_equity
    )


def test_cumulative_return_is_based_on_final_equity() -> None:
    dataset = _make_dataset()

    result = run_baseline_backtest(dataset, config=_zero_cost_config())

    final_equity = result.equity_curve.iloc[-1]["equity"]

    assert result.cumulative_return == pytest.approx(final_equity - 1.0)


def test_hit_rate_and_average_return_are_consistent_with_trades() -> None:
    dataset = _make_dataset()

    result = run_baseline_backtest(dataset, config=_zero_cost_config())

    expected_hit_rate = (result.trades["net_return"] > 0).mean()
    expected_average = result.trades["net_return"].mean()

    assert result.hit_rate == pytest.approx(expected_hit_rate)
    assert result.average_return == pytest.approx(expected_average)


def test_backtest_rejects_empty_dataset() -> None:
    dataset = pd.DataFrame(
        columns=["trade_date", "stock_code", "open_price", "close_price"]
    )

    with pytest.raises(ValueError, match="must not be empty"):
        run_baseline_backtest(dataset)


def test_backtest_rejects_missing_columns() -> None:
    dataset = pd.DataFrame(
        {
            "trade_date": ["2026-07-01"],
            "stock_code": ["005930"],
        }
    )

    with pytest.raises(ValueError, match="Missing required columns"):
        run_baseline_backtest(dataset)


def test_backtest_delegates_stock_count_check_to_canonical() -> None:
    """Only 3 stock codes present: the canonical implementation should
    still be the one enforcing the 5-stock requirement, so the error
    message must come from src.backtest.baseline, not a reimplemented
    check here."""

    dataset = _make_dataset()
    dataset = dataset[dataset["stock_code"].isin(["000660", "005380", "005930"])]

    with pytest.raises(ValueError, match="Baseline expects five stocks"):
        run_baseline_backtest(dataset, config=_zero_cost_config())
