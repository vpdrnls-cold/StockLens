"""Fetch and store raw ``ka10080`` minute-chart data (Phase H pilot).

Usage:
    python3 scripts/ingest_kiwoom_minute_chart.py 005930 --stop-date 20260622
    python3 scripts/ingest_kiwoom_minute_chart.py 005930 --stop-date 20260622 --tic-scope 15

``--stop-date`` is required, not defaulted, so a pilot run never
silently walks back further into history than intended -- see
``KiwoomClient.get_minute_chart_history``'s ``stop_date`` documentation.

Raw storage only: this writes the unmodified provider response under
``data/raw/kiwoom/ka10080/<stock_code>/``, the same pattern
``ingest_kiwoom_daily_chart.py`` uses for ``ka10081``. There is no
normalized minute-bar model yet -- decision-timestamp cutoff (which
minute is "as of 14:00"), regular-session-vs-NXT/overtime filtering,
and the intraday feature schema are still open Phase H design
questions as of 2026-09-22. Do not build normalization/feature code on
top of this script's output until those are decided.
"""

from __future__ import annotations

import argparse
from datetime import datetime
import logging
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.api import KiwoomClient, KiwoomClientError
from src.data.ingest import ingest_kiwoom_minute_chart_raw
from src.data.storage import HistoricalStorageError
from src.utils.config import ConfigurationError


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Store raw Kiwoom ka10080 minute-chart data for one stock."
    )
    parser.add_argument("stock_code", nargs="?", default="005930")
    parser.add_argument(
        "--stop-date",
        required=True,
        help=(
            "YYYYMMDD. Do not collect bars older than this date -- "
            "required so a pilot run has an explicit, bounded window "
            "instead of silently walking all the way back."
        ),
    )
    parser.add_argument(
        "--base-date",
        default=datetime.now().strftime("%Y%m%d"),
        help="Chart base date (most recent date to fetch from) in YYYYMMDD format; defaults to today.",
    )
    parser.add_argument(
        "--tic-scope",
        default="15",
        choices=["1", "3", "5", "10", "15", "30", "45", "60"],
        help="Minute-bar width in minutes; defaults to 15.",
    )
    arguments = parser.parse_args()

    try:
        result = ingest_kiwoom_minute_chart_raw(
            KiwoomClient.from_env(),
            arguments.stock_code,
            arguments.base_date,
            arguments.stop_date,
            tic_scope=arguments.tic_scope,
        )
    except (
        ConfigurationError,
        KiwoomClientError,
        HistoricalStorageError,
        ValueError,
    ) as error:
        print(f"Minute-chart ingestion failed: {error}", file=sys.stderr)
        return 1

    print(f"row_count={result.row_count}")
    print(f"raw_path={result.raw_path}")
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    raise SystemExit(main())
