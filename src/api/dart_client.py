"""OpenDART client: disclosure list and corp-code map (CURRENT_STATUS items 60/72).

Only the two endpoints the disclosure card needs. The API key comes from the
environment / .env (``DART_API_KEY``) and is removed from every error message,
the same way ``scripts/check_dart_sources.py`` (item 60) handled it.
"""

from __future__ import annotations

import io
import os
import time
from typing import Any, Callable
import xml.etree.ElementTree as ET
import zipfile

import requests

DART_BASE = "https://opendart.fss.or.kr/api"
OK_STATUSES = ("000", "013")  # 013 = no data for the query


class DartClientError(RuntimeError):
    """Request failed, or DART answered with an error status."""


class DartClient:
    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = DART_BASE,
        timeout_seconds: float = 30.0,
        sleep_seconds: float = 0.12,  # far below the documented per-minute limit
        http_get: Callable[..., Any] = requests.get,
    ) -> None:
        if not api_key:
            raise DartClientError("DART_API_KEY is empty.")
        self._key = api_key
        self._base = base_url.rstrip("/")
        self._timeout = timeout_seconds
        self._sleep = sleep_seconds
        self._get = http_get
        self.calls = 0

    @classmethod
    def from_env(cls, **kwargs: Any) -> "DartClient":
        from dotenv import load_dotenv

        load_dotenv()
        return cls(os.environ.get("DART_API_KEY", ""), **kwargs)

    def _scrub(self, text: str) -> str:
        return text.replace(self._key, "***")

    def _request(self, endpoint: str, params: dict[str, Any]) -> Any:
        if self._sleep:
            time.sleep(self._sleep)
        self.calls += 1
        try:
            resp = self._get(f"{self._base}/{endpoint}", params={"crtfc_key": self._key, **params},
                             timeout=self._timeout)
        except requests.RequestException as error:
            raise DartClientError(self._scrub(f"{endpoint} request failed: {error}")) from None
        if not resp.ok:
            raise DartClientError(self._scrub(f"{endpoint} HTTP {resp.status_code}: {resp.text[:300]}"))
        return resp

    def _json(self, endpoint: str, params: dict[str, Any]) -> dict[str, Any]:
        resp = self._request(endpoint, params)
        try:
            payload = resp.json()
        except ValueError:
            raise DartClientError(self._scrub(f"{endpoint} returned non-JSON: {resp.text[:300]}")) from None
        status = payload.get("status")
        if status not in OK_STATUSES:
            raise DartClientError(self._scrub(f"{endpoint} status {status}: {payload.get('message')}"))
        return payload

    def get_filings(self, corp_code: str, begin: str, end: str, *, page_count: int = 100) -> list[dict[str, Any]]:
        """Every filing of one company with receipt date in [begin, end] (YYYYMMDD), all pages.

        ``last_reprt_at=N`` keeps original filings and their corrections as separate rows.
        Returns the raw rows; a period with no filings (status 013) returns [].
        """
        rows: list[dict[str, Any]] = []
        page = 1
        while True:
            payload = self._json("list.json", {
                "corp_code": corp_code, "bgn_de": begin, "end_de": end,
                "last_reprt_at": "N", "page_no": page, "page_count": page_count,
            })
            rows.extend(payload.get("list") or [])
            if page >= int(payload.get("total_page") or 1):
                return rows
            page += 1

    def get_corp_codes(self) -> dict[str, dict[str, str]]:
        """Listed companies: stock_code -> {corp_code, corp_name, modify_date} (corpCode.xml, zipped)."""
        resp = self._request("corpCode.xml", {})
        try:
            with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
                xml_bytes = zf.read(zf.namelist()[0])
        except zipfile.BadZipFile:
            raise DartClientError(self._scrub(f"corpCode.xml is not a zip: {resp.text[:300]}")) from None
        mapping: dict[str, dict[str, str]] = {}
        for node in ET.fromstring(xml_bytes).iter("list"):
            stock = (node.findtext("stock_code") or "").strip()
            if stock:
                mapping[stock] = {
                    "corp_code": (node.findtext("corp_code") or "").strip(),
                    "corp_name": (node.findtext("corp_name") or "").strip(),
                    "modify_date": (node.findtext("modify_date") or "").strip(),
                }
        return mapping
