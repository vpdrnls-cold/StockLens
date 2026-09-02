"""Fetch and display the Kiwoom KOSPI daily index chart."""

from __future__ import annotations

from datetime import datetime
import logging
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.api import KiwoomClient
from src.utils.config import ConfigurationError


KOSPI_CODE = "001"


def main() -> int:
    base_date = datetime.now().strftime("%Y%m%d")

    try:
        client = KiwoomClient.from_env()
    except ConfigurationError as error:
        print(f"KOSPI setup failed: {error}", file=sys.stderr)
        return 1

    try:
        response = client.get_index_daily_chart(
            inds_cd=KOSPI_CODE,
            base_date=base_date,
        )
    except Exception as error:
        print(f"KOSPI request failed: {error}", file=sys.stderr)
        return 1

    print(f"inds_cd={response.get('inds_cd')}")
    print(f"return_code={response.get('return_code')}")
    print(f"return_msg={response.get('return_msg')}")

    rows = response.get("inds_dt_pole_qry", [])

    print(f"row_count={len(rows)}")

    for row in rows[:5]:
        print(row)

    return 0


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s %(message)s",
    )
    raise SystemExit(main())