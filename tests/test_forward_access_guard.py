"""Guards against side doors into the forward holdout (CURRENT_STATUS item 65).

``tests/test_run_ml_backtest_config.py`` only catches ``select_segment(..., "forward")``.
A script that rebuilds the intraday panel straight from the raw minute files reads
every date there is, forward included, without ever calling ``select_segment``.
Every script that touches the raw minute data must therefore be listed here with
the reason it is safe; a new one fails this test until someone reviews it.
"""
from __future__ import annotations

import re
from pathlib import Path

import pandas as pd
import pytest

from scripts import intraday_ic_diagnostic as diag
from src.data.intraday_split import FORWARD_START

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
_MINUTE_READ = re.compile(r"build_panel\(|load_minute\(|data/raw/kiwoom/ka10080")

# script -> why it may touch the raw minute files
MINUTE_DATA_SCRIPTS = {
    "intraday_ic_diagnostic.py": "panel capped before FORWARD_START (cap_before_forward)",
    "experiment_intraday_overlay_dev.py": "dev / semi_holdout only, through select_segment",
    "evaluate_forward_holdout.py": "the one forward evaluation (item 54)",
    "rehearse_january_runs.py": "panel and dataset cut before FORWARD_START (before_forward), dev segment only (item 88)",
    "check_forward_minute_coverage.py": "bar counts only (ok / incomplete / missing), no prices or labels",
    "check_intraday_raw.py": "data-quality checks only (coverage, reconcile, bar times), no labels",
    "ingest_kiwoom_minute_chart.py": "writer (API -> raw files)",
    "ingest_kiwoom_minute_chart_universe.py": "writer (API -> raw files)",
}


def test_every_script_reading_raw_minute_data_is_reviewed() -> None:
    readers = {
        path.name
        for path in SCRIPTS_DIR.glob("*.py")
        if _MINUTE_READ.search(path.read_text(encoding="utf-8"))
    }
    assert readers == set(MINUTE_DATA_SCRIPTS), (
        "A script reading data/raw/kiwoom/ka10080 was added or removed. Check that it cannot "
        "read the forward holdout, then update MINUTE_DATA_SCRIPTS."
    )


def test_diagnostic_default_end_is_the_day_before_forward() -> None:
    assert pd.Timestamp(diag.default_end_date()) == pd.Timestamp(FORWARD_START) - pd.Timedelta(days=1)


def test_diagnostic_refuses_an_end_inside_the_forward_holdout() -> None:
    panel = pd.DataFrame({"date": pd.to_datetime(["2026-09-22", "2026-09-24"]), "x": [1.0, 2.0]})
    with pytest.raises(SystemExit):
        diag.cap_before_forward(panel, FORWARD_START)


def test_diagnostic_drops_forward_rows() -> None:
    panel = pd.DataFrame({
        "date": pd.to_datetime(["2026-09-22", "2026-09-23", "2026-09-24", "2026-10-02"]),
        "x": [1.0, 2.0, 3.0, 4.0],
    })
    out = diag.cap_before_forward(panel, diag.default_end_date())
    assert out["date"].max() < pd.Timestamp(FORWARD_START)
    assert len(out) == 2


def test_diagnostic_caps_before_building_labels() -> None:
    source = (SCRIPTS_DIR / "intraday_ic_diagnostic.py").read_text(encoding="utf-8")
    main = source[source.index("def main"):]
    assert main.index("cap_before_forward(") < main.index("add_labels_and_benchmarks(")


def test_rehearsal_cuts_forward_rows() -> None:
    from scripts.rehearse_january_runs import before_forward

    frame = pd.DataFrame({"trade_date": pd.to_datetime(["2026-09-22", "2026-09-23", "2026-09-24", "2026-10-02"])})
    kept = before_forward(frame)
    assert pd.to_datetime(kept["trade_date"]).max() < pd.Timestamp(FORWARD_START) and len(kept) == 2
