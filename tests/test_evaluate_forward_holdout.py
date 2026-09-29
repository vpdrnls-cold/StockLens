"""Pre-registered forward decisions (CURRENT_STATUS items 46/50: D2 + I6)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from scripts import evaluate_forward_holdout as fh


def _res(ic_daily: float, ic_overlay: float) -> pd.DataFrame:
    return pd.DataFrame({"strategy": ["daily", "overlay", "momentum"], "ic": [ic_daily, ic_overlay, float("nan")]})


def test_fixed_settings() -> None:
    assert fh.OVERLAY_W == 0.5
    assert fh.TOP_N == 10
    assert fh.BUFFER_MULTIPLIER == 3.0


def test_both_not_rejected() -> None:
    v = fh.verdicts(_res(0.02, 0.03))
    assert v["d2_not_rejected"] and v["i6_not_rejected"]


def test_daily_rejected_when_ic_not_positive() -> None:
    assert fh.verdicts(_res(0.0, 0.01))["d2_not_rejected"] is False


def test_overlay_rejected_when_not_better() -> None:
    v = fh.verdicts(_res(0.02, 0.02))
    assert v["d2_not_rejected"] is True
    assert v["i6_not_rejected"] is False


# --- tie-break sensitivity (item 52, info only) ------------------------------


def _synthetic_part(n_stocks: int = 12, n_dates: int = 40, tied: bool = True) -> pd.DataFrame:
    rng = np.random.default_rng(1)
    dates = pd.bdate_range("2030-01-01", periods=n_dates)
    rows = []
    for k in range(n_stocks):
        close = 100 * np.cumprod(1 + rng.normal(0, 0.02, n_dates))
        for i, d in enumerate(dates):
            score = float(i % 3) if tied else float(i % 3) + k * 1e-3
            rows.append({"trade_date": d, "stock_code": f"{k:06d}", "open_price": close[i] * 0.999,
                         "close_price": close[i], "target_return_5d": 0.0, "score_w0.0": score})
    return pd.DataFrame(rows)


def test_tie_settings_fixed() -> None:
    assert fh.TIE_PERMUTATIONS == 20
    assert fh.TIE_SEED == 20260928


def test_tie_orders_are_deterministic_permutations() -> None:
    codes = [f"{k:06d}" for k in range(8)]
    a, b = fh.tie_orders(codes, 5, 7), fh.tie_orders(codes, 5, 7)
    assert a == b
    assert all(sorted(o) == codes for o in a)
    assert len({tuple(o) for o in a}) > 1


def test_tie_stats_counts_ties_at_the_cutoff() -> None:
    part = pd.DataFrame({"trade_date": ["d"] * 5, "score": [3.0, 2.0, 2.0, 2.0, 1.0]})
    s = fh.tie_stats(part, "score", top_n=2)
    assert s["distinct_per_date"] == 3
    assert s["at_or_above_topn"] == 4


def test_tie_order_changes_results_only_through_ties() -> None:
    strat = (("daily", "score_w0.0"),)
    tie_free = fh.tie_sensitivity(_synthetic_part(tied=False), strat, n=5)
    assert tie_free["net_cum"].nunique() == 1
    tied = fh.tie_sensitivity(_synthetic_part(tied=True), strat, n=5)
    assert tied["net_cum"].nunique() > 1


def test_summarize_ties_percentile() -> None:
    sens = pd.DataFrame({"strategy": ["daily"] * 4, "net_cum": [0.1, 0.2, 0.3, 0.4], "mdd": [-0.1, -0.3, -0.2, -0.1]})
    res = pd.DataFrame({"strategy": ["daily"], "net_cum": [0.3]})
    part = pd.DataFrame({"trade_date": ["d"] * 10, "score_w0.0": np.arange(10.0)})
    out = fh.summarize_ties(sens, res, part, (("daily", "score_w0.0"),)).iloc[0]
    assert out["code_asc_pctile"] == 0.625  # 2 below + half of 1 tie, out of 4
    assert out["median"] == 0.25 and out["mdd_worst"] == -0.3


def test_forward_look_requires_the_frozen_model() -> None:
    assert fh.frozen_model_ok(9) is True
    assert fh.frozen_model_ok(8) is False


# --- item 53 deployment rules (confirmed 2026-09-29) ---------------------------


def test_overlay_deployed_only_when_both_pass() -> None:
    v = fh.verdicts(_res(0.02, 0.03), coverage=0.95)
    assert v["i6_status"] == "not_rejected" and v["overlay_deploy"] is True


def test_overlay_not_deployed_when_daily_rejected() -> None:
    v = fh.verdicts(_res(-0.02, 0.01), coverage=0.95)
    assert v["d2_not_rejected"] is False
    assert v["i6_not_rejected"] is True  # I6 itself is still recorded as pre-registered
    assert v["overlay_deploy"] is False


def test_i6_withheld_below_coverage_threshold() -> None:
    v = fh.verdicts(_res(0.02, 0.03), coverage=0.79)
    assert v["i6_status"] == "withheld" and v["overlay_deploy"] is False
    assert fh.verdicts(_res(0.02, 0.01), coverage=0.79)["i6_status"] == "withheld"
    assert fh.verdicts(_res(0.02, 0.03), coverage=0.80)["i6_status"] == "not_rejected"
