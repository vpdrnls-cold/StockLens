"""Days with an all-identical score must count as IC=0, not be dropped."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from scripts.feature_selection_ic_rerun import cross_sectional_ic


def _panel(scores_by_day: list[list[float]], targets: list[float]) -> pd.DataFrame:
    rows = []
    for day, scores in enumerate(scores_by_day):
        for stock, score in enumerate(scores):
            rows.append(
                {
                    "trade_date": pd.Timestamp("2026-01-01") + pd.Timedelta(days=day),
                    "stock_code": f"S{stock}",
                    "score": score,
                    "target_return_5d": targets[stock],
                }
            )
    return pd.DataFrame(rows)


def test_perfect_days_and_constant_days_are_averaged_together() -> None:
    targets = [0.01, 0.02, 0.03, 0.04]
    # Day 0: perfectly ranked (IC=1). Days 1-3: model gives every stock the
    # same score (undefined IC). Dropping them would report IC=1.0.
    df = _panel([[1, 2, 3, 4], [5, 5, 5, 5], [5, 5, 5, 5], [5, 5, 5, 5]], targets)

    mean_ic, pct_pos, n_days, coverage = cross_sectional_ic(df, "score")

    assert n_days == 4
    assert mean_ic == pytest.approx(0.25)
    assert pct_pos == pytest.approx(0.25)
    assert coverage == pytest.approx(0.25)


def test_fully_defined_series_is_unchanged() -> None:
    targets = [0.01, 0.02, 0.03, 0.04]
    df = _panel([[1, 2, 3, 4], [4, 3, 2, 1]], targets)

    mean_ic, pct_pos, n_days, coverage = cross_sectional_ic(df, "score")

    assert mean_ic == pytest.approx(0.0)
    assert pct_pos == pytest.approx(0.5)
    assert n_days == 2 and coverage == 1.0


def test_days_with_fewer_than_three_stocks_are_ignored() -> None:
    df = _panel([[1, 2], [1, 2, 3, 4]], [0.01, 0.02, 0.03, 0.04])
    _, _, n_days, _ = cross_sectional_ic(df, "score")
    assert n_days == 1
    assert not np.isnan(cross_sectional_ic(df, "score")[0])
