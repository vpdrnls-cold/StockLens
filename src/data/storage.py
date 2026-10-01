"""Local storage for raw provider payloads and normalized historical data."""

from __future__ import annotations

from datetime import date, datetime, timezone
import json
from pathlib import Path
import re
from typing import Any, Mapping, Sequence
from decimal import Decimal

from src.data.models import (
    INVESTOR_CATEGORIES,
    DailyBar,
    IndexDailyBar,
    InvestorFlowDay,
)


class HistoricalStorageError(RuntimeError):
    """Raised when local historical-data storage cannot be read or written safely."""


class HistoricalStorage:
    """Persist raw Kiwoom payloads separately from StockLens daily bars."""

    def __init__(self, data_root: Path | str = "data") -> None:
        self._data_root = Path(data_root)

    def save_raw_ka10081(
        self,
        stock_code: str,
        response: Mapping[str, Any],
        *,
        retrieved_at: datetime | None = None,
    ) -> Path:
        """Store the unmodified provider response in the raw data zone."""
        safe_stock_code = _safe_stock_code(stock_code)
        timestamp = (retrieved_at or datetime.now(timezone.utc)).strftime(
            "%Y%m%dT%H%M%S%fZ"
        )
        path = (
            self._data_root
            / "raw"
            / "kiwoom"
            / "ka10081"
            / safe_stock_code
            / f"{timestamp}.json"
        )
        _write_json(path, dict(response))
        return path

    def save_raw_ka10080(
        self,
        stock_code: str,
        response: Mapping[str, Any],
        *,
        retrieved_at: datetime | None = None,
    ) -> Path:
        """Store the unmodified ka10080 minute-chart provider response.

        Raw only, deliberately: there is no normalized minute-bar model
        yet (Phase H design is still open on decision-timestamp cutoff
        and regular-session-vs-NXT/overtime filtering as of
        2026-09-22). Mirrors ``save_raw_ka10081``'s storage layout one
        level down under ``ka10080`` instead.
        """
        safe_stock_code = _safe_stock_code(stock_code)
        timestamp = (retrieved_at or datetime.now(timezone.utc)).strftime(
            "%Y%m%dT%H%M%S%fZ"
        )
        path = (
            self._data_root
            / "raw"
            / "kiwoom"
            / "ka10080"
            / safe_stock_code
            / f"{timestamp}.json"
        )
        _write_json(path, dict(response))
        return path

    def save_daily_bars(self, stock_code: str, bars: Sequence[DailyBar]) -> Path:
        """Merge normalized bars by date and write a canonical historical dataset."""
        safe_stock_code = _safe_stock_code(stock_code)
        path = self._data_root / "processed" / "historical" / f"{safe_stock_code}.json"
        records_by_date = {
            record["trade_date"]: record for record in _read_json_list(path)
        }
        for bar in bars:
            if bar.stock_code != stock_code:
                raise HistoricalStorageError("All bars must belong to the requested stock code.")
            records_by_date[bar.trade_date.isoformat()] = bar.to_dict()

        records = [records_by_date[key] for key in sorted(records_by_date)]
        _write_json(path, records)
        return path

    def load_daily_bars(self, stock_code: str) -> list[DailyBar]:
        """Load normalized historical daily bars for one stock."""
        safe_stock_code = _safe_stock_code(stock_code)
        path = (
            self._data_root
            / "processed"
            / "historical"
            / f"{safe_stock_code}.json"
        )

        records = _read_json_list(path)

        bars: list[DailyBar] = []

        for record in records:
            try:
                bars.append(
                    DailyBar(
                        stock_code=str(record["stock_code"]),
                        trade_date=date.fromisoformat(str(record["trade_date"])),
                        open_price=int(record["open_price"]),
                        high_price=int(record["high_price"]),
                        low_price=int(record["low_price"]),
                        close_price=int(record["close_price"]),
                        volume=int(record["volume"]),
                        trade_value_million_krw=int(
                            record["trade_value_million_krw"]
                        ),
                        previous_close_change=int(
                            record["previous_close_change"]
                        ),
                        previous_close_change_sign=int(
                            record["previous_close_change_sign"]
                        ),
                        turnover_rate=Decimal(str(record["turnover_rate"])),
                    )
                )
            except (KeyError, TypeError, ValueError) as error:
                raise HistoricalStorageError(
                    f"Invalid normalized daily bar in {path}."
                ) from error

        return bars


    def save_raw_kiwoom(
        self,
        api_id: str,
        code: str,
        response: Mapping[str, Any],
        *,
        retrieved_at: datetime,
    ) -> Path:
        """Store an unmodified provider response under ``raw/kiwoom/<api_id>/<code>/``."""
        safe_api_id = _safe_stock_code(api_id)
        safe_code = _safe_stock_code(code)
        timestamp = retrieved_at.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        path = self._data_root / "raw" / "kiwoom" / safe_api_id / safe_code / f"{timestamp}.json"
        _write_json(path, dict(response))
        return path

    def save_index_bars(self, index_code: str, bars: Sequence[IndexDailyBar]) -> Path:
        """Merge index bars by date into ``processed/index/<code>.json``."""
        if any(bar.index_code != index_code for bar in bars):
            raise HistoricalStorageError("All bars must belong to the requested index code.")
        path = self._index_path(index_code)
        _merge_by_date(path, [bar.to_dict() for bar in bars])
        return path

    def load_index_bars(
        self, index_code: str, *, include_incomplete: bool = False
    ) -> list[IndexDailyBar]:
        """Load index bars; in-progress bars are excluded unless asked for."""
        path = self._index_path(index_code)
        bars: list[IndexDailyBar] = []
        for record in _read_json_list(path):
            try:
                bar = IndexDailyBar(
                    index_code=str(record["index_code"]),
                    trade_date=date.fromisoformat(str(record["trade_date"])),
                    open_price=Decimal(str(record["open_price"])),
                    high_price=Decimal(str(record["high_price"])),
                    low_price=Decimal(str(record["low_price"])),
                    close_price=Decimal(str(record["close_price"])),
                    volume=int(record["volume"]),
                    trade_value_million_krw=int(record["trade_value_million_krw"]),
                    retrieved_at=datetime.fromisoformat(str(record["retrieved_at"])),
                    is_complete=_parse_bool(record["is_complete"]),
                )
            except (KeyError, TypeError, ValueError) as error:
                raise HistoricalStorageError(f"Invalid index bar in {path}.") from error
            if include_incomplete or bar.is_complete:
                bars.append(bar)
        return bars

    def save_investor_flows(
        self, stock_code: str, days: Sequence[InvestorFlowDay]
    ) -> Path:
        """Merge investor-flow days by date into ``processed/investor_flow/<code>.json``."""
        if any(day.stock_code != stock_code for day in days):
            raise HistoricalStorageError("All flows must belong to the requested stock code.")
        path = self._investor_flow_path(stock_code)
        _merge_by_date(path, [day.to_dict() for day in days])
        return path

    def load_investor_flows(
        self, stock_code: str, *, include_incomplete: bool = False
    ) -> list[InvestorFlowDay]:
        """Load investor flows; provisional/unbalanced days are excluded unless asked for."""
        path = self._investor_flow_path(stock_code)
        days: list[InvestorFlowDay] = []
        for record in _read_json_list(path):
            try:
                day = InvestorFlowDay(
                    stock_code=str(record["stock_code"]),
                    trade_date=date.fromisoformat(str(record["trade_date"])),
                    volume=int(record["volume"]),
                    trade_value_million_krw=int(record["trade_value_million_krw"]),
                    institution_reported=int(record["institution_reported"]),
                    retrieved_at=datetime.fromisoformat(str(record["retrieved_at"])),
                    is_complete=_parse_bool(record["is_complete"]),
                    **{name: int(record[name]) for name in INVESTOR_CATEGORIES},
                )
            except (KeyError, TypeError, ValueError) as error:
                raise HistoricalStorageError(f"Invalid investor flow in {path}.") from error
            if include_incomplete or day.is_complete:
                days.append(day)
        return days

    def _index_path(self, index_code: str) -> Path:
        return self._data_root / "processed" / "index" / f"{_safe_stock_code(index_code)}.json"

    def _investor_flow_path(self, stock_code: str) -> Path:
        return (
            self._data_root
            / "processed"
            / "investor_flow"
            / f"{_safe_stock_code(stock_code)}.json"
        )


def _merge_by_date(path: Path, new_records: Sequence[dict[str, Any]]) -> None:
    """Merge records keyed by ``trade_date``; a later fetch replaces an earlier one,
    except that an incomplete record never overwrites a complete one (a
    provisional re-fetch must not erase a final value)."""
    records_by_date = {record["trade_date"]: record for record in _read_json_list(path)}
    for record in new_records:
        existing = records_by_date.get(record["trade_date"])
        if existing is not None and existing.get("is_complete") is True and not record["is_complete"]:
            continue
        records_by_date[record["trade_date"]] = record
    _write_json(path, [records_by_date[key] for key in sorted(records_by_date)])


def _parse_bool(value: Any) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"Expected a boolean, received {value!r}.")
    return value


def _safe_stock_code(stock_code: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_]+", stock_code):
        raise HistoricalStorageError("stock_code contains unsupported path characters.")
    return stock_code


def _read_json_list(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise HistoricalStorageError(f"Unable to read normalized data at {path}.") from error
    if not isinstance(loaded, list) or not all(isinstance(record, dict) for record in loaded):
        raise HistoricalStorageError(f"Normalized data at {path} must be a JSON list of objects.")
    if any("trade_date" not in record for record in loaded):
        raise HistoricalStorageError(f"Normalized data at {path} is missing trade_date.")
    return loaded


def _write_json(path: Path, content: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(f"{path.suffix}.tmp")
    try:
        temporary_path.write_text(
            json.dumps(content, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary_path.replace(path)
    except OSError as error:
        raise HistoricalStorageError(f"Unable to write data at {path}.") from error
