"""Token-issuance failure stops a batch step instead of retrying stock by stock.

2026-10-08 log: on a network whose IP was not registered (8050), every stock
re-issued the token, failed, and after 12 stocks the token endpoint was rate
limited (1700). These tests pin the fix: ``KiwoomTokenError`` is raised by
``authenticate()`` and re-raised by the batch loops and nightly scripts.
"""

from __future__ import annotations

import sys
from typing import Any

import pytest

import src.api.kiwoom_client as kiwoom_client_module
from scripts import ingest_kiwoom_daily_chart_batch as daily_script
from scripts import ingest_kiwoom_flow_index as flow_script
from scripts import ingest_kiwoom_minute_chart_universe as minute_script
from src.api.kiwoom_client import (
    KiwoomAPIError,
    KiwoomClient,
    KiwoomTokenError,
)
from src.data.ingest import (
    ingest_kiwoom_daily_chart_batch,
    ingest_kiwoom_investor_flow_batch,
)
from src.utils.config import KiwoomSettings

IP_MSG = (
    "인증에 실패했습니다[8050:IP가 등록되지 않았습니다. "
    "키움 REST API 홈페이지 > API 사용신청 화면에서 IP를 등록해주세요.]"
)


class FakeResponse:
    def __init__(self, payload: dict[str, Any], status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code
        self.ok = 200 <= status_code < 400
        self.headers: dict[str, str] = {}

    def json(self) -> dict[str, Any]:
        return self._payload


class FakeSession:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self.responses = responses
        self.calls: list[str] = []

    def post(self, url: str, **kwargs: Any) -> FakeResponse:
        self.calls.append(url)
        return self.responses.pop(0)


def _client(responses: list[FakeResponse]) -> tuple[KiwoomClient, FakeSession]:
    session = FakeSession(responses)
    settings = KiwoomSettings(app_key="app-key-SECRET", secret_key="secret-key-SECRET")
    return KiwoomClient(settings, session=session), session  # type: ignore[arg-type]


def test_ip_not_registered_raises_token_error_without_retry() -> None:
    client, session = _client([FakeResponse({"return_code": 3, "return_msg": IP_MSG})])

    with pytest.raises(KiwoomTokenError) as caught:
        client.authenticate()

    assert isinstance(caught.value, KiwoomAPIError)  # existing except clauses still match
    assert caught.value.return_code == 3
    assert len(session.calls) == 1  # not a rate limit -> no retry
    line = caught.value.stop_line()
    assert "IP" in line and "8050" in line
    assert "SECRET" not in line


def test_token_rate_limit_after_retries_is_token_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(kiwoom_client_module.time, "sleep", lambda seconds: None)
    responses = [
        FakeResponse({"return_code": 5, "return_msg": "허용된 요청 개수를 초과하였습니다"}, 429)
        for _ in range(KiwoomClient._RATE_LIMIT_MAX_RETRIES + 1)
    ]
    client, session = _client(responses)

    with pytest.raises(KiwoomTokenError) as caught:
        client.authenticate()

    assert caught.value.status_code == 429
    assert "IP" not in caught.value.stop_line().split(":")[0]  # no 8050 hint
    assert len(session.calls) == KiwoomClient._RATE_LIMIT_MAX_RETRIES + 1


def test_data_request_error_after_valid_token_is_not_token_error() -> None:
    token = FakeResponse(
        {"token": "t", "token_type": "bearer", "expires_dt": "20991231235959", "return_code": 0}
    )
    client, _ = _client([token, FakeResponse({"return_code": 2, "return_msg": "bad stock"})])

    with pytest.raises(KiwoomAPIError) as caught:
        client.get_daily_chart("005930", "20261008")

    assert not isinstance(caught.value, KiwoomTokenError)


class _TokenFailClient:
    """Fails token issuance on every call and counts how often it was asked."""

    def __init__(self) -> None:
        self.calls = 0

    def _fail(self, *args: Any, **kwargs: Any) -> Any:
        self.calls += 1
        raise KiwoomTokenError(IP_MSG, return_code=3)

    get_daily_chart = _fail
    get_investor_flow_history = _fail
    get_index_daily_history = _fail
    get_minute_chart_history = _fail


class _PerStockFailClient:
    def __init__(self) -> None:
        self.calls = 0

    def get_investor_flow_history(self, *args: Any, **kwargs: Any) -> Any:
        self.calls += 1
        raise KiwoomAPIError("per-stock problem", return_code=2)


def test_flow_batch_stops_on_token_error_but_continues_on_per_stock_error(tmp_path) -> None:
    from src.data.storage import HistoricalStorage

    storage = HistoricalStorage(tmp_path)
    codes = ["005930", "000660", "005380"]

    token_client = _TokenFailClient()
    with pytest.raises(KiwoomTokenError):
        ingest_kiwoom_investor_flow_batch(token_client, codes, "20261008", storage=storage)  # type: ignore[arg-type]
    assert token_client.calls == 1

    other_client = _PerStockFailClient()
    results = ingest_kiwoom_investor_flow_batch(other_client, codes, "20261008", storage=storage)  # type: ignore[arg-type]
    assert other_client.calls == 3 and not any(r.success for r in results)


def test_daily_batch_stops_on_token_error(tmp_path) -> None:
    from src.data.storage import HistoricalStorage

    client = _TokenFailClient()
    with pytest.raises(KiwoomTokenError):
        ingest_kiwoom_daily_chart_batch(
            client, ["005930", "000660"], "20261008", storage=HistoricalStorage(tmp_path)  # type: ignore[arg-type]
        )
    assert client.calls == 1


@pytest.mark.parametrize(
    ("module", "argv"),
    [
        (flow_script, ["--lookback-days", "10", "005930", "000660"]),
        (daily_script, ["005930", "000660"]),
        (minute_script, ["--only", "005930", "000660", "--force", "--no-skip-existing", "--sleep", "0"]),
    ],
)
def test_nightly_scripts_exit_1_with_one_stop_line(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], module: Any, argv: list[str]
) -> None:
    client = _TokenFailClient()
    monkeypatch.setattr(module.KiwoomClient, "from_env", classmethod(lambda cls: client))
    if module is minute_script:
        monkeypatch.setattr(module, "ingest_kiwoom_minute_chart_raw", lambda c, *a, **k: c._fail())
    monkeypatch.setattr(sys, "argv", [module.__name__, *argv])

    assert module.main() == 1
    assert client.calls == 1  # first request only, then the step stops
    err = capsys.readouterr().err
    assert err.count("토큰 발급 실패") == 1
