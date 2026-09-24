"""Fetch and store raw ``ka10080`` minute-chart data for a whole universe.

``scripts/ingest_kiwoom_minute_chart.py`` 의 다종목 버전이다. 유니버스 파일의
종목을 순서대로 돌면서 기존 ``ingest_kiwoom_minute_chart_raw`` 를 그대로
호출하므로 저장 경로와 형식은 단일 종목 스크립트와 같다.
  data/raw/kiwoom/ka10080/<stock_code>/<UTC timestamp>.json

확인된 사실 (2026-09-23, 005930, tic_scope=15):
  - ka10080 은 약 1년치(2025-09-01~)까지만 제공한다. 그보다 이른
    --stop-date 를 줘도 API가 주는 데까지만 받고 끝난다.
  - 장중에 받으면 당일 봉이 미완성으로 저장된다. KRX 애프터마켓
    (2026-09-14~, 16:00~20:00) 때문에 하루가 확정되는 시각은 20:00 KST 이다.

Usage (저장소 루트에서, 20:00 KST 이후):
    python3 scripts/ingest_kiwoom_minute_chart_universe.py
    python3 scripts/ingest_kiwoom_minute_chart_universe.py --only 005930 000660
    python3 scripts/ingest_kiwoom_minute_chart_universe.py --no-skip-existing
"""

from __future__ import annotations

import argparse
import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
import re
import sys
import time

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.api import KiwoomClient, KiwoomClientError
from src.data.ingest import ingest_kiwoom_minute_chart_raw
from src.data.storage import HistoricalStorageError
from src.utils.config import ConfigurationError

KST = timezone(timedelta(hours=9))
DAY_CLOSE_HOUR_KST = 20  # 애프터마켓 종료 → 당일 봉 확정 시각
DEFAULT_UNIVERSE = PROJECT_ROOT / "config" / "universe_kospi200_top50.json"
RAW_DIR = PROJECT_ROOT / "data" / "raw" / "kiwoom" / "ka10080"
_CODE_RE = re.compile(r"^\d{6}$")
_FILE_TS_RE = re.compile(r"^(\d{8}T\d{6})")


def load_universe(path: Path) -> list[str]:
    """유니버스 JSON에서 6자리 종목코드를 등장 순서대로 뽑는다 (구조와 무관)."""
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)

    codes: list[str] = []

    def walk(obj) -> None:
        if isinstance(obj, dict):
            for key, value in obj.items():
                if isinstance(key, str) and _CODE_RE.match(key):
                    codes.append(key)
                walk(value)
        elif isinstance(obj, list):
            for item in obj:
                walk(item)
        elif isinstance(obj, str) and _CODE_RE.match(obj.strip()):
            codes.append(obj.strip())

    walk(data)
    return list(dict.fromkeys(codes))  # 순서 유지 중복 제거


def last_day_close_utc(now_kst: datetime) -> datetime:
    """이미 지난 가장 최근의 20:00 KST (UTC로 반환)."""
    cutoff = now_kst.replace(hour=DAY_CLOSE_HOUR_KST, minute=0, second=0, microsecond=0)
    if now_kst < cutoff:
        cutoff -= timedelta(days=1)
    return cutoff.astimezone(timezone.utc)


def has_fresh_file(stock_code: str, cutoff_utc: datetime) -> bool:
    """가장 최근 20:00 KST 이후에 저장된 raw 파일이 있으면 True (재실행 시 건너뛰기용)."""
    stock_dir = RAW_DIR / stock_code
    if not stock_dir.is_dir():
        return False
    for f in stock_dir.glob("*.json"):
        m = _FILE_TS_RE.match(f.name)
        if not m:
            continue
        saved = datetime.strptime(m.group(1), "%Y%m%dT%H%M%S").replace(tzinfo=timezone.utc)
        if saved >= cutoff_utc:
            return True
    return False


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Store raw Kiwoom ka10080 minute-chart data for every stock in a universe."
    )
    parser.add_argument("--universe", default=str(DEFAULT_UNIVERSE))
    parser.add_argument("--only", nargs="+", help="이 종목코드만 수집 (유니버스 대신)")
    parser.add_argument(
        "--stop-date",
        default="20100101",
        help="YYYYMMDD. 기본값은 API가 주는 최대치(현재 약 1년)까지 받도록 충분히 과거로 둔다.",
    )
    parser.add_argument(
        "--base-date",
        default=datetime.now(KST).strftime("%Y%m%d"),
        help="가장 최근 날짜 (YYYYMMDD, 기본값: 오늘 KST)",
    )
    parser.add_argument("--tic-scope", default="15",
                        choices=["1", "3", "5", "10", "15", "30", "45", "60"])
    parser.add_argument("--sleep", type=float, default=1.0, help="종목 사이 대기(초)")
    parser.add_argument(
        "--no-skip-existing",
        action="store_true",
        help="기본은 가장 최근 20:00 KST 이후 저장된 파일이 있는 종목을 건너뛴다 (중단 후 재실행용)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="20:00 KST 이전에도 실행 (당일 봉이 미완성으로 저장됨)",
    )
    args = parser.parse_args()

    now_kst = datetime.now(KST)
    if now_kst.hour < DAY_CLOSE_HOUR_KST and now_kst.weekday() < 5 and not args.force:
        print(
            f"지금은 {now_kst:%H:%M} KST 입니다. 20:00 이전에 받으면 오늘 봉이 미완성으로 저장됩니다.\n"
            "20:00 이후에 다시 실행하거나, 알고 있다면 --force 를 붙이세요.",
            file=sys.stderr,
        )
        return 2

    codes = args.only if args.only else load_universe(Path(args.universe))
    bad = [c for c in codes if not _CODE_RE.match(c)]
    if bad:
        print(f"잘못된 종목코드: {bad}", file=sys.stderr)
        return 1
    if not codes:
        print(f"종목코드를 찾지 못함: {args.universe}", file=sys.stderr)
        return 1

    cutoff_utc = last_day_close_utc(now_kst)
    print(f"대상 {len(codes)}종목, base_date={args.base_date}, stop_date={args.stop_date}, "
          f"tic_scope={args.tic_scope}")

    try:
        client = KiwoomClient.from_env()
    except ConfigurationError as error:
        print(f"설정 오류: {error}", file=sys.stderr)
        return 1

    ok, skipped, failed = [], [], []
    started = time.monotonic()
    for i, code in enumerate(codes, 1):
        prefix = f"[{i:>2}/{len(codes)}] {code}"
        if not args.no_skip_existing and has_fresh_file(code, cutoff_utc):
            print(f"{prefix} 건너뜀 (이미 최신 파일 있음)")
            skipped.append(code)
            continue
        try:
            result = ingest_kiwoom_minute_chart_raw(
                client,
                code,
                args.base_date,
                args.stop_date,
                tic_scope=args.tic_scope,
            )
        except (KiwoomClientError, HistoricalStorageError, ValueError) as error:
            print(f"{prefix} 실패: {error}")
            failed.append(code)
        else:
            print(f"{prefix} rows={result.row_count} → {result.raw_path}")
            ok.append(code)
        if i < len(codes):
            time.sleep(args.sleep)

    elapsed = time.monotonic() - started
    print(f"\n완료 {len(ok)} / 건너뜀 {len(skipped)} / 실패 {len(failed)}  ({elapsed/60:.1f}분)")
    if failed:
        print("실패 종목 재시도:")
        print(f"  python3 scripts/ingest_kiwoom_minute_chart_universe.py --only {' '.join(failed)}")
        return 1
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    raise SystemExit(main())
