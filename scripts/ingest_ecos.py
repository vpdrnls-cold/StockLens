"""Collect the ECOS daily series of the market card (CURRENT_STATUS item 74).

Five series (src/data/macro.py ECOS_SERIES): KTB 3y/10y, corporate AA- 3y, CD 91d,
KRW/USD. A series never fetched before is loaded from --full-start (default
2000-01-01); after that only the last --lookback-days calendar days are refetched
and merged by date. Reference data only -- no model or experiment reads it.

    PYTHONPATH=. python scripts/ingest_ecos.py
    PYTHONPATH=. python scripts/ingest_ecos.py --lookback-days 60

About five requests a night. Needs ECOS_API_KEY in .env; the key is never printed.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.api.ecos_client import EcosClient, EcosClientError  # noqa: E402
from src.data.macro import ECOS_SERIES, MacroStorage  # noqa: E402

KST = timezone(timedelta(hours=9))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--lookback-days", type=int, default=30)
    ap.add_argument("--full-start", default="20000101")
    ap.add_argument("--data-root", default=str(PROJECT_ROOT / "data"))
    args = ap.parse_args()

    storage = MacroStorage(args.data_root)
    try:
        client = EcosClient.from_env()
    except EcosClientError as error:
        print(f"ECOS 설정 오류: {error}", file=sys.stderr)
        return 1

    now = datetime.now(KST)
    end = now.strftime("%Y%m%d")
    recent = (now - timedelta(days=args.lookback_days)).strftime("%Y%m%d")
    retrieved_at = now.isoformat(timespec="seconds")
    failed = 0
    for key, spec in ECOS_SERIES.items():
        begin = recent if storage.load(spec["stat"], spec["item"]) else args.full_start
        try:
            rows = client.get_daily_series(spec["stat"], spec["item"], begin, end)
        except EcosClientError as error:
            failed += 1
            print(f"{key} 실패: {error}")
            continue
        storage.save_raw(spec["stat"], spec["item"], rows)
        new = storage.merge(spec["stat"], spec["item"], rows, retrieved_at=retrieved_at)
        points = storage.load(spec["stat"], spec["item"])
        last = points[-1] if points else None
        print(f"{key} {spec['label']}: {len(rows)}행 받음 (신규 {new}), "
              f"최근 {last['date']} = {last['value']}" if last else f"{key}: 데이터 없음")
    print(f"ecos_summary={len(ECOS_SERIES) - failed}/{len(ECOS_SERIES)} successful, requests {client.calls}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
