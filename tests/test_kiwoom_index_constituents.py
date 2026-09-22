from __future__ import annotations

import pytest

import src.api.kiwoom_client as kiwoom_client_module
from src.api.kiwoom_client import KiwoomClient
from tests.test_kiwoom_client import FakeResponse, FakeSession, _settings

TOKEN = FakeResponse(
    {
        "token": "access-token",
        "token_type": "bearer",
        "expires_dt": "20991231235959",
        "return_code": 0,
    }
)


def test_get_index_constituents_follows_continuation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(kiwoom_client_module.time, "sleep", lambda seconds: None)
    session = FakeSession(
        [
            TOKEN,
            FakeResponse(
                {"inds_stkpc": [{"stk_cd": "005930"}, {"stk_cd": "000660"}], "return_code": 0},
                headers={"cont-yn": "Y", "next-key": "k2"},
            ),
            FakeResponse(
                {"inds_stkpc": [{"stk_cd": "005380"}], "return_code": 0},
                headers={"cont-yn": "N", "next-key": ""},
            ),
        ]
    )
    client = KiwoomClient(_settings(), session=session)  # type: ignore[arg-type]

    rows = client.get_index_constituents()

    assert [row["stk_cd"] for row in rows] == ["005930", "000660", "005380"]
    first, second = session.calls[1], session.calls[2]
    assert first["url"].endswith("/api/dostk/sect")
    assert first["json"] == {"mrkt_tp": "2", "inds_cd": "201", "stex_tp": "1"}
    assert first["headers"]["api-id"] == "ka20002"
    assert first["headers"]["cont-yn"] == "N"
    assert second["headers"]["cont-yn"] == "Y"
    assert second["headers"]["next-key"] == "k2"
