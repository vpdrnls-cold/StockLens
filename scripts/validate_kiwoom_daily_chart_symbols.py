"""Validate ka10081 ingestion across a small set of domestic stock symbols."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime
import json
import logging
from pathlib import Path
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.api import KiwoomClient, KiwoomClientError
from src.data.ingest import ingest_kiwoom_daily_chart
from src.data.models import DailyBar
from src.data.normalization import HistoricalDataValidationError
from src.data.storage import HistoricalStorageError
from src.utils.config import ConfigurationError


DEFAULT_STOCK_CODES = ("005930", "000660", "005380", "035420", "035720")
NORMALIZED_FIELDS = frozenset(DailyBar.__dataclass_fields__)
KIWOOM_RAW_FIELDS = {
    "dt",
    "cur_prc",
    "trde_qty",
    "trde_prica",
    "open_pric",
    "high_pric",
    "low_pric",
    "pred_pre",
    "pred_pre_sig",
    "trde_tern_rt",
}


@dataclass(frozen=True)
class SymbolValidationResult:
    """Outcome of fetching, normalizing, storing, and inspecting one symbol."""

    stock_code: str
    success: bool
    bar_count: int = 0
    schema_valid: bool = False
    normalization_valid: bool = False
    storage_valid: bool = False
    error: str | None = None


def _validate_normalized_file(path: Path, stock_code: str) -> tuple[bool, bool]:
    """Check the provider-neutral normalized dataset written by ingestion."""
    records: Any = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(records, list) or not records:
        return False, False

    schema_valid = all(
        isinstance(record, dict)
        and set(record) == NORMALIZED_FIELDS
        and not (set(record) & KIWOOM_RAW_FIELDS)
        for record in records
    )
    stock_code_valid = all(record.get("stock_code") == stock_code for record in records)
    return schema_valid, stock_code_valid


def validate_symbols(stock_codes: tuple[str, ...], base_date: str) -> list[SymbolValidationResult]:
    """Run the existing ingestion flow and inspect its persisted result for each symbol."""
    client = KiwoomClient.from_env()
    results: list[SymbolValidationResult] = []

    for stock_code in stock_codes:
        try:
            ingestion = ingest_kiwoom_daily_chart(client, stock_code, base_date)
            schema_valid, stock_code_valid = _validate_normalized_file(
                ingestion.normalized_path, stock_code
            )
            storage_valid = (
                ingestion.raw_path.is_file()
                and ingestion.normalized_path.is_file()
                and ingestion.raw_path.parent.name == stock_code
            )
            success = (
                ingestion.bar_count > 0
                and schema_valid
                and stock_code_valid
                and storage_valid
            )
            results.append(
                SymbolValidationResult(
                    stock_code=stock_code,
                    success=success,
                    bar_count=ingestion.bar_count,
                    schema_valid=schema_valid,
                    normalization_valid=stock_code_valid,
                    storage_valid=storage_valid,
                    error=None if success else "Post-ingestion validation failed.",
                )
            )
        except (
            ConfigurationError,
            KiwoomClientError,
            HistoricalDataValidationError,
            HistoricalStorageError,
            OSError,
            ValueError,
        ) as error:
            results.append(SymbolValidationResult(stock_code=stock_code, success=False, error=str(error)))
    return results


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate existing ka10081 ingestion across multiple stock codes."
    )
    parser.add_argument("stock_codes", nargs="*", default=DEFAULT_STOCK_CODES)
    parser.add_argument(
        "--base-date",
        default=datetime.now().strftime("%Y%m%d"),
        help="Chart base date in YYYYMMDD format; defaults to today.",
    )
    arguments = parser.parse_args()
    results = validate_symbols(tuple(arguments.stock_codes), arguments.base_date)

    for result in results:
        if result.success:
            print(f"{result.stock_code} → 성공 / {result.bar_count}")
        else:
            print(f"{result.stock_code} → 실패 / {result.error}")

    print("schema → " + ("동일" if all(item.schema_valid for item in results) else "불일치"))
    print(
        "normalization → "
        + ("전체 성공" if all(item.normalization_valid for item in results) else "실패 있음")
    )
    print("storage → " + ("전체 성공" if all(item.storage_valid for item in results) else "실패 있음"))
    return 0 if all(item.success for item in results) else 1


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    raise SystemExit(main())
