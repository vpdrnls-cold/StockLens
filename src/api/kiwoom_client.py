"""Kiwoom REST authentication and domestic-stock basic information client.

Only endpoints documented in ``config/kiwoom-rest-api-spec.json`` are used here:
``au10001`` for token issuance and ``ka10001`` for stock basic information.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import hashlib
import logging
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
    _JSON_CONTENT_TYPE = "application/json;charset=UTF-8"

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
        response = self._post(
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
        response = self._post(
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
    ) -> Mapping[str, Any]:
        """Return the raw ``ka10081`` daily-chart response for one stock.

        ``base_date`` must use the ``YYYYMMDD`` format documented by Kiwoom.
        ``adjusted_price_type`` is the documented ``upd_stkpc_tp`` value: ``0``
        for unadjusted prices or ``1`` for adjusted prices.
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

        token = self.authenticate()
        headers = self._json_headers(
            **{
                "api-id": "ka10081",
                "authorization": f"Bearer {token.value}",
                "cont-yn": "N",
                "next-key": "",
            }
        )
        return self._post(
            self._DAILY_CHART_PATH,
            {
                "stk_cd": normalized_code,
                "base_dt": base_date,
                "upd_stkpc_tp": adjusted_price_type,
            },
            headers,
            stage="daily_chart",
        )

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

        return self._post(
            self._DAILY_CHART_PATH,
            {
                "inds_cd": normalized_code,
                "base_dt": base_date,
            },
            headers,
            stage="index_daily_chart",
        )

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
    ) -> Mapping[str, Any]:
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
        return response


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
