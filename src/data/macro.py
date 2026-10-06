"""Storage for ECOS daily series used by the market card (CURRENT_STATUS item 74).

raw        data/raw/ecos/<stat>_<item>/<UTC timestamp>.json   rows as returned
processed  data/processed/macro/ecos_<stat>_<item>.json        {"series": ..., "points": [{date, value}]}

Points are merged by date; a later fetch replaces an earlier value for the same
date. Rows whose value is not a number (ECOS leaves some holidays blank) are skipped.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Iterable

# The five series of item 74 (codes confirmed by the item 59 probe).
ECOS_SERIES: dict[str, dict[str, str]] = {
    "ktb3y": {"stat": "817Y002", "item": "010200000", "label": "국고채 3년", "unit": "%"},
    "ktb10y": {"stat": "817Y002", "item": "010210000", "label": "국고채 10년", "unit": "%"},
    "corp_aa3y": {"stat": "817Y002", "item": "010300000", "label": "회사채 3년(AA-)", "unit": "%"},
    "cd91": {"stat": "817Y002", "item": "010502000", "label": "CD 91일", "unit": "%"},
    "usdkrw": {"stat": "731Y001", "item": "0000001", "label": "원/달러 매매기준율", "unit": "원"},
}


def _value(raw: Any) -> float | None:
    try:
        return float(str(raw).replace(",", ""))
    except (TypeError, ValueError):
        return None


class MacroStorage:
    def __init__(self, data_root: str | Path = "data") -> None:
        self.root = Path(data_root)

    def _name(self, stat: str, item: str) -> str:
        return f"ecos_{stat}_{item}"

    def processed_path(self, stat: str, item: str) -> Path:
        return self.root / "processed" / "macro" / f"{self._name(stat, item)}.json"

    def save_raw(self, stat: str, item: str, rows: list[dict[str, Any]], *, now: datetime | None = None) -> Path:
        now = now or datetime.now(timezone.utc)
        folder = self.root / "raw" / "ecos" / f"{stat}_{item}"
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{now:%Y%m%dT%H%M%S%fZ}.json"
        path.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
        return path

    def load(self, stat: str, item: str) -> list[dict[str, Any]]:
        """[{date: YYYY-MM-DD, value: float}] sorted by date; [] when never fetched."""
        path = self.processed_path(stat, item)
        if not path.exists():
            return []
        return json.loads(path.read_text(encoding="utf-8"))["points"]

    def merge(self, stat: str, item: str, rows: Iterable[dict[str, Any]], *, retrieved_at: str) -> int:
        by_date = {p["date"]: p for p in self.load(stat, item)}
        before = len(by_date)
        for row in rows:
            t, v = str(row.get("TIME", "")), _value(row.get("DATA_VALUE"))
            if len(t) != 8 or v is None:
                continue
            by_date[f"{t[:4]}-{t[4:6]}-{t[6:]}"] = {"date": f"{t[:4]}-{t[4:6]}-{t[6:]}", "value": v}
        points = sorted(by_date.values(), key=lambda p: p["date"])
        path = self.processed_path(stat, item)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"stat": stat, "item": item, "updated_at": retrieved_at, "points": points},
                                   ensure_ascii=False), encoding="utf-8")
        return len(by_date) - before
