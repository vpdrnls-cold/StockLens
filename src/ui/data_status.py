"""Data-status bar of the analyst panel (CURRENT_STATUS item 99, audit UI-P0-1).

Read-only and Streamlit-free (tested in the main environment). Shows only values
that already exist: card folder dates, the nightly log's own ``status`` line and
the quant cards' ``fingerprint_match``. Nothing is estimated; there is no KRX
holiday calendar, so a late card is reported in weekdays with "휴장일이면 정상".
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path
import re

from src.data.normalization import KST

LOG_DIR = Path("logs")
LOG_GLOB = "nightly_ingest_*.log"
# The nightly job starts at 20:37 and (with daily bars every night, item 96) ends well
# before this; after it, today's cards are expected.
NIGHTLY_DONE_BY_KST = time(22, 0)
IP_NOT_REGISTERED = "[8050:"  # Kiwoom return code inside the token error (not a stock code like 028050)

_START = re.compile(r"^=== (\d{4}-\d{2}-\d{2}) (\d{2}:\d{2}):\d{2} KST nightly ingest start ===$")
_DONE = re.compile(r"^=== done, status=(\d+) ===$")


@dataclass(frozen=True)
class NightlyRun:
    run_date: date
    started: str  # HH:MM KST
    status: int | None  # None = no "done" line (still running or killed)
    ip_not_registered: bool


@dataclass(frozen=True)
class StatusLine:
    text: str
    problem: bool


def parse_last_run(log_text: str) -> NightlyRun | None:
    """The last run recorded in one nightly log file (a file can hold several runs)."""
    lines = log_text.splitlines()
    starts = [i for i, line in enumerate(lines) if _START.match(line)]
    if not starts:
        return None
    first = starts[-1]
    day, hhmm = _START.match(lines[first]).groups()
    body = lines[first + 1:]
    done = next((_DONE.match(line) for line in body if _DONE.match(line)), None)
    return NightlyRun(
        run_date=date.fromisoformat(day),
        started=hhmm,
        status=int(done.group(1)) if done else None,
        ip_not_registered=any(IP_NOT_REGISTERED in line for line in body),
    )


def last_nightly_run(log_dir: Path = LOG_DIR) -> NightlyRun | None:
    """Last run in the newest nightly log (file names carry the KST date)."""
    files = sorted(Path(log_dir).glob(LOG_GLOB)) if Path(log_dir).is_dir() else []
    for path in reversed(files):
        try:
            run = parse_last_run(path.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
        if run is not None:
            return run
    return None


def _previous_weekday(day: date) -> date:
    day -= timedelta(days=1)
    while day.weekday() >= 5:
        day -= timedelta(days=1)
    return day


def expected_card_day(now: datetime) -> date:
    """Weekday whose cards should exist by ``now``: today after the nightly job, else the weekday before."""
    local = now.astimezone(KST)
    today = local.date()
    if today.weekday() < 5 and local.time() >= NIGHTLY_DONE_BY_KST:
        return today
    return _previous_weekday(today)


def weekdays_after(start: date, end: date) -> int:
    """Number of weekdays in (start, end]."""
    return sum(1 for k in range(1, (end - start).days + 1) if (start + timedelta(days=k)).weekday() < 5)


def _card_day(name: str) -> date:
    return date(int(name[:4]), int(name[4:6]), int(name[6:]))


def _md(day: date) -> str:
    return f"{day:%m-%d}"


def card_line(latest: date, expected: date) -> StatusLine:
    gap = weekdays_after(latest, expected)
    if gap == 0:
        return StatusLine(f"최신 카드 판단일 {_md(latest)}", False)
    return StatusLine(f"최신 카드 판단일 {_md(latest)} — 평일 기준 {gap}일 늦음(휴장일이면 정상)", True)


def nightly_line(run: NightlyRun | None, expected: date) -> StatusLine:
    if run is None:
        return StatusLine("야간 수집 기록 없음 (logs/nightly_ingest_*.log)", True)
    head = f"마지막 야간 수집 {_md(run.run_date)} {run.started}"
    if run.status is None:
        text, problem = f"{head} · 끝나지 않음(실행 중이거나 중단)", True
    elif run.status == 0:
        text, problem = f"{head} · 정상", False
    else:
        text, problem = f"{head} · 실패(status={run.status})", True
    if run.ip_not_registered:
        text, problem = f"{text} · 키움 IP 미등록(8050)", True
    if run.run_date < expected:
        text, problem = f"{text} · {_md(expected)} 실행 기록 없음", True
    return StatusLine(text, problem)


def model_line(fingerprint_match: bool | None) -> StatusLine:
    if fingerprint_match is None:
        return StatusLine("고정 모델 지문 정보 없음", True)
    if fingerprint_match:
        return StatusLine("고정 모델 지문 일치", False)
    return StatusLine("고정 모델 지문 불일치 — 기록된 모델과 다른 모델의 순위", True)


def status_lines(
    selected: str, latest: str, run: NightlyRun | None, fingerprint_match: bool | None, now: datetime
) -> list[StatusLine]:
    """Every line of the status bar; ``selected``/``latest`` are card folder names (YYYYMMDD)."""
    expected = expected_card_day(now)
    lines = [card_line(_card_day(latest), expected), nightly_line(run, expected), model_line(fingerprint_match)]
    if selected != latest:
        lines.append(StatusLine(f"과거 판단일 {_md(_card_day(selected))} 보는 중 (최신 {_md(_card_day(latest))})", False))
    return lines
