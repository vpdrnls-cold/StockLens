"""Sequentially ingest and store ka10081 daily charts for multiple symbols."""

from __future__ import annotations

import argparse
from datetime import datetime
import logging
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.api import KiwoomClient
from src.data.ingest import ingest_kiwoom_daily_chart_batch
from src.utils.config import ConfigurationError


DEFAULT_STOCK_CODES = ("005930", "000660", "005380", "035420", "035720")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Sequentially ingest Kiwoom ka10081 daily charts for multiple symbols."
    )
    parser.add_argument(
        "stock_codes",
        nargs="*",
        default=DEFAULT_STOCK_CODES,
        help="Stock codes to ingest; defaults to the five validated Korean symbols.",
    )
    parser.add_argument(
        "--base-date",
        default=datetime.now().strftime("%Y%m%d"),
        help="Chart base date in YYYYMMDD format; defaults to today.",
    )
    arguments = parser.parse_args()

    try:
        client = KiwoomClient.from_env()
    except ConfigurationError as error:
        print(f"Batch ingestion setup failed: {error}", file=sys.stderr)
        return 1

    results = ingest_kiwoom_daily_chart_batch(
        client,
        arguments.stock_codes,
        arguments.base_date,
    )
    for result in results:
        if result.success:
            assert result.ingestion is not None
            print(f"{result.stock_code} → 성공 / {result.ingestion.bar_count}")
            print(f"  raw_path={result.ingestion.raw_path}")
            print(f"  normalized_path={result.ingestion.normalized_path}")
        else:
            print(f"{result.stock_code} → 실패 / {result.error}")

    success_count = sum(result.success for result in results)
    print(f"batch_summary={success_count}/{len(results)} successful")
    return 0 if success_count == len(results) else 1


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    raise SystemExit(main())
