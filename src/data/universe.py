"""Stock universe definitions shared by every script.

Two universes exist:

``core5``
    The original five stocks (Samsung Electronics, SK Hynix, Hyundai
    Motor, NAVER, Kakao). All results recorded in CURRENT_STATUS.md items
    14~26 were produced on this universe. It stays the default so those
    results remain reproducible.

``top50``
    The 50 largest KOSPI200 constituents by market cap, stored in
    ``config/universe_kospi200_top50.json``. The file is generated (and
    should be regenerated when refreshed) by
    ``scripts/build_universe.py`` from the Kiwoom API -- it is not
    hand-written.

Select a universe for any script without editing it::

    STOCKLENS_UNIVERSE=top50 PYTHONPATH=. python3 scripts/<script>.py

Survivorship caveat (AGENTS.md 23): ``top50`` is "the largest companies
*today*", applied to 2002~2026 history. Every member is by construction
a company that survived and grew, so backtests on it are optimistic in a
way the five hand-picked stocks were as well. Treat absolute performance
numbers accordingly and rely on relative comparisons (ML vs. momentum on
the same universe).
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

CORE_STOCKS: tuple[str, ...] = ("000660", "005380", "005930", "035420", "035720")

UNIVERSE_ENV_VAR = "STOCKLENS_UNIVERSE"
DEFAULT_UNIVERSE = "core5"

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TOP50_UNIVERSE_PATH = PROJECT_ROOT / "config" / "universe_kospi200_top50.json"

_UNIVERSE_FILES: dict[str, Path] = {"top50": TOP50_UNIVERSE_PATH}


class UniverseError(RuntimeError):
    """Raised when a universe cannot be resolved."""


@dataclass(frozen=True)
class UniverseStock:
    code: str
    name: str
    market_cap_eok: int


def get_universe(name: str | None = None) -> tuple[str, ...]:
    """Return the stock codes of a universe.

    ``name`` defaults to the ``STOCKLENS_UNIVERSE`` environment variable,
    then to ``core5``.
    """
    resolved = (name or os.environ.get(UNIVERSE_ENV_VAR) or DEFAULT_UNIVERSE).strip()

    if resolved == "core5":
        return CORE_STOCKS

    path = _UNIVERSE_FILES.get(resolved)
    if path is None:
        valid = ["core5", *sorted(_UNIVERSE_FILES)]
        raise UniverseError(f"Unknown universe {resolved!r}; expected one of {valid}.")

    return tuple(stock.code for stock in load_universe_file(path))


def load_universe_file(path: str | Path) -> list[UniverseStock]:
    path = Path(path)
    if not path.exists():
        raise UniverseError(
            f"{path} does not exist. Generate it first with "
            "`PYTHONPATH=. python3 scripts/build_universe.py`."
        )

    payload = json.loads(path.read_text(encoding="utf-8"))
    stocks = [
        UniverseStock(
            code=str(item["code"]),
            name=str(item.get("name", "")),
            market_cap_eok=int(item.get("market_cap_eok", 0)),
        )
        for item in payload["stocks"]
    ]

    codes = [stock.code for stock in stocks]
    if not codes or len(set(codes)) != len(codes):
        raise UniverseError(f"{path} must list at least one unique stock code.")

    return stocks


def normalize_stock_code(raw: Any) -> str:
    """Kiwoom may return exchange-suffixed codes (e.g. ``005930_NX``)."""
    return str(raw).strip().split("_")[0]


def is_common_stock_code(code: str) -> bool:
    """Common shares have codes ending in ``0``; preferred shares do not.

    Preferred shares (``005935`` Samsung Electronics Pref., ...) trade
    at a different price than the common share of the same company, so
    they would enter the universe as a near-duplicate of it.
    """
    return len(code) == 6 and code.endswith("0")


def select_top_by_market_cap(
    candidates: Iterable[Mapping[str, Any]],
    top_n: int,
) -> list[UniverseStock]:
    """Pick the ``top_n`` largest common stocks.

    ``candidates`` are mappings with ``code``, ``name`` and
    ``market_cap_eok`` (market cap in 100M KRW, as Kiwoom reports it).
    Preferred shares, duplicates and entries without a market cap are
    dropped.
    """
    if top_n <= 0:
        raise ValueError("top_n must be positive.")

    unique: dict[str, UniverseStock] = {}
    for item in candidates:
        code = normalize_stock_code(item["code"])
        market_cap = item.get("market_cap_eok")
        if not is_common_stock_code(code) or not market_cap or market_cap <= 0:
            continue
        unique[code] = UniverseStock(code, str(item.get("name", "")), int(market_cap))

    ranked = sorted(unique.values(), key=lambda stock: (-stock.market_cap_eok, stock.code))
    return ranked[:top_n]


def save_universe_file(
    path: str | Path,
    stocks: Sequence[UniverseStock],
    *,
    name: str,
    as_of: str,
    source: str,
) -> None:
    payload = {
        "name": name,
        "as_of": as_of,
        "source": source,
        "note": (
            "Largest common-stock KOSPI200 constituents by market cap on "
            "`as_of`; survivorship-biased for earlier history."
        ),
        "stocks": [
            {"code": s.code, "name": s.name, "market_cap_eok": s.market_cap_eok}
            for s in stocks
        ],
    }
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
