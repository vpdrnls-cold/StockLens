"""OHLC-inconsistent bars from before 2000 are dropped; later ones still fail."""

from __future__ import annotations

from copy import deepcopy
import json
import logging
from pathlib import Path

import pytest

from src.data.normalization import HistoricalDataValidationError, normalize_ka10081_response


@pytest.fixture
def response() -> dict:
    path = Path(__file__).parent / "fixtures" / "ka10081_response.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _legacy_row(date: str, **overrides: str) -> dict:
    row = {
        "cur_prc": "1000", "trde_qty": "10", "trde_prica": "1", "dt": date,
        "open_pric": "1000", "high_pric": "1000", "low_pric": "1000",
        "pred_pre": "0", "pred_pre_sig": "3", "trde_tern_rt": "0.01",
    }
    row.update(overrides)
    return row


def test_inconsistent_legacy_bar_is_dropped_with_warning(
    response: dict, caplog: pytest.LogCaptureFixture
) -> None:
    data = deepcopy(response)
    data["stk_dt_pole_chart_qry"] += [
        _legacy_row("19860125", high_pric="900"),   # high below open/close
        _legacy_row("19850130", low_pric="1100"),   # low above open/close
        _legacy_row("19860126"),                    # consistent legacy bar
    ]
    good_count = len(response["stk_dt_pole_chart_qry"]) + 1

    with caplog.at_level(logging.WARNING):
        bars = normalize_ka10081_response(data)

    assert len(bars) == good_count
    assert {b.trade_date.isoformat() for b in bars} >= {"1986-01-26"}
    assert not {"1986-01-25", "1985-01-30"} & {b.trade_date.isoformat() for b in bars}
    assert "Dropped 2 OHLC-inconsistent legacy bar" in caplog.text


def test_inconsistent_bar_after_cutoff_is_still_rejected(response: dict) -> None:
    data = deepcopy(response)
    data["stk_dt_pole_chart_qry"].append(_legacy_row("20050103", high_pric="900"))
    with pytest.raises(HistoricalDataValidationError, match="High price is below"):
        normalize_ka10081_response(data)
