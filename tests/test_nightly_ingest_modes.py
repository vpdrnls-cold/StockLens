"""Nightly modes of scripts/nightly_ingest.sh (CURRENT_STATUS item 96).

The script runs in a copy under tmp_path with a fake python (records each call,
no network) and a fake ``date`` that answers ``+%u`` with the chosen weekday.
"""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import stat
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
FRIDAY, WEDNESDAY = "5", "3"


def _executable(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def _run(tmp_path: Path, weekday: str, nightly_daily: str | None) -> list[str]:
    (tmp_path / "scripts").mkdir()
    shutil.copy(ROOT / "scripts" / "nightly_ingest.sh", tmp_path / "scripts" / "nightly_ingest.sh")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    calls = tmp_path / "calls.txt"
    _executable(bin_dir / "python", f'#!/bin/bash\necho "$*" >> "{calls}"\nexit 0\n')
    _executable(bin_dir / "curl", "#!/bin/bash\necho 203.0.113.7\n")  # no network in tests
    _executable(bin_dir / "date", f'#!/bin/bash\nif [[ "$1" == "+%u" ]]; then echo {weekday}; else exec /bin/date "$@"; fi\n')
    env = {k: v for k, v in os.environ.items() if not k.startswith("STOCKLENS_")}
    env.update(PATH=f"{bin_dir}:{env['PATH']}", STOCKLENS_PYTHON=str(bin_dir / "python"))
    if nightly_daily is not None:
        env["STOCKLENS_NIGHTLY_DAILY"] = nightly_daily
    result = subprocess.run(["bash", str(tmp_path / "scripts" / "nightly_ingest.sh")], env=env, cwd=tmp_path)
    assert result.returncode == 0
    return calls.read_text(encoding="utf-8").splitlines()


def _scripts(calls: list[str]) -> list[str]:
    return [c.split()[0] for c in calls]


@pytest.mark.parametrize("weekday", [WEDNESDAY, FRIDAY])
def test_daily_bars_and_viewer_cards_every_night(tmp_path: Path, weekday: str) -> None:
    called = _scripts(_run(tmp_path, weekday, None))
    for script in ("ingest_kiwoom_daily_chart_batch.py", "monitor_price_adjustments.py", "recommend.py",
                   "chart_card.py", "disclosure_card.py", "market_card.py", "news_card.py"):
        assert f"scripts/{script}" in called


def test_midweek_night_writes_cards_only_never_the_paper_log(tmp_path: Path) -> None:
    calls = _run(tmp_path, WEDNESDAY, None)
    recommend = [c for c in calls if c.startswith("scripts/recommend.py")]
    assert recommend == ["scripts/recommend.py --cards-only"]


@pytest.mark.parametrize(("weekday", "nightly_daily"), [(FRIDAY, None), (WEDNESDAY, "1")])
def test_friday_or_forced_night_writes_the_paper_log(tmp_path: Path, weekday: str, nightly_daily: str | None) -> None:
    calls = _run(tmp_path, weekday, nightly_daily)
    recommend = [c for c in calls if c.startswith("scripts/recommend.py")]
    assert recommend == ["scripts/recommend.py"]


def test_nightly_daily_0_skips_daily_bars_and_cards(tmp_path: Path) -> None:
    called = _scripts(_run(tmp_path, FRIDAY, "0"))
    assert "scripts/ingest_kiwoom_minute_chart_universe.py" in called
    for script in ("ingest_kiwoom_daily_chart_batch.py", "recommend.py", "chart_card.py"):
        assert f"scripts/{script}" not in called


def test_log_records_the_public_ip_of_the_night_run(tmp_path: Path) -> None:
    _run(tmp_path, WEDNESDAY, "0")
    log = next((tmp_path / "logs").glob("nightly_ingest_*.log")).read_text(encoding="utf-8")
    assert "public IP: 203.0.113.7" in log
