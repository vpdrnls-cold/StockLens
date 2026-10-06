"""News analyst card for given stocks (CURRENT_STATUS item 75, AGENTS.md 43).

    STOCKLENS_UNIVERSE=top50 PYTHONPATH=. python scripts/news_card.py --from-picks 50
    STOCKLENS_UNIVERSE=top50 PYTHONPATH=. python scripts/news_card.py --codes 005930 --date 2026-10-06

Reference layer: the newest stored headlines naming each company, published
before T 20:00 KST within the last 3 days (scripts/ingest_naver_news.py). No API
call, no judgment of the articles, nothing written to reports/daily_picks/. The
decision date and stock list are chosen the same way as scripts/chart_card.py.
Headlines cannot be fetched after the fact, so a card for a date before news
collection started is empty.

Output: reports/analyst_cards/<T>/<code>_news.json
"""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

from scripts.chart_card import codes_from_picks
from scripts.recommend import latest_decision_date, live_features, stock_names
from scripts.run_ml_backtest import STOCK_CODES
from src.analysts.news import build_news_card, write_news_card
from src.data.news import NewsStorage
from src.data.normalization import KST
from src.data.session import intraday_bar_error

OUT_DIR = Path("reports/analyst_cards")


def summary_line(card: dict) -> str:
    """One console line per card (schema v2, item 76)."""
    excluded = sum(card["excluded"]["counts"].values())
    return (f"{card['name']}({card['stock_code']}) {card['decision_date']}: 기간 내 수집 {card['n_collected_in_window']}건, "
            f"제목 일치 {card['n_title_match']}건, 이슈 {card['n_issues']}개, 제외 {excluded}건")


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

    storage = NewsStorage("data")
    names = stock_names()
    empty = []
    for code in codes:
        card = build_news_card(stock_code=code, name=names.get(code, code), decision_date=date.date(),
                               articles=storage.load(code), collected_at=storage.collected_at(code))
        if card["n_collected_in_window"] == 0:
            empty.append(code)
        print(summary_line(card))
        if not args.no_save:
            write_news_card(card, OUT_DIR)
    if empty:
        print(f"이 판단일 기간에 수집된 기사가 없는 종목 {len(empty)}개 — 뉴스 수집(scripts/ingest_naver_news.py)은 "
              "지난 기사를 나중에 받을 수 없어, 수집 시작 이전 판단일은 비어 있습니다.")
    if not args.no_save:
        print(f"저장: {OUT_DIR / f'{date:%Y%m%d}'}/<code>_news.json ({len(codes)}개)")


if __name__ == "__main__":
    main()
