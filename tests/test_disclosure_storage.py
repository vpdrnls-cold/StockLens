"""Disclosure list storage (CURRENT_STATUS item 72) -- tmp_path only."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from src.data.disclosures import DisclosureStorage


def _row(no: str, dt: str, rm: str = "") -> dict:
    return {"rcept_no": no, "rcept_dt": dt, "report_nm": "보고서", "flr_nm": "회사", "rm": rm,
            "corp_code": "00126380", "corp_name": "삼성전자", "stock_code": "005930", "corp_cls": "Y",
            "extra": "dropped"}


def test_merge_by_receipt_number_without_duplicates(tmp_path) -> None:
    s = DisclosureStorage(tmp_path)
    assert s.merge("005930", [_row("1", "20260901"), _row("2", "20260902")], retrieved_at="t1") == 2
    assert s.merge("005930", [_row("2", "20260902", rm="유"), _row("3", "20260903")], retrieved_at="t2") == 1
    rows = s.load("005930")
    assert [r["rcept_no"] for r in rows] == ["1", "2", "3"]       # old rows kept, sorted
    assert rows[1]["rm"] == "유" and rows[1]["retrieved_at"] == "t2"  # later fetch replaces
    assert "extra" not in rows[0]
    assert s.data_through("005930") == "t2"


def test_raw_saved_per_fetch(tmp_path) -> None:
    s = DisclosureStorage(tmp_path)
    p = s.save_raw("005930", [_row("1", "20260901")], now=datetime(2026, 10, 5, tzinfo=timezone.utc))
    assert p.parent == tmp_path / "raw" / "dart" / "list" / "005930" and p.exists()


def test_corp_map_expires(tmp_path) -> None:
    s = DisclosureStorage(tmp_path)
    t0 = datetime(2026, 10, 5, tzinfo=timezone.utc)
    assert s.load_corp_map(now=t0) is None
    s.save_corp_map({"005930": {"corp_code": "00126380"}}, now=t0)
    assert s.load_corp_map(now=t0 + timedelta(days=29))["005930"]["corp_code"] == "00126380"
    assert s.load_corp_map(now=t0 + timedelta(days=31)) is None
