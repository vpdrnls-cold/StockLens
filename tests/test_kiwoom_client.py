"""Tests for the documented Kiwoom REST client endpoints."""

from __future__ import annotations

from typing import Any

import pytest

import src.api.kiwoom_client as kiwoom_client_module
from src.api.kiwoom_client import KiwoomAPIError, KiwoomClient
from src.utils.config import KiwoomSettings


class FakeResponse:
    def __init__(
        self,
        payload: dict[str, Any],
        status_code: int = 200,
        headers: dict[str, str] | None = None,
    ) -> None:
        self._payload = payload
        self.status_code = status_code
        self.ok = 200 <= status_code < 400
        self.headers = headers or {}

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

def test_daily_chart_follows_continuation_across_multiple_pages() -> None:
    """cont-yn/next-key are Kiwoom RESPONSE headers, not body fields. A
    single ka10081 call only returns the most recent page of history;
    this must keep requesting with the previous page's next-key until
    the server reports cont-yn != "Y"."""

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
            # Page 1: server says more history is available.
            FakeResponse(
                {
                    "stk_cd": "005930",
                    "stk_dt_pole_chart_qry": [
                        {"dt": "20260828", "cur_prc": "250000"},
                    ],
                    "return_code": 0,
                },
                headers={"cont-yn": "Y", "next-key": "page-2-key"},
            ),
            # Page 2: server says that was the last page.
            FakeResponse(
                {
                    "stk_cd": "005930",
                    "stk_dt_pole_chart_qry": [
                        {"dt": "20240313", "cur_prc": "230000"},
                    ],
                    "return_code": 0,
                },
                headers={"cont-yn": "N", "next-key": ""},
            ),
        ]
    )
    client = KiwoomClient(_settings(), session=session)  # type: ignore[arg-type]

    response = client.get_daily_chart("005930", "20260828")

    rows = response["stk_dt_pole_chart_qry"]
    assert [row["dt"] for row in rows] == ["20260828", "20240313"]

    # token call + 2 chart pages
    assert len(session.calls) == 3

    first_call_headers = session.calls[1]["headers"]
    assert first_call_headers["cont-yn"] == "N"
    assert first_call_headers["next-key"] == ""

    second_call_headers = session.calls[2]["headers"]
    assert second_call_headers["cont-yn"] == "Y"
    assert second_call_headers["next-key"] == "page-2-key"
    # base_dt/stk_cd/upd_stkpc_tp stay the same across pages.
    assert session.calls[2]["json"] == session.calls[1]["json"]


def test_post_retries_after_rate_limit_then_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    sleeps: list[float] = []
    monkeypatch.setattr(
        kiwoom_client_module.time, "sleep", lambda seconds: sleeps.append(seconds)
    )

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
                    "return_code": 5,
                    "return_msg": (
                        "허용된 요청 개수를 초과하였습니다"
                        "[1700:허용된 API 요청 개수를 초과하였습니다. "
                        "유량=5, API ID=ka10081]"
                    ),
                },
                status_code=429,
            ),
            FakeResponse(
                {
                    "stk_cd": "005930",
                    "stk_dt_pole_chart_qry": [{"dt": "20260828"}],
                    "return_code": 0,
                },
                headers={"cont-yn": "N", "next-key": ""},
            ),
        ]
    )
    client = KiwoomClient(_settings(), session=session)  # type: ignore[arg-type]

    response = client.get_daily_chart("005930", "20260828")

    assert len(response["stk_dt_pole_chart_qry"]) == 1
    # token + rate-limited attempt + successful retry
    assert len(session.calls) == 3
    assert sleeps == [KiwoomClient._RATE_LIMIT_BACKOFF_SECONDS]


def test_post_gives_up_after_max_rate_limit_retries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(kiwoom_client_module.time, "sleep", lambda seconds: None)

    responses = [
        FakeResponse(
            {
                "token": "access-token",
                "token_type": "bearer",
                "expires_dt": "20991231235959",
                "return_code": 0,
            }
        )
    ]
    for _ in range(KiwoomClient._RATE_LIMIT_MAX_RETRIES + 1):
        responses.append(
            FakeResponse(
                {"return_code": 5, "return_msg": "허용된 요청 개수를 초과하였습니다"},
                status_code=429,
            )
        )

    session = FakeSession(responses)
    client = KiwoomClient(_settings(), session=session)  # type: ignore[arg-type]

    with pytest.raises(KiwoomAPIError, match="허용된 요청 개수"):
        client.get_daily_chart("005930", "20260828")


def test_daily_chart_paces_continuation_requests(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sleeps: list[float] = []
    monkeypatch.setattr(
        kiwoom_client_module.time, "sleep", lambda seconds: sleeps.append(seconds)
    )

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
                    "stk_dt_pole_chart_qry": [{"dt": "20260828"}],
                    "return_code": 0,
                },
                headers={"cont-yn": "Y", "next-key": "key-1"},
            ),
            FakeResponse(
                {
                    "stk_cd": "005930",
                    "stk_dt_pole_chart_qry": [{"dt": "20260827"}],
                    "return_code": 0,
                },
                headers={"cont-yn": "N", "next-key": ""},
            ),
        ]
    )
    client = KiwoomClient(_settings(), session=session)  # type: ignore[arg-type]

    client.get_daily_chart("005930", "20260828")

    # No sleep before the first page; one pacing sleep before the second.
    assert sleeps == [KiwoomClient._PAGE_REQUEST_INTERVAL_SECONDS]


def test_daily_chart_stops_after_single_page_when_no_continuation() -> None:
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
                    "stk_dt_pole_chart_qry": [{"dt": "20260828"}],
                    "return_code": 0,
                },
                headers={"cont-yn": "N", "next-key": ""},
            ),
        ]
    )
    client = KiwoomClient(_settings(), session=session)  # type: ignore[arg-type]

    response = client.get_daily_chart("005930", "20260828")

    assert len(response["stk_dt_pole_chart_qry"]) == 1
    # token call + exactly 1 chart page.
    assert len(session.calls) == 2


def test_daily_chart_respects_max_pages_safety_bound(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If the server claimed continuation forever, this must not loop
    forever -- max_pages is a hard cap, not advisory."""

    monkeypatch.setattr(kiwoom_client_module.time, "sleep", lambda seconds: None)

    responses = [
        FakeResponse(
            {
                "token": "access-token",
                "token_type": "bearer",
                "expires_dt": "20991231235959",
                "return_code": 0,
            }
        )
    ]
    for i in range(5):
        responses.append(
            FakeResponse(
                {
                    "stk_cd": "005930",
                    "stk_dt_pole_chart_qry": [{"dt": f"2026010{i}"}],
                    "return_code": 0,
                },
                headers={"cont-yn": "Y", "next-key": f"key-{i}"},
            )
        )

    session = FakeSession(responses)
    client = KiwoomClient(_settings(), session=session)  # type: ignore[arg-type]

    response = client.get_daily_chart("005930", "20260828", max_pages=3)

    assert len(response["stk_dt_pole_chart_qry"]) == 3
    # token call + exactly 3 chart pages, not all 5 available.
    assert len(session.calls) == 4


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