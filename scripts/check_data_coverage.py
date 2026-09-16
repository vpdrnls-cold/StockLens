"""Report each stock's collected date range and the 5-stock overlap window.

The backtest engine (src.backtest.baseline.prepare_universe) inner-joins
all 5 stocks on trade_date -- it can only ever use dates where every
stock already existed. This script finds that overlap explicitly instead
of assuming it from bar counts.
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.data.storage import HistoricalStorage

STOCK_CODES = (
    "000660",
    "005380",
    "005930",
    "035420",
    "035720",
)


def main() -> None:
    storage = HistoricalStorage("data")

    ranges: dict[str, tuple] = {}

    for code in STOCK_CODES:
        bars = storage.load_daily_bars(code)
        dates = sorted(bar.trade_date for bar in bars)
        ranges[code] = (dates[0], dates[-1], len(dates))
        print(f"{code}: {dates[0]} ~ {dates[-1]} ({len(dates)} bars)")

    overlap_start = max(start for start, _end, _n in ranges.values())
    overlap_end = min(end for _start, end, _n in ranges.values())

    print()
    print(f"5-stock overlap window: {overlap_start} ~ {overlap_end}")
    print(
        f"Overlap length: ~{(overlap_end - overlap_start).days / 365.25:.1f} years"
    )
    print()
    print(
        "The backtest can only ever place trades inside this overlap "
        "window, no matter how much more history any single stock has."
    )


if __name__ == "__main__":
    main()
