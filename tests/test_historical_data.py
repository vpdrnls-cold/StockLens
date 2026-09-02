"""Tests for ka10081 normalization, validation, and separate local storage."""

from __future__ import annotations

from copy import deepcopy
from datetime import date
from decimal import Decimal
import json
from pathlib import Path

import pytest

from src.data.normalization import HistoricalDataValidationError, normalize_ka10081_response
from src.data.storage import HistoricalStorage
from src.data.ingest import ingest_kiwoom_daily_chart_batch


@pytest.fixture
def ka10081_response() -> dict:
    fixture_path = Path(__file__).parent / "fixtures" / "ka10081_response.json"
    return json.loads(fixture_path.read_text(encoding="utf-8"))


def test_normalizes_documented_ka10081_fields(ka10081_response: dict) -> None:
    bars = normalize_ka10081_response(ka10081_response)

    first = bars[0]
    assert first.stock_code == "005930"
    assert first.trade_date == date(2026, 8, 31)
    assert first.close_price == 251000
    assert first.open_price == 249000
    assert first.high_price == 253000
    assert first.low_price == 246000
    assert first.volume == 6801511
    assert first.trade_value_million_krw == 1700337
    assert first.previous_close_change == -6000
    assert first.previous_close_change_sign == 5
    assert first.turnover_rate == Decimal("0.12")


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda response: response["stk_dt_pole_chart_qry"][0].__setitem__("dt", None), "missing or blank"),
        (lambda response: response["stk_dt_pole_chart_qry"][0].__setitem__("cur_prc", "not-a-number"), "must be an integer"),
        (lambda response: response["stk_dt_pole_chart_qry"][0].__setitem__("high_pric", "200000"), "High price is below"),
    ],
)
def test_rejects_missing_malformed_and_invalid_ohlc(
    ka10081_response: dict, mutate, message: str
) -> None:
    response = deepcopy(ka10081_response)
    mutate(response)

    with pytest.raises(HistoricalDataValidationError, match=message):
        normalize_ka10081_response(response)


def test_rejects_duplicate_trade_dates(ka10081_response: dict) -> None:
    response = deepcopy(ka10081_response)
    response["stk_dt_pole_chart_qry"][1]["dt"] = "20260831"

    with pytest.raises(HistoricalDataValidationError, match="Duplicate daily bar"):
        normalize_ka10081_response(response)


def test_stores_raw_and_normalized_data_in_separate_paths(
    ka10081_response: dict, tmp_path: Path
) -> None:
    storage = HistoricalStorage(tmp_path / "data")
    bars = normalize_ka10081_response(ka10081_response)

    raw_path = storage.save_raw_ka10081("005930", ka10081_response)
    normalized_path = storage.save_daily_bars("005930", bars)

    assert "raw/kiwoom/ka10081/005930" in raw_path.as_posix()
    assert "processed/historical/005930.json" in normalized_path.as_posix()
    assert json.loads(raw_path.read_text(encoding="utf-8")) == ka10081_response
    normalized = json.loads(normalized_path.read_text(encoding="utf-8"))
    assert normalized[0]["trade_date"] == "2026-08-28"
    assert "cur_prc" not in normalized[0]
    assert normalized[0]["close_price"] == 257000


class FakeDailyChartClient:
    """A test double that supplies a per-symbol ka10081 response."""

    def __init__(self, template: dict, failing_codes: set[str] | None = None) -> None:
        self._template = template
        self._failing_codes = failing_codes or set()

    def get_daily_chart(self, stock_code: str, base_date: str) -> dict:
        if stock_code in self._failing_codes:
            raise ValueError(f"simulated failure for {stock_code}")
        response = deepcopy(self._template)
        response["stk_cd"] = stock_code
        return response


def test_batch_ingestion_reuses_single_symbol_flow_and_continues_after_failure(
    ka10081_response: dict, tmp_path: Path
) -> None:
    client = FakeDailyChartClient(ka10081_response, failing_codes={"000660"})
    storage = HistoricalStorage(tmp_path / "data")

    results = ingest_kiwoom_daily_chart_batch(  # type: ignore[arg-type]
        client,
        ["005930", "000660", "035420"],
        "20260831",
        storage=storage,
    )

    assert [result.success for result in results] == [True, False, True]
    assert results[0].ingestion is not None
    assert results[0].ingestion.bar_count == 2
    assert "simulated failure" in (results[1].error or "")
    assert (tmp_path / "data" / "processed" / "historical" / "035420.json").is_file()
