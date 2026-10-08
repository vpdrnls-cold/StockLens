"""Ingest market index daily bars (ka20006) and per-stock investor flows (ka10059).

Usage:
    # full history (first run; ~19 index pages, up to 80 flow pages per stock)
    STOCKLENS_UNIVERSE=top50 PYTHONPATH=. python scripts/ingest_kiwoom_flow_index.py
    # incremental (nightly): only walk back to N days ago
    STOCKLENS_UNIVERSE=top50 PYTHONPATH=. python scripts/ingest_kiwoom_flow_index.py --lookback-days 10

Writes raw responses to data/raw/kiwoom/{ka20006,ka10059}/<code>/ and merged,
validated series to data/processed/index/<code>.json and
data/processed/investor_flow/<code>.json. Rows that were provisional when
fetched (same-day before the KST cutoff, or unbalanced flows) are stored
with is_complete=false and excluded by the default loaders.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta
import logging
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.api import KiwoomClient, KiwoomClientError, KiwoomTokenError
from src.data.ingest import ingest_kiwoom_index_daily, ingest_kiwoom_investor_flow_batch
from src.data.normalization import HistoricalDataValidationError
from src.data.storage import HistoricalStorageError
from src.data.universe import get_universe
from src.utils.config import ConfigurationError


# 001 = KOSPI composite, 201 = KOSPI200 (ka20006 documented inds_cd values).
DEFAULT_INDEX_CODES = ("001", "201")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("stock_codes", nargs="*", default=get_universe())
    parser.add_argument("--index-codes", nargs="*", default=list(DEFAULT_INDEX_CODES))
    parser.add_argument("--base-date", default=datetime.now().strftime("%Y%m%d"))
    parser.add_argument(
        "--lookback-days",
        type=int,
        help="Stop paging once rows reach this many calendar days back (incremental update).",
    )
    parser.add_argument("--skip-flows", action="store_true")
    args = parser.parse_args()

    stop_date = None
    if args.lookback_days is not None:
        base = datetime.strptime(args.base_date, "%Y%m%d")
        stop_date = (base - timedelta(days=args.lookback_days)).strftime("%Y%m%d")

    try:
        client = KiwoomClient.from_env()
    except ConfigurationError as error:
        print(f"setup failed: {error}", file=sys.stderr)
        return 1

    failures = 0
    for index_code in args.index_codes:
        try:
            result = ingest_kiwoom_index_daily(
                client, index_code, args.base_date, stop_date=stop_date
            )
        except KiwoomTokenError as error:
            print(error.stop_line(), file=sys.stderr, flush=True)
            return 1
        except (
            KiwoomClientError,
            HistoricalDataValidationError,
            HistoricalStorageError,
            ValueError,
        ) as error:
            print(f"index {index_code} → 실패 / {error}", flush=True)
            failures += 1
            continue
        print(
            f"index {index_code} → 성공 / {result.row_count} bars"
            + (f" / incomplete {list(result.incomplete_dates)}" if result.incomplete_dates else ""),
            flush=True,
        )

    if not args.skip_flows:
        def _progress(done: int, total: int, result) -> None:
            head = f"[{done}/{total}] flow {result.code}"
            if not result.success:
                print(f"{head} → 실패 / {result.error}", flush=True)
            else:
                tail = f" / incomplete {list(result.incomplete_dates)}" if result.incomplete_dates else ""
                print(f"{head} → {result.row_count} days{tail}", flush=True)

        try:
            results = ingest_kiwoom_investor_flow_batch(
                client, args.stock_codes, args.base_date, stop_date=stop_date, on_result=_progress
            )
        except KiwoomTokenError as error:
            print(error.stop_line(), file=sys.stderr, flush=True)
            return 1
        failures += sum(not result.success for result in results)
        ok = sum(result.success for result in results)
        print(f"flow_summary={ok}/{len(results)} successful")

    return 0 if failures == 0 else 1


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
    raise SystemExit(main())
