from __future__ import annotations

import pandas as pd
import pytest

from src.ml.backtest import run_baseline_backtest


def _make_dataset() -> pd.DataFrame:
    """Create deterministic data for backtest tests."""

    dates = pd.bdate_range("2026-07-01", periods=11)

    rows = []

    for i, date in enumerate(dates):
        # Each date has 3 stocks.
        # 005380 has the highest 5-day momentum,
        # so it should always be selected.
        rows.extend(
            [
                {
                    "trade_date": date,
                    "stock_code": "000660",
                    "return_5d": 0.02,
                    "close_price": 100.0 + i,
                },
                {
                    "trade_date": date,
                    "stock_code": "005380",
                    "return_5d": 0.08,
                    "close_price": 100.0 + i * 2,
                },
                {
                    "trade_date": date,
                    "stock_code": "005930",
                    "return_5d": -0.01,
                    "close_price": 100.0 - i,
                },
            ]
        )

    return pd.DataFrame(rows)


def test_backtest_selects_highest_momentum_stock() -> None:
    dataset = _make_dataset()

    result = run_baseline_backtest(dataset)

    assert not result.trades.empty
    assert result.trades["stock_code"].tolist() == [
        "005380",
        "005380",
    ]


def test_backtest_records_correct_ranking() -> None:
    dataset = _make_dataset()

    result = run_baseline_backtest(dataset)

    assert result.trades["rank"].tolist() == [1, 1]

    assert result.trades["score"].tolist() == pytest.approx(
        [0.08, 0.08]
    )


def test_backtest_connects_decision_date_to_t_plus_5() -> None:
    dataset = _make_dataset()

    result = run_baseline_backtest(dataset)

    first_trade = result.trades.iloc[0]

    assert first_trade["decision_date"] == pd.Timestamp(
        "2026-07-01"
    )

    assert first_trade["exit_date"] == pd.Timestamp(
        "2026-07-08"
    )


def test_backtest_calculates_return_correctly() -> None:
    dataset = _make_dataset()

    result = run_baseline_backtest(dataset)

    first_trade = result.trades.iloc[0]

    # 005380:
    # T close = 100
    # T+5 close = 110
    # return = 110 / 100 - 1 = 0.10
    assert first_trade["entry_price"] == pytest.approx(100.0)
    assert first_trade["exit_price"] == pytest.approx(110.0)
    assert first_trade["gross_return"] == pytest.approx(0.10)
    assert first_trade["net_return"] == pytest.approx(0.10)


def test_transaction_cost_and_slippage_are_applied() -> None:
    dataset = _make_dataset()

    result = run_baseline_backtest(
        dataset,
        transaction_cost=0.01,
        slippage=0.005,
    )

    first_trade = result.trades.iloc[0]

    # Gross return = 10%
    # Cost = 1%
    # Slippage = 0.5%
    # Net return = 8.5%
    assert first_trade["gross_return"] == pytest.approx(0.10)
    assert first_trade["net_return"] == pytest.approx(0.085)


def test_equity_curve_compounds_trade_returns() -> None:
    dataset = _make_dataset()

    result = run_baseline_backtest(dataset)

    assert len(result.equity_curve) == 2

    first_return = result.trades.iloc[0]["net_return"]
    second_return = result.trades.iloc[1]["net_return"]

    expected_first_equity = 1.0 * (1.0 + first_return)
    expected_second_equity = (
        expected_first_equity * (1.0 + second_return)
    )

    assert result.equity_curve.iloc[0]["equity"] == pytest.approx(
        expected_first_equity
    )

    assert result.equity_curve.iloc[1]["equity"] == pytest.approx(
        expected_second_equity
    )


def test_cumulative_return_is_based_on_final_equity() -> None:
    dataset = _make_dataset()

    result = run_baseline_backtest(dataset)

    final_equity = result.equity_curve.iloc[-1]["equity"]

    assert result.cumulative_return == pytest.approx(
        final_equity - 1.0
    )


def test_average_return_is_calculated_correctly() -> None:
    dataset = _make_dataset()

    result = run_baseline_backtest(dataset)

    expected = result.trades["net_return"].mean()

    assert result.average_return == pytest.approx(expected)


def test_hit_rate_is_calculated_correctly() -> None:
    dataset = _make_dataset()

    result = run_baseline_backtest(dataset)

    expected = (
        result.trades["net_return"] > 0
    ).mean()

    assert result.hit_rate == pytest.approx(expected)


def test_max_drawdown_is_calculated_correctly() -> None:
    dataset = _make_dataset()

    result = run_baseline_backtest(dataset)

    equity = result.equity_curve["equity"]
    running_max = equity.cummax()
    expected_drawdown = (equity / running_max - 1.0).min()

    assert result.max_drawdown == pytest.approx(
        expected_drawdown
    )


def test_future_scores_do_not_change_past_decision() -> None:
    dataset = _make_dataset()

    original = run_baseline_backtest(dataset)

    modified = dataset.copy()

    # Change future-day momentum scores dramatically.
    # The decision on 2026-07-01 must not change because
    # the baseline only uses data from the decision date.
    future_date = pd.Timestamp("2026-07-02")

    mask = modified["trade_date"] == future_date

    modified.loc[
        mask & (modified["stock_code"] == "000660"),
        "return_5d",
    ] = 100.0

    modified.loc[
        mask & (modified["stock_code"] == "005380"),
        "return_5d",
    ] = -100.0

    modified.loc[
        mask & (modified["stock_code"] == "005930"),
        "return_5d",
    ] = -200.0

    changed = run_baseline_backtest(modified)

    assert original.trades.iloc[0]["stock_code"] == (
        changed.trades.iloc[0]["stock_code"]
    )

    assert original.trades.iloc[0]["score"] == pytest.approx(
        changed.trades.iloc[0]["score"]
    )


def test_backtest_rejects_empty_dataset() -> None:
    dataset = pd.DataFrame(
        columns=[
            "trade_date",
            "stock_code",
            "return_5d",
            "close_price",
        ]
    )

    with pytest.raises(ValueError, match="must not be empty"):
        run_baseline_backtest(dataset)


def test_backtest_rejects_missing_columns() -> None:
    dataset = pd.DataFrame(
        {
            "trade_date": ["2026-07-01"],
            "stock_code": ["005930"],
            "return_5d": [0.05],
        }
    )

    with pytest.raises(ValueError, match="Missing required columns"):
        run_baseline_backtest(dataset)


def test_backtest_rejects_invalid_holding_period() -> None:
    dataset = _make_dataset()

    with pytest.raises(ValueError, match="holding_period"):
        run_baseline_backtest(
            dataset,
            holding_period=0,
        )


def test_backtest_rejects_insufficient_dates() -> None:
    dataset = _make_dataset().iloc[:9].copy()

    with pytest.raises(
        ValueError,
        match="Not enough dates",
    ):
        run_baseline_backtest(dataset)