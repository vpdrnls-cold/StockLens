"""Live reference data for the viewer: index level, one stock's quote, latest news (CURRENT_STATUS item 93).

Reference layer only (AGENTS.md 43.1/43.2): nothing here feeds the model, the
ranking, the cards or the paper log, and nothing is saved. Values are what the
APIs return now, shown with the query time. No return since the decision date is
computed -- only the API's own change versus the previous close (item 70 condition 2).

No Streamlit import; clients are passed in so this is tested with fakes.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from typing import Any, Iterable, Mapping

from src.analysts.news import noise_category, search_terms, title_matches
from src.data.news import normalize_item

KST = timezone(timedelta(hours=9))
SESSION_OPEN = time(9, 0)
SESSION_CLOSE = time(15, 30)
QUOTE_TTL_SECONDS = 60
NEWS_TTL_SECONDS = 600
NEWS_LIMIT = 10
NEWS_PAGES = 1  # 100 newest articles per refresh (Naver daily quota is shared with the nightly job)
# (label, mrkt_tp, inds_cd) as documented for ka20001 / used for ka20006 (market card).
LIVE_INDICES = (("KOSPI", "0", "001"), ("KOSPI200", "0", "201"))
# ka20001's cur_prc unit is unconfirmed (item 93): a level outside this ratio of the
# market card's last close is shown as "unit check needed" instead of a wrong number.
UNIT_RATIO_RANGE = (0.7, 1.3)
INDEX_POINT_SCALE = 100  # ka20006 documents index points as integers x100

SESSION_LABELS = {"open": "장중 · 미확정 값", "closed": "장 운영시간 아님 · 마지막 체결 기준"}


def session_state(now: datetime) -> str:
    """'open' on weekdays 09:00-15:30 KST, else 'closed' (KRX holidays are not checked)."""
    local = now.astimezone(KST)
    is_open = local.weekday() < 5 and SESSION_OPEN <= local.time() <= SESSION_CLOSE
    return "open" if is_open else "closed"


def _clean(value: Any) -> str | None:
    text = "" if value is None else str(value).strip().replace(",", "")
    return text or None


def parse_index_points(value: Any) -> float | None:
    """Signed index string -> points, sign kept. A decimal point means points as is;
    an integer is read as points x100 (ka20006's documented encoding)."""
    text = _clean(value)
    if text is None:
        return None
    number = float(text)
    return number if "." in text else number / INDEX_POINT_SCALE


def _rate(value: Any) -> float | None:
    text = _clean(value)
    return None if text is None else float(text)


def _hhmmss(value: Any) -> str | None:
    text = _clean(value)
    if text is None or len(text) != 6 or not text.isdigit():
        return None
    return f"{text[:2]}:{text[2:4]}:{text[4:]}"


def index_row(label: str, raw: Mapping[str, Any], reference_close: float | None) -> dict[str, Any]:
    """One live index line. ``cur_prc``'s leading sign is a direction mark, so the level is
    its absolute value; ``pred_pre``/``flu_rt`` keep their sign. ``unit_ok`` is None when
    there is no reference close to check against."""
    level = parse_index_points(raw.get("cur_prc"))
    level = None if level is None else abs(level)
    unit_ok = None
    if level is not None and reference_close:
        low, high = UNIT_RATIO_RANGE
        unit_ok = low <= level / reference_close <= high
    ticks = raw.get("inds_cur_prc_tm") or []
    first_tick = ticks[0] if isinstance(ticks, list) and ticks and isinstance(ticks[0], Mapping) else {}
    return {
        "label": label,
        "level": level if unit_ok is not False else None,
        "change": parse_index_points(raw.get("pred_pre")) if unit_ok is not False else None,
        "change_rate": _rate(raw.get("flu_rt")),
        "tick_time": _hhmmss(first_tick.get("tm_n")),
        "unit_ok": unit_ok,
    }


def stock_row(quote: Any) -> dict[str, Any]:
    """``KiwoomClient.get_current_quote`` result -> display values (price without the direction sign)."""
    price = quote.current_price
    return {
        "stock_code": quote.stock_code,
        "price": None if price is None else abs(price),
        "change": quote.change_from_previous_day,
        "change_rate": quote.change_rate,
        "volume": quote.volume,
    }


def live_news(items: Iterable[Mapping[str, Any]], stock_code: str, name: str,
              limit: int = NEWS_LIMIT) -> list[dict[str, Any]]:
    """Newest headlines that name the stock, noise rules of the news card applied
    (src/analysts/news.py), one line per distinct title."""
    terms = search_terms(stock_code, name)
    seen: set[str] = set()
    kept = []
    for item in items:
        art = normalize_item(dict(item))
        if art is None or not title_matches(art["title"], terms) or noise_category(art["title"]):
            continue
        if art["title"] in seen:
            continue
        seen.add(art["title"])
        kept.append(art)
    kept.sort(key=lambda a: a["published"], reverse=True)
    return kept[:limit]


def error_text(error: Exception) -> str:
    """What the screen may say about a failed call: error type and Kiwoom return code only
    (never the message, which can carry URLs or request details)."""
    code = getattr(error, "return_code", None)
    # Kiwoom puts 8050 (IP not registered) inside the message with return_code 3 (2026-10-12);
    # only the presence of the code is used, the message itself is never shown.
    if str(code) == "8050" or "8050" in str(error):
        return "키움 IP 미등록(8050) — 키움 REST API 홈페이지에서 지금 네트워크의 IP를 등록하세요."
    return f"조회 실패: {type(error).__name__}" + (f" (return_code {code})" if code not in (None, "") else "")


def fetch_indices(client: Any, reference_closes: Mapping[str, float | None]) -> list[dict[str, Any]]:
    return [index_row(label, client.get_index_quote(code, market_type=market), reference_closes.get(label))
            for label, market, code in LIVE_INDICES]


def fetch_stock(client: Any, stock_code: str) -> dict[str, Any]:
    return stock_row(client.get_current_quote(stock_code))


def fetch_news(client: Any, stock_code: str, name: str) -> list[dict[str, Any]]:
    query = search_terms(stock_code, name)[0]
    return live_news(client.latest(query, pages=NEWS_PAGES), stock_code, name)
