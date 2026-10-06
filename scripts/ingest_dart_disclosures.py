"""Collect OpenDART disclosure lists for the universe (CURRENT_STATUS item 72).

Incremental: fetches filings received in the last --lookback-days calendar days
(default 40, enough for the 30-day disclosure card plus slack) for every stock of
the universe and merges them by receipt number. Reference data only -- no model,
ranking or experiment reads it.

    STOCKLENS_UNIVERSE=kospi200 PYTHONPATH=. python scripts/ingest_dart_disclosures.py
    STOCKLENS_UNIVERSE=top50 PYTHONPATH=. python scripts/ingest_dart_disclosures.py --only 005930 --lookback-days 90

About one request per stock and night (200 stocks ~ 200 requests; the free
limit is 20,000 a day), plus the corp-code map once a month. Needs DART_API_KEY
in .env; the key is never printed.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.api.dart_client import DartClient, DartClientError  # noqa: E402
from src.data.disclosures import DisclosureStorage  # noqa: E402
from src.data.universe import get_universe  # noqa: E402

KST = timezone(timedelta(hours=9))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--only", nargs="+", help="these stock codes instead of the universe")
    ap.add_argument("--lookback-days", type=int, default=40)
    ap.add_argument("--data-root", default=str(PROJECT_ROOT / "data"))
    args = ap.parse_args()
    if args.lookback_days < 1:
        print("--lookback-days must be >= 1", file=sys.stderr)
        return 2

    codes = list(args.only) if args.only else list(get_universe())
    storage = DisclosureStorage(args.data_root)
    try:
        client = DartClient.from_env()
    except DartClientError as error:
        print(f"DART 설정 오류: {error}", file=sys.stderr)
        return 1

    corp_map = storage.load_corp_map()
    if corp_map is None:
        corp_map = client.get_corp_codes()
        storage.save_corp_map(corp_map)
        print(f"회사코드 맵 갱신: {len(corp_map)}개 상장사")

    today = datetime.now(KST).date()
    begin = (today - timedelta(days=args.lookback_days)).strftime("%Y%m%d")
    end = today.strftime("%Y%m%d")
    retrieved_at = datetime.now(KST).isoformat(timespec="seconds")
    ok = failed = 0
    unmapped = []
    for i, code in enumerate(codes, 1):
        entry = corp_map.get(code)
        if entry is None:
            unmapped.append(code)
            continue
        try:
            rows = client.get_filings(entry["corp_code"], begin, end)
        except DartClientError as error:
            failed += 1
            print(f"[{i:>3}/{len(codes)}] {code} 실패: {error}")
            continue
        storage.save_raw(code, rows)
        new = storage.merge(code, rows, retrieved_at=retrieved_at)
        ok += 1
        print(f"[{i:>3}/{len(codes)}] {code} {entry['corp_name']}: {len(rows)}건 (신규 {new})")
    if unmapped:
        print(f"회사코드 없음(건너뜀): {unmapped}")
    print(f"dart_summary={ok}/{len(codes)} successful, failed {failed}, unmapped {len(unmapped)}, "
          f"window {begin}~{end}, requests {client.calls}")
    # an unmapped code (e.g. a listing newer than the cached corp map) is reported, not a failure
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
