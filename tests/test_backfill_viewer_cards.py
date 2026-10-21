"""Viewer card backfill (CURRENT_STATUS item 97). Pure helpers only, no subprocess."""
from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from scripts import backfill_viewer_cards as bf
from src.data.intraday_split import FORWARD_START
from src.data.normalization import KST

START = date.fromisoformat(FORWARD_START)
EVENING = datetime(2026, 10, 14, 21, 0, tzinfo=KST)
MORNING = datetime(2026, 10, 14, 10, 30, tzinfo=KST)


def test_covered_dates_need_most_of_the_universe() -> None:
    d1, d2 = date(2026, 10, 12), date(2026, 10, 13)
    stocks = [{d1, d2}] * 9 + [{d1}]
    assert bf.covered_trade_dates(stocks, min_coverage=0.9) == [d1, d2]
    assert bf.covered_trade_dates(stocks, min_coverage=1.0) == [d1]
    assert bf.covered_trade_dates([]) == []


def test_backfill_never_reaches_before_forward_start() -> None:
    days = [date(2026, 9, 16), date(2026, 9, 23), START, date(2026, 9, 28)]
    assert bf.dates_to_backfill(days, set(), START, EVENING) == [START, date(2026, 9, 28)]


def test_backfill_skips_carded_days_and_todays_intraday_bar() -> None:
    days = [date(2026, 10, 12), date(2026, 10, 13), date(2026, 10, 14)]
    assert bf.dates_to_backfill(days, {date(2026, 10, 12)}, START, MORNING) == [date(2026, 10, 13)]
    assert bf.dates_to_backfill(days, {date(2026, 10, 12)}, START, EVENING) == [date(2026, 10, 13), date(2026, 10, 14)]


def test_card_commands_are_cards_only_and_never_the_paper_log() -> None:
    commands = bf.card_commands(date(2026, 10, 12))
    assert commands[0][1:] == ["scripts/recommend.py", "--cards-only", "--date", "2026-10-12"]
    assert all("--date" in c and "2026-10-12" in c for c in commands)
    assert [Path(c[1]).name for c in commands[1:]] == ["chart_card.py", "disclosure_card.py", "news_card.py",
                                                      "market_card.py"]


def test_carded_dates_reads_only_folders_with_quant_cards(tmp_path: Path) -> None:
    (tmp_path / "20261012").mkdir()
    (tmp_path / "20261012" / "005930_quant.json").write_text("{}", encoding="utf-8")
    (tmp_path / "20261013").mkdir()
    (tmp_path / "20261013" / "005930_chart.json").write_text("{}", encoding="utf-8")
    assert bf.carded_dates(tmp_path) == {date(2026, 10, 12)}
    assert bf.carded_dates(tmp_path / "missing") == set()
