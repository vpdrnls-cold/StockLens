"""Normalize and validate provider responses before they enter StockLens data."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping, Sequence

from src.data.models import DailyBar


DAILY_CHART_ROWS_KEY = "stk_dt_pole_chart_qry"


class HistoricalDataValidationError(ValueError):
    """Raised when raw historical market data is missing, malformed, or invalid."""


def normalize_ka10081_response(response: Mapping[str, Any]) -> list[DailyBar]:
    """Convert one documented ``ka10081`` response into validated daily bars."""
    stock_code = _required_text(response, "stk_cd", context="response")
    rows = response.get(DAILY_CHART_ROWS_KEY)
    if not isinstance(rows, list):
        raise HistoricalDataValidationError(
            f"response.{DAILY_CHART_ROWS_KEY} must be a list."
        )

    bars = [
        _normalize_daily_chart_row(stock_code, row, row_index)
        for row_index, row in enumerate(rows)
    ]
    validate_daily_bars(bars)
    return bars


def validate_daily_bars(bars: Sequence[DailyBar]) -> None:
    """Validate cross-row integrity that cannot be checked during parsing."""
    seen_dates: set[datetime.date] = set()
    for bar in bars:
        if bar.trade_date in seen_dates:
            raise HistoricalDataValidationError(
                f"Duplicate daily bar for {bar.stock_code} on {bar.trade_date.isoformat()}."
            )
        seen_dates.add(bar.trade_date)

        if bar.low_price > min(bar.open_price, bar.close_price):
            raise HistoricalDataValidationError(
                f"Low price exceeds open or close on {bar.trade_date.isoformat()}."
            )
        if bar.high_price < max(bar.open_price, bar.close_price):
            raise HistoricalDataValidationError(
                f"High price is below open or close on {bar.trade_date.isoformat()}."
            )
        if bar.low_price > bar.high_price:
            raise HistoricalDataValidationError(
                f"Low price exceeds high price on {bar.trade_date.isoformat()}."
            )
        if bar.volume < 0 or bar.trade_value_million_krw < 0:
            raise HistoricalDataValidationError(
                f"Trading activity must not be negative on {bar.trade_date.isoformat()}."
            )
        if bar.turnover_rate < 0:
            raise HistoricalDataValidationError(
                f"Turnover rate must not be negative on {bar.trade_date.isoformat()}."
            )
        if bar.previous_close_change_sign not in {1, 2, 3, 4, 5}:
            raise HistoricalDataValidationError(
                f"Invalid previous-close change sign on {bar.trade_date.isoformat()}."
            )


def _normalize_daily_chart_row(
    stock_code: str,
    raw_row: Any,
    row_index: int,
) -> DailyBar:
    if not isinstance(raw_row, Mapping):
        raise HistoricalDataValidationError(f"row {row_index} must be an object.")
    context = f"row {row_index}"
    return DailyBar(
        stock_code=stock_code,
        trade_date=_parse_date(_required_text(raw_row, "dt", context=context), context),
        close_price=_parse_int(raw_row.get("cur_prc"), "cur_prc", context),
        volume=_parse_int(raw_row.get("trde_qty"), "trde_qty", context),
        trade_value_million_krw=_parse_int(
            raw_row.get("trde_prica"), "trde_prica", context
        ),
        open_price=_parse_int(raw_row.get("open_pric"), "open_pric", context),
        high_price=_parse_int(raw_row.get("high_pric"), "high_pric", context),
        low_price=_parse_int(raw_row.get("low_pric"), "low_pric", context),
        previous_close_change=_parse_int(raw_row.get("pred_pre"), "pred_pre", context),
        previous_close_change_sign=_parse_int(
            raw_row.get("pred_pre_sig"), "pred_pre_sig", context
        ),
        turnover_rate=_parse_decimal(raw_row.get("trde_tern_rt"), "trde_tern_rt", context),
    )


def _required_text(source: Mapping[str, Any], key: str, *, context: str) -> str:
    value = source.get(key)
    if value is None or not str(value).strip():
        raise HistoricalDataValidationError(f"{context}.{key} is missing or blank.")
    return str(value).strip()


def _parse_date(value: str, context: str):
    try:
        return datetime.strptime(value, "%Y%m%d").date()
    except ValueError as error:
        raise HistoricalDataValidationError(
            f"{context}.dt must use YYYYMMDD format, received {value!r}."
        ) from error


def _parse_int(value: Any, field: str, context: str) -> int:
    if value is None or not str(value).strip():
        raise HistoricalDataValidationError(f"{context}.{field} is missing or blank.")
    try:
        return int(str(value).strip().replace(",", ""))
    except ValueError as error:
        raise HistoricalDataValidationError(
            f"{context}.{field} must be an integer, received {value!r}."
        ) from error


def _parse_decimal(value: Any, field: str, context: str) -> Decimal:
    if value is None or not str(value).strip():
        raise HistoricalDataValidationError(f"{context}.{field} is missing or blank.")
    try:
        parsed = Decimal(str(value).strip().replace(",", ""))
    except InvalidOperation as error:
        raise HistoricalDataValidationError(
            f"{context}.{field} must be a decimal, received {value!r}."
        ) from error
    if not parsed.is_finite():
        raise HistoricalDataValidationError(f"{context}.{field} must be finite.")
    return parsed
