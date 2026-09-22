"""Kiwoom REST authentication and domestic-stock basic information client.

Only endpoints documented in ``config/kiwoom-rest-api-spec.json`` are used here:
``au10001`` for token issuance and ``ka10001`` for stock basic information.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import hashlib
import logging
import time
from typing import Any, Mapping

import requests

from src.utils.config import KiwoomSettings


logger = logging.getLogger(__name__)


class KiwoomClientError(RuntimeError):
    """Base exception for Kiwoom client failures."""


class KiwoomTransportError(KiwoomClientError):
    """Raised when a request cannot be completed or decoded."""


class KiwoomAPIError(KiwoomClientError):
    """Raised when Kiwoom returns an HTTP or API-level error."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        return_code: int | str | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.return_code = return_code


@dataclass(frozen=True)
class AccessToken:
    """An in-memory access token returned by ``au10001``."""

    value: str
    expires_at: datetime
    token_type: str

    def is_valid(self, now: datetime | None = None) -> bool:
        """Return whether the token remains usable with a one-minute safety buffer."""
        return (now or datetime.now()) < self.expires_at - timedelta(minutes=1)


@dataclass(frozen=True)
class StockQuote:
    """Selected current fields from the ``ka10001`` stock-basic-information response."""

    stock_code: str
    stock_name: str
    current_price: int | None
    change_from_previous_day: int | None
    change_rate: float | None
    volume: int | None
    raw: Mapping[str, Any]


class KiwoomClient:
    """Small extensible REST client for documented Kiwoom API endpoints."""

    _TOKEN_PATH = "/oauth2/token"
    _STOCK_INFO_PATH = "/api/dostk/stkinfo"
    _DAILY_CHART_PATH = "/api/dostk/chart"
    _SECTOR_PATH = "/api/dostk/sect"
    _JSON_CONTENT_TYPE = "application/json;charset=UTF-8"

    # Kiwoom returns HTTP 429 (return_code=5, "허용된 요청 개수를
    # 초과하였습니다") when a client sends requests faster than its
    # per-endpoint rate limit. A single get_daily_chart() call can fire
    # dozens of back-to-back continuation requests, which reliably hits
    # this after ~12 pages with no pacing. _PAGE_REQUEST_INTERVAL_SECONDS
    # paces continuation requests preemptively; _RATE_LIMIT_MAX_RETRIES /
    # _RATE_LIMIT_BACKOFF_SECONDS are a safety net for when the limit is
    # still hit anyway (e.g. another process sharing the same app key).
    _PAGE_REQUEST_INTERVAL_SECONDS = 0.3
    _RATE_LIMIT_STATUS_CODE = 429
    _RATE_LIMIT_MAX_RETRIES = 5
    _RATE_LIMIT_BACKOFF_SECONDS = 2.0

    def __init__(
        self,
        settings: KiwoomSettings,
        *,
        session: requests.Session | None = None,
    ) -> None:
        self._settings = settings
        self._session = session or requests.Session()
        self._access_token: AccessToken | None = None

    @classmethod
    def from_env(cls) -> "KiwoomClient":
        """Construct a client from ``.env`` and process environment variables."""
        return cls(KiwoomSettings.from_env())

    def authenticate(self, *, force: bool = False) -> AccessToken:
        """Issue or reuse an ``au10001`` access token."""
        if not force and self._access_token and self._access_token.is_valid():
            return self._access_token

        payload = {
            "grant_type": "client_credentials",
            "appkey": self._settings.app_key,
            "secretkey": self._settings.secret_key,
        }
        response, _headers = self._post(
            self._TOKEN_PATH,
            payload,
            headers=self._json_headers(),
            stage="token_issuance",
        )
        token = str(response.get("token", "")).strip()
        expires_dt = str(response.get("expires_dt", "")).strip()
        token_type = str(response.get("token_type", "bearer")).strip() or "bearer"
        if not token or not expires_dt:
            raise KiwoomAPIError("Token response is missing token or expires_dt.")

        try:
            expires_at = datetime.strptime(expires_dt, "%Y%m%d%H%M%S")
        except ValueError as error:
            raise KiwoomAPIError("Token response has an invalid expires_dt value.") from error

        self._access_token = AccessToken(token, expires_at, token_type)
        return self._access_token

    def get_current_quote(self, stock_code: str) -> StockQuote:
        """Return the current quote fields supplied by ``ka10001`` for one stock code."""
        normalized_code = stock_code.strip()
        if not normalized_code:
            raise ValueError("stock_code must not be empty.")

        token = self.authenticate()
        headers = self._json_headers(
            **{
                "api-id": "ka10001",
                "authorization": f"Bearer {token.value}",
                "cont-yn": "N",
                "next-key": "",
            }
        )
        response, _headers = self._post(
            self._STOCK_INFO_PATH,
            {"stk_cd": normalized_code},
            headers,
            stage="stock_info",
        )
        return StockQuote(
            stock_code=str(response.get("stk_cd", normalized_code)),
            stock_name=str(response.get("stk_nm", "")),
            current_price=_parse_int(response.get("cur_prc")),
            change_from_previous_day=_parse_int(response.get("pred_pre")),
            change_rate=_parse_float(response.get("flu_rt")),
            volume=_parse_int(response.get("trde_qty")),
            raw=response,
        )

    def get_daily_chart(
        self,
        stock_code: str,
        base_date: str,
        *,
        adjusted_price_type: str = "1",
        max_pages: int = 60,
    ) -> Mapping[str, Any]:
        """Return the merged ``ka10081`` daily-chart history for one stock.

        ``base_date`` must use the ``YYYYMMDD`` format documented by Kiwoom.
        ``adjusted_price_type`` is the documented ``upd_stkpc_tp`` value: ``0``
        for unadjusted prices or ``1`` for adjusted prices.

        A single ``ka10081`` call returns at most one page of bars (in
        practice, roughly the most recent ~600 trading days before
        ``base_date``). Kiwoom's documented continuation mechanism
        (response headers ``cont-yn`` / ``next-key``, echoed back on the
        next request) is how you page further into the past. This method
        follows that continuation automatically and returns every page's
        ``stk_dt_pole_chart_qry`` rows concatenated together, so callers
        get full available history in one call instead of silently only
        the most recent page.

        ``max_pages`` is a safety bound (60 pages * ~600 rows/page is far
        more than any of these five stocks' listed trading history), not
        a tuning knob -- it exists so a server-side continuation bug
        can't cause an unbounded loop.
        """
        normalized_code = stock_code.strip()
        if not normalized_code:
            raise ValueError("stock_code must not be empty.")
        try:
            datetime.strptime(base_date, "%Y%m%d")
        except ValueError as error:
            raise ValueError("base_date must use YYYYMMDD format.") from error
        if adjusted_price_type not in {"0", "1"}:
            raise ValueError("adjusted_price_type must be '0' or '1'.")
        if max_pages <= 0:
            raise ValueError("max_pages must be positive.")

        token = self.authenticate()
        payload = {
            "stk_cd": normalized_code,
            "base_dt": base_date,
            "upd_stkpc_tp": adjusted_price_type,
        }

        all_rows: list[Any] = []
        merged_response: dict[str, Any] | None = None
        cont_yn = "N"
        next_key = ""

        for page in range(max_pages):
            if page > 0:
                time.sleep(self._PAGE_REQUEST_INTERVAL_SECONDS)

            headers = self._json_headers(
                **{
                    "api-id": "ka10081",
                    "authorization": f"Bearer {token.value}",
                    "cont-yn": cont_yn,
                    "next-key": next_key,
                }
            )

            response, response_headers = self._post(
                self._DAILY_CHART_PATH,
                payload,
                headers,
                stage="daily_chart",
            )

            rows = response.get("stk_dt_pole_chart_qry", [])
            if not isinstance(rows, list):
                raise KiwoomTransportError(
                    "stk_dt_pole_chart_qry must be a list."
                )
            all_rows.extend(rows)

            if merged_response is None:
                merged_response = dict(response)

            logger.info(
                "Kiwoom daily_chart page=%d stock=%s rows=%d cumulative=%d",
                page + 1,
                normalized_code,
                len(rows),
                len(all_rows),
            )

            cont_yn = str(response_headers.get("cont-yn", "N")).strip().upper()
            next_key = str(response_headers.get("next-key", "")).strip()

            if cont_yn != "Y" or not next_key or not rows:
                break
        else:
            logger.warning(
                "Kiwoom daily_chart stock=%s stopped at max_pages=%d "
                "with continuation still available -- history may be "
                "incomplete.",
                normalized_code,
                max_pages,
            )

        if merged_response is None:
            merged_response = {"stk_cd": normalized_code}

        merged_response["stk_dt_pole_chart_qry"] = all_rows
        return merged_response

    def get_index_constituents(
        self,
        inds_cd: str = "201",
        *,
        market_type: str = "2",
        exchange_type: str = "1",
        max_pages: int = 20,
    ) -> list[Mapping[str, Any]]:
        """Return the ``ka20002`` (업종별주가) rows for one index/sector.

        The defaults request KOSPI200 (``mrkt_tp="2"``, ``inds_cd="201"``)
        on KRX (``stex_tp="1"``) as documented in
        ``config/kiwoom-rest-api-spec.json``. Continuation pages
        (``cont-yn`` / ``next-key``) are followed automatically, the same
        way ``get_daily_chart`` does.
        """
        token = self.authenticate()
        payload = {
            "mrkt_tp": market_type,
            "inds_cd": inds_cd,
            "stex_tp": exchange_type,
        }

        rows: list[Mapping[str, Any]] = []
        cont_yn = "N"
        next_key = ""

        for page in range(max_pages):
            if page > 0:
                time.sleep(self._PAGE_REQUEST_INTERVAL_SECONDS)

            headers = self._json_headers(
                **{
                    "api-id": "ka20002",
                    "authorization": f"Bearer {token.value}",
                    "cont-yn": cont_yn,
                    "next-key": next_key,
                }
            )
            response, response_headers = self._post(
                self._SECTOR_PATH,
                payload,
                headers,
                stage="index_constituents",
            )

            page_rows = response.get("inds_stkpc", [])
            if not isinstance(page_rows, list):
                raise KiwoomTransportError("inds_stkpc must be a list.")
            rows.extend(page_rows)

            cont_yn = str(response_headers.get("cont-yn", "N")).strip().upper()
            next_key = str(response_headers.get("next-key", "")).strip()
            if cont_yn != "Y" or not next_key or not page_rows:
                break
        else:
            logger.warning(
                "Kiwoom index_constituents inds_cd=%s stopped at max_pages=%d "
                "with continuation still available -- list may be incomplete.",
                inds_cd,
                max_pages,
            )

        return rows

    def get_index_daily_chart(
        self,
        inds_cd: str,
        base_date: str,
    ) -> Mapping[str, Any]:
        """Return the raw ``ka20006`` daily-chart response for one market index.

        ``base_date`` must use the ``YYYYMMDD`` format documented by Kiwoom.
        """
        normalized_code = inds_cd.strip()
        if not normalized_code:
            raise ValueError("inds_cd must not be empty.")

        try:
            datetime.strptime(base_date, "%Y%m%d")
        except ValueError as error:
            raise ValueError("base_date must use YYYYMMDD format.") from error

        token = self.authenticate()

        headers = self._json_headers(
            **{
                "api-id": "ka20006",
                "authorization": f"Bearer {token.value}",
                "cont-yn": "N",
                "next-key": "",
            }
        )

        response, _headers = self._post(
            self._DAILY_CHART_PATH,
            {
                "inds_cd": normalized_code,
                "base_dt": base_date,
            },
            headers,
            stage="index_daily_chart",
        )
        return response

    def _json_headers(self, **headers: str) -> dict[str, str]:
        return {"Content-Type": self._JSON_CONTENT_TYPE, **headers}

    def diagnostic_context(self) -> dict[str, str | None]:
        """Return safe configuration diagnostics without credential values."""
        app_key_fingerprint = hashlib.sha256(
            self._settings.app_key.encode("utf-8")
        ).hexdigest()[:12]
        return {
            "environment": self._settings.environment,
            "base_url": self._settings.base_url,
            "app_key_fingerprint": f"sha256:{app_key_fingerprint}",
            "registered_ip": self._settings.registered_ip,
        }

    def _post(
        self,
        path: str,
        payload: Mapping[str, Any],
        headers: Mapping[str, str],
        *,
        stage: str,
    ) -> tuple[Mapping[str, Any], Mapping[str, str]]:
        delay = self._RATE_LIMIT_BACKOFF_SECONDS

        for attempt in range(self._RATE_LIMIT_MAX_RETRIES + 1):
            try:
                return self._post_once(path, payload, headers, stage=stage)
            except KiwoomAPIError as error:
                is_rate_limited = error.status_code == self._RATE_LIMIT_STATUS_CODE
                if not is_rate_limited or attempt == self._RATE_LIMIT_MAX_RETRIES:
                    raise
                logger.warning(
                    "Kiwoom rate limit hit stage=%s attempt=%d/%d; "
                    "retrying in %.1fs",
                    stage,
                    attempt + 1,
                    self._RATE_LIMIT_MAX_RETRIES,
                    delay,
                )
                time.sleep(delay)
                delay *= 2

        raise AssertionError("unreachable")  # pragma: no cover

    def _post_once(
        self,
        path: str,
        payload: Mapping[str, Any],
        headers: Mapping[str, str],
        *,
        stage: str,
    ) -> tuple[Mapping[str, Any], Mapping[str, str]]:
        logger.info(
            "Kiwoom request stage=%s environment=%s endpoint=%s",
            stage,
            self._settings.environment,
            path,
        )
        try:
            http_response = self._session.post(
                f"{self._settings.base_url}{path}",
                json=dict(payload),
                headers=dict(headers),
                timeout=self._settings.timeout_seconds,
            )
        except requests.RequestException as error:
            raise KiwoomTransportError(f"Kiwoom request failed: {error}") from error

        try:
            response = http_response.json()
        except ValueError as error:
            raise KiwoomTransportError("Kiwoom response is not valid JSON.") from error
        if not isinstance(response, dict):
            raise KiwoomTransportError("Kiwoom response JSON must be an object.")

        return_code = response.get("return_code")
        return_message = str(response.get("return_msg", "Kiwoom API request failed."))
        logger.info(
            "Kiwoom response stage=%s http_status=%s return_code=%s",
            stage,
            http_response.status_code,
            return_code,
        )
        if not http_response.ok:
            raise KiwoomAPIError(
                return_message,
                status_code=http_response.status_code,
                return_code=return_code,
            )
        if return_code not in (None, 0, "0"):
            raise KiwoomAPIError(return_message, return_code=return_code)

        response_headers = getattr(http_response, "headers", {}) or {}
        return response, response_headers


def _parse_int(value: Any) -> int | None:
    """Parse Kiwoom's signed numeric strings without masking blank values."""
    if value is None or str(value).strip() == "":
        return None
    try:
        return int(str(value).strip().replace(",", ""))
    except ValueError as error:
        raise KiwoomAPIError(f"Expected an integer field, received {value!r}.") from error


def _parse_float(value: Any) -> float | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        return float(str(value).strip().replace(",", ""))
    except ValueError as error:
        raise KiwoomAPIError(f"Expected a decimal field, received {value!r}.") from error
