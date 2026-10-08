"""Daily-bar data quality audit of the KOSPI200 collection universe (CURRENT_STATUS item 86, pre-January 1-4).

    PYTHONPATH=. .venv/bin/python scripts/audit_universe_data.py --fetch-listing   # once: KRX listing dates (ka10099)
    PYTHONPATH=. .venv/bin/python scripts/audit_universe_data.py                   # audit only, no API call

Checks cover TRAIN_START_DATE (2002-10-29) .. the day before FORWARD_START, the dates the
model data uses; bars before the listing date are counted over everything stored.

Integrity only -- no returns, scores or performance are computed. Every check stops
the day before FORWARD_START, so nothing from the forward period is looked at.

Per stock: first/last bar, bar count, KRX listing date (``regDay``) and bars before it,
KOSPI trading days with no bar between the first and last bar, the longest such run,
non-positive prices, OHLC violations, zero-volume days, and closes that moved more
than the daily price limit (15% before 2015-06-15, 30% after, +0.5%p rounding margin)
-- counted only, as a sign of a broken adjustment, never summed or signed.

``--fetch-listing`` stores the raw ka10099 response under data/raw/kiwoom/ka10099/
and the 200 codes' listing dates in config/listing_dates_kospi200.json.
"""

from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path

import pandas as pd

from src.data.dataset import TRAIN_START_DATE
from src.data.intraday_split import FORWARD_START
from src.data.storage import HistoricalStorage
from src.eval.next_cycle import limit_breach_positions, price_limit  # single source (item 86)
from src.data.universe import get_universe, load_universe_file, KOSPI200_UNIVERSE_PATH

LISTING_FILE = Path("config/listing_dates_kospi200.json")
RAW_DIR = Path("data/raw/kiwoom/ka10099")
OUT = Path("reports/data_audit/kospi200_daily_audit.csv")
INDEX_CODE = "001"                       # KOSPI composite: the trading calendar


def audit_end() -> date:
    return date.fromisoformat(FORWARD_START) - timedelta(days=1)


def listing_dates(rows: list[dict], codes: list[str]) -> dict[str, dict]:
    """code -> {name, reg_day (YYYY-MM-DD)} for ``codes`` found in the ka10099 rows."""
    by_code = {str(r.get("code", "")).strip(): r for r in rows}
    out = {}
    for c in codes:
        r = by_code.get(c)
        if r and str(r.get("regDay", "")).strip():
            d = str(r["regDay"]).strip()
            out[c] = {"name": str(r.get("name", "")).strip(), "reg_day": f"{d[:4]}-{d[4:6]}-{d[6:8]}"}
    return out


def audit_stock(code: str, bars, calendar: list[date], reg_day: date | None, end: date,
                start: date = date.fromisoformat(TRAIN_START_DATE)) -> dict:
    """Integrity counts for one stock's bars in ``start``..``end`` (bars must be date-sorted).

    ``bars_before_listing`` counts every stored bar before the listing date; the other
    checks cover only the dates the model data uses (from TRAIN_START_DATE).
    """
    before_listing = sum(1 for b in bars if reg_day and b.trade_date < reg_day and b.trade_date <= end)
    first_stored = bars[0].trade_date.isoformat() if bars else ""
    bars = [b for b in bars if start <= b.trade_date <= end]
    row = {"stock_code": code, "n_bars": len(bars), "reg_day": reg_day.isoformat() if reg_day else "",
           "first_stored": first_stored, "bars_before_listing": before_listing}
    if not bars:
        return row
    first, last = bars[0].trade_date, bars[-1].trade_date
    have = {b.trade_date for b in bars}
    window = [d for d in calendar if first <= d <= last]
    missing = [d for d in window if d not in have]
    longest = run = 0
    for d in window:
        run = run + 1 if d not in have else 0
        longest = max(longest, run)
    breaches = [bars[i].trade_date.isoformat() for i in limit_breach_positions(bars)]
    row.update({
        "first_bar": first.isoformat(), "last_bar": last.isoformat(),
        "missing_trading_days": len(missing), "longest_missing_run": longest,
        "first_missing": missing[0].isoformat() if missing else "",
        "nonpositive_price": sum(1 for b in bars if min(b.open_price, b.high_price, b.low_price, b.close_price) <= 0),
        "ohlc_violation": sum(1 for b in bars if not (b.low_price <= min(b.open_price, b.close_price)
                                                      and max(b.open_price, b.close_price) <= b.high_price)),
        "zero_volume_days": sum(1 for b in bars if b.volume == 0),
        "limit_breaches": len(breaches), "limit_breach_dates": " ".join(breaches[:10]),
    })
    return row


def fetch_listing(codes: list[str]) -> None:
    from dotenv import load_dotenv

    from src.api.kiwoom_client import KiwoomClient

    load_dotenv(".env")
    rows = KiwoomClient.from_env().get_stock_list("0")
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    (RAW_DIR / f"{stamp}.json").write_text(json.dumps({"list": rows}, ensure_ascii=False), encoding="utf-8")
    found = listing_dates(rows, codes)
    payload = {"source": "Kiwoom ka10099 (mrkt_tp=0, KOSPI)", "as_of": date.today().isoformat(),
               "note": "KRX listing date (regDay) of the current listing; a stock moved from KOSDAQ shows its KOSPI date.",
               "missing": [c for c in codes if c not in found], "stocks": found}
    LISTING_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"ka10099: {len(rows)} KOSPI rows, listing date for {len(found)}/{len(codes)} universe stocks "
          f"(missing: {payload['missing'] or 'none'}) -> {LISTING_FILE}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fetch-listing", action="store_true")
    args = ap.parse_args(argv)

    codes = list(get_universe("kospi200"))
    names = {s.code: s.name for s in load_universe_file(KOSPI200_UNIVERSE_PATH)}
    if args.fetch_listing:
        fetch_listing(codes)
    listing = json.loads(LISTING_FILE.read_text(encoding="utf-8"))["stocks"] if LISTING_FILE.exists() else {}

    storage = HistoricalStorage("data")
    end = audit_end()
    calendar = sorted(b.trade_date for b in storage.load_index_bars(INDEX_CODE) if b.trade_date <= end)
    top50 = set(get_universe("top50"))
    rows = []
    for c in codes:
        reg = listing.get(c, {}).get("reg_day")
        row = audit_stock(c, storage.load_daily_bars(c), calendar, date.fromisoformat(reg) if reg else None, end)
        row.update(name=names.get(c, ""), in_top50=c in top50)
        rows.append(row)
    table = pd.DataFrame(rows)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    table.to_csv(OUT, index=False, encoding="utf-8-sig")

    print(f"audit {TRAIN_START_DATE} ~ {end} (bars before listing: all stored), calendar = index {INDEX_CODE} "
          f"{calendar[0] if calendar else '-'} ~ {calendar[-1] if calendar else '-'}, {len(codes)} stocks")
    flag_cols = ["bars_before_listing", "missing_trading_days", "nonpositive_price", "ohlc_violation",
                 "zero_volume_days", "limit_breaches"]
    for col in flag_cols:
        hit = table[table[col].fillna(0) > 0] if col in table else table.iloc[0:0]
        print(f"\n{col}: {len(hit)} stocks")
        if len(hit):
            cols = ["stock_code", "name", "in_top50", "first_stored", "reg_day", col]
            if col == "missing_trading_days":
                cols += ["longest_missing_run", "first_missing"]
            if col == "limit_breaches":
                cols += ["limit_breach_dates"]
            print(hit[cols].sort_values(col, ascending=False).head(25).to_string(index=False))
    print(f"\nno bars: {list(table.loc[table['n_bars'] == 0, 'stock_code'])}")
    print(f"saved: {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
