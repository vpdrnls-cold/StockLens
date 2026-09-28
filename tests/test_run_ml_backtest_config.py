"""Guards for the pre-registered D1 settings (CURRENT_STATUS items 46/47)."""
from __future__ import annotations

import pandas as pd
import pytest

from scripts import run_ml_backtest as rmb
from src.data.intraday_split import FORWARD_ENV_VAR, select_segment
from src.eval.test_lock import TestSetLockedError


def test_pre_registered_parameters_are_fixed() -> None:
    assert rmb.TOP_N == 10
    assert rmb.BUFFER_MULTIPLIER == 3.0
    assert rmb.BUFFERED_CONFIG.buffer_multiplier == 3.0
    # buffered and plain runs must pay exactly the same costs
    for field in ("buy_fee", "sell_fee", "sell_tax", "buy_slippage", "sell_slippage", "holding_days"):
        assert getattr(rmb.BUFFERED_CONFIG, field) == getattr(rmb.PLAIN_CONFIG, field)


def test_forward_segment_stays_locked_without_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(FORWARD_ENV_VAR, raising=False)
    df = pd.DataFrame({"trade_date": pd.bdate_range("2026-09-01", "2027-06-30"), "x": 1.0})
    with pytest.raises(TestSetLockedError):
        select_segment(df, "forward", caller="run_ml_backtest.py")


def test_script_no_longer_reads_the_consumed_test_split() -> None:
    source = open(rmb.__file__, encoding="utf-8").read()
    assert "splits.test" not in source
    assert "confirm_final_test_use" not in source
