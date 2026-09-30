"""Risk overlay (CURRENT_STATUS item 55): pre-registered constants, no look-ahead, costs, decision rule."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from src.backtest.baseline import Trade, calculate_performance
from src.portfolio import risk_overlay as ro


def _prices(n_days: int = 400, n_stocks: int = 4, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2010-01-01", periods=n_days)
    rows = []
    for k in range(n_stocks):
        close = 100 * np.cumprod(1 + rng.normal(0.0003, 0.02, n_days))
        rows += [{"trade_date": d, "stock_code": f"{k:06d}", "close_price": c} for d, c in zip(dates, close)]
    return pd.DataFrame(rows)


def test_preregistered_constants_are_fixed():
    assert ro.VOL_WINDOW == 20
    assert ro.TREND_WINDOW == 200
    assert ro.TREND_LOW_EXPOSURE == 0.5
    assert ro.EXPOSURE_CHANGE_COST == pytest.approx(0.00315)
    assert ro.MDD_MARGIN == 0.05
    assert ro.CALMAR_TIE == 0.05
    assert ro.CANDIDATES == ("R0", "R1", "R2", "R3")
    assert ro.SIMPLICITY_ORDER == ("R2", "R1", "R3")


def test_universe_ew_index_is_mean_of_daily_returns():
    p = pd.DataFrame({
        "trade_date": pd.to_datetime(["2020-01-01", "2020-01-02"] * 2),
        "stock_code": ["A", "A", "B", "B"],
        "close_price": [100.0, 110.0, 50.0, 45.0],
    })
    idx = ro.universe_ew_index(p)
    assert idx.iloc[0] == 1.0
    assert idx.iloc[1] == pytest.approx(1.0 + (0.10 - 0.10) / 2)


def test_exposures_are_bounded_and_trend_takes_two_values():
    index = ro.universe_ew_index(_prices())
    dates = index.index[::5]
    sigma_star = float(ro.realized_vol(index).dropna().median())
    exp = ro.candidate_exposures(index, dates, sigma_star)
    for e in exp.values():
        assert ((e >= 0) & (e <= 1)).all()
    assert set(exp["R2"].unique()) <= {0.5, 1.0}
    assert (exp["R0"] == 1.0).all()
    np.testing.assert_allclose(exp["R3"], exp["R1"] * exp["R2"])
    # not enough history for MA200 -> no opinion -> fully invested
    assert (exp["R2"][dates < index.index[199]] == 1.0).all()


def test_no_lookahead_future_prices_do_not_change_exposure():
    p = _prices()
    cut = pd.Timestamp(sorted(p["trade_date"].unique())[300])
    shocked = p.copy()
    shocked.loc[shocked["trade_date"] > cut, "close_price"] *= 0.3  # crash after T
    dates = pd.DatetimeIndex(sorted(p["trade_date"].unique())[:301:5])
    a = ro.candidate_exposures(ro.universe_ew_index(p), dates, 0.2)
    b = ro.candidate_exposures(ro.universe_ew_index(shocked), dates, 0.2)
    for k in ro.CANDIDATES:
        pd.testing.assert_series_equal(a[k], b[k])


def test_apply_exposure_cost_and_identity():
    dates = pd.to_datetime(["2020-01-03", "2020-01-10", "2020-01-17"])
    r = pd.Series([0.02, -0.01, 0.03], index=dates)
    same = ro.apply_exposure(r, pd.Series(1.0, index=dates))
    pd.testing.assert_series_equal(same.returns, r, check_names=False)
    assert same.change_cost.sum() == 0.0

    e = pd.Series([1.0, 0.5, 1.0], index=dates)
    out = ro.apply_exposure(r, e)
    c = 0.5 * ro.EXPOSURE_CHANGE_COST
    np.testing.assert_allclose(out.returns, [0.02, 0.5 * -0.01 - c, 0.03 - c])

    with pytest.raises(ValueError):
        ro.apply_exposure(r, pd.Series([1.0, 1.2, 1.0], index=dates))


def test_period_returns_match_engine_performance():
    t = pd.Timestamp
    trades = [
        Trade(t("2020-01-03"), "A", 1.0, t("2020-01-06"), 10.0, t("2020-01-10"), 11.0, 0.10, 0.09, 0.5),
        Trade(t("2020-01-03"), "B", 0.5, t("2020-01-06"), 10.0, t("2020-01-10"), 9.0, -0.10, -0.11, 0.5),
        Trade(t("2020-01-10"), "A", 1.0, t("2020-01-13"), 11.0, t("2020-01-17"), 12.0, 0.09, 0.08, 1.0),
    ]
    r = ro.period_returns(trades)
    m = ro.risk_metrics(ro.apply_exposure(r, pd.Series(1.0, index=r.index)))
    perf = calculate_performance(trades)
    assert m["net_cum"] == pytest.approx(perf["total_return"])
    assert m["mdd"] == pytest.approx(perf["max_drawdown"])


def _results(mdd: dict, calmar: dict) -> pd.DataFrame:
    return pd.DataFrame([
        {"window": w, "candidate": k, "mdd": mdd[k][i], "calmar": calmar[k][i]}
        for k in ro.CANDIDATES for i, w in enumerate(["W1", "W2", "W3"])
    ])


def test_decision_requires_all_windows_and_prefers_simpler_on_ties():
    mdd = {"R0": [-0.40] * 3, "R1": [-0.30] * 3, "R2": [-0.34] * 3, "R3": [-0.25] * 3}
    cal = {"R0": [0.5] * 3, "R1": [0.62] * 3, "R2": [0.60] * 3, "R3": [0.70] * 3}
    v = ro.decide(_results(mdd, cal))
    assert v["passed"] == {"R2": True, "R1": True, "R3": True}
    assert v["adopt"] == "R3"  # R3 best by >= 0.05

    cal["R3"] = [0.64] * 3  # R2 within 0.05 of best -> simplest wins
    assert ro.decide(_results(mdd, cal))["adopt"] == "R2"

    mdd["R2"] = [-0.34, -0.37, -0.34]  # W2 gain only 3%p -> R2 fails
    v = ro.decide(_results(mdd, cal))
    assert v["passed"]["R2"] is False
    assert v["adopt"] == "R1"

    none = ro.decide(_results({k: [-0.40] * 3 for k in ro.CANDIDATES}, {k: [0.5] * 3 for k in ro.CANDIDATES}))
    assert none["adopt"] == "R0"


def test_risk_metrics_annualization():
    dates = pd.bdate_range("2020-01-01", periods=int(ro.PERIODS_PER_YEAR * 2), freq="5B")
    r = pd.Series(0.001, index=dates)
    m = ro.risk_metrics(ro.apply_exposure(r, pd.Series(1.0, index=dates)))
    assert m["ann_return"] == pytest.approx((1.001) ** ro.PERIODS_PER_YEAR - 1, rel=1e-3)
    assert m["mdd"] == 0.0 and math.isnan(m["calmar"])
