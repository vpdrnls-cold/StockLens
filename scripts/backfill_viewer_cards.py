"""Backfill viewer cards for past decision dates (CURRENT_STATUS item 97).

For every trading day from FORWARD_START (2026-09-24) up to the latest daily bar that
has no quant cards yet, runs the same card steps as the nightly job (item 96):

    recommend.py --cards-only --date D        (quant cards + profile ranks, never the paper log)
    chart_card / disclosure_card / news_card --from-picks 50 --date D
    market_card --date D

Rankings only -- no returns are computed or shown (the viewer never reads prices of
the paper log, item 70). Dates before FORWARD_START are refused: they belong to the
daily test split, already used once (item 41) and locked.

Run (repo root, after the daily bars are up to date):
    STOCKLENS_UNIVERSE=top50 PYTHONPATH=. .venv/bin/python scripts/backfill_viewer_cards.py --dry-run
    STOCKLENS_UNIVERSE=top50 PYTHONPATH=. .venv/bin/python scripts/backfill_viewer_cards.py
"""

from __future__ import annotations

import argparse
from datetime import date, datetime
import os
from pathlib import Path
import subprocess
import sys

from src.data.intraday_split import FORWARD_START
from src.data.normalization import KST
from src.data.session import intraday_bar_error
from src.data.storage import HistoricalStorage
from src.data.universe import TOP50_UNIVERSE_PATH, load_universe_file

CARDS_ROOT = Path("reports/analyst_cards")
MIN_COVERAGE = 0.9  # same rule as recommend.py: a date needs bars for >= 90% of the universe
REFERENCE_CARD_SCRIPTS = ("chart_card.py", "disclosure_card.py", "news_card.py")


def covered_trade_dates(dates_per_stock: list[set[date]], min_coverage: float = MIN_COVERAGE) -> list[date]:
    """Dates on which at least ``min_coverage`` of the stocks have a bar, ascending."""
    if not dates_per_stock:
        return []
    counts: dict[date, int] = {}
    for stock_dates in dates_per_stock:
        for d in stock_dates:
            counts[d] = counts.get(d, 0) + 1
    need = min_coverage * len(dates_per_stock)
    return sorted(d for d, n in counts.items() if n >= need)


def dates_to_backfill(trade_dates: list[date], carded: set[date], start: date, now: datetime) -> list[date]:
    """Trading days on/after ``start`` with no quant cards yet and a final bar at ``now``
    (today's bar before the session-final time is intraday, item 63)."""
    return [d for d in trade_dates if d >= start and d not in carded and intraday_bar_error(d, now) is None]


def carded_dates(root: Path = CARDS_ROOT) -> set[date]:
    if not root.is_dir():
        return set()
    return {date(int(p.name[:4]), int(p.name[4:6]), int(p.name[6:]))
            for p in root.iterdir() if p.is_dir() and any(p.glob("*_quant.json"))}


def card_commands(day: date) -> list[list[str]]:
    iso = day.isoformat()
    python = sys.executable
    commands = [[python, "scripts/recommend.py", "--cards-only", "--date", iso]]
    commands += [[python, f"scripts/{s}", "--from-picks", "50", "--date", iso] for s in REFERENCE_CARD_SCRIPTS]
    commands.append([python, "scripts/market_card.py", "--date", iso])
    return commands


def run_day(day: date) -> bool:
    for command in card_commands(day):
        result = subprocess.run(command, stdout=subprocess.DEVNULL, env={**os.environ, "STOCKLENS_UNIVERSE": "top50"})
        if result.returncode != 0:
            print(f"{day}: 실패 ({Path(command[1]).name}, exit {result.returncode}) — 이 날짜의 남은 카드는 건너뜀",
                  file=sys.stderr)
            return False
    return True


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="채울 날짜만 출력")
    args = ap.parse_args()

    storage = HistoricalStorage("data")
    codes = [s.code for s in load_universe_file(TOP50_UNIVERSE_PATH)]
    trade_dates = covered_trade_dates([{b.trade_date for b in storage.load_daily_bars(c)} for c in codes])
    todo = dates_to_backfill(trade_dates, carded_dates(), date.fromisoformat(FORWARD_START), datetime.now(KST))
    print(f"카드 없는 판단일 {len(todo)}개: {', '.join(d.isoformat() for d in todo) or '없음'}")
    if args.dry_run or not todo:
        return
    failed = [d for d in todo if not run_day(d)]
    print(f"완료 {len(todo) - len(failed)} / 실패 {len(failed)}" + (f" ({', '.join(map(str, failed))})" if failed else ""))
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
