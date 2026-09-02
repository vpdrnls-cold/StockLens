"""Historical and live data ingestion entry points."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from src.api.kiwoom_client import KiwoomClient, KiwoomClientError
from src.data.normalization import HistoricalDataValidationError, normalize_ka10081_response
from src.data.storage import HistoricalStorage, HistoricalStorageError


@dataclass(frozen=True)
class HistoricalIngestionResult:
    """Locations and record count produced by one daily-chart ingestion run."""

    raw_path: Path
    normalized_path: Path
    bar_count: int


@dataclass(frozen=True)
class BatchIngestionItemResult:
    """The outcome of one symbol within a sequential historical batch."""

    stock_code: str
    ingestion: HistoricalIngestionResult | None = None
    error: str | None = None

    @property
    def success(self) -> bool:
        """Return whether the symbol completed ingestion successfully."""
        return self.ingestion is not None and self.error is None


def ingest_kiwoom_daily_chart(
    client: KiwoomClient,
    stock_code: str,
    base_date: str,
    *,
    storage: HistoricalStorage | None = None,
) -> HistoricalIngestionResult:
    """Fetch, preserve, normalize, validate, and store one ``ka10081`` response."""
    raw_response = client.get_daily_chart(stock_code, base_date)
    bars = normalize_ka10081_response(raw_response)
    historical_storage = storage or HistoricalStorage()
    raw_path = historical_storage.save_raw_ka10081(stock_code, raw_response)
    normalized_path = historical_storage.save_daily_bars(stock_code, bars)
    return HistoricalIngestionResult(raw_path, normalized_path, len(bars))


def ingest_kiwoom_daily_chart_batch(
    client: KiwoomClient,
    stock_codes: Sequence[str],
    base_date: str,
    *,
    storage: HistoricalStorage | None = None,
) -> list[BatchIngestionItemResult]:
    """Sequentially ingest daily charts and continue after a per-symbol failure."""
    historical_storage = storage or HistoricalStorage()
    results: list[BatchIngestionItemResult] = []

    for stock_code in stock_codes:
        try:
            ingestion = ingest_kiwoom_daily_chart(
                client,
                stock_code,
                base_date,
                storage=historical_storage,
            )
        except (
            KiwoomClientError,
            HistoricalDataValidationError,
            HistoricalStorageError,
            ValueError,
        ) as error:
            results.append(BatchIngestionItemResult(stock_code=stock_code, error=str(error)))
        else:
            results.append(BatchIngestionItemResult(stock_code=stock_code, ingestion=ingestion))
    return results
