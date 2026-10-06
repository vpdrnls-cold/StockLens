"""ECOS client and macro storage (CURRENT_STATUS item 74) -- network mocked, tmp_path only."""
from __future__ import annotations

import pytest
import requests

from src.api.ecos_client import EcosClient, EcosClientError
from src.data.macro import ECOS_SERIES, MacroStorage

KEY = "ecos-secret-777"


class _Resp:
    def __init__(self, payload=None, status=200, text="x"):
        self._p, self.status_code, self.ok, self.text = payload, status, status < 400, text

    def json(self):
        if self._p is None:
            raise ValueError
        return self._p


def _client(responses, urls, page=2):
    def get(url, timeout):
        urls.append(url)
        r = responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return r
    return EcosClient(KEY, sleep_seconds=0, page_size=page, http_get=get)


def _rows(*pairs):
    return [{"TIME": t, "DATA_VALUE": v} for t, v in pairs]


def test_pages_until_total() -> None:
    urls: list = []
    pages = [
        _Resp({"StatisticSearch": {"list_total_count": 3, "row": _rows(("20261001", "2.50"), ("20261002", "2.55"))}}),
        _Resp({"StatisticSearch": {"list_total_count": 3, "row": _rows(("20261005", "2.60"))}}),
    ]
    rows = _client(pages, urls).get_daily_series("817Y002", "010200000", "20261001", "20261005")
    assert [r["TIME"] for r in rows] == ["20261001", "20261002", "20261005"]
    assert "/json/kr/1/2/817Y002/D/20261001/20261005/010200000" in urls[0]
    assert "/json/kr/3/4/" in urls[1]


def test_no_data_is_empty_and_errors_hide_the_key() -> None:
    no_data = _Resp({"RESULT": {"CODE": "INFO-200", "MESSAGE": "해당하는 데이터가 없습니다."}})
    assert _client([no_data], []).get_daily_series("817Y002", "x", "a", "b") == []
    for bad in (_Resp({"RESULT": {"CODE": "ERROR-100", "MESSAGE": f"key {KEY}"}}),
                _Resp(None, status=500, text=f"oops {KEY}"),
                requests.ConnectionError(f"https://ecos.bok.or.kr/api/StatisticSearch/{KEY}/json")):
        with pytest.raises(EcosClientError) as err:
            _client([bad], []).get_daily_series("817Y002", "x", "a", "b")
        assert KEY not in str(err.value)


def test_storage_merge_by_date_skips_blanks(tmp_path) -> None:
    s = MacroStorage(tmp_path)
    assert s.merge("817Y002", "010200000", _rows(("20261001", "2.50"), ("20261002", "")), retrieved_at="t1") == 1
    assert s.merge("817Y002", "010200000", _rows(("20261001", "2.51"), ("20261005", "2.60")), retrieved_at="t2") == 1
    assert s.load("817Y002", "010200000") == [{"date": "2026-10-01", "value": 2.51}, {"date": "2026-10-05", "value": 2.6}]
    assert s.save_raw("817Y002", "010200000", []).exists()


def test_series_codes_are_the_item_59_ones() -> None:
    assert ECOS_SERIES["ktb3y"] == {"stat": "817Y002", "item": "010200000", "label": "국고채 3년", "unit": "%"}
    assert ECOS_SERIES["usdkrw"]["stat"] == "731Y001" and ECOS_SERIES["usdkrw"]["item"] == "0000001"
