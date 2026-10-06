"""Storage for OpenDART disclosure lists (CURRENT_STATUS item 72).

raw        data/raw/dart/list/<stock_code>/<UTC timestamp>.json   every fetched row, as returned
processed  data/processed/disclosures/<stock_code>.json            merged by receipt number
corp map   data/processed/dart_corp_codes.json                     stock_code -> corp_code (refreshed after 30 days)

Merging keeps one row per ``rcept_no``; a later fetch of the same receipt number
replaces the stored row (DART can update the remark field), and nothing is
dropped because it is outside the latest fetch window.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from typing import Any, Iterable

KEEP_FIELDS = ("rcept_no", "rcept_dt", "report_nm", "flr_nm", "rm", "corp_code", "corp_name", "stock_code", "corp_cls")
CORP_MAP_MAX_AGE = timedelta(days=30)


class DisclosureStorage:
    def __init__(self, data_root: str | Path = "data") -> None:
        self.root = Path(data_root)
        self.raw_dir = self.root / "raw" / "dart" / "list"
        self.processed_dir = self.root / "processed" / "disclosures"
        self.corp_map_path = self.root / "processed" / "dart_corp_codes.json"

    # --- filings ------------------------------------------------------------
    def save_raw(self, stock_code: str, rows: list[dict[str, Any]], *, now: datetime | None = None) -> Path:
        now = now or datetime.now(timezone.utc)
        folder = self.raw_dir / stock_code
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{now:%Y%m%dT%H%M%S%fZ}.json"
        path.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
        return path

    def load(self, stock_code: str) -> list[dict[str, Any]]:
        path = self.processed_dir / f"{stock_code}.json"
        if not path.exists():
            return []
        return json.loads(path.read_text(encoding="utf-8"))["filings"]

    def merge(self, stock_code: str, rows: Iterable[dict[str, Any]], *, retrieved_at: str) -> int:
        """Merge fetched rows into the processed file; returns the number of new receipt numbers."""
        by_no = {r["rcept_no"]: r for r in self.load(stock_code)}
        before = len(by_no)
        for row in rows:
            no = str(row.get("rcept_no", "")).strip()
            if not no:
                continue
            by_no[no] = {k: str(row.get(k, "")).strip() for k in KEEP_FIELDS} | {"retrieved_at": retrieved_at}
        filings = sorted(by_no.values(), key=lambda r: (r["rcept_dt"], r["rcept_no"]))
        self.processed_dir.mkdir(parents=True, exist_ok=True)
        payload = {"stock_code": stock_code, "updated_at": retrieved_at, "filings": filings}
        (self.processed_dir / f"{stock_code}.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
        return len(by_no) - before

    def data_through(self, stock_code: str) -> str | None:
        """When this stock's list was last fetched (the card shows it as the data date)."""
        path = self.processed_dir / f"{stock_code}.json"
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8")).get("updated_at")

    # --- corp-code map --------------------------------------------------------
    def load_corp_map(self, *, now: datetime | None = None) -> dict[str, dict[str, str]] | None:
        """The saved map, or None when missing or older than CORP_MAP_MAX_AGE."""
        if not self.corp_map_path.exists():
            return None
        payload = json.loads(self.corp_map_path.read_text(encoding="utf-8"))
        saved = datetime.fromisoformat(payload["saved_at"])
        if (now or datetime.now(timezone.utc)) - saved > CORP_MAP_MAX_AGE:
            return None
        return payload["map"]

    def save_corp_map(self, mapping: dict[str, dict[str, str]], *, now: datetime | None = None) -> None:
        self.corp_map_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"saved_at": (now or datetime.now(timezone.utc)).isoformat(), "map": mapping}
        self.corp_map_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
