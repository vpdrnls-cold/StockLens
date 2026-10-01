"""Normalize and validate provider responses before they enter StockLens data."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, InvalidOperation
import logging
from typing import Any, Mapping, Sequence

from src.data.models import (
    INVESTOR_CATEGORIES,
    DailyBar,
    IndexDailyBar,
    InvestorFlowDay,
)


logger = logging.getLogger(__name__)

DAILY_CHART_ROWS_KEY = "stk_dt_pole_chart_qry"
INDEX_DAILY_ROWS_KEY = "inds_dt_pole_qry"
INVESTOR_FLOW_ROWS_KEY = "stk_invsr_orgn"

KST = timezone(timedelta(hours=9))
# A bar/flow row for the trading day it was retrieved on counts as
# complete only if retrieved at or after this KST time. Conservative
# placeholder: when ka20006/ka10059 values stop changing after the close
# has not been measured yet (scripts/check_kiwoom_flow_index.py runs
# planned for 2026-10-01 evening / 10-02 morning). The nightly job runs
# at 20:37, after it either way.
SESSION_FINAL_TIME_KST = time(18, 0)

# Every flow field is rounded to 1 million KRW, so a balanced day's
# residual over the 12 categories is at most 12 * 0.5 = 6. Observed max
# on 005930 2010-06~2026-09: 4. A provisional intraday row was off by
# ~68,000.
FLOW_BALANCE_TOLERANCE_MILLION_KRW = len(INVESTOR_CATEGORIES) // 2

# Kiwoom ka10059 field -> StockLens InvestorFlowDay field.
_KA10059_FLOW_FIELDS = {
    "ind_invsr": "individual",
    "frgnr_invsr": "foreign",
    "orgn": "institution_reported",
    "fnnc_invt": "financial_investment",
    "insrnc": "insurance",
    "invtrt": "investment_trust",
    "etc_fnnc": "other_financial",
    "bank": "bank",
    "penfnd_etc": "pension_fund",
    "samo_fund": "private_equity",
    "natn": "government",
    "etc_corp": "other_corporation",
    "natfor": "domestic_foreigner",
}

# Kiwoom documents pred_pre_sig (previous_close_change_sign) as one of
# 1 (upper limit), 2 (up), 3 (unchanged), 4 (lower limit), 5 (down).
# In practice, multi-decade history includes reference-price-reset
# events (stock splits, rights issues) where Kiwoom returns values
# outside this documented set. This field is metadata only -- nothing
# in feature engineering, target construction, or the backtest reads
# it, all of which compute returns directly from close_price -- so an
# undocumented value here should not discard otherwise-valid OHLCV
# data. See _DOCUMENTED_CHANGE_SIGNS usage in validate_daily_bars.
_DOCUMENTED_CHANGE_SIGNS = {1, 2, 3, 4, 5}


# Very old bars (1980s~1990s) of long-listed stocks come back from Kiwoom
# with internally inconsistent OHLC (e.g. high below close), an artifact
# of adjusting/rounding prices for decades of splits and rights issues
# (seen for 000270 Kia in 1985 and 009150 Samsung Electro-Mechanics in
# 1986). Nothing in the model pipeline uses them: the training window
# starts at 2002-10-29 (src/data/dataset.py) and rolling features only
# look back ~60 bars. Rather than discard a whole stock over a 40-year-old
# bar, OHLC-inconsistent bars dated BEFORE this cutoff are dropped with a
# warning; the same inconsistency on/after it is still a hard error.
LEGACY_OHLC_TOLERANCE_BEFORE = date(2000, 1, 1)


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
    bars = _drop_legacy_ohlc_inconsistent_bars(bars)
    validate_daily_bars(bars)
    return bars


def _ohlc_is_inconsistent(bar: DailyBar | IndexDailyBar) -> bool:
    return (
        bar.low_price > min(bar.open_price, bar.close_price)
        or bar.high_price < max(bar.open_price, bar.close_price)
        or bar.low_price > bar.high_price
    )


def _drop_legacy_ohlc_inconsistent_bars(bars: list[Any]) -> list[Any]:
    dropped = [
        bar
        for bar in bars
        if bar.trade_date < LEGACY_OHLC_TOLERANCE_BEFORE and _ohlc_is_inconsistent(bar)
    ]
    if not dropped:
        return bars

    logger.warning(
        "Dropped %d OHLC-inconsistent legacy bar(s) before %s for %s "
        "(%s ~ %s). They predate the model's training window.",
        len(dropped),
        LEGACY_OHLC_TOLERANCE_BEFORE.isoformat(),
        getattr(dropped[0], "stock_code", None) or getattr(dropped[0], "index_code", None),
        min(bar.trade_date for bar in dropped).isoformat(),
        max(bar.trade_date for bar in dropped).isoformat(),
    )
    dropped_ids = {id(bar) for bar in dropped}
    return [bar for bar in bars if id(bar) not in dropped_ids]


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
        if bar.previous_close_change_sign not in _DOCUMENTED_CHANGE_SIGNS:
            logger.warning(
                "Undocumented previous-close change sign %r for %s on %s "
                "(likely a reference-price reset event, e.g. a stock "
                "split). Keeping the bar -- this field is metadata only "
                "and unused downstream.",
                bar.previous_close_change_sign,
                bar.stock_code,
                bar.trade_date.isoformat(),
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


def is_complete_for_retrieval(trade_date: date, retrieved_at: datetime) -> bool:
    """Return whether a row for ``trade_date`` was final when retrieved.

    Rows for earlier days are final; a row for the retrieval day itself is
    final only after ``SESSION_FINAL_TIME_KST``. A row dated after the
    retrieval day is impossible and raises.
    """
    if retrieved_at.tzinfo is None:
        raise ValueError("retrieved_at must be timezone-aware.")
    local = retrieved_at.astimezone(KST)
    if trade_date > local.date():
        raise HistoricalDataValidationError(
            f"Row dated {trade_date.isoformat()} is after its retrieval time "
            f"{local.isoformat()}."
        )
    return trade_date < local.date() or local.time() >= SESSION_FINAL_TIME_KST


def normalize_ka20006_response(
    response: Mapping[str, Any], *, retrieved_at: datetime
) -> list[IndexDailyBar]:
    """Convert a (possibly multi-page merged) ``ka20006`` response into index bars."""
    index_code = _required_text(response, "inds_cd", context="response")
    rows = response.get(INDEX_DAILY_ROWS_KEY)
    if not isinstance(rows, list):
        raise HistoricalDataValidationError(
            f"response.{INDEX_DAILY_ROWS_KEY} must be a list."
        )

    bars: list[IndexDailyBar] = []
    for row_index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise HistoricalDataValidationError(f"row {row_index} must be an object.")
        context = f"row {row_index}"
        trade_date = _parse_date(_required_text(row, "dt", context=context), context)
        bars.append(
            IndexDailyBar(
                index_code=index_code,
                trade_date=trade_date,
                open_price=_parse_index_points(row.get("open_pric"), "open_pric", context),
                high_price=_parse_index_points(row.get("high_pric"), "high_pric", context),
                low_price=_parse_index_points(row.get("low_pric"), "low_pric", context),
                close_price=_parse_index_points(row.get("cur_prc"), "cur_prc", context),
                volume=_parse_int(row.get("trde_qty"), "trde_qty", context),
                trade_value_million_krw=_parse_int(
                    row.get("trde_prica"), "trde_prica", context
                ),
                retrieved_at=retrieved_at,
                is_complete=is_complete_for_retrieval(trade_date, retrieved_at),
            )
        )

    bars = _drop_legacy_ohlc_inconsistent_bars(bars)
    _validate_index_bars(bars)
    return sorted(bars, key=lambda bar: bar.trade_date)


def _validate_index_bars(bars: Sequence[IndexDailyBar]) -> None:
    seen_dates: set[date] = set()
    for bar in bars:
        day = bar.trade_date.isoformat()
        if bar.trade_date in seen_dates:
            raise HistoricalDataValidationError(
                f"Duplicate index bar for {bar.index_code} on {day}."
            )
        seen_dates.add(bar.trade_date)
        if _ohlc_is_inconsistent(bar):
            raise HistoricalDataValidationError(
                f"Inconsistent OHLC for index {bar.index_code} on {day}."
            )
        if min(bar.open_price, bar.high_price, bar.low_price, bar.close_price) <= 0:
            raise HistoricalDataValidationError(
                f"Index prices must be positive on {day}."
            )
        if bar.volume < 0 or bar.trade_value_million_krw < 0:
            raise HistoricalDataValidationError(
                f"Trading activity must not be negative on {day}."
            )


def normalize_ka10059_response(
    response: Mapping[str, Any], *, stock_code: str, retrieved_at: datetime
) -> list[InvestorFlowDay]:
    """Convert a (possibly multi-page merged) amount-mode net-buy ``ka10059`` response.

    The response carries no stock code, so the caller passes the one it
    requested. Only the amount (``amt_qty_tp=1``), net-buy
    (``trde_tp=0``) request shape is supported -- the balance check
    assumes net buys in million KRW.

    Unbalanced rows are kept with ``is_complete=False`` rather than
    dropped, so a later run can replace them and the gap stays visible.
    """
    rows = response.get(INVESTOR_FLOW_ROWS_KEY)
    if not isinstance(rows, list):
        raise HistoricalDataValidationError(
            f"response.{INVESTOR_FLOW_ROWS_KEY} must be a list."
        )

    days: list[InvestorFlowDay] = []
    seen_dates: set[date] = set()
    for row_index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise HistoricalDataValidationError(f"row {row_index} must be an object.")
        context = f"row {row_index}"
        trade_date = _parse_date(_required_text(row, "dt", context=context), context)
        if trade_date in seen_dates:
            raise HistoricalDataValidationError(
                f"Duplicate investor flow for {stock_code} on {trade_date.isoformat()}."
            )
        seen_dates.add(trade_date)

        flows = {
            internal: _parse_int(row.get(field), field, context)
            for field, internal in _KA10059_FLOW_FIELDS.items()
        }
        volume = _parse_int(row.get("acc_trde_qty"), "acc_trde_qty", context)
        trade_value = _parse_int(row.get("acc_trde_prica"), "acc_trde_prica", context)
        if volume < 0 or trade_value < 0:
            raise HistoricalDataValidationError(
                f"Trading activity must not be negative on {trade_date.isoformat()}."
            )
        balanced = (
            abs(sum(flows[name] for name in INVESTOR_CATEGORIES))
            <= FLOW_BALANCE_TOLERANCE_MILLION_KRW
        )
        day = InvestorFlowDay(
            stock_code=stock_code,
            trade_date=trade_date,
            volume=volume,
            trade_value_million_krw=trade_value,
            retrieved_at=retrieved_at,
            is_complete=balanced
            and is_complete_for_retrieval(trade_date, retrieved_at),
            **flows,
        )
        if not balanced:
            logger.warning(
                "Unbalanced investor flow for %s on %s (residual %d million KRW); "
                "kept as incomplete.",
                stock_code,
                trade_date.isoformat(),
                day.balance_residual,
            )
        days.append(day)
    return sorted(days, key=lambda item: item.trade_date)


def _parse_index_points(value: Any, field: str, context: str) -> Decimal:
    """Undo ka20006's documented 100x integer encoding of index points."""
    return Decimal(_parse_int(value, field, context)).scaleb(-2)


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
