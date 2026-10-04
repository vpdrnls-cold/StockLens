"""OpenDART probe (item 60): report-name parsing and point-in-time verdicts, no network."""
from __future__ import annotations

from typing import Any

from scripts import check_dart_sources as dart


def test_normalize_drops_tags_and_spaces() -> None:
    assert dart.normalize_report_name("[기재정정]사업보고서 (2018.12)") == "사업보고서(2018.12)"
    assert dart.normalize_report_name("[기재정정][첨부추가] 주요사항보고서(자기주식취득결정)") == "주요사항보고서(자기주식취득결정)"
    assert dart.correction_tag("[기재정정]사업보고서 (2018.12)") == "[기재정정]"
    assert dart.correction_tag("사업보고서 (2018.12)") is None


def test_categorize_first_match_wins() -> None:
    assert dart.categorize("주요사항보고서(자기주식취득결정)") == "buyback_acquire"
    assert dart.categorize("연결재무제표기준영업(잠정)실적(공정공시)") == "prelim_earnings"
    assert dart.categorize("주요사항보고서(유상증자결정)") == "rights_offering"
    assert dart.categorize("임원ㆍ주요주주특정증권등소유상황보고서") == "insider_holding"
    assert dart.categorize("기업설명회(IR)개최(안내공시)") == "other"


def test_window_of_uses_validation_windows_only() -> None:
    assert dart.window_of("20120101") == "W1"
    assert dart.window_of("20191231") == "W2"
    assert dart.window_of("20230630") == "W3"
    assert dart.window_of("20230701") is None  # test split: never counted
    assert dart.window_of("20111231") is None


class _FakeDart:
    def __init__(self, api_rcepts: list[str]) -> None:
        self.api_rcepts = api_rcepts

    def get(self, endpoint: str, params: dict[str, Any], raw: bool = False) -> dict[str, Any]:
        return {"status": "000", "list": [{"rcept_no": r} for r in self.api_rcepts]}


def _filings() -> list[dict[str, Any]]:
    return [
        {"report_nm": "[기재정정]사업보고서 (2018.12)", "rcept_dt": "20190520", "rcept_no": "B"},
        {"report_nm": "사업보고서 (2018.12)", "rcept_dt": "20190401", "rcept_no": "A"},
        {"report_nm": "분기보고서 (2018.09)", "rcept_dt": "20181114", "rcept_no": "Q"},
    ]


def test_pit_verdicts() -> None:
    assert [f["rcept_no"] for f in dart.annual_report_filings(_filings(), 2018)] == ["A", "B"]
    latest = dart.probe_pit(_FakeDart(["B"]), "x", _filings(), range(2018, 2019))[0]
    assert latest["verdict"] == "latest_correction"
    original = dart.probe_pit(_FakeDart(["A"]), "x", _filings(), range(2018, 2019))[0]
    assert original["verdict"] == "original_despite_correction"
    empty = dart.probe_pit(_FakeDart([]), "x", _filings(), range(2018, 2019))[0]
    assert empty["verdict"] == "no_data"
