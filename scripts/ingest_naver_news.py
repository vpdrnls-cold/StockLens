"""Collect recent news headlines per stock from NAVER API HUB (CURRENT_STATUS item 75).

For every stock of the universe the newest --pages x 100 articles for the name the
press uses (src/analysts/news.py NEWS_ALIASES, else the universe name) are fetched
(date order) and merged by link. The search API only pages back
about 1,000 articles, so for large companies this is a recent sample, not a full
record -- and past articles cannot be fetched later, so collection runs nightly.
Reference data only -- no model, ranking or experiment reads it.

    STOCKLENS_UNIVERSE=top50 PYTHONPATH=. python scripts/ingest_naver_news.py
    STOCKLENS_UNIVERSE=top50 PYTHONPATH=. python scripts/ingest_naver_news.py --only 005930 --pages 1

About 10 requests per stock (top50 ~ 500 a night; HUB limit 775,000 a month).
Keys: NAVER_CLIENT_ID / NAVER_CLIENT_SECRET in .env, never printed.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.analysts.news import search_terms  # noqa: E402
from src.api.naver_news_client import NaverNewsClient, NaverNewsClientError  # noqa: E402
from src.data.news import NewsStorage  # noqa: E402
from src.data.universe import KOSPI200_UNIVERSE_PATH, get_universe, load_universe_file  # noqa: E402

KST = timezone(timedelta(hours=9))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--only", nargs="+", help="these stock codes instead of the universe")
    ap.add_argument("--pages", type=int, default=10, help="pages of 100 newest articles per stock (max 10)")
    ap.add_argument("--data-root", default=str(PROJECT_ROOT / "data"))
    args = ap.parse_args()
    if not 1 <= args.pages <= 10:
        print("--pages must be 1..10", file=sys.stderr)
        return 2

    codes = list(args.only) if args.only else list(get_universe())
    names = {s.code: s.name for s in load_universe_file(KOSPI200_UNIVERSE_PATH)}  # superset of top50
    storage = NewsStorage(args.data_root)
    try:
        client = NaverNewsClient.from_env()
    except NaverNewsClientError as error:
        print(f"네이버 API 설정 오류: {error}", file=sys.stderr)
        return 1

    retrieved_at = datetime.now(KST).isoformat(timespec="seconds")
    ok = failed = 0
    for i, code in enumerate(codes, 1):
        name = names.get(code)
        if not name:
            print(f"[{i:>3}/{len(codes)}] {code}: 종목명 없음 — 건너뜀")
            continue
        query = search_terms(code, name)[0]  # the name the press uses (src/analysts/news.py)
        try:
            items = client.latest(query, pages=args.pages)
        except NaverNewsClientError as error:
            failed += 1
            print(f"[{i:>3}/{len(codes)}] {code} {name} 실패: {error}")
            continue
        storage.save_raw(code, items)
        new = storage.merge(code, items, retrieved_at=retrieved_at)
        ok += 1
        print(f"[{i:>3}/{len(codes)}] {code} {name} (검색어 {query}): {len(items)}건 (신규 {new})")
    print(f"news_summary={ok}/{len(codes)} successful, failed {failed}, requests {client.calls}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
