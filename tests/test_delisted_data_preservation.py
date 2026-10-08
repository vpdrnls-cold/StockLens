"""A delisted stock's stored history must survive re-collection (CURRENT_STATUS item 87, 1-5).

Kiwoom answers ka10081 for a delisted code with return_code 0 and ONE row whose fields
are all empty strings (checked live on 2026-10-08 for 117930/103130/067250, item 83).
The Friday job re-downloads full history for every collected code, so a stock that
delists during forward2 would get that answer every week. Its stored bars (needed for
the last-price exit, item 87 decision 2) must never be deleted or shortened by it --
pinned here rather than assumed from "the storage merges by date".
"""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest

from src.data.ingest import ingest_kiwoom_daily_chart_batch
from src.data.storage import HistoricalStorage

FIXTURE = Path(__file__).parent / "fixtures" / "ka10081_response.json"
EMPTY_ROW = {"cur_prc": "", "trde_qty": "", "trde_prica": "", "dt": "", "open_pric": "", "high_pric": "",
             "low_pric": "", "pred_pre": "", "pred_pre_sig": "", "trde_tern_rt": "", "upd_stkpc_tp": "", "upd_rt": ""}


class FakeClient:
    def __init__(self, responses: dict[str, dict]) -> None:
        self.responses = responses

    def get_daily_chart(self, stock_code: str, base_date: str) -> dict:
        return deepcopy(self.responses[stock_code])


def _full() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))  # 005930, 2026-08-28 and 2026-08-31


def _seed(tmp_path: Path) -> tuple[HistoricalStorage, Path, bytes]:
    storage = HistoricalStorage(tmp_path)
    ingest_kiwoom_daily_chart_batch(FakeClient({"005930": _full()}), ["005930"], "20260831", storage=storage)
    path = tmp_path / "processed" / "historical" / "005930.json"
    return storage, path, path.read_bytes()


def test_kiwoom_delisted_answer_leaves_stored_bars_untouched(tmp_path: Path) -> None:
    storage, path, before = _seed(tmp_path)
    delisted = {"stk_cd": "005930", "stk_dt_pole_chart_qry": [dict(EMPTY_ROW)], "return_code": 0,
                "return_msg": "정상적으로 처리되었습니다"}
    results = ingest_kiwoom_daily_chart_batch(FakeClient({"005930": delisted}), ["005930"], "20261009", storage=storage)
    assert not results[0].success  # reported as a per-stock failure, not silently "0 bars"
    assert path.read_bytes() == before
    assert [b.trade_date.isoformat() for b in storage.load_daily_bars("005930")] == ["2026-08-28", "2026-08-31"]


def test_empty_row_list_keeps_every_stored_bar(tmp_path: Path) -> None:
    storage, path, before = _seed(tmp_path)
    empty = {"stk_cd": "005930", "stk_dt_pole_chart_qry": [], "return_code": 0, "return_msg": ""}
    results = ingest_kiwoom_daily_chart_batch(FakeClient({"005930": empty}), ["005930"], "20261009", storage=storage)
    assert results[0].success and results[0].ingestion.bar_count == 0
    assert json.loads(path.read_text(encoding="utf-8")) == json.loads(before.decode("utf-8"))


def test_shorter_history_never_removes_older_bars(tmp_path: Path) -> None:
    storage, _, _ = _seed(tmp_path)
    recent_only = _full()
    recent_only["stk_dt_pole_chart_qry"] = recent_only["stk_dt_pole_chart_qry"][:1]  # 2026-08-31 only
    ingest_kiwoom_daily_chart_batch(FakeClient({"005930": recent_only}), ["005930"], "20261009", storage=storage)
    assert [b.trade_date.isoformat() for b in storage.load_daily_bars("005930")] == ["2026-08-28", "2026-08-31"]


def test_one_delisted_stock_does_not_stop_or_touch_the_others(tmp_path: Path) -> None:
    storage, path, before = _seed(tmp_path)
    other = _full()
    other["stk_cd"] = "000660"
    delisted = {"stk_cd": "005930", "stk_dt_pole_chart_qry": [dict(EMPTY_ROW)], "return_code": 0, "return_msg": ""}
    results = ingest_kiwoom_daily_chart_batch(
        FakeClient({"005930": delisted, "000660": other}), ["005930", "000660"], "20261009", storage=storage)
    assert [r.success for r in results] == [False, True]
    assert path.read_bytes() == before and len(storage.load_daily_bars("000660")) == 2


@pytest.mark.parametrize("saver", ["save_investor_flows", "save_index_bars"])
def test_merged_series_keep_records_on_an_empty_fetch(tmp_path: Path, saver: str) -> None:
    storage = HistoricalStorage(tmp_path)
    code = "005930" if saver == "save_investor_flows" else "201"
    path = storage._investor_flow_path(code) if saver == "save_investor_flows" else storage._index_path(code)
    path.parent.mkdir(parents=True, exist_ok=True)
    seeded = [{"trade_date": "2026-08-31", "is_complete": True, "value": 1}]
    path.write_text(json.dumps(seeded), encoding="utf-8")
    getattr(storage, saver)(code, [])
    assert json.loads(path.read_text(encoding="utf-8")) == seeded
