"""Fetch, validate, and store raw and normalized ka10081 daily-chart data."""

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
from src.data.ingest import ingest_kiwoom_daily_chart
from src.data.normalization import HistoricalDataValidationError
from src.data.storage import HistoricalStorageError
from src.utils.config import ConfigurationError


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Store raw and normalized Kiwoom ka10081 daily-chart data."
    )
    parser.add_argument("stock_code", nargs="?", default="005930")
    parser.add_argument(
        "--base-date",
        default=datetime.now().strftime("%Y%m%d"),
        help="Chart base date in YYYYMMDD format; defaults to today.",
    )
    arguments = parser.parse_args()

    try:
        result = ingest_kiwoom_daily_chart(
            KiwoomClient.from_env(), arguments.stock_code, arguments.base_date
        )
    except (
        ConfigurationError,
        KiwoomClientError,
        HistoricalDataValidationError,
        HistoricalStorageError,
        ValueError,
    ) as error:
        print(f"Historical ingestion failed: {error}", file=sys.stderr)
        return 1

    print(f"bar_count={result.bar_count}")
    print(f"raw_path={result.raw_path}")
    print(f"normalized_path={result.normalized_path}")
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    raise SystemExit(main())
