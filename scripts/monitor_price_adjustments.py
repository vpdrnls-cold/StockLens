"""Adjusted-price recalculation monitor (CURRENT_STATUS item 82, item 78 A5).

Why: the weekly ka10081 fetch rewrites each stock's whole adjusted history, so a
recalculation after a corporate action (item 62: 207940, all bars up to
2026-10-01 x0.99230) is otherwise noticed only by chance in a git diff. Scale-free
features and labels barely move, but the frozen-model fingerprint, the analyst
cards' historical statistics and raw-scale values can.

What it does, per stock of the universe: compares the bars seen last time
(``data/processed/price_snapshots/<code>.json``, gitignored) with the bars now in
``data/processed/historical/<code>.json`` on the dates both have, classifies the
change (``src/data/price_adjustment.classify_change``), appends changes to
``reports/price_adjustments/events.csv`` (ratios and dates only, no prices) and
then refreshes the snapshot. It only watches and records: it never edits the
historical data and computes no returns, features, labels or scores.

First run for a stock: the snapshot is created, no event. ``--dry-run``: neither
snapshots nor the event log are written.

Exit codes: 0 no change, 4 change detected (recorded -- not a failure),
1 a stock could not be read or written.

    STOCKLENS_UNIVERSE=kospi200 PYTHONPATH=. python scripts/monitor_price_adjustments.py
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
import sys
from typing import Sequence

from src.data.normalization import KST
from src.data.price_adjustment import (
    FIELDS,
    PARTIAL_CHANGE,
    ROWS_REMOVED,
    UNCHANGED,
    UNIFORM_RESCALE,
    Bars,
    PriceChange,
    bars_from_daily,
    classify_change,
)
from src.data.storage import HistoricalStorage, HistoricalStorageError
from src.data.universe import get_universe

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT_SUBDIR = Path("processed") / "price_snapshots"
EVENTS_PATH = PROJECT_ROOT / "reports" / "price_adjustments" / "events.csv"

CHANGES_DETECTED_EXIT = 4
ERROR_EXIT = 1

NEW_SNAPSHOT = "new_snapshot"
NO_DATA = "no_data"
ERROR = "error"
STATUS_ORDER = (UNCHANGED, UNIFORM_RESCALE, PARTIAL_CHANGE, ROWS_REMOVED, NEW_SNAPSHOT, NO_DATA, ERROR)

FINGERPRINT_HINT = (
    "고정 모델 지문 확인 필요: "
    "STOCKLENS_UNIVERSE=top50 PYTHONPATH=. .venv/bin/python scripts/run_ml_backtest.py"
)

# No price values on purpose: the log is committed to a public repo.
EVENT_COLUMNS = (
    "detected_at",
    "stock_code",
    "top50",
    "classification",
    "close_ratio",
    "volume_ratio",
    "first_date",
    "last_date",
    "n_overlap",
    "n_changed",
    "n_matched",
    "n_removed",
    "fields",
)


@dataclass(frozen=True)
class StockResult:
    stock_code: str
    status: str
    change: PriceChange | None = None
    message: str = ""


# --- snapshot IO -------------------------------------------------------------


def snapshot_path(data_root: Path, stock_code: str) -> Path:
    return data_root / SNAPSHOT_SUBDIR / f"{stock_code}.json"


def read_snapshot(path: Path) -> dict[str, tuple[int, ...]] | None:
    """Bars of the last snapshot, or ``None`` when there is none yet."""
    if not path.exists():
        return None
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
        bars = loaded["bars"]
        return {str(day): tuple(int(x) for x in values) for day, values in bars.items()}
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError, AttributeError) as error:
        raise HistoricalStorageError(f"Unreadable price snapshot {path}: {error}") from error


def write_snapshot(path: Path, stock_code: str, bars: Bars, taken_at: datetime) -> None:
    """Atomic write; compact JSON (a full history is ~10k rows)."""
    content = {
        "stock_code": stock_code,
        "taken_at": taken_at.isoformat(timespec="seconds"),
        "fields": list(FIELDS),
        "bars": {day: list(bars[day]) for day in sorted(bars)},
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    try:
        temporary.write_text(json.dumps(content, separators=(",", ":")) + "\n", encoding="utf-8")
        temporary.replace(path)
    except OSError as error:
        raise HistoricalStorageError(f"Unable to write price snapshot {path}: {error}") from error


# --- event log ---------------------------------------------------------------


def event_row(stock_code: str, change: PriceChange, *, top50: bool, detected_at: datetime) -> dict[str, str]:
    def text(value: object) -> str:
        return "" if value is None else str(value)

    return {
        "detected_at": detected_at.isoformat(timespec="seconds"),
        "stock_code": stock_code,
        "top50": str(top50),
        "classification": change.classification,
        "close_ratio": text(change.close_ratio),
        "volume_ratio": text(change.volume_ratio),
        "first_date": text(change.first_date),
        "last_date": text(change.last_date),
        "n_overlap": str(change.n_overlap),
        "n_changed": str(change.n_changed),
        "n_matched": str(change.n_matched),
        "n_removed": str(change.n_removed),
        "fields": "|".join(change.fields),
    }


def append_events(path: Path, rows: Sequence[dict[str, str]]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    write_header = not path.exists() or path.stat().st_size == 0
    with path.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=EVENT_COLUMNS)
        if write_header:
            writer.writeheader()
        writer.writerows(rows)


# --- per-stock check ---------------------------------------------------------


def check_stock(
    storage: HistoricalStorage, data_root: Path, stock_code: str, *, dry_run: bool, now: datetime
) -> StockResult:
    """Compare one stock against its snapshot; refresh the snapshot unless dry-run."""
    try:
        current = bars_from_daily(storage.load_daily_bars(stock_code))
        if not current:
            return StockResult(stock_code, NO_DATA)  # never replace a snapshot with nothing
        path = snapshot_path(data_root, stock_code)
        previous = read_snapshot(path)
        change = None if previous is None else classify_change(previous, current)
        if not dry_run:
            write_snapshot(path, stock_code, current, now)
    except HistoricalStorageError as error:
        return StockResult(stock_code, ERROR, message=str(error))
    if change is None:
        return StockResult(stock_code, NEW_SNAPSHOT)
    return StockResult(stock_code, change.classification, change)


def run(
    codes: Sequence[str],
    *,
    top50: frozenset[str],
    data_root: Path,
    events_path: Path,
    dry_run: bool,
    now: datetime,
) -> list[StockResult]:
    storage = HistoricalStorage(data_root)
    results = [check_stock(storage, data_root, code, dry_run=dry_run, now=now) for code in codes]
    if not dry_run:
        append_events(
            events_path,
            [
                event_row(r.stock_code, r.change, top50=r.stock_code in top50, detected_at=now)
                for r in results
                if r.change is not None and r.change.is_change
            ],
        )
    return results


# --- reporting ---------------------------------------------------------------


def changed_results(results: Sequence[StockResult]) -> list[StockResult]:
    return [r for r in results if r.change is not None and r.change.is_change]


def exit_code(results: Sequence[StockResult]) -> int:
    if any(r.status == ERROR for r in results):
        return ERROR_EXIT
    return CHANGES_DETECTED_EXIT if changed_results(results) else 0


def describe(result: StockResult) -> str:
    change = result.change
    assert change is not None
    if change.classification == UNIFORM_RESCALE:
        return (
            f"{result.stock_code}(uniform_rescale x{change.close_ratio} vol x{change.volume_ratio} "
            f"{change.first_date}~{change.last_date})"
        )
    if change.classification == ROWS_REMOVED:
        return f"{result.stock_code}(rows_removed {change.n_removed} {change.first_date}~{change.last_date})"
    return (
        f"{result.stock_code}(partial_change {change.n_changed} rows "
        f"{change.first_date}~{change.last_date} {'|'.join(change.fields)})"
    )


def summary_line(results: Sequence[StockResult], top50: frozenset[str], *, dry_run: bool) -> str:
    counts = {status: sum(r.status == status for r in results) for status in STATUS_ORDER}
    parts = [
        f"price adjustments: {len(results)} stocks",
        ", ".join(f"{status} {n}" for status, n in counts.items()),
    ]
    changed = changed_results(results)
    if changed:
        parts.append("changed: " + ", ".join(describe(r) for r in changed))
    errors = [r.stock_code for r in results if r.status == ERROR]
    if errors:
        parts.append("errors: " + ", ".join(errors))
    if any(r.stock_code in top50 for r in changed):
        parts.append(FINGERPRINT_HINT)
    if dry_run:
        parts.append("dry-run (snapshots/events not written)")
    return " | ".join(parts)


def print_report(results: Sequence[StockResult], top50: frozenset[str], *, dry_run: bool, events_path: Path) -> None:
    counts = {status: sum(r.status == status for r in results) for status in STATUS_ORDER}
    print(f"종목 수: {len(results)}")
    for status, n in counts.items():
        print(f"  {status:16s} {n}")
    changed = changed_results(results)
    if changed:
        print("\n바뀐 종목:")
        for r in changed:
            tag = " [top50]" if r.stock_code in top50 else ""
            print(f"  {describe(r)}{tag}")
    for r in results:
        if r.status == ERROR:
            print(f"  ERROR {r.stock_code}: {r.message}", file=sys.stderr)
    if dry_run:
        print("\n(dry-run: 스냅샷·이벤트 로그를 쓰지 않음)")
    elif changed:
        print(f"\n이벤트 기록: {events_path}")
    if any(r.stock_code in top50 for r in changed):
        print(FINGERPRINT_HINT)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--universe", default=None, help="default: STOCKLENS_UNIVERSE")
    parser.add_argument("--data-root", type=Path, default=PROJECT_ROOT / "data")
    parser.add_argument("--events", type=Path, default=EVENTS_PATH)
    parser.add_argument("--dry-run", action="store_true", help="compare only; write nothing")
    parser.add_argument("--summary-only", action="store_true", help="print one summary line (nightly log)")
    args = parser.parse_args(argv)

    codes = get_universe(args.universe)
    top50 = frozenset(get_universe("top50"))
    now = datetime.now(KST)
    results = run(codes, top50=top50, data_root=args.data_root, events_path=args.events, dry_run=args.dry_run, now=now)
    if args.summary_only:
        print(summary_line(results, top50, dry_run=args.dry_run))
    else:
        print_report(results, top50, dry_run=args.dry_run, events_path=args.events)
    return exit_code(results)


if __name__ == "__main__":
    sys.exit(main())
