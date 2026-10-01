"""Fetch and inspect raw Kiwoom index (ka20006) and investor-flow (ka10059/ka10060) pages.

Usage:
    PYTHONPATH=. python scripts/check_kiwoom_flow_index.py
    PYTHONPATH=. python scripts/check_kiwoom_flow_index.py --stock 005930 --max-pages 40
    PYTHONPATH=. python scripts/check_kiwoom_flow_index.py --only ka10060 --print-rows 3

Questions this answers against the live API before any ingestion is built
(same approach as ``check_kiwoom_minute_chart.py``, AGENTS.md 19):

1. How many daily rows does one page return, and over what date range?
2. Does following ``cont-yn``/``next-key`` walk further back in time,
   and how far back does history go in total?
3. Does a request made during market hours include a row for today?
   If so it is provisional (가집계 for flow, in-progress candle for the
   index -- AGENTS.md 2.3). Raw pages are saved with the fetch time so a
   run during market hours can be diffed against a run after the close.

Prints only response structure and row values -- never tokens or keys.
"""

from __future__ import annotations

import argparse
from datetime import datetime
import json
import logging
from pathlib import Path
import sys
import time
from typing import Any, Callable, Mapping

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.api import KiwoomClient, KiwoomClientError
from src.utils.config import ConfigurationError


ROWS_KEYS = {
    "ka20006": "inds_dt_pole_qry",
    "ka10059": "stk_invsr_orgn",
    "ka10060": "stk_invsr_orgn_chart",
}
DEFAULT_SAVE_ROOT = PROJECT_ROOT / "data" / "raw" / "kiwoom" / "probe_flow_index"
PAGE_INTERVAL_SECONDS = 0.3


def _probe(
    api_id: str,
    fetch_page: Callable[[str, str], tuple[Mapping[str, Any], Mapping[str, str]]],
    *,
    max_pages: int,
    print_rows: int,
    save_dir: Path,
) -> None:
    rows_key = ROWS_KEYS[api_id]
    print(f"\n===== {api_id} ({rows_key}) =====")
    cont_yn, next_key = "N", ""
    all_dates: list[str] = []
    for page in range(max_pages):
        if page > 0:
            time.sleep(PAGE_INTERVAL_SECONDS)
        response, headers = fetch_page(cont_yn, next_key)
        rows = response.get(rows_key, [])
        if not isinstance(rows, list):
            print(f"page {page + 1}: {rows_key} is {type(rows).__name__}, not a list")
            return
        (save_dir / f"{api_id}_page{page + 1:03d}.json").write_text(
            json.dumps(
                {"response": response, "cont-yn": headers.get("cont-yn")},
                ensure_ascii=False,
                indent=1,
            ),
            encoding="utf-8",
        )
        dates = [str(row.get("dt", "")).strip() for row in rows]
        dates = [d for d in dates if d]
        all_dates.extend(dates)
        cont_yn = str(headers.get("cont-yn", "N")).strip().upper()
        next_key = str(headers.get("next-key", "")).strip()
        span = f"{min(dates)}..{max(dates)}" if dates else "-"
        print(
            f"page {page + 1}: rows={len(rows)} dates={span} "
            f"cont-yn={cont_yn!r} next-key={'present' if next_key else 'empty'}"
        )
        if page == 0:
            print("response_keys=" + ",".join(response.keys()))
            for row in rows[:print_rows]:
                print(f"  {row}")
        if cont_yn != "Y" or not next_key or not rows:
            break
    else:
        print(f"stopped at --max-pages={max_pages} with continuation still available")

    if all_dates:
        unique = sorted(set(all_dates))
        print(
            f"total rows={len(all_dates)} unique dates={len(unique)} "
            f"range={unique[0]}..{unique[-1]} duplicates={len(all_dates) - len(unique)}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--stock", default="005930")
    parser.add_argument("--index", default="001", help="ka20006 inds_cd (001 = KOSPI)")
    parser.add_argument("--date", default=datetime.now().strftime("%Y%m%d"))
    parser.add_argument("--max-pages", type=int, default=3)
    parser.add_argument("--print-rows", type=int, default=2)
    parser.add_argument("--only", choices=sorted(ROWS_KEYS), action="append")
    args = parser.parse_args()

    fetched_at = datetime.now()
    save_dir = DEFAULT_SAVE_ROOT / fetched_at.strftime("%Y%m%d_%H%M%S")
    save_dir.mkdir(parents=True, exist_ok=True)
    print(f"fetched_at={fetched_at.isoformat(timespec='seconds')} date={args.date}")
    print(f"raw pages -> {save_dir}")

    try:
        client = KiwoomClient.from_env()
    except ConfigurationError as error:
        print(f"setup failed: {error}", file=sys.stderr)
        return 1

    probes: dict[str, Callable[[str, str], Any]] = {
        "ka20006": lambda c, k: client.get_index_daily_chart_page(
            args.index, args.date, cont_yn=c, next_key=k
        ),
        "ka10059": lambda c, k: client.get_investor_flow_page(
            args.stock, args.date, api_id="ka10059", cont_yn=c, next_key=k
        ),
        "ka10060": lambda c, k: client.get_investor_flow_page(
            args.stock, args.date, api_id="ka10060", cont_yn=c, next_key=k
        ),
    }
    status = 0
    for api_id, fetch_page in probes.items():
        if args.only and api_id not in args.only:
            continue
        try:
            _probe(
                api_id,
                fetch_page,
                max_pages=args.max_pages,
                print_rows=args.print_rows,
                save_dir=save_dir,
            )
        except KiwoomClientError as error:
            print(f"{api_id} failed: {error}", file=sys.stderr)
            status = 1
    return status


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
    raise SystemExit(main())
