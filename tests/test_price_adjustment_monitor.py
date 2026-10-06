"""Adjusted-price recalculation monitor (CURRENT_STATUS item 82). tmp_path only, synthetic bars."""
from __future__ import annotations

import csv
from datetime import date, datetime, timedelta
import json
from pathlib import Path

import pytest

from scripts import monitor_price_adjustments as mon
from src.data.normalization import KST
from src.data.price_adjustment import (
    PARTIAL_CHANGE,
    ROWS_REMOVED,
    UNCHANGED,
    UNIFORM_RESCALE,
    classify_change,
)

ROOT = Path(__file__).resolve().parents[1]
CODE = "207940"
NOW = datetime(2026, 10, 9, 21, 0, tzinfo=KST)
PRICE_RATIO = 0.9923
VOLUME_RATIO = 1.0078


def _days(n: int, start: date = date(2025, 1, 1)) -> list[str]:
    return [(start + timedelta(days=k)).isoformat() for k in range(n)]


def _bars(n: int = 300, base: int = 200_000) -> dict[str, tuple[int, ...]]:
    return {
        day: (base + 10 * k, base + 10 * k + 500, base + 10 * k - 500, base + 10 * k + 100, 300_000 + 7 * k)
        for k, day in enumerate(_days(n))
    }


def _rescale(bars: dict[str, tuple[int, ...]], days: list[str]) -> dict[str, tuple[int, ...]]:
    return {
        day: (
            tuple(round(x * PRICE_RATIO) for x in bar[:4]) + (round(bar[4] * VOLUME_RATIO),)
            if day in days
            else bar
        )
        for day, bar in bars.items()
    }


# --- classify_change (pure) --------------------------------------------------


def test_uniform_rescale_records_ratio_volume_ratio_and_last_adjusted_date() -> None:
    old = _bars()
    days = sorted(old)
    adjusted = days[:-3]  # the event is effective after this date; the last 3 bars stay as they were
    new = {**_rescale(old, adjusted), **{d: b for d, b in _bars(305).items() if d not in old}}

    change = classify_change(old, new)

    assert change.classification == UNIFORM_RESCALE
    assert change.close_ratio == pytest.approx(PRICE_RATIO, abs=1e-5)
    assert change.volume_ratio == pytest.approx(VOLUME_RATIO, abs=1e-4)
    assert change.first_date == days[0] and change.last_date == adjusted[-1]
    assert change.n_overlap == 300 and change.n_matched == len(adjusted)
    assert change.fields == ("open", "high", "low", "close", "volume")


def test_uniform_rescale_tolerates_integer_rounding_on_low_prices() -> None:
    # 005930 had closes down to 116 won: rounding alone exceeds a flat 1e-4 there
    old = _bars(base=1_000)
    new = {d: tuple(round(x * 0.5) for x in b[:4]) + (b[4] * 2,) for d, b in old.items()}
    change = classify_change(old, new)
    assert change.classification == UNIFORM_RESCALE
    assert change.close_ratio == pytest.approx(0.5, abs=1e-3)


def test_correction_of_a_few_dates_is_partial_change() -> None:
    old = _bars()
    days = sorted(old)
    fixed = [days[10], days[50], days[51]]
    new = {d: (b[:3] + (b[3] + 1_000,) + b[4:] if d in fixed else b) for d, b in old.items()}

    change = classify_change(old, new)

    assert change.classification == PARTIAL_CHANGE
    assert change.n_changed == 3
    assert (change.first_date, change.last_date) == (days[10], days[51])
    assert change.fields == ("close",)
    assert change.close_ratio is None


def test_removed_past_dates_are_rows_removed() -> None:
    old = _bars()
    days = sorted(old)
    new = {d: b for d, b in old.items() if d not in (days[5], days[7])}
    change = classify_change(old, new)
    assert change.classification == ROWS_REMOVED
    assert change.n_removed == 2 and (change.first_date, change.last_date) == (days[5], days[7])


def test_new_recent_bars_alone_are_unchanged() -> None:
    old = _bars(300)
    change = classify_change(old, _bars(310))
    assert change.classification == UNCHANGED and not change.is_change and change.n_overlap == 300


# --- IO (tmp_path) -----------------------------------------------------------


def _write_historical(data_root: Path, code: str, bars: dict[str, tuple[int, ...]]) -> None:
    records = [
        {
            "stock_code": code,
            "trade_date": day,
            "open_price": bar[0],
            "high_price": bar[1],
            "low_price": bar[2],
            "close_price": bar[3],
            "volume": bar[4],
            "trade_value_million_krw": 1,
            "previous_close_change": 0,
            "previous_close_change_sign": 3,
            "turnover_rate": "0.10",
        }
        for day, bar in sorted(bars.items())
    ]
    path = data_root / "processed" / "historical" / f"{code}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(records), encoding="utf-8")


def _run(tmp_path: Path, *, dry_run: bool = False, top50: frozenset[str] = frozenset({CODE})):
    return mon.run(
        [CODE],
        top50=top50,
        data_root=tmp_path / "data",
        events_path=tmp_path / "events.csv",
        dry_run=dry_run,
        now=NOW,
    )


def test_first_run_creates_snapshot_without_alert(tmp_path: Path) -> None:
    _write_historical(tmp_path / "data", CODE, _bars())
    results = _run(tmp_path)

    assert [r.status for r in results] == [mon.NEW_SNAPSHOT]
    assert mon.read_snapshot(mon.snapshot_path(tmp_path / "data", CODE)) == _bars()
    assert not (tmp_path / "events.csv").exists()
    assert mon.exit_code(results) == 0
    assert mon.FINGERPRINT_HINT not in mon.summary_line(results, frozenset({CODE}), dry_run=False)


def test_change_is_logged_snapshot_refreshed_and_exit_code_nonzero(tmp_path: Path) -> None:
    data = tmp_path / "data"
    _write_historical(data, CODE, _bars())
    _run(tmp_path)
    rescaled = _rescale(_bars(), sorted(_bars()))
    _write_historical(data, CODE, rescaled)

    results = _run(tmp_path)

    assert [r.status for r in results] == [UNIFORM_RESCALE]
    assert mon.exit_code(results) == mon.CHANGES_DETECTED_EXIT != 0
    assert mon.read_snapshot(mon.snapshot_path(data, CODE)) == rescaled
    line = mon.summary_line(results, frozenset({CODE}), dry_run=False)
    assert "\n" not in line and "uniform_rescale 1" in line and mon.FINGERPRINT_HINT in line
    assert mon.FINGERPRINT_HINT not in mon.summary_line(results, frozenset(), dry_run=False)
    # the next run sees no change against the refreshed snapshot
    assert [r.status for r in _run(tmp_path)] == [UNCHANGED]


def test_dry_run_does_not_touch_snapshot_or_event_log(tmp_path: Path) -> None:
    data = tmp_path / "data"
    _write_historical(data, CODE, _bars())
    _run(tmp_path)
    snapshot = mon.snapshot_path(data, CODE)
    before = snapshot.read_bytes()
    _write_historical(data, CODE, _rescale(_bars(), sorted(_bars())))

    results = _run(tmp_path, dry_run=True)

    assert [r.status for r in results] == [UNIFORM_RESCALE]
    assert snapshot.read_bytes() == before
    assert not (tmp_path / "events.csv").exists()

    fresh = tmp_path / "fresh"
    _write_historical(fresh / "data", CODE, _bars())
    assert [r.status for r in _run(fresh, dry_run=True)] == [mon.NEW_SNAPSHOT]
    assert not mon.snapshot_path(fresh / "data", CODE).exists()  # dry-run creates no first snapshot


def test_event_log_holds_ratios_and_dates_but_no_prices(tmp_path: Path) -> None:
    data = tmp_path / "data"
    old = _bars()
    _write_historical(data, CODE, old)
    _run(tmp_path)
    new = _rescale(old, sorted(old))
    _write_historical(data, CODE, new)
    _run(tmp_path)

    with (tmp_path / "events.csv").open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    assert tuple(rows[0].keys()) == mon.EVENT_COLUMNS
    assert not any("price" in column for column in mon.EVENT_COLUMNS)
    assert rows[0]["classification"] == UNIFORM_RESCALE and rows[0]["top50"] == "True"
    price_values = {str(x) for bars in (old, new) for bar in bars.values() for x in bar}
    assert not price_values & {cell for row in rows for cell in row.values()}


def test_missing_historical_file_keeps_existing_snapshot(tmp_path: Path) -> None:
    data = tmp_path / "data"
    _write_historical(data, CODE, _bars())
    _run(tmp_path)
    (data / "processed" / "historical" / f"{CODE}.json").unlink()

    results = _run(tmp_path)

    assert [r.status for r in results] == [mon.NO_DATA]
    assert mon.read_snapshot(mon.snapshot_path(data, CODE)) == _bars()
    assert mon.exit_code(results) == 0


def test_nightly_runs_monitor_right_after_friday_daily_bars_and_treats_exit_4_as_recorded() -> None:
    script = (ROOT / "scripts" / "nightly_ingest.sh").read_text(encoding="utf-8")
    daily_block = script[script.index('if [[ "$daily" == "1" ]]; then'):script.index("daily bars skipped")]
    assert daily_block.index("ingest_kiwoom_daily_chart_batch.py") < daily_block.index(
        "monitor_price_adjustments.py --summary-only"
    )
    assert 'STOCKLENS_UNIVERSE="$COLLECT" "$PYTHON" scripts/monitor_price_adjustments.py' in daily_block
    monitor = daily_block[daily_block.index("monitor_price_adjustments.py"):]
    assert "if [[ $rc -eq 4 ]]" in monitor and "status=1" in monitor
    assert monitor.index("if [[ $rc -eq 4 ]]") < monitor.index("status=1")
    assert mon.CHANGES_DETECTED_EXIT == 4
