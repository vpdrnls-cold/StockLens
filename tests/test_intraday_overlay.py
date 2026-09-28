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
