"""Build an ML dataset for a chosen universe and save it to its own CSV.

scripts/build_ml_dataset.py 는 그대로 두고, 유니버스별 데이터셋을 별도 파일로 저장한다.
기존 5종목 data/processed/ml_dataset.csv 를 덮어쓰지 않기 위함.

Usage (저장소 루트에서):
    STOCKLENS_UNIVERSE=top50 PYTHONPATH=. python3 scripts/build_ml_dataset_universe.py
    STOCKLENS_UNIVERSE=top50 PYTHONPATH=. python3 scripts/build_ml_dataset_universe.py --entry next_open
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.data.dataset import (  # noqa: E402
    DEFAULT_ENTRY_MODE,
    ENTRY_MODES,
    build_combined_dataset,
    split_by_time,
)
from src.data.storage import HistoricalStorage  # noqa: E402
from src.data.universe import UNIVERSE_ENV_VAR, get_universe  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--entry", default=DEFAULT_ENTRY_MODE, choices=ENTRY_MODES)
    parser.add_argument(
        "--out",
        default=None,
        help="저장 경로. 기본값: data/processed/ml_dataset_<universe>[_<entry>].csv",
    )
    args = parser.parse_args()

    universe_name = os.environ.get(UNIVERSE_ENV_VAR) or "core5"
    codes = get_universe()
    out = Path(args.out) if args.out else (
        PROJECT_ROOT / "data" / "processed"
        / f"ml_dataset_{universe_name}{'' if args.entry == 'close' else '_' + args.entry}.csv"
    )
    legacy = PROJECT_ROOT / "data" / "processed" / "ml_dataset.csv"
    if out.resolve() == legacy.resolve():
        print(f"기존 5종목 파일을 덮어쓰지 않습니다: {legacy}", file=sys.stderr)
        return 1

    storage = HistoricalStorage("data")
    stock_bars = {}
    for code in codes:
        bars = storage.load_daily_bars(code)
        if not bars:
            print(f"{code}: bar 없음 → 제외")
            continue
        stock_bars[code] = bars
        print(f"{code}: {len(bars)} bars, {bars[0].trade_date} ~ {bars[-1].trade_date}")

    dataset = build_combined_dataset(stock_bars, entry=args.entry)
    splits = split_by_time(dataset)

    print(f"\nuniverse={universe_name} entry={args.entry}")
    print(f"rows={len(dataset)} stocks={dataset['stock_code'].nunique()} "
          f"dates={dataset['trade_date'].min()} ~ {dataset['trade_date'].max()}")
    for name, part in (("train", splits.train), ("validation", splits.validation), ("test", splits.test)):
        print(f"  {name}: {len(part)} rows, 종목 {part['stock_code'].nunique()}개, "
              f"{part['trade_date'].min()} ~ {part['trade_date'].max()}")

    out.parent.mkdir(parents=True, exist_ok=True)
    dataset.to_csv(out, index=False)
    print(f"\n저장: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
