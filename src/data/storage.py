"""Local storage for raw provider payloads and normalized historical data."""

from __future__ import annotations

from datetime import date, datetime, timezone
import json
from pathlib import Path
import re
from typing import Any, Mapping, Sequence
from decimal import Decimal

from src.data.models import DailyBar


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
