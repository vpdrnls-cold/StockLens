"""When do today's daily bar / investor flow / index rows stop changing? (item 64)

``SESSION_FINAL_TIME_KST`` (18:00) is a provisional guess (item 58). It decides
when a same-day row counts as final for index/flow storage AND when
recommend.py / chart_card.py may decide on today's bar (item 63). This probe
fetches ONE page per API several times during an evening and records today's
row each time, so the time a value last changed can be read off directly.

    # snapshots every 20 min from now until 21:30 KST (leave the terminal open)
    STOCKLENS_UNIVERSE=top50 PYTHONPATH=. python scripts/check_session_final_time.py snapshot --repeat-minutes 20 --until 2130
    # one more the next morning, then compare
    STOCKLENS_UNIVERSE=top50 PYTHONPATH=. python scripts/check_session_final_time.py snapshot --date 20261005
    STOCKLENS_UNIVERSE=top50 PYTHONPATH=. python scripts/check_session_final_time.py compare --date 20261005

Snapshots: data/raw/kiwoom/session_final_probe/<date>/<HHMMSS>.json (gitignored).
Cost: (stocks x 2 + indices) calls per snapshot -- 12 by default.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta
import json
from pathlib import Path
import sys
import time
from typing import Any, Callable, Mapping

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.data.normalization import (  # noqa: E402
    DAILY_CHART_ROWS_KEY, INDEX_DAILY_ROWS_KEY, INVESTOR_FLOW_ROWS_KEY, KST,
)

SAVE_ROOT = PROJECT_ROOT / "data" / "raw" / "kiwoom" / "session_final_probe"
DEFAULT_STOCKS = ("005930", "000660", "005380", "035420", "105560")
DEFAULT_INDICES = ("001", "201")


def pick_row(response: Mapping[str, Any], rows_key: str, day: str) -> dict[str, Any] | None:
    for row in response.get(rows_key) or []:
        if str(row.get("dt", "")).strip() == day:
            return dict(row)
    return None


def take_snapshot(client: Any, day: str, stocks: tuple[str, ...], indices: tuple[str, ...]) -> dict[str, Any]:
    rows: dict[str, dict[str, Any]] = {"ka10081": {}, "ka10059": {}, "ka20006": {}}
    errors: list[str] = []
    jobs: list[tuple[str, str, Callable[[], Mapping[str, Any]], str]] = []
    for code in stocks:
        jobs.append(("ka10081", code, lambda c=code: client.get_daily_chart(c, day, max_pages=1), DAILY_CHART_ROWS_KEY))
        jobs.append(("ka10059", code, lambda c=code: client.get_investor_flow_page(c, day, api_id="ka10059")[0],
                     INVESTOR_FLOW_ROWS_KEY))
    for code in indices:
        jobs.append(("ka20006", code, lambda c=code: client.get_index_daily_chart_page(c, day)[0], INDEX_DAILY_ROWS_KEY))
    for api, code, fetch, key in jobs:
        try:
            rows[api][code] = pick_row(fetch(), key, day)
        except Exception as error:  # probe: record and keep going
            errors.append(f"{api} {code}: {type(error).__name__}: {error}"[:200])
    return {"date": day, "retrieved_at": datetime.now(KST).isoformat(timespec="seconds"),
            "rows": rows, "errors": errors}


def stability_report(snapshots: list[dict[str, Any]]) -> dict[str, Any]:
    """Per API: when each (code, field) last changed across time-ordered snapshots.

    ``last_change`` is the retrieved_at of the first snapshot showing the final
    value after a different earlier value (None = never changed / row appeared
    once). ``first_seen`` is when the row first appeared at all.
    """
    snaps = sorted(snapshots, key=lambda s: s["retrieved_at"])
    out: dict[str, Any] = {}
    for api in ("ka10081", "ka10059", "ka20006"):
        codes = sorted({c for s in snaps for c in s["rows"].get(api, {})})
        per_code = {}
        for code in codes:
            series = [(s["retrieved_at"], s["rows"].get(api, {}).get(code)) for s in snaps]
            present = [(t, r) for t, r in series if r]
            if not present:
                per_code[code] = {"first_seen": None, "last_change": None, "changed_fields": []}
                continue
            last_change, changed = None, set()
            prev = present[0][1]
            for t, row in present[1:]:
                diff = {k for k in set(prev) | set(row) if prev.get(k) != row.get(k)}
                if diff:
                    last_change, changed = t, changed | diff
                prev = row
            per_code[code] = {"first_seen": present[0][0], "last_change": last_change,
                              "changed_fields": sorted(changed)}
        changes = [v["last_change"] for v in per_code.values() if v["last_change"]]
        out[api] = {"latest_change": max(changes) if changes else None, "codes": per_code}
    out["snapshot_times"] = [s["retrieved_at"] for s in snaps]
    return out


def _until(hhmm: str) -> datetime:
    now = datetime.now(KST)
    end = now.replace(hour=int(hhmm[:2]), minute=int(hhmm[2:]), second=0, microsecond=0)
    return end if end > now else end + timedelta(days=1)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("mode", choices=("snapshot", "compare"))
    ap.add_argument("--date", default=datetime.now(KST).strftime("%Y%m%d"), help="trade date YYYYMMDD")
    ap.add_argument("--stocks", nargs="*", default=list(DEFAULT_STOCKS))
    ap.add_argument("--indices", nargs="*", default=list(DEFAULT_INDICES))
    ap.add_argument("--repeat-minutes", type=int, default=0)
    ap.add_argument("--until", default="2130", help="HHMM KST, with --repeat-minutes")
    args = ap.parse_args()
    folder = SAVE_ROOT / args.date

    if args.mode == "compare":
        snaps = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(folder.glob("*.json"))]
        if not snaps:
            print(f"no snapshots in {folder}")
            return 1
        rep = stability_report(snaps)
        print(f"date {args.date}: {len(snaps)} snapshots -> " + ", ".join(t[11:16] for t in rep["snapshot_times"]))
        for api in ("ka10081", "ka10059", "ka20006"):
            r = rep[api]
            print(f"\n[{api}] latest change across codes: {r['latest_change'] or 'none'}")
            for code, v in r["codes"].items():
                print(f"  {code}: first_seen={v['first_seen']} last_change={v['last_change']} "
                      f"fields={','.join(v['changed_fields']) or '-'}")
        (folder / "report.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"\nsaved {folder / 'report.json'}")
        print("읽는 법: latest change 이후 스냅샷에서 값이 더 안 바뀌었다면, 그 다음 스냅샷 시각이 '확정 관측' 시각.")
        return 0

    from src.api import KiwoomClient  # imported here so `compare` works without credentials

    client = KiwoomClient.from_env()
    folder.mkdir(parents=True, exist_ok=True)
    end = _until(args.until) if args.repeat_minutes else None
    while True:
        snap = take_snapshot(client, args.date, tuple(args.stocks), tuple(args.indices))
        path = folder / f"{datetime.now(KST):%H%M%S}.json"
        path.write_text(json.dumps(snap, ensure_ascii=False, indent=1), encoding="utf-8")
        found = sum(1 for api in snap["rows"].values() for r in api.values() if r)
        total = sum(len(api) for api in snap["rows"].values())
        print(f"{snap['retrieved_at']} rows {found}/{total}" + (f" errors {snap['errors']}" if snap["errors"] else ""),
              flush=True)
        if not end or datetime.now(KST) + timedelta(minutes=args.repeat_minutes) > end:
            break
        time.sleep(args.repeat_minutes * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
