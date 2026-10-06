"""Bank of Korea ECOS client: daily statistic series (CURRENT_STATUS items 59/74).

Only ``StatisticSearch`` for daily (D) series. ECOS puts the API key in the URL
path, so every error message has it removed. Key: ``ECOS_API_KEY`` (.env).
"""

from __future__ import annotations

import os
import time
from typing import Any, Callable

import requests

ECOS_BASE = "https://ecos.bok.or.kr/api"
NO_DATA_CODE = "INFO-200"  # "해당하는 데이터가 없습니다"


class EcosClientError(RuntimeError):
    """Request failed, or ECOS answered with an error code."""


class EcosClient:
    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = ECOS_BASE,
        timeout_seconds: float = 30.0,
        sleep_seconds: float = 0.2,
        page_size: int = 10000,
        http_get: Callable[..., Any] = requests.get,
    ) -> None:
        if not api_key:
            raise EcosClientError("ECOS_API_KEY is empty.")
        self._key = api_key
        self._base = base_url.rstrip("/")
        self._timeout = timeout_seconds
        self._sleep = sleep_seconds
        self._page = page_size
        self._get = http_get
        self.calls = 0

    @classmethod
    def from_env(cls, **kwargs: Any) -> "EcosClient":
        from dotenv import load_dotenv

        load_dotenv()
        return cls(os.environ.get("ECOS_API_KEY", ""), **kwargs)

    def _scrub(self, text: str) -> str:
        return text.replace(self._key, "***")

    def _page_json(self, first: int, last: int, stat: str, begin: str, end: str, item: str) -> dict[str, Any]:
        url = f"{self._base}/StatisticSearch/{self._key}/json/kr/{first}/{last}/{stat}/D/{begin}/{end}/{item}"
        if self._sleep:
            time.sleep(self._sleep)
        self.calls += 1
        try:
            resp = self._get(url, timeout=self._timeout)
        except requests.RequestException as error:
            raise EcosClientError(self._scrub(f"ECOS {stat}/{item} request failed: {error}")) from None
        if not resp.ok:
            raise EcosClientError(self._scrub(f"ECOS {stat}/{item} HTTP {resp.status_code}: {resp.text[:300]}"))
        try:
            return resp.json()
        except ValueError:
            raise EcosClientError(self._scrub(f"ECOS {stat}/{item} returned non-JSON: {resp.text[:300]}")) from None

    def get_daily_series(self, stat: str, item: str, begin: str, end: str) -> list[dict[str, Any]]:
        """Raw rows of one daily series between ``begin`` and ``end`` (YYYYMMDD), all pages."""
        rows: list[dict[str, Any]] = []
        first = 1
        while True:
            payload = self._page_json(first, first + self._page - 1, stat, begin, end, item)
            if "RESULT" in payload:  # ECOS error envelope
                result = payload["RESULT"]
                if result.get("CODE") == NO_DATA_CODE:
                    return rows
                raise EcosClientError(self._scrub(f"ECOS {stat}/{item} {result.get('CODE')}: {result.get('MESSAGE')}"))
            body = payload.get("StatisticSearch") or {}
            batch = body.get("row") or []
            rows.extend(batch)
            total = int(body.get("list_total_count") or len(rows))
            if not batch or len(rows) >= total:
                return rows
            first += self._page
