"""OpenDART client (CURRENT_STATUS item 72) -- network mocked."""
from __future__ import annotations

import io
import json
import zipfile

import pytest
import requests

from src.api.dart_client import DartClient, DartClientError

KEY = "secret-key-123"


class _Resp:
    def __init__(self, payload=None, *, status=200, content=b"", text=None):
        self._payload = payload
        self.status_code = status
        self.ok = status < 400
        self.content = content
        self.text = text if text is not None else json.dumps(payload or {})

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


def _client(responses, calls):
    def fake_get(url, params, timeout):
        calls.append((url, dict(params)))
        r = responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return r
    return DartClient(KEY, sleep_seconds=0, http_get=fake_get)


def test_filings_follow_all_pages() -> None:
    calls: list = []
    pages = [
        _Resp({"status": "000", "total_page": 2, "list": [{"rcept_no": "1"}]}),
        _Resp({"status": "000", "total_page": 2, "list": [{"rcept_no": "2"}]}),
    ]
    rows = _client(pages, calls).get_filings("00126380", "20260901", "20261002")
    assert [r["rcept_no"] for r in rows] == ["1", "2"]
    assert [c[1]["page_no"] for c in calls] == [1, 2]
    assert all(c[1]["last_reprt_at"] == "N" and c[1]["crtfc_key"] == KEY for c in calls)


def test_no_data_status_is_an_empty_list() -> None:
    assert _client([_Resp({"status": "013", "message": "조회된 데이타가 없습니다."})], []).get_filings("x", "a", "b") == []


def test_errors_never_contain_the_key() -> None:
    for bad in (
        _Resp({"status": "020", "message": f"limit for {KEY}"}),
        _Resp(None, status=500, text=f"server error {KEY}"),
        requests.ConnectionError(f"failed url ...crtfc_key={KEY}"),
    ):
        with pytest.raises(DartClientError) as err:
            _client([bad], []).get_filings("x", "a", "b")
        assert KEY not in str(err.value)


def test_corp_codes_from_zip() -> None:
    xml = ("<result><list><corp_code>00126380</corp_code><corp_name>삼성전자</corp_name>"
           "<stock_code>005930</stock_code><modify_date>20260101</modify_date></list>"
           "<list><corp_code>99999999</corp_code><corp_name>비상장</corp_name><stock_code> </stock_code></list></result>")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("CORPCODE.xml", xml)
    mapping = _client([_Resp(None, content=buf.getvalue())], []).get_corp_codes()
    assert mapping == {"005930": {"corp_code": "00126380", "corp_name": "삼성전자", "modify_date": "20260101"}}


def test_empty_key_rejected() -> None:
    with pytest.raises(DartClientError):
        DartClient("")
