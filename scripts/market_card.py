"""Market analyst card for one decision date (CURRENT_STATUS item 74, AGENTS.md 43).

    STOCKLENS_UNIVERSE=top50 PYTHONPATH=. python scripts/market_card.py
    STOCKLENS_UNIVERSE=top50 PYTHONPATH=. python scripts/market_card.py --date 2026-10-02

Reference layer, the same for every stock: index levels and changes (Kiwoom
ka20006), rates and KRW/USD (ECOS, scripts/ingest_ecos.py), and the top50
universe's net buying (ka10059). Reads stored data only -- no API call -- and only
values dated on or before the decision date. The decision date is chosen the same
way as scripts/chart_card.py.

Output: reports/analyst_cards/<T>/market.json
"""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

from scripts.recommend import latest_decision_date, live_features
from scripts.run_ml_backtest import STOCK_CODES
from src.analysts.market import INDEX_LABELS, build_market_card, write_market_card
from src.data.macro import ECOS_SERIES, MacroStorage
from src.data.normalization import KST
from src.data.session import intraday_bar_error
from src.data.storage import HistoricalStorage

OUT_DIR = Path("reports/analyst_cards")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--date", default=None, help="YYYY-MM-DD (기본: 최신 판단일)")
    ap.add_argument("--no-save", action="store_true")
    args = ap.parse_args()

    date = latest_decision_date(live_features(), args.date)
    guard = intraday_bar_error(date.date(), datetime.now(KST))  # item 63
    if guard:
        raise SystemExit(guard)

    storage = HistoricalStorage("data")
    macro = MacroStorage("data")
    index_closes = {code: [(b.trade_date, float(b.close_price)) for b in storage.load_index_bars(code)]
                    for code in INDEX_LABELS}
    ecos = {key: macro.load(spec["stat"], spec["item"]) for key, spec in ECOS_SERIES.items()}
    flows = {code: [(d.trade_date, d.foreign, d.institution_total) for d in storage.load_investor_flows(code)]
             for code in STOCK_CODES}
    card = build_market_card(decision_date=date.date(), index_closes=index_closes, ecos=ecos,
                             ecos_labels={k: s["label"] for k, s in ECOS_SERIES.items()}, flows_by_stock=flows)

    for i in card["indices"]:
        if i.get("close") is not None:
            print(f"{i['label']} {i['close']:,.2f} ({i['date']}) 20일 {i['chg_20d']:+.1%}" if i["chg_20d"] is not None
                  else f"{i['label']} {i['close']:,.2f} ({i['date']})")
    for r in card["rates"]:
        print(f"{r['label']} {r['value']} ({r['date']})" if r["value"] is not None else f"{r['label']}: 데이터 없음")
    fx = card["fx"]
    print(f"{fx['label']} {fx['value']} ({fx['date']})" if fx["value"] is not None else f"{fx['label']}: 데이터 없음")
    missing = [k for k, v in ecos.items() if not v]
    if missing:
        print(f"ECOS 데이터 없음: {missing} — 먼저 scripts/ingest_ecos.py")
    if not args.no_save:
        print(f"저장: {write_market_card(card, OUT_DIR)}")


if __name__ == "__main__":
    main()
