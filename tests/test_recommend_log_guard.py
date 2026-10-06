"""Paper-log overwrite guard and --cards-only (CURRENT_STATUS item 71). tmp_path only."""
from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd
import pytest

from scripts import recommend as rc

ROOT = Path(__file__).resolve().parents[1]
T = pd.Timestamp("2026-10-02")


def _features() -> pd.DataFrame:
    codes = [f"{k:06d}" for k in range(len(rc.STOCK_CODES))] if rc.STOCK_CODES else ["000001"]
    return pd.DataFrame({"trade_date": [T] * len(codes), "stock_code": codes})


def _run_main(monkeypatch, argv: list[str]) -> int:
    def no_training(*_a, **_k):
        raise AssertionError("training must not start")

    monkeypatch.setattr(rc, "live_features", _features)
    monkeypatch.setattr(rc, "intraday_bar_error", lambda *_a, **_k: None)
    monkeypatch.setattr(rc, "train_frozen_model", no_training)
    monkeypatch.setattr(rc, "_load_priced_dataset", lambda: None)
    monkeypatch.setattr(sys, "argv", ["recommend.py", *argv])
    with pytest.raises(SystemExit) as stop:
        rc.main()
    return stop.value.code


def test_existing_log_stops_before_training(monkeypatch, tmp_path) -> None:
    (tmp_path / "20261002.csv").write_text("trade_date,rank,stock_code,score\n", encoding="utf-8")
    assert rc.existing_log_path(tmp_path, T) == tmp_path / "20261002.csv"
    code = _run_main(monkeypatch, ["--out", str(tmp_path), "--date", "2026-10-02"])
    assert code == rc.LOG_EXISTS_EXIT == 3
    assert (tmp_path / "20261002.csv").read_text(encoding="utf-8").startswith("trade_date")  # untouched


def test_no_log_passes_the_guard(tmp_path) -> None:
    assert rc.existing_log_path(tmp_path, T) is None


def test_cards_only_rejects_profiles_and_no_save(monkeypatch, tmp_path) -> None:
    assert rc.cli_error("conservative", cards_only=True, no_save=False)
    assert rc.cli_error("neutral", cards_only=True, no_save=True)
    assert rc.cli_error("neutral", cards_only=True, no_save=False) is None
    assert rc.cli_error("aggressive", cards_only=False, no_save=False) is None
    code = _run_main(monkeypatch, ["--cards-only", "--profile", "conservative", "--out", str(tmp_path)])
    assert code == 2


def test_cards_only_never_writes_the_csv_and_passes_an_existing_log() -> None:
    assert rc.should_write_csv(no_save=False, cards_only=True) is False
    assert rc.should_write_csv(no_save=False, cards_only=False) is True
    assert rc.should_write_cards("neutral", no_save=False, cards_only=True) is True
    assert rc.should_write_cards("conservative", no_save=False, cards_only=False) is False
    # the guard only fires for runs that would write the CSV
    assert not rc.should_write_csv(False, True)


def _day() -> pd.DataFrame:
    return pd.DataFrame({"rank": [1, 2, 3], "score": [0.03, 0.02, 0.01]},
                        index=pd.Index(["000001", "000002", "000003"], name="stock_code"))


def _log(**over) -> pd.DataFrame:
    log = pd.DataFrame({"stock_code": ["1", "2", "3"], "rank": [1, 2, 3], "score": [0.03, 0.02, 0.01]})
    for k, v in over.items():
        log[k] = v
    return log


def test_compare_identical_and_tiny_score_noise() -> None:
    assert rc.compare_with_log(_day(), _log()) == ([], False)
    noisy = _log(score=[0.03 + 1e-12, 0.02, 0.01])
    assert rc.compare_with_log(_day(), noisy)[0] == []


def test_compare_detects_rank_and_score_and_presence() -> None:
    diffs, _ = rc.compare_with_log(_day(), _log(rank=[1, 3, 2]))
    assert {(d["stock_code"], d["field"]) for d in diffs} == {("000002", "rank"), ("000003", "rank")}
    diffs, _ = rc.compare_with_log(_day(), _log(score=[0.03, 0.021, 0.01]))
    assert [(d["stock_code"], d["field"]) for d in diffs] == [("000002", "score")]
    short = _log().iloc[:2]
    diffs, _ = rc.compare_with_log(_day(), short)
    assert [(d["stock_code"], d["field"]) for d in diffs] == [("000003", "presence")]


def test_compare_held_only_when_the_log_has_it() -> None:
    diffs, compared = rc.compare_with_log(_day(), _log(), held={"000001"})
    assert diffs == [] and compared is False
    assert rc.holdings_note(Path("x.csv"), compared).startswith("로그에 보유 기록 없음")
    diffs, compared = rc.compare_with_log(_day(), _log(held_buffered=[True, False, True]), held={"000001"})
    assert compared is True and [(d["stock_code"], d["field"]) for d in diffs] == [("000003", "held_buffered")]
    assert rc.holdings_note(None, False).startswith("페이퍼 로그 없는 판단일")


def test_nightly_treats_exit_3_as_skipped() -> None:
    script = (ROOT / "scripts" / "nightly_ingest.sh").read_text(encoding="utf-8")
    assert "if [[ $rc -eq 3 ]]" in script and "recommend: skipped (log exists)" in script
    block = script[script.index('scripts/recommend.py\n'):]
    assert "chart_card.py" in block  # chart cards still run after a skipped recommend
