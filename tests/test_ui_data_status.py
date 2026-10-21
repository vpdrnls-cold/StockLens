"""Viewer data-status bar (CURRENT_STATUS item 99, audit UI-P0-1). No Streamlit."""
from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from src.data.normalization import KST
from src.ui import data_status as ds

OK_LOG = """=== 2026-10-13 10:25:50 KST nightly ingest start ===
지금은 10:25 KST 입니다.
=== done, status=1 ===
=== 2026-10-13 20:37:00 KST nightly ingest start ===
public IP: 203.0.113.7
[ 68/200] 028050 삼성E&A: 9건 (신규 0)
=== done, status=0 ===
"""
IP_FAIL_LOG = """=== 2026-10-12 20:37:00 KST nightly ingest start ===
[ 1/200] 005930 토큰 발급 실패로 이 단계 중단 — 인증에 실패했습니다[8050:IP가 등록되지 않았습니다.]
=== done, status=1 ===
"""
WED_2300 = datetime(2026, 10, 14, 23, 0, tzinfo=KST)
WED_1100 = datetime(2026, 10, 14, 11, 0, tzinfo=KST)


def test_parse_takes_the_last_run_and_ignores_stock_codes_containing_8050() -> None:
    run = ds.parse_last_run(OK_LOG)
    assert run == ds.NightlyRun(date(2026, 10, 13), "20:37", 0, False)


def test_parse_detects_ip_error_and_unfinished_run() -> None:
    assert ds.parse_last_run(IP_FAIL_LOG).ip_not_registered is True
    unfinished = ds.parse_last_run("=== 2026-10-14 20:37:00 KST nightly ingest start ===\n--- [1/5] ---\n")
    assert unfinished.status is None
    assert ds.parse_last_run("no runs here") is None


def test_last_nightly_run_reads_the_newest_file(tmp_path: Path) -> None:
    (tmp_path / "nightly_ingest_20261012.log").write_text(IP_FAIL_LOG, encoding="utf-8")
    (tmp_path / "nightly_ingest_20261013.log").write_text(OK_LOG, encoding="utf-8")
    assert ds.last_nightly_run(tmp_path).run_date == date(2026, 10, 13)
    assert ds.last_nightly_run(tmp_path / "missing") is None


def test_expected_card_day_follows_the_nightly_job_and_skips_weekends() -> None:
    assert ds.expected_card_day(WED_2300) == date(2026, 10, 14)
    assert ds.expected_card_day(WED_1100) == date(2026, 10, 13)
    assert ds.expected_card_day(datetime(2026, 10, 12, 9, 0, tzinfo=KST)) == date(2026, 10, 9)  # Monday morning
    assert ds.expected_card_day(datetime(2026, 10, 17, 23, 0, tzinfo=KST)) == date(2026, 10, 16)  # Saturday


def test_weekdays_after_counts_only_weekdays() -> None:
    assert ds.weekdays_after(date(2026, 10, 8), date(2026, 10, 13)) == 3  # Fri 9, Mon 12, Tue 13
    assert ds.weekdays_after(date(2026, 10, 13), date(2026, 10, 13)) == 0


def test_all_fine_has_no_problem_line() -> None:
    lines = ds.status_lines("20261013", "20261013", ds.parse_last_run(OK_LOG), True, WED_1100)
    assert not any(line.problem for line in lines)
    assert [line.text for line in lines] == ["최신 카드 판단일 10-13", "마지막 야간 수집 10-13 20:37 · 정상", "고정 모델 지문 일치"]


def test_problems_are_flagged_with_measured_values_only() -> None:
    lines = ds.status_lines("20261008", "20261012", ds.parse_last_run(IP_FAIL_LOG), False, WED_2300)
    text = [line.text for line in lines]
    assert text[0] == "최신 카드 판단일 10-12 — 평일 기준 2일 늦음(휴장일이면 정상)"
    assert text[1] == "마지막 야간 수집 10-12 20:37 · 실패(status=1) · 키움 IP 미등록(8050) · 10-14 실행 기록 없음"
    assert text[2].startswith("고정 모델 지문 불일치")
    assert text[3] == "과거 판단일 10-08 보는 중 (최신 10-12)"
    assert [line.problem for line in lines] == [True, True, True, False]


def test_missing_log_and_fingerprint_are_problems() -> None:
    lines = ds.status_lines("20261013", "20261013", None, None, WED_1100)
    assert [line.problem for line in lines] == [False, True, True]
