"""Chart analyst card for given stocks (CURRENT_STATUS item 61, AGENTS.md 43).

    STOCKLENS_UNIVERSE=top50 PYTHONPATH=. python scripts/chart_card.py --codes 005930 000660
    STOCKLENS_UNIVERSE=top50 PYTHONPATH=. python scripts/chart_card.py --from-picks 10

Reference layer: shows each stock's current pre-registered states with their
historical base rates (built by scripts/build_chart_base_rates.py) and recent
investor flows. It does not score or rank anything, and never writes to
reports/daily_picks/. --from-picks only READS the latest neutral picks file to
know which stocks to show.

Output: printed card + reports/analyst_cards/<T>/<code>_chart.json.
"""

from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path

import pandas as pd

from scripts.recommend import latest_decision_date, live_features, stock_names
from scripts.run_ml_backtest import STOCK_CODES
from src.analysts.chart import build_card, classify_states, flow_summary, render_text
from src.data.normalization import KST
from src.data.session import intraday_bar_error
from src.data.storage import HistoricalStorage

BASE_RATES = Path("data/processed/analysts/chart_base_rates.json")
PICKS_DIR = Path("reports/daily_picks")
OUT_DIR = Path("reports/analyst_cards")


def codes_from_picks(n: int) -> list[str]:
    files = sorted(PICKS_DIR.glob("*.csv"))
    if not files:
        raise SystemExit("reports/daily_picks/ 에 추천 파일이 없습니다. 먼저 recommend.py 를 실행하세요.")
    picks = pd.read_csv(files[-1], dtype={"stock_code": str})
    return picks.sort_values("rank")["stock_code"].head(n).tolist()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--codes", nargs="*", default=None)
    ap.add_argument("--from-picks", type=int, default=None, metavar="N", help="최신 추천 파일의 상위 N종목")
    ap.add_argument("--date", default=None, help="YYYY-MM-DD (기본: 최신 판단일)")
    ap.add_argument("--no-save", action="store_true")
    args = ap.parse_args()

    if not BASE_RATES.exists():
        raise SystemExit(f"{BASE_RATES} 없음. 먼저: STOCKLENS_UNIVERSE=top50 PYTHONPATH=. python scripts/build_chart_base_rates.py")
    table = json.loads(BASE_RATES.read_text(encoding="utf-8"))
    codes = args.codes or (codes_from_picks(args.from_picks) if args.from_picks else None)
    if not codes:
        raise SystemExit("--codes 또는 --from-picks N 을 지정하세요.")
    unknown = [c for c in codes if c not in STOCK_CODES]
    if unknown:
        raise SystemExit(f"유니버스에 없는 종목: {unknown} (현재 유니버스 {len(STOCK_CODES)}종목 — "
                         "STOCKLENS_UNIVERSE=top50 이 설정됐는지 확인하세요)")

    feats = live_features()
    date = latest_decision_date(feats, args.date)
    guard = intraday_bar_error(date.date(), datetime.now(KST))  # item 63
    if guard:
        raise SystemExit(guard)
    day = feats[feats["trade_date"] == date].reset_index(drop=True)
    day = pd.concat([day, classify_states(day)], axis=1).set_index("stock_code")  # quintiles over the whole day
    names = stock_names()
    storage = HistoricalStorage("data")

    for code in codes:
        if code not in day.index:
            print(f"{code}: {date.date()} 봉 없음 — 건너뜀\n")
            continue
        row = day.loc[code]
        flows = flow_summary(storage.load_investor_flows(code), date.date())
        card = build_card(code, names.get(code, code), date.date(), row, row, table["base_rates"], flows, table["meta"])
        print(render_text(card) + "\n")
        if not args.no_save:
            out = OUT_DIR / f"{date:%Y%m%d}"
            out.mkdir(parents=True, exist_ok=True)
            (out / f"{code}_chart.json").write_text(json.dumps(card, ensure_ascii=False, indent=1), encoding="utf-8")
    if not args.no_save:
        print(f"저장: {OUT_DIR / f'{date:%Y%m%d}'}/<code>_chart.json")


if __name__ == "__main__":
    main()
