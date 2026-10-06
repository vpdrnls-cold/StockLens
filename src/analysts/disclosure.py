"""Disclosure analyst card (CURRENT_STATUS item 72, AGENTS.md 43): recent filings, no judgment.

Reference layer: lists what a company filed with DART in the 30 calendar days up to
the decision date, grouped by type, with corrections flagged and the original
link. It never says whether a filing is good or bad news (nothing validated
supports that, AGENTS 43.1/43.5) and uses no structured financial values (the
DART financial API is not point-in-time, item 60).

The report-name rules came from scripts/check_dart_sources.py (item 60), which now
imports them from here. ``CATEGORIES`` is unchanged so the item 60 counts stay
reproducible; the card adds one display-only group in front of it
(``CARD_CATEGORIES``: securities-issuance paperwork such as ELS filings).
"""

from __future__ import annotations

from datetime import date, timedelta
import json
from pathlib import Path
import re
from typing import Any, Iterable, Mapping

# Report-name keyword -> category. Matched on the normalized name (spaces and the
# leading [..] correction tag removed). First match wins, so order matters.
CATEGORIES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("prelim_earnings", ("영업(잠정)실적", "잠정실적")),
    ("periodic_report", ("사업보고서", "반기보고서", "분기보고서")),
    ("buyback_acquire", ("자기주식취득결정", "자기주식취득신탁계약체결결정")),
    ("buyback_dispose", ("자기주식처분결정", "자기주식취득신탁계약해지결정")),
    ("treasury_cancel", ("주식소각결정",)),
    ("rights_offering", ("유상증자결정",)),
    ("bonus_issue", ("무상증자결정",)),
    ("convertible_bond", ("전환사채권발행결정", "신주인수권부사채권발행결정", "교환사채권발행결정")),
    ("dividend", ("현금ㆍ현물배당결정", "현금·현물배당결정", "배당결정")),
    ("merger_split", ("합병결정", "분할결정", "분할합병결정", "영업양수결정", "영업양도결정")),
    ("supply_contract", ("단일판매ㆍ공급계약", "단일판매·공급계약")),
    ("large_holding_5pct", ("주식등의대량보유상황보고서",)),
    ("insider_holding", ("임원ㆍ주요주주특정증권등소유상황보고서", "임원·주요주주특정증권등소유상황보고서")),
    ("largest_holder_change", ("최대주주변경", "최대주주등소유주식변동신고서")),
    ("fair_disclosure_other", ("공정공시",)),
)
# Card only (item 72): issuance paperwork (e.g. 006800's ELS filings, item 60) is
# grouped first so it does not bury the company's own event filings.
CARD_CATEGORIES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("securities_filing", ("증권발행실적보고서", "투자설명서", "일괄신고서", "일괄신고추가서류", "증권신고서")),
    *CATEGORIES,
)
CATEGORY_LABELS = {
    "securities_filing": "증권 발행 서류",
    "prelim_earnings": "잠정실적",
    "periodic_report": "정기보고서",
    "buyback_acquire": "자기주식 취득",
    "buyback_dispose": "자기주식 처분",
    "treasury_cancel": "주식 소각",
    "rights_offering": "유상증자",
    "bonus_issue": "무상증자",
    "convertible_bond": "CB·BW·EB 발행",
    "dividend": "배당",
    "merger_split": "합병·분할·영업양수도",
    "supply_contract": "단일판매·공급계약",
    "large_holding_5pct": "5% 대량보유 보고",
    "insider_holding": "임원·주요주주 소유 보고",
    "largest_holder_change": "최대주주 관련",
    "fair_disclosure_other": "기타 공정공시",
    "other": "기타",
}
WINDOW_DAYS = 30
DART_VIEW_URL = "https://dart.fss.or.kr/dsaf001/main.do?rcpNo={}"
SCHEMA_VERSION = 1
CAVEATS = (
    "공시 접수일만 있고 시각이 없어, 판단일 당일 공시가 장 마감 전인지 후인지 구분할 수 없습니다.",
    "공시의 좋고 나쁨은 판단하지 않습니다 — 이를 뒷받침하는 검증된 근거가 없습니다.",
    "재무 수치는 넣지 않습니다 — DART 재무 API 값은 공시 당시 값이 아닐 수 있습니다(정정 반영).",
)
DEFAULT_OUT_ROOT = Path("reports/analyst_cards")
_TAG_RE = re.compile(r"^\[[^\]]*\]")


def normalize_report_name(name: str) -> str:
    """Drop the leading [기재정정]/[첨부추가]... tag and all whitespace."""
    name = name.strip()
    while True:
        stripped = _TAG_RE.sub("", name).strip()
        if stripped == name:
            break
        name = stripped
    return re.sub(r"\s+", "", name)


def correction_tag(name: str) -> str | None:
    match = _TAG_RE.match(name.strip())
    return match.group(0) if match else None


def categorize(report_nm: str, categories: tuple[tuple[str, tuple[str, ...]], ...] = CATEGORIES) -> str:
    norm = normalize_report_name(report_nm)
    for category, keys in categories:
        if any(key in norm for key in keys):
            return category
    return "other"


def window_bounds(decision_date: date, days: int = WINDOW_DAYS) -> tuple[date, date]:
    """Inclusive [T - days + 1, T] in calendar days."""
    return decision_date - timedelta(days=days - 1), decision_date


def filings_in_window(filings: Iterable[Mapping[str, Any]], decision_date: date,
                      days: int = WINDOW_DAYS) -> list[dict[str, Any]]:
    start, end = window_bounds(decision_date, days)
    lo, hi = start.strftime("%Y%m%d"), end.strftime("%Y%m%d")
    return [dict(f) for f in filings if lo <= str(f.get("rcept_dt", "")) <= hi]


def build_disclosure_card(
    *,
    stock_code: str,
    name: str,
    decision_date: date,
    filings: Iterable[Mapping[str, Any]],
    data_through: str | None,
    days: int = WINDOW_DAYS,
) -> dict[str, Any]:
    """Arrange the stored filing rows of one company for the decision date (no judgment)."""
    rows = []
    for f in filings_in_window(filings, decision_date, days):
        report = str(f.get("report_nm", "")).strip()
        category = categorize(report, CARD_CATEGORIES)
        rows.append({
            "rcept_dt": f"{f['rcept_dt'][:4]}-{f['rcept_dt'][4:6]}-{f['rcept_dt'][6:8]}",
            "report_nm": report,
            "category": category,
            "label": CATEGORY_LABELS[category],
            "correction": correction_tag(report),
            "filer": str(f.get("flr_nm", "")).strip(),
            "rcept_no": str(f.get("rcept_no", "")),
            "url": DART_VIEW_URL.format(f.get("rcept_no", "")),
        })
    rows.sort(key=lambda r: (r["rcept_dt"], r["rcept_no"]), reverse=True)
    counts: dict[str, int] = {}
    for r in rows:
        counts[r["category"]] = counts.get(r["category"], 0) + 1
    order = [c for c, _ in CARD_CATEGORIES] + ["other"]
    by_category = [{"category": c, "label": CATEGORY_LABELS[c], "count": counts[c]} for c in order if c in counts]
    start, end = window_bounds(decision_date, days)
    return {
        "card": "disclosure", "layer": "reference", "used_by_model": False,
        "stock_code": stock_code, "name": name, "decision_date": decision_date.isoformat(),
        "schema_version": SCHEMA_VERSION,
        "window": {"start": start.isoformat(), "end": end.isoformat(), "days": days},
        "data_through": data_through,
        "n_filings": len(rows),
        "n_corrections": sum(1 for r in rows if r["correction"]),
        "by_category": by_category,
        "filings": rows,
        "caveats": list(CAVEATS),
    }


def write_disclosure_card(card: dict[str, Any], out_root: Path = DEFAULT_OUT_ROOT) -> Path:
    folder = Path(out_root) / card["decision_date"].replace("-", "")
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{card['stock_code']}_disclosure.json"
    path.write_text(json.dumps(card, ensure_ascii=False, indent=1, allow_nan=False), encoding="utf-8")
    return path
