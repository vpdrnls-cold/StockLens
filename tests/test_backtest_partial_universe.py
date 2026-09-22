"""Tests for BaselineConfig(allow_partial_universe=True)."""

from __future__ import annotations

import pandas as pd
import pytest

from src.backtest.baseline import BaselineConfig, run_baseline_backtest
from src.ml.backtest import run_baseline_backtest as run_adapter_backtest
from src.ml.strategy import make_model_score_fn


def _stock(code: str, closes: list[float], *, start: int = 0, total: int = 45) -> pd.DataFrame:
    """A stock listed ``start`` business days after the calendar start."""
    dates = pd.date_range("2026-01-01", periods=total, freq="B")[start:]
    assert len(dates) == len(closes)
    return pd.DataFrame(
        {
            "stock_code": code,
            "trade_date": dates,
            "open_price": closes,
            "close_price": closes,
        }
    )


def _zero_cost(partial: bool) -> BaselineConfig:
    return BaselineConfig(
        buy_fee=0.0, sell_fee=0.0, sell_tax=0.0,
        buy_slippage=0.0, sell_slippage=0.0,
        allow_partial_universe=partial,
    )


def test_default_still_requires_exactly_five_stocks() -> None:
    stocks = {c: _stock(c, [100.0] * 45) for c in "ABC"}
    with pytest.raises(ValueError, match="allow_partial_universe"):
        run_baseline_backtest(stocks, _zero_cost(False))


def test_partial_mode_matches_default_when_all_stocks_share_the_calendar() -> None:
    stocks = {
        code: _stock(code, [100.0 + i * step for i in range(45)])
        for code, step in zip("ABCDE", (0.1, 0.2, 0.3, 0.4, 0.5))
    }

    default_trades = run_baseline_backtest(stocks, _zero_cost(False), top_n=2)
    partial_trades = run_baseline_backtest(stocks, _zero_cost(True), top_n=2)

    assert partial_trades == default_trades


def test_late_listed_stock_does_not_shrink_the_history() -> None:
    # A..D exist for all 30 days; L lists on day 20 and is the strongest
    # performer once it exists. With an inner join the whole backtest
    # would be limited to days 20+ (too short to trade at all).
    stocks = {c: _stock(c, [100.0 + i * 0.1 for i in range(45)]) for c in "ABCD"}
    stocks["L"] = _stock("L", [100.0 + i * 5 for i in range(25)], start=20)

    trades = run_baseline_backtest(stocks, _zero_cost(True), top_n=1)

    decision_dates = sorted({t.decision_date for t in trades})
    assert len(decision_dates) > 2
    assert decision_dates[0] < pd.Timestamp("2026-01-01") + pd.offsets.BDay(20)
    # Before L exists it can never be picked.
    listing_date = stocks["L"]["trade_date"].iloc[0]
    assert all(t.stock_code != "L" for t in trades if t.decision_date < listing_date)
    # Once it has enough history it is the top scorer and does get picked.
    assert any(t.stock_code == "L" for t in trades)


def test_stock_is_not_ranked_before_it_has_lookback_history() -> None:
    stocks = {c: _stock(c, [100.0] * 45) for c in "ABC"}
    # L lists at index 20 and rises steeply; its 5-day score needs a close at
    # decision_index - 5, so it cannot be ranked before index 25.
    stocks["L"] = _stock("L", [100.0 + i * 10 for i in range(25)], start=20)

    trades = run_baseline_backtest(stocks, _zero_cost(True), top_n=1)

    listing_date = stocks["L"]["trade_date"].iloc[0]
    earliest_rankable = stocks["L"]["trade_date"].iloc[5]
    for trade in trades:
        if trade.stock_code == "L":
            assert trade.decision_date >= earliest_rankable > listing_date


def test_period_is_skipped_when_fewer_than_top_n_stocks_are_tradable() -> None:
    # Only two stocks exist at all; top_n=3 is impossible.
    stocks = {c: _stock(c, [100.0 + i for i in range(45)]) for c in "AB"}
    with pytest.raises(ValueError, match="top_n must be between"):
        run_baseline_backtest(stocks, _zero_cost(True), top_n=3)

    # Three stocks in the universe, but one only lists late: early periods
    # have just two tradable names, so top_n=3 skips them and trades later.
    stocks["C"] = _stock("C", [100.0 + i for i in range(25)], start=20)
    trades = run_baseline_backtest(stocks, _zero_cost(True), top_n=3)
    assert trades, "later periods with all three stocks should still trade"
    assert all(t.decision_date >= stocks["C"]["trade_date"].iloc[5] for t in trades)
    assert all(t.weight == pytest.approx(1 / 3) for t in trades)


def test_model_score_fn_without_prediction_marks_stock_ineligible() -> None:
    stocks = {c: _stock(c, [100.0 + i * 0.1 for i in range(45)]) for c in "ABC"}
    # Predictions exist for A and B only; C has none (feature warm-up).
    rows = [
        {"trade_date": d, "stock_code": code, "predicted_return": value}
        for code, value in (("A", 0.01), ("B", 0.02))
        for d in stocks[code]["trade_date"]
    ]
    score_fn = make_model_score_fn(pd.DataFrame(rows))

    trades = run_baseline_backtest(
        stocks, _zero_cost(True), score_fn=score_fn, top_n=2
    )

    assert trades
    assert {t.stock_code for t in trades} == {"A", "B"}


def test_adapter_rankings_only_include_listed_stocks() -> None:
    stocks = {c: _stock(c, [100.0 + i * 0.1 for i in range(45)]) for c in "ABCD"}
    stocks["L"] = _stock("L", [100.0 + i for i in range(25)], start=20)
    dataset = pd.concat(stocks.values(), ignore_index=True)

    result = run_adapter_backtest(dataset, config=_zero_cost(True))

    early = result.rankings[
        result.rankings["decision_date"] < stocks["L"]["trade_date"].iloc[5]
    ]
    assert "L" not in set(early["stock_code"])
    assert early.groupby("decision_date")["rank"].max().eq(4).all()
