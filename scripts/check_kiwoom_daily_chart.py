"""Fetch and inspect a raw Kiwoom ``ka10081`` daily-chart response.

Usage:
    python3 scripts/check_kiwoom_daily_chart.py 005930
    python3 scripts/check_kiwoom_daily_chart.py 005930 --print-json
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


CHART_ROWS_KEY = "stk_dt_pole_chart_qry"


def _print_response_structure(response: Mapping[str, Any], *, print_json: bool) -> None:
    """Show the raw response shape without exposing authentication information."""
    print("response_keys=" + ",".join(response.keys()))
    rows = response.get(CHART_ROWS_KEY, [])
    if not isinstance(rows, list):
        print(f"{CHART_ROWS_KEY}_type={type(rows).__name__}")
        return

    print(f"{CHART_ROWS_KEY}_count={len(rows)}")
    if rows:
        print("first_row_keys=" + ",".join(rows[0].keys()))
        print("first_row=")
        print(json.dumps(rows[0], ensure_ascii=False, indent=2))
    if print_json:
        print("raw_response=")
        print(json.dumps(response, ensure_ascii=False, indent=2))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Authenticate with Kiwoom and inspect a ka10081 daily-chart response."
    )
    parser.add_argument("stock_code", nargs="?", default="005930")
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
    arguments = parser.parse_args()

    try:
        response = KiwoomClient.from_env().get_daily_chart(
            arguments.stock_code,
            arguments.base_date,
        )
    except (ConfigurationError, KiwoomClientError, ValueError) as error:
        print(f"Kiwoom daily-chart check failed: {error}", file=sys.stderr)
        return 1

    _print_response_structure(response, print_json=arguments.print_json)
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    raise SystemExit(main())
