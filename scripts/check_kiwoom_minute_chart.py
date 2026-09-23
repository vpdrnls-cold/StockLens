"""Fetch and inspect a raw Kiwoom ``ka10080`` minute-chart response.

Usage:
    python3 scripts/check_kiwoom_minute_chart.py 005930
    python3 scripts/check_kiwoom_minute_chart.py 005930 --tic-scope 15
    python3 scripts/check_kiwoom_minute_chart.py 005930 --print-json
    python3 scripts/check_kiwoom_minute_chart.py 005930 --follow-continuation

This script exists to answer two questions against the *live* API that
``KiwoomClient.get_minute_chart_page()`` deliberately does not answer on
its own (Phase H decision-timestamp design, 2026-09-22):

1. Does a single page cover only ``--base-date``, or does it (like
   ka10081) return many days of history ending at ``--base-date``?
2. If ``cont-yn``/``next-key`` are present on the response, does
   following them page further back in *time* (more days) the same way
   they do for ka10081, or something else (e.g. more bars within the
   same day)?

Do not build an accumulating multi-day/multi-page ingestion method on
top of ``get_minute_chart_page`` until these are confirmed from real
output -- see AGENTS.md section 8.
"""

from __future__ import annotations

import argparse
from datetime import datetime
import json
import logging
from pathlib import Path
import sys
from typing import Any, Mapping

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.api import KiwoomClient, KiwoomClientError
from src.utils.config import ConfigurationError


MINUTE_ROWS_KEY = "stk_min_pole_chart_qry"


def _summarize_rows(rows: list[Any]) -> None:
    """Print the distinct calendar dates and time range actually returned.

    ``cntr_tm`` (체결시간) is documented as ``YYYYMMDDHHmmss``. Comparing
    the set of distinct ``YYYYMMDD`` prefixes against ``--base-date`` is
    the direct way to answer "does one page cover one day or many?".
    """
    timestamps = [str(row.get("cntr_tm", "")).strip() for row in rows]
    timestamps = [ts for ts in timestamps if ts]
    dates = sorted({ts[:8] for ts in timestamps if len(ts) >= 8})
    print(f"distinct_dates_in_page={len(dates)}")
    if dates:
        print(f"date_range={dates[0]}..{dates[-1]}")
    if timestamps:
        print(f"cntr_tm_range={min(timestamps)}..{max(timestamps)}")


def _print_response_structure(
    response: Mapping[str, Any],
    response_headers: Mapping[str, str],
    *,
    print_json: bool,
) -> None:
    """Show the raw response shape without exposing authentication information."""
    print("response_keys=" + ",".join(response.keys()))
    print(f"cont-yn={response_headers.get('cont-yn')!r}")
    print(f"next-key={response_headers.get('next-key')!r}")

    rows = response.get(MINUTE_ROWS_KEY, [])
    if not isinstance(rows, list):
        print(f"{MINUTE_ROWS_KEY}_type={type(rows).__name__}")
        return

    print(f"{MINUTE_ROWS_KEY}_count={len(rows)}")
    if rows:
        print("first_row_keys=" + ",".join(rows[0].keys()))
        print("first_row=")
        print(json.dumps(rows[0], ensure_ascii=False, indent=2))
        print("last_row=")
        print(json.dumps(rows[-1], ensure_ascii=False, indent=2))
        _summarize_rows(rows)
    if print_json:
        print("raw_response=")
        print(json.dumps(response, ensure_ascii=False, indent=2))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Authenticate with Kiwoom and inspect a ka10080 minute-chart response."
    )
    parser.add_argument("stock_code", nargs="?", default="005930")
    parser.add_argument(
        "--tic-scope",
        default="15",
        choices=["1", "3", "5", "10", "15", "30", "45", "60"],
        help="Minute-bar width in minutes; defaults to 15.",
    )
    parser.add_argument(
        "--base-date",
        default=datetime.now().strftime("%Y%m%d"),
        help="Chart base date in YYYYMMDD format; defaults to today.",
    )
    parser.add_argument(
        "--print-json",
        action="store_true",
        help="Print the complete market-data JSON response.",
    )
    parser.add_argument(
        "--follow-continuation",
        action="store_true",
        help=(
            "If the first page reports cont-yn=Y, also send one "
            "continuation request using its next-key, and print that "
            "page too -- to check whether continuation pages further "
            "back in time."
        ),
    )
    arguments = parser.parse_args()

    try:
        client = KiwoomClient.from_env()
        response, response_headers = client.get_minute_chart_page(
            arguments.stock_code,
            arguments.base_date,
            tic_scope=arguments.tic_scope,
        )
    except (ConfigurationError, KiwoomClientError, ValueError) as error:
        print(f"Kiwoom minute-chart check failed: {error}", file=sys.stderr)
        return 1

    print("=== page 1 ===")
    _print_response_structure(response, response_headers, print_json=arguments.print_json)

    cont_yn = str(response_headers.get("cont-yn", "N")).strip().upper()
    next_key = str(response_headers.get("next-key", "")).strip()
    if arguments.follow_continuation and cont_yn == "Y" and next_key:
        try:
            response2, response_headers2 = client.get_minute_chart_page(
                arguments.stock_code,
                arguments.base_date,
                tic_scope=arguments.tic_scope,
                cont_yn=cont_yn,
                next_key=next_key,
            )
        except (KiwoomClientError, ValueError) as error:
            print(f"Continuation request failed: {error}", file=sys.stderr)
            return 1
        print("=== page 2 (continuation) ===")
        _print_response_structure(response2, response_headers2, print_json=arguments.print_json)
    elif arguments.follow_continuation:
        print("(page 1 reported no continuation available; nothing to follow.)")

    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    raise SystemExit(main())
