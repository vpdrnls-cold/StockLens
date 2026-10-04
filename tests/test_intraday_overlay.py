"""Pre-registered pieces of scripts/experiment_intraday_overlay_dev.py (item 46 I1-I4)."""
from __future__ import annotations

import pandas as pd
import pytest

from scripts import experiment_intraday_overlay_dev as ov


def test_features_signs_and_weights_are_the_pre_registered_ones() -> None:
    assert ov.FEATURE_SIGNS == {
        "vshare_auction": 1.0, "vshare_open30": -1.0, "vshare_late": 1.0, "rv_intraday": -1.0,
    }
    assert ov.WEIGHTS == (0.0, 0.25, 0.5)


def test_zscore_by_date_is_cross_sectional_and_nan_when_flat() -> None:
    df = pd.DataFrame({
        "trade_date": ["d1"] * 3 + ["d2"] * 2,
        "x": [1.0, 2.0, 3.0, 5.0, 5.0],
    })
    z = ov.zscore_by_date(df, "x")
    assert z.iloc[:3].tolist() == pytest.approx([-1.0, 0.0, 1.0])
    assert z.iloc[3:].isna().all()


def _results(ic: dict[tuple[str, float], float]) -> pd.DataFrame:
    return pd.DataFrame([{"segment": s, "w": w, "ic": v} for (s, w), v in ic.items()])


def test_decision_requires_all_three_blocks() -> None:
    base = {(s, 0.0): 0.01 for s in ("dev", "B1", "B2", "B3")}
    fails_one = {**base, ("dev", 0.25): 0.05, ("B1", 0.25): 0.02, ("B2", 0.25): 0.02, ("B3", 0.25): 0.0,
                 ("dev", 0.5): 0.0, ("B1", 0.5): 0.0, ("B2", 0.5): 0.0, ("B3", 0.5): 0.0}
    chosen, _ = ov.decide(_results(fails_one))
    assert chosen is None


def test_decision_picks_best_dev_ic_among_passing() -> None:
    base = {(s, 0.0): 0.01 for s in ("dev", "B1", "B2", "B3")}
    both_pass = {**base,
                 ("dev", 0.25): 0.03, ("B1", 0.25): 0.02, ("B2", 0.25): 0.02, ("B3", 0.25): 0.02,
                 ("dev", 0.5): 0.02, ("B1", 0.5): 0.02, ("B2", 0.5): 0.02, ("B3", 0.5): 0.02}
    chosen, _ = ov.decide(_results(both_pass))
    assert chosen == 0.25


def test_i5_candidate_is_fixed_and_rule_is_sign_only() -> None:
    assert ov.CANDIDATE_W == 0.5
    res = pd.DataFrame({"w": [0.0, 0.5], "ic": [0.010, 0.011]})
    assert ov.i5_verdict(res) == (pytest.approx(0.001), True)
    res = pd.DataFrame({"w": [0.0, 0.5], "ic": [0.010, 0.009]})
    assert ov.i5_verdict(res)[1] is False


# Item 68: the minute folder now also holds non-universe stocks (KOSPI200 collection).
def test_extra_stocks_in_the_minute_panel_do_not_change_universe_scores() -> None:
    import numpy as np

    from src.models.predict import train_model

    rng = np.random.default_rng(3)
    dates = pd.bdate_range("2026-01-05", periods=6)
    universe = [f"{k:06d}" for k in range(6)]
    extra = [f"9{k:05d}" for k in range(4)]
    dataset = pd.DataFrame(
        [{"trade_date": d, "stock_code": c, "a": rng.normal(), "b": rng.normal()} for d in dates for c in universe]
    )
    trained = train_model(
        dataset, pd.Series(rng.normal(size=len(dataset))), dataset, pd.Series(rng.normal(size=len(dataset))),
        feature_columns=("a", "b"), params={"n_estimators": 5, "n_jobs": 1, "tree_method": "exact"},
    )

    def panel_for(codes):
        return pd.DataFrame(
            [{"trade_date": d, "stock_code": c, **{f: float(int(c) % 7 + i) for f in ov.FEATURE_SIGNS}}
             for i, d in enumerate(dates) for c in codes]
        )

    base = ov.build_scores(dataset, panel_for(universe), trained)
    with_extra = ov.build_scores(dataset, panel_for(universe + extra), trained)
    cols = ["trade_date", "stock_code", "z_intraday", "score_w0.5"]
    pd.testing.assert_frame_equal(base[cols], with_extra[cols])
    assert set(with_extra["stock_code"]) == set(universe)
