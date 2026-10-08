"""Item 84 next-cycle grid: fixed rules and the runner's gates -- synthetic data, tmp_path only."""
from __future__ import annotations

from math import isclose

import numpy as np
import pandas as pd
import pytest

from scripts import run_next_cycle_grid as rg
from scripts.walk_forward_backtest_compare import universe_average_gross
from src.eval import next_cycle as nc
from src.models.predict import MinTreesEarlyStopping, train_model


def _part(n_stocks: int = 12, n_dates: int = 80, seed: int = 1) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2030-01-01", periods=n_dates)
    rows = []
    for k in range(n_stocks):
        close = 100 * np.cumprod(1 + rng.normal(0, 0.02, n_dates))
        for i, d in enumerate(dates):
            rows.append({"trade_date": d, "stock_code": f"{k:06d}", "open_price": close[i] * 0.999,
                         "close_price": close[i], "target_return_5d": 0.0, "score": float(k) + 0.1 * (i % 3)})
    return pd.DataFrame(rows)


# --- fixed values (item 84) ---------------------------------------------------

def test_preregistered_values() -> None:
    assert nc.CANDIDATES == ("M0P0", "M0P1", "M0P2", "M1P0", "M1P1", "M1P2") and nc.BASELINE == "M0P0"
    assert {k: (p.top_n, p.holding_days, p.buffer_multiplier) for k, p in nc.PORTFOLIOS.items()} == {
        "P0": (10, 5, 3.0), "P1": (20, 10, 3.0), "P2": (30, 20, 3.0)}
    assert (nc.MIN_TREES, nc.MIN_WINS, nc.PHASE_OFFSETS) == (100, 4, (0, 1, 2, 3, 4))
    assert (nc.ASSUMED_TRUE_IC, nc.T_THRESHOLD, nc.TARGET_POWER, nc.LENGTH_STEP, nc.LENGTH_CAP) == (0.03, 1.65, 0.60, 125, 500)
    assert nc.DEV_START == "2025-09-01" and nc.selection_train_end() == "2025-08-31" and nc.PURGE_DAYS == 5


# --- A-5 forward2 length ------------------------------------------------------

def test_forward2_power_matches_item_79_numbers() -> None:
    assert isclose(nc.forward2_power(250, 0.155), 0.39, abs_tol=0.01)
    assert isclose(nc.forward2_power(500, 0.155), 0.61, abs_tol=0.01)
    assert nc.forward2_power(500, 0.10) > nc.forward2_power(250, 0.10)


def test_forward2_length_rule() -> None:
    assert nc.forward2_length(0.155) == 500     # 61% only at the cap
    assert nc.forward2_length(0.10) == 250      # 125 days ~44%, 250 days ~68%
    assert nc.forward2_length(0.20) is None     # cap not enough -> harm check only
    with pytest.raises(ValueError):
        nc.forward2_power(250, 0.0)


# --- A-3 selection rule -------------------------------------------------------

def _phases(excess: dict[str, list[float]]) -> pd.DataFrame:
    base = {c: [0.0] * 5 for c in nc.CANDIDATES}
    base.update(excess)
    return pd.DataFrame([{"candidate": c, "offset": k, "excess_vs_univ": v[k]}
                         for c, v in base.items() for k in nc.PHASE_OFFSETS])


def test_baseline_kept_when_nothing_passes() -> None:
    chosen, table = nc.decide(_phases({"M0P0": [0.05] * 5, "M1P1": [0.06, 0.06, 0.06, 0.0, 0.0]}))
    assert chosen == "M0P0"
    assert table.set_index("candidate").loc["M1P1", "wins_vs_baseline"] == 3 and not table["passes"].any()


def test_four_wins_and_positive_mean_pass_best_mean_chosen() -> None:
    chosen, table = nc.decide(_phases({"M0P0": [0.0] * 5, "M0P2": [0.01, 0.01, 0.01, 0.01, -0.01],
                                       "M1P2": [0.02, 0.02, 0.02, 0.02, -0.5]}))
    t = table.set_index("candidate")
    assert t.loc["M0P2", "passes"] and not t.loc["M1P2", "passes"]  # 4 wins but mean < 0
    assert chosen == "M0P2"


def test_negative_baseline_does_not_lower_the_bar_below_zero() -> None:
    chosen, _ = nc.decide(_phases({"M0P0": [-0.3] * 5, "M1P0": [-0.1] * 5}))
    assert chosen == "M0P0"  # beats the baseline everywhere but mean excess is not > 0


def test_tie_break_follows_candidate_order() -> None:
    chosen, _ = nc.decide(_phases({"M1P2": [0.02] * 5, "M0P1": [0.02] * 5}))
    assert chosen == "M0P1"


def test_decide_needs_every_candidate_and_offset() -> None:
    with pytest.raises(ValueError):
        nc.decide(_phases({})[lambda d: d["candidate"] != "M1P2"])


# --- B. M1 training boundaries ------------------------------------------------

def _dated(start: str, end: str) -> pd.DataFrame:
    dates = pd.bdate_range(start, end)
    return pd.DataFrame({"trade_date": np.repeat(dates, 2), "stock_code": ["a", "b"] * len(dates), "x": 1.0})


def test_m1_frames_purged_and_inside_range() -> None:
    data = _dated("2020-01-01", "2026-12-31")
    fit, val = nc.m1_training_frames(data, "2025-08-31")
    fit_dates, val_dates = sorted(fit["trade_date"].unique()), sorted(val["trade_date"].unique())
    all_dates = sorted(data["trade_date"].unique())
    assert val_dates[0] == pd.Timestamp("2024-09-02")  # first business day of the last year
    assert all_dates.index(val_dates[0]) - all_dates.index(fit_dates[-1]) == nc.PURGE_DAYS + 1
    last_kept = all_dates.index(val_dates[-1])
    assert all_dates[last_kept + nc.PURGE_DAYS] == pd.Timestamp("2025-08-29")  # last date <= end
    assert val["trade_date"].max() < pd.Timestamp(nc.DEV_START)


def test_m1_frames_ignore_rows_after_end() -> None:
    data = _dated("2020-01-01", "2026-12-31")
    changed = data.copy()
    changed.loc[changed["trade_date"] > "2025-08-31", "x"] = 99.0
    for a, b in zip(nc.m1_training_frames(data, "2025-08-31"), nc.m1_training_frames(changed, "2025-08-31")):
        pd.testing.assert_frame_equal(a, b)


def test_drop_last_dates() -> None:
    data = _dated("2030-01-01", "2030-01-10")
    assert nc.drop_last_dates(data, 0).equals(data)
    assert data["trade_date"].nunique() - nc.drop_last_dates(data, 3)["trade_date"].nunique() == 3
    assert nc.drop_last_dates(data, 99).empty


# --- C. M1 min-trees early stopping -------------------------------------------

def _xy(n: int, seed: int) -> tuple[pd.DataFrame, pd.Series]:
    rng = np.random.default_rng(seed)
    X = pd.DataFrame(rng.normal(size=(n, 2)), columns=["f1", "f2"])
    return X, pd.Series(X["f1"] + rng.normal(scale=5.0, size=n))


def test_min_trees_never_selects_fewer_trees() -> None:
    (X, y), (Xv, yv) = _xy(400, 0), _xy(200, 1)
    params = {"n_jobs": 1, "tree_method": "exact"}
    plain = train_model(X, y, Xv, yv, feature_columns=("f1", "f2"), params=params)
    floored = train_model(X, y, Xv, yv, feature_columns=("f1", "f2"), params=params, min_trees=100)
    assert plain.best_iteration < 99 <= floored.best_iteration
    booster = floored.model.get_booster()
    assert booster.num_boosted_rounds() - floored.best_iteration - 1 <= 30
    # predict uses exactly the selected trees
    np.testing.assert_allclose(floored.model.predict(Xv),
                               floored.model.predict(Xv, iteration_range=(0, floored.best_iteration + 1)))


def test_min_trees_validation() -> None:
    (X, y), (Xv, yv) = _xy(50, 0), _xy(20, 1)
    with pytest.raises(ValueError):
        train_model(X, y, Xv, yv, feature_columns=("f1", "f2"), params={"n_estimators": 50}, min_trees=100)
    with pytest.raises(ValueError):
        MinTreesEarlyStopping(0, 100)


# --- engine pieces ------------------------------------------------------------

def test_universe_benchmark_follows_holding_days() -> None:
    data = rg._to_data_by_stock(_part())
    pd.testing.assert_series_equal(universe_average_gross(data), universe_average_gross(data, holding=5))
    d5, d10 = universe_average_gross(data).index, universe_average_gross(data, holding=10).index
    assert len(d10) < len(d5) and (pd.Series(d10).diff().dropna() > pd.Series(d5).diff().dropna().iloc[0]).all()


def test_candidate_phases_runs_every_offset_with_its_portfolio() -> None:
    part = _part(n_stocks=35, n_dates=120)
    p0 = rg.candidate_phases(part, "M0P0", "score")
    p2 = rg.candidate_phases(part, "M1P2", "score")
    assert list(p0["offset"]) == list(nc.PHASE_OFFSETS) and set(p2["candidate"]) == {"M1P2"}
    assert (p2["periods"] < p0["periods"]).all()  # 20-day holds -> fewer periods
    assert np.allclose(p0["excess_vs_univ"], p0["net_cum"] - p0["univ_ew_gross"])


def test_diagnostics_point_the_right_way() -> None:
    part = _part()
    part["target_return_5d"] = part["score"] * 0.01  # perfect ranking
    assert nc.decile_spread(part, "score") > 0 and nc.bottom_avoid_excess(part, "score") > 0


# --- gates (nothing is read when they stop) -----------------------------------

TOP50 = [f"{k:06d}" for k in range(50)]


def test_gate_stops(tmp_path) -> None:
    out = tmp_path / "grid"
    missing = tmp_path / "forward_results.csv"
    assert rg.gate(out, "2026-01-05", ["005930"], TOP50, missing)[0] == 2           # not top50
    assert rg.gate(out, "2026/01/05", TOP50, TOP50, missing)[0] == 2                # bad date
    assert rg.gate(out, "2025-08-01", TOP50, TOP50, missing)[0] == 2                # before dev start
    assert rg.gate(out, "2099-01-01", TOP50, TOP50, missing)[0] == 2                # future
    assert rg.gate(out, "2026-09-24", TOP50, TOP50, missing)[0] == 6                # forward still closed
    assert rg.gate(out, "2026-09-23", TOP50, TOP50, missing)[0] == 6                # no early, shorter run either
    missing.write_text("x")
    assert rg.gate(out, "2026-09-23", TOP50, TOP50, missing)[0] == 2                # dev must reach the forward period
    assert rg.gate(out, "2026-09-24", TOP50, TOP50, missing) is None                # after the forward look
    out.mkdir()
    (out / rg.SUMMARY_FILE).write_text("x")
    assert rg.gate(out, "2026-09-24", TOP50, TOP50, missing)[0] == 3                # runs once
