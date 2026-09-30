"""Pre-registered decision rule of scripts/evaluate_personalization.py (CURRENT_STATUS item 56)."""

from __future__ import annotations

import pandas as pd

from scripts.evaluate_personalization import MIN_IC, MIN_MODEL_CORR, decide


def _results(over: dict | None = None) -> pd.DataFrame:
    over = over or {}
    base = {
        "conservative": dict(hold_vol=0.015, period_std=0.030, model_corr=0.8, ic=0.01),
        "neutral": dict(hold_vol=0.020, period_std=0.035, model_corr=1.0, ic=0.02),
        "aggressive": dict(hold_vol=0.025, period_std=0.040, model_corr=0.8, ic=0.01),
    }
    rows = []
    for w in ("W1", "W2", "W3"):
        for p, vals in base.items():
            v = dict(vals)
            v.update(over.get((w, p), {}))
            rows.append({"window": w, "profile": p, **v})
    return pd.DataFrame(rows)


def test_thresholds_are_preregistered():
    assert MIN_MODEL_CORR == 0.7
    assert MIN_IC == 0.0


def test_both_pass_when_direction_and_signal_hold():
    assert decide(_results()) == {"conservative": True, "aggressive": True}


def test_single_window_failure_fails_the_profile():
    assert decide(_results({("W2", "conservative"): dict(period_std=0.036)}))["conservative"] is False
    assert decide(_results({("W1", "aggressive"): dict(ic=-0.001)}))["aggressive"] is False
    assert decide(_results({("W3", "aggressive"): dict(model_corr=0.69)}))["aggressive"] is False
    assert decide(_results({("W3", "aggressive"): dict(hold_vol=0.019)}))["aggressive"] is False


def test_aggressive_has_no_return_volatility_condition():
    assert decide(_results({("W1", "aggressive"): dict(period_std=0.01)}))["aggressive"] is True
