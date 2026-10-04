"""Probe OpenDART before deciding on disclosure features (item 60).

Usage:
    STOCKLENS_UNIVERSE=top50 PYTHONPATH=. python scripts/check_dart_sources.py
    STOCKLENS_UNIVERSE=top50 PYTHONPATH=. python scripts/check_dart_sources.py --codes 005930 000660

Same approach as ``check_macro_sources.py`` (AGENTS.md 19): look at the real
responses before designing anything. This script only reads disclosure
metadata and financial statements -- no prices, no labels -- and only for the
validation windows W1~W3 (2012-01-01 ~ 2023-06-30).

Questions this answers:
1. Mapping: does every universe stock code resolve to a DART corp_code?
2. History: from which business year do the structured financial APIs
   (fnlttSinglAcnt, fnlttSinglAcntAll) return data? Does W1 (2012~) get covered?
3. Sample size: per event type and per window, how many filings does the
   universe actually have (disclosure list, all filing types)?
4. Point-in-time: for annual reports, does fnlttSinglAcnt return the
   original filing's rcept_no or a later correction ([기재정정])?
5. Timing fields: what does a list row contain (date only, or time too)?

Key comes from .env (DART_API_KEY) and is never printed.
Raw responses + summary CSVs go to data/raw/dart_probe/<timestamp>/ (gitignored).
"""

from __future__ import annotations

import argparse
import csv
from collections import Counter, defaultdict
from datetime import datetime
import io
import json
import os
from pathlib import Path
import re
import sys
import time
from typing import Any
import xml.etree.ElementTree as ET
import zipfile

import requests
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.data.universe import get_universe  # noqa: E402

SAVE_ROOT = PROJECT_ROOT / "data" / "raw" / "dart_probe"
DART_BASE = "https://opendart.fss.or.kr/api"
TIMEOUT = 30
SLEEP = 0.12  # stay far below the documented per-minute limits

# Validation windows only (same dates as scripts/walk_forward_*.py).
WINDOWS = (
    ("W1", "20120101", "20151231"),
    ("W2", "20160101", "20191231"),
    ("W3", "20200101", "20230630"),
)
PROBE_START, PROBE_END = WINDOWS[0][1], WINDOWS[-1][2]

# Report-name keyword -> category. Matched on the normalized name (spaces and
# the leading [..] correction tag removed). First match wins, so order matters.
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
_TAG_RE = re.compile(r"^\[[^\]]*\]")


class DartError(RuntimeError):
    pass


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


def categorize(report_nm: str) -> str:
    norm = normalize_report_name(report_nm)
    for category, keys in CATEGORIES:
        if any(key in norm for key in keys):
            return category
    return "other"


def window_of(rcept_dt: str) -> str | None:
    for name, start, end in WINDOWS:
        if start <= rcept_dt <= end:
            return name
    return None


def annual_report_filings(rows: list[dict[str, Any]], year: int) -> list[dict[str, Any]]:
    """Business-report filings (original + corrections) for fiscal ``year``, oldest first."""
    period = f"({year}.12)"
    out = [
        r for r in rows
        if "사업보고서" in normalize_report_name(r.get("report_nm", ""))
        and period in str(r.get("report_nm", "")).replace(" ", "")
    ]
    return sorted(out, key=lambda r: (r.get("rcept_dt", ""), r.get("rcept_no", "")))


class Dart:
    def __init__(self, key: str, save_dir: Path) -> None:
        self.key = key
        self.save_dir = save_dir
        self.calls = 0

    def _scrub(self, text: str) -> str:
        return text.replace(self.key, "***") if self.key else text

    def get(self, endpoint: str, params: dict[str, Any], raw: bool = False) -> Any:
        time.sleep(SLEEP)
        self.calls += 1
        try:
            resp = requests.get(
                f"{DART_BASE}/{endpoint}", params={"crtfc_key": self.key, **params}, timeout=TIMEOUT
            )
        except requests.RequestException as error:
            raise DartError(self._scrub(f"request failed: {error}")) from None
        if not resp.ok:
            raise DartError(self._scrub(f"HTTP {resp.status_code}: {resp.text[:300]}"))
        if raw:
            return resp.content
        try:
            payload = resp.json()
        except ValueError:
            raise DartError(self._scrub(f"not JSON: {resp.text[:300]}")) from None
        status = payload.get("status")
        if status not in ("000", "013"):  # 013 = no data
            raise DartError(f"{endpoint} status {status}: {payload.get('message')}")
        return payload

    def save(self, name: str, payload: Any) -> None:
        (self.save_dir / f"{name}.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8"
        )


def load_corp_codes(dart: Dart) -> dict[str, dict[str, str]]:
    content = dart.get("corpCode.xml", {}, raw=True)
    with zipfile.ZipFile(io.BytesIO(content)) as zf:
        xml_bytes = zf.read(zf.namelist()[0])
    mapping: dict[str, dict[str, str]] = {}
    for node in ET.fromstring(xml_bytes).iter("list"):
        stock = (node.findtext("stock_code") or "").strip()
        if stock:
            mapping[stock] = {
                "corp_code": (node.findtext("corp_code") or "").strip(),
                "corp_name": (node.findtext("corp_name") or "").strip(),
                "modify_date": (node.findtext("modify_date") or "").strip(),
            }
    return mapping


def fetch_filings(dart: Dart, corp_code: str, start: str, end: str) -> list[dict[str, Any]]:
    """All filings (every pblntf_ty) for one corp, year by year, all pages."""
    rows: list[dict[str, Any]] = []
    for year in range(int(start[:4]), int(end[:4]) + 1):
        bgn = max(start, f"{year}0101")
        fin = min(end, f"{year}1231")
        page = 1
        while True:
            payload = dart.get(
                "list.json",
                {"corp_code": corp_code, "bgn_de": bgn, "end_de": fin,
                 "last_reprt_at": "N", "page_no": page, "page_count": 100},
            )
            rows.extend(payload.get("list", []) or [])
            if page >= int(payload.get("total_page") or 1):
                break
            page += 1
    return rows


def probe_history(dart: Dart, corp_code: str) -> list[dict[str, Any]]:
    """Which business years the structured financial APIs answer for one corp."""
    out = []
    for year in range(2010, 2018):
        for endpoint in ("fnlttSinglAcnt.json", "fnlttSinglAcntAll.json"):
            params = {"corp_code": corp_code, "bsns_year": str(year), "reprt_code": "11011"}
            if endpoint == "fnlttSinglAcntAll.json":
                params["fs_div"] = "CFS"
            try:
                payload = dart.get(endpoint, params)
                status, n = payload.get("status"), len(payload.get("list", []) or [])
            except DartError as error:
                status, n = f"ERR {error}"[:80], 0
            out.append({"bsns_year": year, "endpoint": endpoint, "status": status, "rows": n})
    return out


def probe_pit(dart: Dart, corp_code: str, filings: list[dict[str, Any]], years: range) -> list[dict[str, Any]]:
    """Does fnlttSinglAcnt return the original annual report or a correction?"""
    out = []
    for year in years:
        annual = annual_report_filings(filings, year)
        try:
            payload = dart.get(
                "fnlttSinglAcnt.json",
                {"corp_code": corp_code, "bsns_year": str(year), "reprt_code": "11011"},
            )
        except DartError as error:
            out.append({"bsns_year": year, "verdict": f"error: {error}"[:80]})
            continue
        api_rcepts = sorted({r.get("rcept_no") for r in payload.get("list", []) or []})
        original = annual[0]["rcept_no"] if annual else None
        latest = annual[-1]["rcept_no"] if annual else None
        if not api_rcepts:
            verdict = "no_data"
        elif not annual:
            verdict = "no_filing_in_list"
        elif api_rcepts == [original]:
            verdict = "original" if len(annual) == 1 else "original_despite_correction"
        elif latest in api_rcepts:
            verdict = "latest_correction"
        else:
            verdict = "other"
        out.append({
            "bsns_year": year, "n_filings": len(annual), "original": original,
            "latest": latest, "api_rcept_no": ";".join(api_rcepts), "verdict": verdict,
        })
    return out


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    fields: list[str] = []
    for row in rows:
        fields.extend(k for k in row if k not in fields)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--codes", nargs="*", help="stock codes (default: STOCKLENS_UNIVERSE)")
    parser.add_argument("--pit-corps", type=int, default=10, help="corps used for the point-in-time check")
    args = parser.parse_args()

    load_dotenv(PROJECT_ROOT / ".env")
    key = os.getenv("DART_API_KEY", "").strip()
    if not key:
        print("DART_API_KEY missing in .env")
        return 1
    codes = list(args.codes or get_universe())

    fetched_at = datetime.now()
    save_dir = SAVE_ROOT / fetched_at.strftime("%Y%m%d_%H%M%S")
    save_dir.mkdir(parents=True, exist_ok=True)
    print(f"fetched_at={fetched_at.isoformat(timespec='seconds')} universe={len(codes)} raw -> {save_dir}")
    dart = Dart(key, save_dir)

    # 1. mapping
    print("\n===== 1. corp_code mapping =====")
    corp_map = load_corp_codes(dart)
    mapped = {c: corp_map[c] for c in codes if c in corp_map}
    missing = [c for c in codes if c not in corp_map]
    print(f"  {len(mapped)}/{len(codes)} mapped; missing: {missing or '-'}")

    # 2. history of structured financial APIs (largest stock as the probe)
    print("\n===== 2. financial API history (annual report, first mapped stock) =====")
    first = next(iter(mapped), None)
    if first:
        hist = probe_history(dart, mapped[first]["corp_code"])
        dart.save("history_financial_api", hist)
        for row in hist:
            print(f"  {first} {row['bsns_year']} {row['endpoint']:<24} status={row['status']} rows={row['rows']}")

    # 3. filing counts
    print(f"\n===== 3. filings {PROBE_START}~{PROBE_END} (all types, incl. corrections) =====")
    all_rows: list[dict[str, Any]] = []
    filings_by_code: dict[str, list[dict[str, Any]]] = {}
    for i, (code, info) in enumerate(mapped.items(), 1):
        try:
            rows = fetch_filings(dart, info["corp_code"], PROBE_START, PROBE_END)
        except DartError as error:
            print(f"  {code} failed: {error}")
            continue
        filings_by_code[code] = rows
        dart.save(f"list_{code}", rows)
        for r in rows:
            r["_code"] = code
        all_rows.extend(rows)
        print(f"  [{i}/{len(mapped)}] {code} {info['corp_name']}: {len(rows)} filings (calls so far {dart.calls})")

    if all_rows:
        print(f"  list row keys: {sorted(k for k in all_rows[0] if not k.startswith('_'))}")
        print(f"  rm values: {dict(Counter(r.get('rm', '') for r in all_rows).most_common(10))}")

    counts: dict[tuple[str, str], Counter] = defaultdict(Counter)  # (category, window) -> codes
    corrections: Counter = Counter()
    for r in all_rows:
        win = window_of(r.get("rcept_dt", ""))
        if win is None:
            continue
        tag = correction_tag(r.get("report_nm", ""))
        if tag:
            corrections[tag] += 1
            continue  # count original filings only
        counts[(categorize(r.get("report_nm", "")), win)][r["_code"]] += 1

    summary = []
    cats = [c for c, _ in CATEGORIES] + ["other"]
    print(f"\n  {'category':<24}" + "".join(f"{w:>14}" for w, _, _ in WINDOWS) + "   (filings / stocks with >=1)")
    for cat in cats:
        cells, row = [], {"category": cat}
        for w, _, _ in WINDOWS:
            c = counts.get((cat, w), Counter())
            cells.append(f"{sum(c.values()):>8}/{len(c):>4}")
            row[f"{w}_filings"], row[f"{w}_stocks"] = sum(c.values()), len(c)
        summary.append(row)
        print(f"  {cat:<24}" + "".join(f"{x:>14}" for x in cells))
    print(f"  correction-tagged filings (excluded above): {dict(corrections.most_common())}")
    write_csv(save_dir / "summary_counts.csv", summary)

    other = Counter(
        normalize_report_name(r.get("report_nm", "")) for r in all_rows
        if window_of(r.get("rcept_dt", "")) and not correction_tag(r.get("report_nm", ""))
        and categorize(r.get("report_nm", "")) == "other"
    )
    print("  top 'other' report names:")
    for name, n in other.most_common(15):
        print(f"    {n:>6}  {name}")
    write_csv(save_dir / "other_report_names.csv", [{"report_nm": k, "n": v} for k, v in other.most_common()])

    # 4. point-in-time check on annual financials
    print("\n===== 4. point-in-time: fnlttSinglAcnt vs original annual report =====")
    pit_rows = []
    for code in list(filings_by_code)[: args.pit_corps]:
        for row in probe_pit(dart, mapped[code]["corp_code"], filings_by_code[code], range(2015, 2023)):
            pit_rows.append({"code": code, **row})
    write_csv(save_dir / "pit_check.csv", pit_rows)
    verdicts = Counter(r["verdict"] for r in pit_rows)
    print(f"  verdicts: {dict(verdicts)}")
    for r in pit_rows:
        if r["verdict"] not in ("original", "no_data"):
            print(f"    {r['code']} {r['bsns_year']}: {r['verdict']} (filings={r.get('n_filings')})")

    print(f"\ntotal API calls: {dart.calls}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
