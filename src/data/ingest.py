"""Historical and live data ingestion entry points."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

from src.api.kiwoom_client import KiwoomClient, KiwoomClientError
from src.data.normalization import (
    HistoricalDataValidationError,
    normalize_ka10059_response,
    normalize_ka10081_response,
    normalize_ka20006_response,
)
from src.data.storage import HistoricalStorage, HistoricalStorageError


@dataclass(frozen=True)
class HistoricalIngestionResult:
    """Locations and record count produced by one daily-chart ingestion run."""

    raw_path: Path
    normalized_path: Path
    bar_count: int


@dataclass(frozen=True)
class MinuteChartIngestionResult:
    """Location and row count produced by one raw minute-chart ingestion run.

    Raw only, deliberately: there is no normalized minute-bar model yet.
    Decision-timestamp cutoff, regular-session-vs-NXT/overtime
    filtering, and the intraday feature schema are still open design
    questions (Phase H, as of 2026-09-22) -- do not build normalization
    on top of this until those are settled. See
    ``ingest_kiwoom_daily_chart`` for the raw + normalized pattern this
    is expected to grow into once they are.
    """

    raw_path: Path
    row_count: int


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


def ingest_kiwoom_minute_chart_raw(
    client: KiwoomClient,
    stock_code: str,
    base_date: str,
    stop_date: str,
    *,
    tic_scope: str = "15",
    storage: HistoricalStorage | None = None,
) -> MinuteChartIngestionResult:
    """Fetch and store one ``ka10080`` minute-chart response, raw only.

    ``stop_date`` is a required positional-style keyword (not defaulted)
    so a pilot run never silently walks further back into history than
    intended -- see ``KiwoomClient.get_minute_chart_history``'s
    ``stop_date`` documentation for why that matters for minute bars
    specifically (unlike daily bars, full history would be enormous).
    """
    raw_response = client.get_minute_chart_history(
        stock_code,
        base_date,
        tic_scope=tic_scope,
        stop_date=stop_date,
    )
    historical_storage = storage or HistoricalStorage()
    raw_path = historical_storage.save_raw_ka10080(stock_code, raw_response)
    row_count = len(raw_response.get("stk_min_pole_chart_qry", []))
    return MinuteChartIngestionResult(raw_path, row_count)


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


@dataclass(frozen=True)
class DatedSeriesIngestionResult:
    """Outcome of one index or investor-flow ingestion run."""

    code: str
    raw_path: Path | None = None
    normalized_path: Path | None = None
    row_count: int = 0
    incomplete_dates: tuple[str, ...] = ()
    error: str | None = None

    @property
    def success(self) -> bool:
        return self.error is None


def ingest_kiwoom_index_daily(
    client: KiwoomClient,
    index_code: str,
    base_date: str,
    *,
    stop_date: str | None = None,
    storage: HistoricalStorage | None = None,
    retrieved_at: datetime | None = None,
) -> DatedSeriesIngestionResult:
    """Fetch, preserve, normalize, validate, and merge-store ``ka20006`` index bars."""
    retrieved_at = retrieved_at or datetime.now(timezone.utc)
    historical_storage = storage or HistoricalStorage()
    response = client.get_index_daily_history(index_code, base_date, stop_date=stop_date)
    raw_path = historical_storage.save_raw_kiwoom(
        "ka20006", index_code, response, retrieved_at=retrieved_at
    )
    bars = normalize_ka20006_response(response, retrieved_at=retrieved_at)
    normalized_path = historical_storage.save_index_bars(index_code, bars)
    return DatedSeriesIngestionResult(
        code=index_code,
        raw_path=raw_path,
        normalized_path=normalized_path,
        row_count=len(bars),
        incomplete_dates=tuple(b.trade_date.isoformat() for b in bars if not b.is_complete),
    )


def ingest_kiwoom_investor_flow_batch(
    client: KiwoomClient,
    stock_codes: Sequence[str],
    date: str,
    *,
    stop_date: str | None = None,
    storage: HistoricalStorage | None = None,
) -> list[DatedSeriesIngestionResult]:
    """Sequentially ingest ``ka10059`` flows; one stock's failure does not stop the rest."""
    historical_storage = storage or HistoricalStorage()
    results: list[DatedSeriesIngestionResult] = []
    for stock_code in stock_codes:
        retrieved_at = datetime.now(timezone.utc)
        try:
            response = client.get_investor_flow_history(
                stock_code, date, stop_date=stop_date
            )
            raw_path = historical_storage.save_raw_kiwoom(
                "ka10059", stock_code, response, retrieved_at=retrieved_at
            )
            days = normalize_ka10059_response(
                response, stock_code=stock_code, retrieved_at=retrieved_at
            )
            normalized_path = historical_storage.save_investor_flows(stock_code, days)
        except (
            KiwoomClientError,
            HistoricalDataValidationError,
            HistoricalStorageError,
            ValueError,
        ) as error:
            results.append(DatedSeriesIngestionResult(code=stock_code, error=str(error)))
            continue
        results.append(
            DatedSeriesIngestionResult(
                code=stock_code,
                raw_path=raw_path,
                normalized_path=normalized_path,
                row_count=len(days),
                incomplete_dates=tuple(
                    d.trade_date.isoformat() for d in days if not d.is_complete
                ),
            )
        )
    return results
