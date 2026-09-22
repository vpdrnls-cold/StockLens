from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.ml.cross_section import daily_rank_ic, demean_by_date, rank_by_date, summarize_ic


def _panel() -> pd.DataFrame:
    days = pd.to_datetime(["2026-01-01", "2026-01-02", "2026-01-03"])
    rows = []
    for d, scores, targets in [
        (days[0], [1, 2, 3, 4], [0.1, 0.2, 0.3, 0.4]),   # IC = 1
        (days[1], [1, 2, 3, 4], [0.4, 0.3, 0.2, 0.1]),   # IC = -1
        (days[2], [7, 7, 7, 7], [0.1, 0.2, 0.3, 0.4]),   # score constant -> NaN
    ]:
        for i, (s, t) in enumerate(zip(scores, targets)):
            rows.append({"trade_date": d, "stock_code": f"S{i}", "score": s, "target_return_5d": t})
    return pd.DataFrame(rows)


def test_daily_rank_ic_and_summary() -> None:
    ics = daily_rank_ic(_panel(), "score")
    assert list(ics.round(6)[:2]) == [1.0, -1.0]
    assert np.isnan(ics.iloc[2])

    summary = summarize_ic(ics)
    assert summary.n_days == 3
    assert summary.mean_ic == pytest.approx(0.0)
    assert summary.pct_pos == pytest.approx(1 / 3)
    assert summary.coverage == pytest.approx(2 / 3)


def test_demean_by_date_removes_the_market_component() -> None:
    df = pd.DataFrame(
        {
            "trade_date": pd.to_datetime(["2026-01-01"] * 3 + ["2026-01-02"] * 3),
            "target_return_5d": [0.10, 0.12, 0.14, -0.10, -0.08, -0.06],
        }
    )
    out = demean_by_date(df, "target_return_5d")
    assert out.tolist() == pytest.approx([-0.02, 0.0, 0.02, -0.02, 0.0, 0.02])


def test_rank_by_date_is_centered_and_preserves_order() -> None:
    df = pd.DataFrame(
        {
            "trade_date": pd.to_datetime(["2026-01-01"] * 4),
            "target_return_5d": [0.3, 0.1, 0.4, 0.2],
        }
    )
    out = rank_by_date(df, "target_return_5d")
    assert out.mean() == pytest.approx(0.0)
    assert out.min() > -0.5 and out.max() < 0.5
    assert list(out.rank()) == [3.0, 1.0, 4.0, 2.0]
