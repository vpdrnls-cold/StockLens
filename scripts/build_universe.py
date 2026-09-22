"""Build config/universe_kospi200_top50.json from the Kiwoom API.

Steps:
  1. ka20002 (업종별주가, inds_cd=201) -> current KOSPI200 constituents.
  2. ka10001 (주식기본정보) for each constituent -> market cap (억원).
  3. Drop preferred shares, keep the largest ``--top`` by market cap.

Run from the repo root (needs the same .env credentials as the other
Kiwoom scripts; ~200 requests, about a minute):

    PYTHONPATH=. python3 scripts/build_universe.py --top 50

Kiwoom reports *today's* constituents and market caps, so the resulting
universe is survivorship-biased for earlier history (see
src/data/universe.py). The file records the ``as_of`` date.
"""

from __future__ import annotations

import argparse
from datetime import date
import logging
from pathlib import Path
import sys
import time

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.api import KiwoomClient
from src.api.kiwoom_client import KiwoomClientError
from src.data.universe import (
    TOP50_UNIVERSE_PATH,
    is_common_stock_code,
    normalize_stock_code,
    save_universe_file,
    select_top_by_market_cap,
)
from src.utils.config import ConfigurationError

REQUEST_INTERVAL_SECONDS = 0.3


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--top", type=int, default=50)
    parser.add_argument("--output", default=str(TOP50_UNIVERSE_PATH))
    arguments = parser.parse_args()

    try:
        client = KiwoomClient.from_env()
    except ConfigurationError as error:
        print(f"Setup failed: {error}", file=sys.stderr)
        return 1

    rows = client.get_index_constituents()
    constituents = {
        normalize_stock_code(row.get("stk_cd", "")): str(row.get("stk_nm", "")).strip()
        for row in rows
    }
    constituents = {c: n for c, n in constituents.items() if is_common_stock_code(c)}
    print(f"KOSPI200 constituents (common shares): {len(constituents)}")
    if len(constituents) < arguments.top:
        print(
            f"Only {len(constituents)} constituents returned, fewer than --top "
            f"{arguments.top}; check the ka20002 response before continuing.",
            file=sys.stderr,
        )
        return 1

    candidates = []
    failures = []
    for index, (code, name) in enumerate(sorted(constituents.items()), start=1):
        try:
            quote = client.get_current_quote(code)
            market_cap = int(str(quote.raw.get("mac", "")).replace(",", "").strip() or 0)
        except (KiwoomClientError, ValueError) as error:
            failures.append((code, str(error)))
            continue
        candidates.append(
            {"code": code, "name": quote.stock_name or name, "market_cap_eok": market_cap}
        )
        if index % 25 == 0:
            print(f"  ...{index}/{len(constituents)}")
        time.sleep(REQUEST_INTERVAL_SECONDS)

    if failures:
        print(f"Market cap lookup failed for {len(failures)} stock(s): {failures}")

    top = select_top_by_market_cap(candidates, arguments.top)
    if len(top) < arguments.top:
        print(f"Only {len(top)} stocks with a market cap; not writing.", file=sys.stderr)
        return 1

    save_universe_file(
        arguments.output,
        top,
        name=f"kospi200_top{arguments.top}",
        as_of=date.today().isoformat(),
        source="Kiwoom ka20002 (KOSPI200) + ka10001 (mac)",
    )

    print(f"\nWrote {arguments.output}\n")
    for rank, stock in enumerate(top, start=1):
        print(f"{rank:>3}  {stock.code}  {stock.name:<20} {stock.market_cap_eok:>12,} 억원")
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
    raise SystemExit(main())
