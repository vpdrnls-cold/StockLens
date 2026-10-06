"""A1 cross-sectional holdout (CURRENT_STATUS item 79): fixed rules and run-order guards."""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import numpy as np
import pandas as pd
import pytest

from scripts import evaluate_cross_sectional_holdout as xh
from src.data.dataset import TEST_END_DATE
from src.data.models import DailyBar


def test_fixed_settings() -> None:
    assert xh.MIN_STOCKS == 50 and xh.HORIZON == 5 and xh.T_THRESHOLD == 1.65
    assert [p[0] for p in xh.PERIODS] == ["P", "W3", "W1", "W2"]
    assert [p[0] for p in xh.PERIODS if p[3] == "verdict"] == ["P"]
    assert xh.PERIODS[0][1:3] == ("2023-07-01", "2026-09-16")


def test_holdout_codes_disjoint_and_ordered() -> None:
    assert xh.holdout_codes(["a", "b", "c", "d"], ["b", "d"]) == ("a", "c")
    real = xh.holdout_codes()  # config files only
    assert len(real) == 150 and not set(real) & set(xh.get_universe("top50"))


def test_cap_groups() -> None:
    g = xh.cap_groups(tuple("abcd"), top=2)
    assert g == {"a": "cap_top50of150", "b": "cap_top50of150", "c": "cap_rest100", "d": "cap_rest100"}


def test_t_stat_uses_days_over_horizon() -> None:
    ics = pd.Series([0.1, 0.3] * 50)  # mean 0.2, n 100
    expected = 0.2 / (ics.std(ddof=1) / np.sqrt(100 / 5))
    assert xh.t_stat(ics) == pytest.approx(expected)
    assert np.isnan(xh.t_stat(pd.Series([0.1] * 10)))  # zero spread
    assert xh.t_stat(pd.Series([np.nan, 0.2, 0.4, 0.0])) == pytest.approx(
        xh.t_stat(pd.Series([0.0, 0.2, 0.4, 0.0]))
    )  # undefined days count as 0, as in summarize_ic


def test_verdict_boundaries() -> None:
    assert xh.verdict(0.0, 5.0) == "generalization_failed"
    assert xh.verdict(-0.01, 5.0) == "generalization_failed"
    assert xh.verdict(0.01, 1.65) == "direction_only"
    assert xh.verdict(0.01, 1.66) == "generalization_supported"
    assert xh.verdict(0.01, float("nan")) == "direction_only"


def test_eligible_drops_thin_dates() -> None:
    d1, d2 = pd.Timestamp("2024-01-02"), pd.Timestamp("2024-01-03")
    df = pd.DataFrame({
        "trade_date": [d1] * 3 + [d2] * 2,
        "stock_code": list("abc") + list("ab"),
        xh.SCORE_COL: [1.0, 2.0, 3.0, 1.0, np.nan],
        "target_return_5d": [0.1, 0.2, 0.3, 0.1, 0.2],
    })
    kept, dropped = xh.eligible(df, min_stocks=2)
    assert set(kept["trade_date"]) == {d1} and dropped == 1


def _bars(code: str, start: date, n: int) -> list[DailyBar]:
    out, d = [], start
    rng = np.random.default_rng(0)
    price = 10_000
    while len(out) < n:
        if d.weekday() < 5:
            price = max(1_000, int(price * (1 + rng.normal(0, 0.01))))
            out.append(DailyBar(code, d, price, int(price * 1.01), int(price * 0.99), price,
                                100_000, price, 0, 3, Decimal("0.1")))
        d += timedelta(days=1)
    return out


class _Storage:
    def __init__(self, bars):
        self.bars = bars

    def load_daily_bars(self, code):
        return self.bars[code]


def test_truncation_keeps_everything_at_or_before_test_end() -> None:
    bars = _bars("X", date(2025, 6, 2), 400)  # runs well past 2026-09-16
    cut = xh.truncate_bars(bars)
    assert cut and max(b.trade_date for b in cut) <= date.fromisoformat(TEST_END_DATE)
    assert len(cut) < len(bars)


def test_holdout_dataset_never_reaches_past_test_end_and_skips_short_history() -> None:
    storage = _Storage({
        "AAA": _bars("AAA", date(2025, 6, 2), 400),
        "BBB": _bars("BBB", date(2026, 9, 1), 10),  # too short once cut
    })
    ds, skipped = xh.load_holdout_dataset(("AAA", "BBB"), storage=storage)
    assert skipped == ["BBB"]
    assert ds["trade_date"].max() <= pd.Timestamp(TEST_END_DATE)
    # labels need 5 later bars that all exist before the cut: the last labeled date is before the cut
    labeled = ds.dropna(subset=["target_return_5d"])
    assert labeled["trade_date"].max() < pd.Timestamp(TEST_END_DATE)
    assert {"open_price", "close_price"} <= set(ds.columns)


class _Trained:
    best_iteration = 9


def _no_call(*_a, **_k):
    raise AssertionError("must not be called")


def test_existing_result_stops_before_anything(tmp_path, monkeypatch) -> None:
    (tmp_path / xh.SUMMARY_FILE).write_text("x")
    monkeypatch.setattr(xh, "_load_priced_dataset", _no_call)
    assert xh.main(["--out", str(tmp_path)]) == 3


def test_fingerprint_mismatch_stops_before_extra_stocks(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(xh, "STOCK_CODES", xh.get_universe("top50"))
    monkeypatch.setattr(xh, "_load_priced_dataset", lambda: None)
    monkeypatch.setattr(xh, "train_frozen_model", lambda _d: (_Trained(), None))
    monkeypatch.setattr(xh, "frozen_model_fingerprint", lambda _t: "0" * 64)
    monkeypatch.setattr(xh, "load_holdout_dataset", _no_call)
    monkeypatch.setenv("STOCKLENS_CONFIRM_FINAL_TEST", "1")
    assert xh.main(["--out", str(tmp_path)]) == 4
    assert not (tmp_path / xh.SUMMARY_FILE).exists()


def test_test_lock_stops_before_extra_stocks(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(xh, "STOCK_CODES", xh.get_universe("top50"))
    monkeypatch.setattr(xh, "_load_priced_dataset", lambda: None)
    monkeypatch.setattr(xh, "train_frozen_model", lambda _d: (_Trained(), None))
    monkeypatch.setattr(xh, "frozen_model_fingerprint", lambda _t: "f")
    monkeypatch.setattr(xh.fh, "frozen_model_ok", lambda *_a: True)
    monkeypatch.setattr(xh, "load_holdout_dataset", _no_call)
    monkeypatch.delenv("STOCKLENS_CONFIRM_FINAL_TEST", raising=False)
    assert xh.main(["--out", str(tmp_path)]) == 5


def test_wrong_universe_stops(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(xh, "STOCK_CODES", ("000660",))
    monkeypatch.setattr(xh, "_load_priced_dataset", _no_call)
    assert xh.main(["--out", str(tmp_path)]) == 2
