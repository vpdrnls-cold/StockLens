"""Tests for the documented Kiwoom REST client endpoints."""

from __future__ import annotations

from typing import Any

import pytest

from src.api.kiwoom_client import KiwoomAPIError, KiwoomClient
from src.utils.config import KiwoomSettings


class FakeResponse:
    def __init__(self, payload: dict[str, Any], status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code
        self.ok = 200 <= status_code < 400

    def json(self) -> dict[str, Any]:
        return self._payload


class FakeSession:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self.responses = responses
        self.calls: list[dict[str, Any]] = []

    def post(self, url: str, **kwargs: Any) -> FakeResponse:
        self.calls.append({"url": url, **kwargs})
        return self.responses.pop(0)


def _settings() -> KiwoomSettings:
    return KiwoomSettings(app_key="app-key", secret_key="secret-key")


def test_authentication_is_reused_for_current_quote() -> None:
    session = FakeSession(
        [
            FakeResponse(
                {
                    "token": "access-token",
                    "token_type": "bearer",
                    "expires_dt": "20991231235959",
                    "return_code": 0,
                }
            ),
            FakeResponse(
                {
                    "stk_cd": "005930",
                    "stk_nm": "삼성전자",
                    "cur_prc": "+70000",
                    "pred_pre": "-500",
                    "flu_rt": "-0.71",
                    "trde_qty": "123456",
                    "return_code": 0,
                }
            ),
        ]
    )
    client = KiwoomClient(_settings(), session=session)  # type: ignore[arg-type]

    quote = client.get_current_quote("005930")

    assert quote.current_price == 70000
    assert quote.change_from_previous_day == -500
    assert quote.change_rate == -0.71
    assert quote.volume == 123456
    assert len(session.calls) == 2
    assert session.calls[0]["url"].endswith("/oauth2/token")
    assert session.calls[1]["url"].endswith("/api/dostk/stkinfo")
    assert session.calls[1]["json"] == {"stk_cd": "005930"}
    assert session.calls[1]["headers"]["api-id"] == "ka10001"
    assert session.calls[1]["headers"]["authorization"] == "Bearer access-token"


def test_api_error_response_raises_descriptive_exception() -> None:
    session = FakeSession(
        [FakeResponse({"return_code": -1, "return_msg": "invalid credentials"})]
    )
    client = KiwoomClient(_settings(), session=session)  # type: ignore[arg-type]

    with pytest.raises(KiwoomAPIError, match="invalid credentials"):
        client.authenticate()


def test_diagnostic_context_masks_app_key_value() -> None:
    client = KiwoomClient(_settings(), session=FakeSession([]))  # type: ignore[arg-type]

    diagnostics = client.diagnostic_context()

    assert diagnostics["environment"] == "production"
    assert diagnostics["app_key_fingerprint"].startswith("sha256:")
    assert "app-key" not in diagnostics["app_key_fingerprint"]


def test_daily_chart_uses_documented_ka10081_request_fields() -> None:
    session = FakeSession(
        [
            FakeResponse(
                {
                    "token": "access-token",
                    "token_type": "bearer",
                    "expires_dt": "20991231235959",
                    "return_code": 0,
                }
            ),
            FakeResponse(
                {
                    "stk_cd": "005930",
                    "stk_dt_pole_chart_qry": [
                        {
                            "dt": "20260828",
                            "cur_prc": "250000",
                            "trde_qty": "1000",
                        }
                    ],
                    "return_code": 0,
                }
            ),
        ]
    )
    client = KiwoomClient(_settings(), session=session)  # type: ignore[arg-type]

    response = client.get_daily_chart("005930", "20260828")

    assert response["stk_dt_pole_chart_qry"][0]["dt"] == "20260828"
    assert session.calls[1]["url"].endswith("/api/dostk/chart")
    assert session.calls[1]["headers"]["api-id"] == "ka10081"
    assert session.calls[1]["json"] == {
        "stk_cd": "005930",
        "base_dt": "20260828",
        "upd_stkpc_tp": "1",
    }

def test_index_daily_chart_uses_documented_ka20006_request_fields() -> None:
    session = FakeSession(
        [
            FakeResponse(
                {
                    "token": "access-token",
                    "token_type": "bearer",
                    "expires_dt": "20991231235959",
                    "return_code": 0,
                }
            ),
            FakeResponse(
                {
                    "inds_cd": "001",
                    "inds_dt_pole_qry": [
                        {
                            "cur_prc": "252127",
                            "trde_qty": "393564",
                            "dt": "20260831",
                            "open_pric": "251064",
                            "high_pric": "252733",
                            "low_pric": "249918",
                            "trde_prica": "10582466",
                        }
                    ],
                    "return_code": 0,
                }
            ),
        ]
    )

    client = KiwoomClient(
        _settings(),
        session=session,
    )  # type: ignore[arg-type]

    response = client.get_index_daily_chart(
        "001",
        "20260831",
    )

    assert response["inds_cd"] == "001"
    assert response["inds_dt_pole_qry"][0]["dt"] == "20260831"

    assert session.calls[1]["url"].endswith("/api/dostk/chart")
    assert session.calls[1]["headers"]["api-id"] == "ka20006"
    assert session.calls[1]["headers"]["authorization"] == "Bearer access-token"

    assert session.calls[1]["json"] == {
        "inds_cd": "001",
        "base_dt": "20260831",
    }