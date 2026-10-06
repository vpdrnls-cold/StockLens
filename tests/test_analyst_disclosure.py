"""Disclosure card (CURRENT_STATUS item 72) -- synthetic filings, tmp_path only."""
from __future__ import annotations

from datetime import date
import json

from src.analysts import disclosure as ds

T = date(2026, 10, 2)


def _f(dt: str, name: str, no: str) -> dict:
    return {"rcept_dt": dt, "report_nm": name, "rcept_no": no, "flr_nm": "삼성전자", "corp_name": "삼성전자"}


FILINGS = [
    _f("20261002", "[기재정정]주요사항보고서(자기주식취득결정)", "20261002000001"),  # T: included
    _f("20260903", "임원ㆍ주요주주특정증권등소유상황보고서", "20260903000002"),        # T-29: included
    _f("20260902", "임원ㆍ주요주주특정증권등소유상황보고서", "20260902000003"),        # T-30: excluded
    _f("20261005", "현금ㆍ현물배당결정", "20261005000004"),                          # after T: excluded
    _f("20260915", "투자설명서(일괄신고)", "20260915000005"),
    _f("20260920", "기업설명회(IR)개최(안내공시)", "20260920000006"),
]


def _card():
    return ds.build_disclosure_card(stock_code="005930", name="삼성전자", decision_date=T,
                                    filings=FILINGS, data_through="2026-10-04")


def test_window_includes_t_and_29_days_back_only() -> None:
    assert ds.window_bounds(T) == (date(2026, 9, 3), T)
    nos = {r["rcept_no"] for r in ds.filings_in_window(FILINGS, T)}
    assert nos == {"20261002000001", "20260903000002", "20260915000005", "20260920000006"}


def test_card_keys_layer_and_counts() -> None:
    card = _card()
    assert (card["card"], card["layer"], card["used_by_model"]) == ("disclosure", "reference", False)
    assert card["decision_date"] == "2026-10-02" and card["n_filings"] == 4
    assert sum(c["count"] for c in card["by_category"]) == card["n_filings"]
    assert card["n_corrections"] == 1
    cats = {r["rcept_no"]: r["category"] for r in card["filings"]}
    assert cats["20261002000001"] == "buyback_acquire"
    assert cats["20260915000005"] == "securities_filing"   # card-only group
    assert cats["20260920000006"] == "other"
    assert [r["rcept_dt"] for r in card["filings"]] == sorted((r["rcept_dt"] for r in card["filings"]), reverse=True)
    assert card["filings"][0]["url"].endswith("rcpNo=20261002000001")
    json.dumps(card, allow_nan=False)


def test_probe_categories_unchanged_for_item_60() -> None:
    # the probe keeps the original rules: issuance paperwork stays "other" there
    assert ds.categorize("투자설명서(일괄신고)") == "other"
    assert ds.categorize("투자설명서(일괄신고)", ds.CARD_CATEGORIES) == "securities_filing"
    assert set(ds.CATEGORY_LABELS) == {c for c, _ in ds.CARD_CATEGORIES} | {"other"}


def test_no_judgment_words_in_the_card() -> None:
    text = json.dumps(_card(), ensure_ascii=False)
    for word in ("호재", "악재", "긍정", "부정적", "매수", "매도"):
        assert word not in text


def test_write_and_read_back(tmp_path) -> None:
    card = _card()
    path = ds.write_disclosure_card(card, tmp_path)
    assert path == tmp_path / "20261002" / "005930_disclosure.json"
    assert json.loads(path.read_text(encoding="utf-8")) == card
