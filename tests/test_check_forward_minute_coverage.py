"""Forward minute coverage check (item 53): status rules only, no prices printed."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from scripts import check_forward_minute_coverage as cov
from scripts.intraday_ic_diagnostic import REG_TIMES


def _write_day(code_dir: Path, day: str, times: list[str]) -> None:
    code_dir.mkdir(parents=True, exist_ok=True)
    recs = [{"cntr_tm": f"{day}{t.replace(':', '')}00", "open_pric": "+100", "high_pric": "+101",
             "low_pric": "-99", "cur_prc": "+100", "trde_qty": "10"} for t in times]
    (code_dir / f"{day}.json").write_text(json.dumps({"stk_min_pole_chart_qry": recs}), encoding="utf-8")


def test_day_status_uses_the_27_bar_rule(tmp_path: Path) -> None:
    _write_day(tmp_path / "000001", "20300102", REG_TIMES)
    _write_day(tmp_path / "000001", "20300103", REG_TIMES[:-3])
    _write_day(tmp_path / "000001", "20291230", REG_TIMES)  # before start -> ignored
    st = cov.day_status(tmp_path, ["000001", "000002"], pd.Timestamp("2030-01-01"))
    assert st["000001"] == {pd.Timestamp("2030-01-02"): True, pd.Timestamp("2030-01-03"): False}
    assert st["000002"] == {}


def test_classify_missing_incomplete_and_empty_weekdays() -> None:
    d1, d2, d4 = (pd.Timestamp(x) for x in ("2030-01-01", "2030-01-02", "2030-01-04"))
    status = {"A": {d1: True, d2: False, d4: True}, "B": {d1: True, d4: True}}
    table, empty = cov.classify(status, d1)
    s = table.set_index(["date", "stock_code"])["status"]
    assert s[(d1, "A")] == "ok" and s[(d2, "A")] == "incomplete" and s[(d2, "B")] == "missing"
    assert empty == [pd.Timestamp("2030-01-03")]  # weekday with no bars for any stock


def test_refetch_lookback_reaches_past_the_gap() -> None:
    assert cov.refetch_lookback_days(pd.Timestamp("2030-01-10"), pd.Timestamp("2030-01-20")) == 12
