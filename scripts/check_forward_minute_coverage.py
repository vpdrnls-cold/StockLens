"""Forward-period minute-bar coverage check (item 53) -- run weekly until the forward look.

Why: ka10080 serves only ~1 year and the nightly job re-fetches only the last
10 days, so a gap that is not noticed soon is never refilled automatically.
The forward evaluation warns when intraday coverage is below 80%
(evaluate_forward_holdout.MIN_INTRADAY_COVERAGE) -- by then it is too late to fix.

What it looks at: ONLY whether each (trading day, stock) in the forward period
(FORWARD_START ~) has a complete regular session in the raw files -- the same
27-bar rule (`day_features`) that decides `_valid` / `has_intraday` in the
forward evaluation. It prints no prices, returns, feature values, labels or
scores, so running it does not count as looking at the forward holdout.

Status per (date, stock)
  ok          complete regular session (usable for the overlay)
  incomplete  bars exist but not the full 27-bar session (half day, partial fetch)
  missing     no bars at all for that stock on a day other stocks have bars

Trading days = dates on which at least one universe stock has bars. Weekdays
with no bars for ANY stock are listed separately: a KRX holiday is fine, anything
else means the nightly job did not run that day.

    STOCKLENS_UNIVERSE=top50 PYTHONPATH=. python scripts/check_forward_minute_coverage.py
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from scripts.evaluate_forward_holdout import MIN_INTRADAY_COVERAGE
from scripts.intraday_ic_diagnostic import day_features, load_minute
from src.data.intraday_split import FORWARD_START
from src.data.universe import get_universe

KST = timezone(timedelta(hours=9))
API_HISTORY_DAYS = 365  # ka10080 keeps roughly one year
REFETCH_URGENT_DAYS = 300  # past this, a gap is close to disappearing from the API


def day_status(minute_root: Path, codes: list[str], start: pd.Timestamp) -> dict[str, dict[pd.Timestamp, bool]]:
    """{code: {date: complete_session?}} for dates >= start. Codes without a folder map to {}."""
    out: dict[str, dict[pd.Timestamp, bool]] = {}
    for code in codes:
        code_dir = minute_root / code
        m = load_minute(code_dir) if code_dir.is_dir() else pd.DataFrame()
        if m.empty:
            out[code] = {}
            continue
        m = m[m["date"] >= start]
        out[code] = {d: day_features(g) is not None for d, g in m.groupby("date", sort=True)}
    return out


def classify(status: dict[str, dict[pd.Timestamp, bool]], start: pd.Timestamp) -> tuple[pd.DataFrame, list[pd.Timestamp]]:
    """Long table (date, stock_code, status) over observed trading days + weekdays with no bars at all."""
    days = sorted({d for per_code in status.values() for d in per_code})
    rows = []
    for d in days:
        for code, per_code in status.items():
            s = "missing" if d not in per_code else ("ok" if per_code[d] else "incomplete")
            rows.append({"date": d, "stock_code": code, "status": s})
    table = pd.DataFrame(rows, columns=["date", "stock_code", "status"])
    empty_weekdays: list[pd.Timestamp] = []
    if days:
        weekdays = pd.bdate_range(start, days[-1])
        empty_weekdays = [d for d in weekdays if d not in set(days)]
    return table, empty_weekdays


def refetch_lookback_days(first_gap: pd.Timestamp, today: pd.Timestamp) -> int:
    """--lookback-days that reaches back past ``first_gap`` (with 2 days of margin)."""
    return int((today.normalize() - first_gap.normalize()).days) + 2


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--minute-dir", default="data/raw/kiwoom/ka10080")
    ap.add_argument("--start", default=FORWARD_START)
    ap.add_argument("--out", default="reports/forward_coverage")
    args = ap.parse_args()

    codes = [str(c) for c in get_universe()]
    start = pd.Timestamp(args.start)
    today = pd.Timestamp(datetime.now(KST).date())

    status = day_status(Path(args.minute_dir), codes, start)
    table, empty_weekdays = classify(status, start)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    table.to_csv(out / "forward_minute_status.csv", index=False, encoding="utf-8-sig")

    print("=" * 88)
    print(f"FORWARD MINUTE COVERAGE  {start:%Y-%m-%d} ~ (today {today:%Y-%m-%d} KST), {len(codes)} stocks")
    print("=" * 88)
    if table.empty:
        print("No minute bars on or after the forward start yet.")
        return

    days = sorted(table["date"].unique())
    cov = float((table["status"] == "ok").mean())
    print(f"trading days observed: {len(days)} ({days[0]:%Y-%m-%d} ~ {days[-1]:%Y-%m-%d})")
    print(f"complete (date, stock) share: {cov:.1%}  (forward eval warns below {MIN_INTRADAY_COVERAGE:.0%})")

    no_folder = [c for c, per_code in status.items() if not per_code]
    if no_folder:
        print(f"stocks with NO forward bars at all: {no_folder}")

    per_stock = (table.assign(ok=table["status"].eq("ok")).groupby("stock_code")["ok"].mean().sort_values())
    weak = per_stock[per_stock < 1.0]
    print(f"\nstocks below 100%: {len(weak)} / {len(per_stock)}")
    if len(weak):
        print(weak.head(15).to_string(float_format=lambda x: f"{x:.1%}"))

    per_day = table.pivot_table(index="date", columns="status", values="stock_code", aggfunc="count", fill_value=0)
    bad_days = per_day[per_day.get("ok", 0) < len(codes)]
    print(f"\ndays with at least one gap: {len(bad_days)} / {len(days)}")
    if len(bad_days):
        print(bad_days.to_string())

    if empty_weekdays:
        print("\nweekdays with no bars for ANY stock (fine if KRX holiday, otherwise the nightly job missed it):")
        print("  " + ", ".join(f"{d:%Y-%m-%d}" for d in empty_weekdays))

    last = days[-1]
    lag = len(pd.bdate_range(last + pd.Timedelta(days=1), today - pd.Timedelta(days=1)))
    if lag >= 2:
        print(f"\nWARNING: last bars are from {last:%Y-%m-%d}, {lag} weekdays ago -- check that the nightly job "
              "is running (holidays excepted).")

    gaps = table[table["status"] != "ok"]
    gap_dates = sorted(set(gaps["date"]) | set(empty_weekdays))
    if gap_dates:
        n = refetch_lookback_days(gap_dates[0], today)
        age = (today - gap_dates[0]).days
        print(f"\nto try refilling gaps (earliest {gap_dates[0]:%Y-%m-%d}, {age} days ago):")
        print(f"  STOCKLENS_UNIVERSE=top50 PYTHONPATH=. python scripts/ingest_kiwoom_minute_chart_universe.py "
              f"--lookback-days {n}")
        print("  then rerun this check. 'incomplete' on a known half day (e.g. exam-day late open) cannot be fixed.")
        if age > REFETCH_URGENT_DAYS:
            print(f"  URGENT: the API keeps ~{API_HISTORY_DAYS} days; this gap will soon be unrecoverable.")
    else:
        print("\nno gaps.")
    print(f"\nsaved: {out / 'forward_minute_status.csv'}")


if __name__ == "__main__":
    main()
