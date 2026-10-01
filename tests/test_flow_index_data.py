"""Tests for index (ka20006) and investor-flow (ka10059) normalization, storage, and ingestion."""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from src.api.kiwoom_client import KiwoomAPIError, KiwoomClient
from src.data.ingest import ingest_kiwoom_investor_flow_batch
from src.data.normalization import (
    KST,
    HistoricalDataValidationError,
    is_complete_for_retrieval,
    normalize_ka10059_response,
    normalize_ka20006_response,
)
from src.data.storage import HistoricalStorage
from src.utils.config import KiwoomSettings

AFTER_CLOSE = datetime(2026, 9, 30, 20, 37, tzinfo=KST)
DURING_SESSION = datetime(2026, 9, 30, 13, 18, tzinfo=KST)


def _index_row(dt: str, close: str = "683804", **overrides: str) -> dict[str, str]:
    row = {
        "cur_prc": close,
        "trde_qty": "285982",
        "dt": dt,
        "open_pric": "681000",
        "high_pric": "696564",
        "low_pric": "681000",
        "trde_prica": "20477180",
    }
    row.update(overrides)
    return row


def _flow_row(dt: str, **overrides: str) -> dict[str, str]:
    # A real balanced day (005930, 2026-09-30).
    row = {
        "dt": dt,
        "cur_prc": "-269500",
        "pre_sig": "5",
        "pred_pre": "-3000",
        "flu_rt": "-110",
        "acc_trde_qty": "16477580",
        "acc_trde_prica": "4456294",
        "ind_invsr": "687635",
        "frgnr_invsr": "-865578",
        "orgn": "-382209",
        "fnnc_invt": "-336241",
        "insrnc": "-8254",
        "invtrt": "64403",
        "etc_fnnc": "103",
        "bank": "-1",
        "penfnd_etc": "-18498",
        "samo_fund": "-83721",
        "natn": "0",
        "etc_corp": "556618",
        "natfor": "3534",
    }
    row.update(overrides)
    return row


# ---------------------------------------------------------------- completeness


def test_same_day_row_is_incomplete_before_cutoff_and_complete_after() -> None:
    day = date(2026, 9, 30)
    assert is_complete_for_retrieval(day, DURING_SESSION) is False
    assert is_complete_for_retrieval(day, AFTER_CLOSE) is True
    assert is_complete_for_retrieval(date(2026, 9, 29), DURING_SESSION) is True


def test_completeness_uses_kst_even_for_utc_timestamps() -> None:
    # 2026-09-30 04:18 UTC == 13:18 KST, still during the session.
    utc = DURING_SESSION.astimezone(timezone.utc)
    assert is_complete_for_retrieval(date(2026, 9, 30), utc) is False


def test_row_dated_after_retrieval_is_rejected() -> None:
    with pytest.raises(HistoricalDataValidationError, match="after its retrieval"):
        is_complete_for_retrieval(date(2026, 10, 1), AFTER_CLOSE)


def test_naive_retrieval_time_is_rejected() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        is_complete_for_retrieval(date(2026, 9, 30), datetime(2026, 9, 30, 20, 0))


# ---------------------------------------------------------------- index


def test_index_prices_restore_the_100x_encoding_and_sort_by_date() -> None:
    bars = normalize_ka20006_response(
        {
            "inds_cd": "001",
            "inds_dt_pole_qry": [_index_row("20260930"), _index_row("20260929")],
        },
        retrieved_at=AFTER_CLOSE,
    )

    assert [bar.trade_date for bar in bars] == [date(2026, 9, 29), date(2026, 9, 30)]
    assert bars[-1].close_price == Decimal("6838.04")
    assert bars[-1].high_price == Decimal("6965.64")
    assert bars[-1].volume_thousand_shares == 285982
    assert bars[-1].trade_value_million_krw == 20477180
    assert all(bar.is_complete for bar in bars)


def test_index_in_progress_bar_is_marked_incomplete() -> None:
    bars = normalize_ka20006_response(
        {
            "inds_cd": "001",
            "inds_dt_pole_qry": [_index_row("20260930"), _index_row("20260929")],
        },
        retrieved_at=DURING_SESSION,
    )
    assert {bar.trade_date: bar.is_complete for bar in bars} == {
        date(2026, 9, 29): True,
        date(2026, 9, 30): False,
    }


def test_index_legacy_inconsistent_bar_is_dropped_but_modern_one_raises() -> None:
    legacy = _index_row("19890601", high_pric="600000")  # high below close
    bars = normalize_ka20006_response(
        {"inds_cd": "001", "inds_dt_pole_qry": [_index_row("20260930"), legacy]},
        retrieved_at=AFTER_CLOSE,
    )
    assert [bar.trade_date for bar in bars] == [date(2026, 9, 30)]

    with pytest.raises(HistoricalDataValidationError):
        normalize_ka20006_response(
            {
                "inds_cd": "001",
                "inds_dt_pole_qry": [_index_row("20260930", high_pric="600000")],
            },
            retrieved_at=AFTER_CLOSE,
        )


@pytest.mark.parametrize(
    "rows",
    [
        [_index_row("20260930"), _index_row("20260930")],
        [_index_row("20260930", cur_prc="")],
        [_index_row("20260930", trde_qty="abc")],
    ],
)
def test_index_invalid_rows_raise(rows: list[dict[str, str]]) -> None:
    with pytest.raises(HistoricalDataValidationError):
        normalize_ka20006_response(
            {"inds_cd": "001", "inds_dt_pole_qry": rows}, retrieved_at=AFTER_CLOSE
        )


# ---------------------------------------------------------------- investor flow


def test_flow_fields_map_to_internal_names_and_balance() -> None:
    (day,) = normalize_ka10059_response(
        {"stk_invsr_orgn": [_flow_row("20260930")]},
        stock_code="005930",
        retrieved_at=AFTER_CLOSE,
    )

    assert day.stock_code == "005930"
    assert day.individual == 687635
    assert day.foreign == -865578
    assert day.pension_fund == -18498
    assert day.volume == 16477580
    assert day.trade_value_million_krw == 4456294
    assert day.institution_total == day.institution_reported == -382209
    assert day.balance_residual == 0
    assert day.is_complete is True


def test_institution_total_is_consistent_when_reported_total_excludes_government() -> None:
    # Pre-mid-2012 shape: reported institution total omits the government row.
    row = _flow_row("20120713", natn="8302", etc_corp=str(556618 - 8302))
    (day,) = normalize_ka10059_response(
        {"stk_invsr_orgn": [row]}, stock_code="005930", retrieved_at=AFTER_CLOSE
    )
    assert day.institution_reported == -382209
    assert day.institution_total == -382209 + 8302
    assert day.balance_residual == 0
    assert day.is_complete is True


def test_unbalanced_provisional_flow_is_kept_but_marked_incomplete() -> None:
    provisional = _flow_row("20260930", ind_invsr="0")
    days = normalize_ka10059_response(
        {"stk_invsr_orgn": [provisional, _flow_row("20260929")]},
        stock_code="005930",
        retrieved_at=AFTER_CLOSE,
    )
    assert {d.trade_date: d.is_complete for d in days} == {
        date(2026, 9, 29): True,
        date(2026, 9, 30): False,
    }


def test_rounding_residual_within_tolerance_is_still_complete() -> None:
    (day,) = normalize_ka10059_response(
        {"stk_invsr_orgn": [_flow_row("20260930", natfor="3538")]},
        stock_code="005930",
        retrieved_at=AFTER_CLOSE,
    )
    assert day.balance_residual == 4
    assert day.is_complete is True


def test_balanced_same_day_flow_before_cutoff_is_still_incomplete() -> None:
    (day,) = normalize_ka10059_response(
        {"stk_invsr_orgn": [_flow_row("20260930")]},
        stock_code="005930",
        retrieved_at=DURING_SESSION,
    )
    assert day.balance_residual == 0
    assert day.is_complete is False


@pytest.mark.parametrize(
    "rows",
    [
        [_flow_row("20260930"), _flow_row("20260930")],
        [_flow_row("20260930", frgnr_invsr="")],
        [_flow_row("20260930", acc_trde_qty="-1")],
    ],
)
def test_flow_invalid_rows_raise(rows: list[dict[str, str]]) -> None:
    with pytest.raises(HistoricalDataValidationError):
        normalize_ka10059_response(
            {"stk_invsr_orgn": rows}, stock_code="005930", retrieved_at=AFTER_CLOSE
        )


# ---------------------------------------------------------------- storage


def test_index_storage_round_trip_excludes_incomplete_by_default(tmp_path: Path) -> None:
    storage = HistoricalStorage(tmp_path)
    bars = normalize_ka20006_response(
        {
            "inds_cd": "001",
            "inds_dt_pole_qry": [_index_row("20260930"), _index_row("20260929")],
        },
        retrieved_at=DURING_SESSION,
    )
    storage.save_index_bars("001", bars)

    assert [b.trade_date for b in storage.load_index_bars("001")] == [date(2026, 9, 29)]
    loaded = storage.load_index_bars("001", include_incomplete=True)
    assert loaded == bars


def test_flow_storage_complete_value_replaces_provisional_and_not_vice_versa(
    tmp_path: Path,
) -> None:
    storage = HistoricalStorage(tmp_path)
    provisional = normalize_ka10059_response(
        {"stk_invsr_orgn": [_flow_row("20260930", ind_invsr="0")]},
        stock_code="005930",
        retrieved_at=DURING_SESSION,
    )
    final = normalize_ka10059_response(
        {"stk_invsr_orgn": [_flow_row("20260930")]},
        stock_code="005930",
        retrieved_at=AFTER_CLOSE,
    )

    storage.save_investor_flows("005930", provisional)
    assert storage.load_investor_flows("005930") == []
    storage.save_investor_flows("005930", final)
    assert storage.load_investor_flows("005930") == final
    # A later provisional re-fetch must not erase the final value.
    storage.save_investor_flows("005930", provisional)
    assert storage.load_investor_flows("005930") == final


def test_raw_responses_are_preserved_per_api_and_code(tmp_path: Path) -> None:
    storage = HistoricalStorage(tmp_path)
    path = storage.save_raw_kiwoom(
        "ka10059", "005930", {"stk_invsr_orgn": []}, retrieved_at=AFTER_CLOSE
    )
    assert path.parent == tmp_path / "raw" / "kiwoom" / "ka10059" / "005930"
    assert path.name == "20260930T113700000000Z.json"


# ---------------------------------------------------------------- client paging + ingestion


class _FakeResponse:
    def __init__(self, payload: dict[str, Any], headers: dict[str, str] | None = None) -> None:
        self._payload = payload
        self.status_code = 200
        self.ok = True
        self.headers = headers or {}

    def json(self) -> dict[str, Any]:
        return self._payload


class _FakeSession:
    def __init__(self, responses: list[_FakeResponse]) -> None:
        self.responses = responses
        self.calls: list[dict[str, Any]] = []

    def post(self, url: str, **kwargs: Any) -> _FakeResponse:
        self.calls.append({"url": url, **kwargs})
        return self.responses.pop(0)


def _token() -> _FakeResponse:
    return _FakeResponse(
        {"token": "t", "token_type": "bearer", "expires_dt": "20991231235959", "return_code": 0}
    )


def _client(session: _FakeSession) -> KiwoomClient:
    client = KiwoomClient(
        KiwoomSettings(app_key="app-key", secret_key="secret-key"), session=session  # type: ignore[arg-type]
    )
    client._PAGE_REQUEST_INTERVAL_SECONDS = 0  # type: ignore[misc]
    return client


def test_flow_history_follows_continuation_and_stops_at_stop_date() -> None:
    page = lambda dates, key: _FakeResponse(  # noqa: E731
        {"stk_invsr_orgn": [{"dt": d} for d in dates], "return_code": 0},
        headers={"cont-yn": "Y", "next-key": key},
    )
    session = _FakeSession(
        [
            _token(),
            page(["20260930", "20260929"], "k2"),
            page(["20260926", "20260925"], "k3"),
            page(["20260924"], "k4"),  # must not be requested
        ]
    )

    response = _client(session).get_investor_flow_history(
        "005930", "20260930", stop_date="20260925"
    )

    assert [row["dt"] for row in response["stk_invsr_orgn"]] == [
        "20260930",
        "20260929",
        "20260926",
        "20260925",
    ]
    assert len(session.calls) == 3
    assert session.calls[1]["headers"]["api-id"] == "ka10059"
    assert session.calls[2]["headers"]["next-key"] == "k2"


def test_index_history_stops_when_continuation_ends() -> None:
    session = _FakeSession(
        [
            _token(),
            _FakeResponse(
                {"inds_dt_pole_qry": [{"dt": "20260930"}], "return_code": 0},
                headers={"cont-yn": "Y", "next-key": "k2"},
            ),
            _FakeResponse(
                {"inds_dt_pole_qry": [{"dt": "20260929"}], "return_code": 0},
                headers={"cont-yn": "N", "next-key": ""},
            ),
        ]
    )
    response = _client(session).get_index_daily_history("001", "20260930")
    assert response["inds_cd"] == "001"
    assert len(response["inds_dt_pole_qry"]) == 2
    assert len(session.calls) == 3


def test_flow_batch_continues_after_one_stock_fails(tmp_path: Path) -> None:
    class _Client:
        def get_investor_flow_history(self, stock_code: str, date: str, *, stop_date: Any) -> Any:
            if stock_code == "000660":
                raise KiwoomAPIError("boom", return_code=1)
            return {"stk_cd": stock_code, "stk_invsr_orgn": [_flow_row("20260929")]}

    results = ingest_kiwoom_investor_flow_batch(
        _Client(),  # type: ignore[arg-type]
        ["000660", "005930"],
        "20260930",
        storage=HistoricalStorage(tmp_path),
    )

    assert [r.success for r in results] == [False, True]
    assert results[1].row_count == 1
    assert len(HistoricalStorage(tmp_path).load_investor_flows("005930")) == 1


def test_flow_batch_reports_progress_per_stock(tmp_path: Path) -> None:
    class _Client:
        def get_investor_flow_history(self, stock_code: str, date: str, *, stop_date: Any) -> Any:
            if stock_code == "000660":
                raise KiwoomAPIError("boom", return_code=1)
            return {"stk_cd": stock_code, "stk_invsr_orgn": [_flow_row("20260929")]}

    seen: list[tuple[int, int, str, bool]] = []
    results = ingest_kiwoom_investor_flow_batch(
        _Client(),  # type: ignore[arg-type]
        ["000660", "005930"],
        "20260930",
        storage=HistoricalStorage(tmp_path),
        on_result=lambda done, total, r: seen.append((done, total, r.code, r.success)),
    )

    assert seen == [(1, 2, "000660", False), (2, 2, "005930", True)]
    assert [r.code for r in results] == ["000660", "005930"]


_ZERO_FLOWS = {
    k: "0"
    for k in (
        "ind_invsr", "frgnr_invsr", "orgn", "fnnc_invt", "insrnc", "invtrt", "etc_fnnc",
        "bank", "penfnd_etc", "samo_fund", "natn", "etc_corp", "natfor",
    )
}


def test_all_zero_flows_on_a_traded_day_are_unreported() -> None:
    # ka10059 pads days without a breakdown (e.g. before ~2006) with zeros.
    days = normalize_ka10059_response(
        {
            "stk_invsr_orgn": [
                _flow_row("20260929"),
                _flow_row("20260928", **_ZERO_FLOWS),  # traded, no breakdown
                _flow_row("20260925", acc_trde_qty="0", acc_trde_prica="0", **_ZERO_FLOWS),  # halt
            ]
        },
        stock_code="005930",
        retrieved_at=AFTER_CLOSE,
    )

    by_day = {d.trade_date: d for d in days}
    assert by_day[date(2026, 9, 29)].flow_reported
    assert not by_day[date(2026, 9, 28)].flow_reported
    assert by_day[date(2026, 9, 28)].is_complete  # balances trivially -- why the flag exists
    assert by_day[date(2026, 9, 25)].flow_reported  # halt: genuine zero


def test_loader_excludes_unreported_flows_by_default(tmp_path: Path) -> None:
    days = normalize_ka10059_response(
        {"stk_invsr_orgn": [_flow_row("20260929"), _flow_row("20260928", **_ZERO_FLOWS)]},
        stock_code="005930",
        retrieved_at=AFTER_CLOSE,
    )
    storage = HistoricalStorage(tmp_path)
    storage.save_investor_flows("005930", days)

    assert [d.trade_date for d in storage.load_investor_flows("005930")] == [date(2026, 9, 29)]
    assert len(storage.load_investor_flows("005930", include_unreported=True)) == 2
