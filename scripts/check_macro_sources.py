"""Probe ECOS (Bank of Korea) and FRED before building macro ingestion (item 59).

Usage:
    PYTHONPATH=. python scripts/check_macro_sources.py
    PYTHONPATH=. python scripts/check_macro_sources.py --only fred --days 30

Same approach as ``check_kiwoom_flow_index.py`` (AGENTS.md 19): look at the
real responses before writing a client, instead of guessing codes/fields.

Questions this answers:
1. ECOS: which item codes do the daily market-rate (817Y002) and daily
   FX (731Y001) tables use, how far back does each go, and what does a
   row look like (units, missing-day handling)?
2. FRED: for each candidate series, the history start, frequency, units,
   last update, and how holidays/missing values appear ("." rows).
3. Both: does a request return today's / yesterday's value yet (release lag)?

Keys come from .env (ECOS_API_KEY, FRED_API_KEY) and are never printed:
every URL and error message is scrubbed before printing or saving.
Raw responses go to data/raw/macro_probe/<timestamp>/ (gitignored).
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta
import json
import os
from pathlib import Path
import sys
from typing import Any

import requests
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SAVE_ROOT = PROJECT_ROOT / "data" / "raw" / "macro_probe"
TIMEOUT = 20

ECOS_BASE = "https://ecos.bok.or.kr/api"
ECOS_TABLES = {
    "817Y002": "시장금리(일별)",
    "731Y001": "주요국 통화의 대원화환율(일별)",
}
# Item names we expect to want; matched as substrings against ECOS item names.
ECOS_WANTED = ("국고채(3년)", "국고채(10년)", "CD(91일)", "회사채(3년, AA-)", "원/미국달러")

FRED_BASE = "https://api.stlouisfed.org/fred"
FRED_SERIES = {
    "DCOILWTICO": "WTI crude oil spot",
    "DGS10": "US 10y Treasury",
    "DGS2": "US 2y Treasury",
    "VIXCLS": "CBOE VIX",
    "DTWEXBGS": "Broad USD index",
    "SP500": "S&P 500 (FRED keeps ~10y only)",
    "GOLDAMGBD228NLBM": "LBMA gold AM (may be discontinued)",
}


def _scrub(text: str, secrets: list[str]) -> str:
    for secret in secrets:
        if secret:
            text = text.replace(secret, "***")
    return text


def _get_json(url: str, params: dict[str, Any] | None, secrets: list[str]) -> Any:
    try:
        response = requests.get(url, params=params, timeout=TIMEOUT)
    except requests.RequestException as error:
        raise RuntimeError(_scrub(f"request failed: {error}", secrets)) from None
    if not response.ok:
        raise RuntimeError(_scrub(f"HTTP {response.status_code}: {response.text[:300]}", secrets))
    try:
        return response.json()
    except ValueError:
        raise RuntimeError(_scrub(f"not JSON: {response.text[:300]}", secrets)) from None


def _save(save_dir: Path, name: str, payload: Any) -> None:
    (save_dir / f"{name}.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8"
    )


def _ecos_rows(payload: Any, service: str) -> tuple[int | None, list[dict[str, Any]], str | None]:
    """(list_total_count, rows, error message) from an ECOS JSON response."""
    if isinstance(payload, dict) and "RESULT" in payload:  # ECOS error envelope
        r = payload["RESULT"]
        return None, [], f"{r.get('CODE')} {r.get('MESSAGE')}"
    body = payload.get(service, {}) if isinstance(payload, dict) else {}
    return body.get("list_total_count"), body.get("row", []), None


def probe_ecos(key: str, days: int, save_dir: Path) -> int:
    secrets = [key]
    status = 0
    today = datetime.now()
    for table, title in ECOS_TABLES.items():
        print(f"\n===== ECOS {table} {title} =====")
        try:
            items_payload = _get_json(
                f"{ECOS_BASE}/StatisticItemList/{key}/json/kr/1/500/{table}", None, secrets
            )
        except RuntimeError as error:
            print(f"  item list failed: {error}")
            status = 1
            continue
        _save(save_dir, f"ecos_{table}_items", items_payload)
        _, items, err = _ecos_rows(items_payload, "StatisticItemList")
        if err:
            print(f"  item list error: {err}")
            status = 1
            continue
        print(f"  {len(items)} items")
        wanted = [it for it in items if any(w in str(it.get("ITEM_NAME", "")) for w in ECOS_WANTED)]
        for it in wanted:
            print(
                f"  item {it.get('ITEM_CODE')} {it.get('ITEM_NAME')} | cycle={it.get('CYCLE')} "
                f"{it.get('START_TIME')}~{it.get('END_TIME')} | unit={it.get('UNIT_NAME')} "
                f"| rows={it.get('DATA_CNT')}"
            )
        for it in wanted:
            code = it.get("ITEM_CODE")
            start = (today - timedelta(days=days)).strftime("%Y%m%d")
            end = today.strftime("%Y%m%d")
            try:
                payload = _get_json(
                    f"{ECOS_BASE}/StatisticSearch/{key}/json/kr/1/1000/{table}/D/{start}/{end}/{code}",
                    None,
                    secrets,
                )
            except RuntimeError as error:
                print(f"  search {code} failed: {error}")
                status = 1
                continue
            _save(save_dir, f"ecos_{table}_{code}_recent", payload)
            total, rows, err = _ecos_rows(payload, "StatisticSearch")
            if err:
                print(f"  search {code}: {err}")
                continue
            last = rows[-3:]
            print(
                f"  {code} last {days}d: {total} rows; latest "
                + ", ".join(f"{r.get('TIME')}={r.get('DATA_VALUE')}" for r in last)
            )
            if rows:
                print(f"    row keys: {sorted(rows[-1].keys())}")
    return status


def probe_fred(key: str, days: int, save_dir: Path) -> int:
    secrets = [key]
    status = 0
    start = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    for series_id, title in FRED_SERIES.items():
        print(f"\n===== FRED {series_id} ({title}) =====")
        base = {"series_id": series_id, "api_key": key, "file_type": "json"}
        try:
            info = _get_json(f"{FRED_BASE}/series", base, secrets)
            obs = _get_json(
                f"{FRED_BASE}/series/observations", {**base, "observation_start": start}, secrets
            )
        except RuntimeError as error:
            print(f"  failed: {error}")
            status = 1
            continue
        _save(save_dir, f"fred_{series_id}_info", info)
        _save(save_dir, f"fred_{series_id}_recent", obs)
        for s in info.get("seriess", []):
            print(
                f"  {s.get('observation_start')}~{s.get('observation_end')} | {s.get('frequency_short')} "
                f"| {s.get('units_short')} | last_updated {s.get('last_updated')}"
            )
            notes = str(s.get("notes", "")).replace("\n", " ")
            if "discontinu" in notes.lower():
                print(f"  NOTE: {notes[:200]}")
        rows = obs.get("observations", [])
        missing = sum(1 for r in rows if r.get("value") == ".")
        print(
            f"  last {days}d: {len(rows)} rows ({missing} '.' missing); latest "
            + ", ".join(f"{r.get('date')}={r.get('value')}" for r in rows[-3:])
        )
        if rows:
            print(f"    realtime_start/end of latest: {rows[-1].get('realtime_start')}/{rows[-1].get('realtime_end')}")
    return status


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--only", choices=("ecos", "fred"), action="append")
    parser.add_argument("--days", type=int, default=14, help="recent window to fetch")
    args = parser.parse_args()

    load_dotenv(PROJECT_ROOT / ".env")
    fetched_at = datetime.now()
    save_dir = SAVE_ROOT / fetched_at.strftime("%Y%m%d_%H%M%S")
    save_dir.mkdir(parents=True, exist_ok=True)
    print(f"fetched_at={fetched_at.isoformat(timespec='seconds')} (local) raw -> {save_dir}")

    status = 0
    for name, env, fn in (("ecos", "ECOS_API_KEY", probe_ecos), ("fred", "FRED_API_KEY", probe_fred)):
        if args.only and name not in args.only:
            continue
        key = os.getenv(env, "").strip()
        if not key:
            print(f"\n{name}: {env} missing in .env -- skipped")
            status = 1
            continue
        status |= fn(key, args.days, save_dir)
    return status


if __name__ == "__main__":
    raise SystemExit(main())
