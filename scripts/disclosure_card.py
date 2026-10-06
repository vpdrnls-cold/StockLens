"""Disclosure analyst card for given stocks (CURRENT_STATUS item 72, AGENTS.md 43).

    STOCKLENS_UNIVERSE=top50 PYTHONPATH=. python scripts/disclosure_card.py --from-picks 50
    STOCKLENS_UNIVERSE=top50 PYTHONPATH=. python scripts/disclosure_card.py --codes 005930 --date 2026-10-02

Reference layer: lists each stock's filings in the 30 calendar days up to the
decision date from the stored DART lists (scripts/ingest_dart_disclosures.py).
No API call, no judgment of the filings, nothing written to reports/daily_picks/.
The decision date and stock list are chosen the same way as scripts/chart_card.py.

Output: reports/analyst_cards/<T>/<code>_disclosure.json
"""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

from scripts.chart_card import codes_from_picks
from scripts.recommend import latest_decision_date, live_features, stock_names
from scripts.run_ml_backtest import STOCK_CODES
from src.analysts.disclosure import build_disclosure_card, write_disclosure_card
from src.data.disclosures import DisclosureStorage
from src.data.normalization import KST
from src.data.session import intraday_bar_error

OUT_DIR = Path("reports/analyst_cards")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--codes", nargs="*", default=None)
    ap.add_argument("--from-picks", type=int, default=None, metavar="N", help="최신 추천 파일의 상위 N종목")
    ap.add_argument("--date", default=None, help="YYYY-MM-DD (기본: 최신 판단일)")
    ap.add_argument("--no-save", action="store_true")
    args = ap.parse_args()

    codes = args.codes or (codes_from_picks(args.from_picks) if args.from_picks else None)
    if not codes:
        raise SystemExit("--codes 또는 --from-picks N 을 지정하세요.")
    unknown = [c for c in codes if c not in STOCK_CODES]
    if unknown:
        raise SystemExit(f"유니버스에 없는 종목: {unknown} (현재 유니버스 {len(STOCK_CODES)}종목 — "
                         "STOCKLENS_UNIVERSE=top50 이 설정됐는지 확인하세요)")

    date = latest_decision_date(live_features(), args.date)
    guard = intraday_bar_error(date.date(), datetime.now(KST))  # item 63
    if guard:
        raise SystemExit(guard)

    storage = DisclosureStorage("data")
    names = stock_names()
    missing = []
    for code in codes:
        filings = storage.load(code)
        if not filings and storage.data_through(code) is None:
            missing.append(code)
        card = build_disclosure_card(stock_code=code, name=names.get(code, code), decision_date=date.date(),
                                     filings=filings, data_through=storage.data_through(code))
        print(f"{card['name']}({code}) {card['decision_date']}: 최근 {card['window']['days']}일 공시 "
              f"{card['n_filings']}건, 정정 {card['n_corrections']}건")
        if not args.no_save:
            write_disclosure_card(card, OUT_DIR)
    if missing:
        print(f"공시 목록이 아직 수집되지 않은 종목: {missing} — 먼저 scripts/ingest_dart_disclosures.py")
    if not args.no_save:
        print(f"저장: {OUT_DIR / f'{date:%Y%m%d}'}/<code>_disclosure.json ({len(codes)}개)")


if __name__ == "__main__":
    main()
