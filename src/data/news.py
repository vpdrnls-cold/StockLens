"""Storage for news search results (CURRENT_STATUS item 75).

raw        data/raw/naver_news/<stock_code>/<UTC timestamp>.json   items as returned
processed  data/processed/news/<stock_code>.json                    merged by article link

Only the title, the links, the publication time and the outlet's domain are kept
(the short API description is not shown anywhere, so it is not stored). Titles are
cleaned of the API's <b> highlight tags and HTML entities.
"""

from __future__ import annotations

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import html
import json
from pathlib import Path
import re
from typing import Any, Iterable
from urllib.parse import urlparse

_TAG_RE = re.compile(r"<[^>]+>")


def clean_title(raw: str) -> str:
    return html.unescape(_TAG_RE.sub("", raw or "")).strip()


def parse_pub_date(raw: str) -> str | None:
    """RFC 822 (``Tue, 06 Oct 2026 10:20:00 +0900``) -> ISO 8601 with offset, or None."""
    try:
        return parsedate_to_datetime(raw).isoformat()
    except (TypeError, ValueError, IndexError):
        return None


def outlet(url: str) -> str:
    host = urlparse(url or "").netloc.lower()
    return host[4:] if host.startswith("www.") else host


def normalize_item(item: dict[str, Any]) -> dict[str, Any] | None:
    link = (item.get("link") or item.get("originallink") or "").strip()
    published = parse_pub_date(item.get("pubDate", ""))
    if not link or published is None:
        return None
    original = (item.get("originallink") or "").strip()
    return {"title": clean_title(item.get("title", "")), "link": link, "originallink": original,
            "outlet": outlet(original or link), "published": published}


class NewsStorage:
    def __init__(self, data_root: str | Path = "data") -> None:
        self.root = Path(data_root)
        self.raw_dir = self.root / "raw" / "naver_news"
        self.processed_dir = self.root / "processed" / "news"

    def save_raw(self, stock_code: str, items: list[dict[str, Any]], *, now: datetime | None = None) -> Path:
        now = now or datetime.now(timezone.utc)
        folder = self.raw_dir / stock_code
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{now:%Y%m%dT%H%M%S%fZ}.json"
        path.write_text(json.dumps(items, ensure_ascii=False), encoding="utf-8")
        return path

    def _path(self, stock_code: str) -> Path:
        return self.processed_dir / f"{stock_code}.json"

    def load(self, stock_code: str) -> list[dict[str, Any]]:
        path = self._path(stock_code)
        return json.loads(path.read_text(encoding="utf-8"))["articles"] if path.exists() else []

    def collected_at(self, stock_code: str) -> str | None:
        path = self._path(stock_code)
        return json.loads(path.read_text(encoding="utf-8")).get("updated_at") if path.exists() else None

    def merge(self, stock_code: str, items: Iterable[dict[str, Any]], *, retrieved_at: str) -> int:
        """Merge by link; returns the number of new articles. Older articles are never dropped."""
        by_link = {a["link"]: a for a in self.load(stock_code)}
        before = len(by_link)
        for item in items:
            art = normalize_item(item)
            if art is not None:
                by_link.setdefault(art["link"], art)
        articles = sorted(by_link.values(), key=lambda a: a["published"])
        self.processed_dir.mkdir(parents=True, exist_ok=True)
        self._path(stock_code).write_text(
            json.dumps({"stock_code": stock_code, "updated_at": retrieved_at, "articles": articles},
                       ensure_ascii=False), encoding="utf-8")
        return len(by_link) - before
