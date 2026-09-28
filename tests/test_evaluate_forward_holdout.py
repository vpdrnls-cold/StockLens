"""Pre-registered forward decisions (CURRENT_STATUS items 46/50: D2 + I6)."""
from __future__ import annotations

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
