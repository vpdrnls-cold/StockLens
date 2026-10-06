"""NAVER API HUB news search client (CURRENT_STATUS item 75).

The search APIs moved from the NAVER Developers Center (openapi.naver.com, headers
X-Naver-Client-Id/Secret) to NAVER API HUB on 2026-06-25: new address and the
NCP API-gateway headers below; the response body (total, items with title,
originallink, link, description, pubDate) is unchanged. Keys come from .env as
NAVER_CLIENT_ID / NAVER_CLIENT_SECRET and are removed from every error message.
"""

from __future__ import annotations

import os
import time
from typing import Any, Callable

import requests

HUB_NEWS_URL = "https://naverapihub.apigw.ntruss.com/search/v1/news"
MAX_DISPLAY = 100
MAX_START = 1000  # the search API pages up to start=1000


class NaverNewsClientError(RuntimeError):
    """Request failed or the API answered with an error."""


class NaverNewsClient:
    def __init__(
        self,
        client_id: str,
        client_secret: str,
        *,
        url: str = HUB_NEWS_URL,
        timeout_seconds: float = 20.0,
        sleep_seconds: float = 0.1,
        http_get: Callable[..., Any] = requests.get,
    ) -> None:
        if not client_id or not client_secret:
            raise NaverNewsClientError("NAVER_CLIENT_ID / NAVER_CLIENT_SECRET are empty.")
        self._id, self._secret = client_id, client_secret
        self._url = url
        self._timeout = timeout_seconds
        self._sleep = sleep_seconds
        self._get = http_get
        self.calls = 0

    @classmethod
    def from_env(cls, **kwargs: Any) -> "NaverNewsClient":
        from dotenv import load_dotenv

        load_dotenv()
        return cls(os.environ.get("NAVER_CLIENT_ID", ""), os.environ.get("NAVER_CLIENT_SECRET", ""), **kwargs)

    def _scrub(self, text: str) -> str:
        return text.replace(self._secret, "***").replace(self._id, "***")

    def _page(self, query: str, start: int, display: int) -> dict[str, Any]:
        if self._sleep:
            time.sleep(self._sleep)
        self.calls += 1
        try:
            resp = self._get(
                self._url,
                params={"query": query, "display": display, "start": start, "sort": "date"},
                headers={"X-NCP-APIGW-API-KEY-ID": self._id, "X-NCP-APIGW-API-KEY": self._secret},
                timeout=self._timeout,
            )
        except requests.RequestException as error:
            raise NaverNewsClientError(self._scrub(f"news search request failed: {error}")) from None
        if not resp.ok:
            raise NaverNewsClientError(self._scrub(f"news search HTTP {resp.status_code}: {resp.text[:300]}"))
        try:
            return resp.json()
        except ValueError:
            raise NaverNewsClientError(self._scrub(f"news search returned non-JSON: {resp.text[:300]}")) from None

    def latest(self, query: str, *, pages: int = 3) -> list[dict[str, Any]]:
        """The newest ``pages`` x 100 articles for ``query`` (date order), stopping early when exhausted."""
        items: list[dict[str, Any]] = []
        for i in range(pages):
            start = 1 + i * MAX_DISPLAY
            if start > MAX_START:
                break
            payload = self._page(query, start, MAX_DISPLAY)
            batch = payload.get("items") or []
            items.extend(batch)
            if len(batch) < MAX_DISPLAY or start + MAX_DISPLAY > int(payload.get("total") or 0):
                break
        return items
