"""Guards for the pre-registered D1 settings (CURRENT_STATUS items 46/47/54)."""
from __future__ import annotations

import re
from pathlib import Path

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


# Item 54: the forward holdout is looked at once, so exactly one script may open it.
FORWARD_READERS = {"evaluate_forward_holdout.py"}
_FORWARD_CALL = re.compile(r"select_segment\([^)]*[\"']forward[\"']")


def test_only_the_forward_evaluation_script_reads_the_forward_holdout() -> None:
    scripts_dir = Path(rmb.__file__).parent
    readers = {
        path.name
        for path in scripts_dir.glob("*.py")
        if _FORWARD_CALL.search(path.read_text(encoding="utf-8"))
    }
    assert readers == FORWARD_READERS


# Item 65: the frozen model is identified by its trees, not only by best_iteration.
def _small_model(seed: int):
    import numpy as np
    from src.models.predict import train_model

    rng = np.random.default_rng(seed)
    cols = ("a", "b")
    dates = np.repeat(pd.bdate_range("2020-01-01", periods=60), 8)
    X = pd.DataFrame({"trade_date": dates, "a": rng.normal(size=len(dates)), "b": rng.normal(size=len(dates))})
    y = pd.Series(0.5 * X["a"] + rng.normal(scale=0.5, size=len(dates)))
    return train_model(X, y, X, y, feature_columns=cols, params={**rmb.DETERMINISTIC_PARAMS, "n_estimators": 20})


def test_frozen_model_fingerprint_is_deterministic_and_tree_sensitive() -> None:
    first, again, other = _small_model(0), _small_model(0), _small_model(1)
    assert rmb.frozen_model_fingerprint(first) == rmb.frozen_model_fingerprint(again)
    assert rmb.frozen_model_fingerprint(first) != rmb.frozen_model_fingerprint(other)


def test_frozen_model_matches_needs_both_rounds_and_trees() -> None:
    model = _small_model(0)
    fp = rmb.frozen_model_fingerprint(model)
    assert rmb.frozen_model_matches(model, {"best_iteration": model.best_iteration, "fingerprint": fp})
    assert not rmb.frozen_model_matches(model, {"best_iteration": model.best_iteration + 1, "fingerprint": fp})
    assert not rmb.frozen_model_matches(model, {"best_iteration": model.best_iteration, "fingerprint": "x" * 64})
