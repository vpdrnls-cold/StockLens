"""NAVER API HUB news client and storage (CURRENT_STATUS item 75) -- network mocked, tmp_path only."""
from __future__ import annotations

import pytest
import requests

from src.api.naver_news_client import HUB_NEWS_URL, NaverNewsClient, NaverNewsClientError
from src.data.news import NewsStorage, clean_title, normalize_item, outlet, parse_pub_date

CID, SECRET = "cid0000001", "s" * 40


class _Resp:
    def __init__(self, payload=None, status=200, text="x"):
        self._p, self.status_code, self.ok, self.text = payload, status, status < 400, text

    def json(self):
        if self._p is None:
            raise ValueError
        return self._p


def _item(n: int, minute: int = 0) -> dict:
    return {"title": f"<b>삼성전자</b> 기사 {n} &amp; 소식", "originallink": f"https://www.news.com/a/{n}",
            "link": f"https://n.news.naver.com/mnews/article/001/{n}", "description": "...",
            "pubDate": f"Tue, 06 Oct 2026 10:{minute:02d}:00 +0900"}


def _client(responses, calls):
    def get(url, params, headers, timeout):
        calls.append((url, dict(params), dict(headers)))
        r = responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return r
    return NaverNewsClient(CID, SECRET, sleep_seconds=0, http_get=get)


def test_hub_address_headers_and_pages() -> None:
    calls: list = []
    pages = [_Resp({"total": 250, "items": [_item(i) for i in range(100)]}),
             _Resp({"total": 250, "items": [_item(i) for i in range(100, 200)]}),
             _Resp({"total": 250, "items": [_item(i) for i in range(200, 250)]})]
    items = _client(pages, calls).latest("삼성전자", pages=3)
    assert len(items) == 250 and len(calls) == 3
    url, params, headers = calls[0]
    assert url == HUB_NEWS_URL == "https://naverapihub.apigw.ntruss.com/search/v1/news"
    assert headers == {"X-NCP-APIGW-API-KEY-ID": CID, "X-NCP-APIGW-API-KEY": SECRET}
    assert params == {"query": "삼성전자", "display": 100, "start": 1, "sort": "date"}
    assert [c[1]["start"] for c in calls] == [1, 101, 201]


def test_stops_when_results_run_out() -> None:
    calls: list = []
    items = _client([_Resp({"total": 30, "items": [_item(i) for i in range(30)]})], calls).latest("x", pages=3)
    assert len(items) == 30 and len(calls) == 1


def test_errors_hide_both_keys() -> None:
    for bad in (_Resp(None, status=401, text=f"auth failed {CID} {SECRET}"),
                requests.ConnectionError(f"boom {SECRET}")):
        with pytest.raises(NaverNewsClientError) as err:
            _client([bad], []).latest("x", pages=1)
        assert CID not in str(err.value) and SECRET not in str(err.value)
    with pytest.raises(NaverNewsClientError):
        NaverNewsClient("", SECRET)


def test_cleaning_and_parsing() -> None:
    assert clean_title("<b>삼성전자</b> 실적 &quot;호조&quot; &amp; 전망") == '삼성전자 실적 "호조" & 전망'
    assert parse_pub_date("Tue, 06 Oct 2026 10:20:00 +0900") == "2026-10-06T10:20:00+09:00"
    assert parse_pub_date("not a date") is None
    assert outlet("https://www.hankyung.com/article/1") == "hankyung.com"
    art = normalize_item(_item(7, 5))
    assert art["link"].endswith("/7") and art["outlet"] == "news.com" and art["title"] == "삼성전자 기사 7 & 소식"
    assert "description" not in art


def test_merge_by_link_keeps_old_articles(tmp_path) -> None:
    s = NewsStorage(tmp_path)
    assert s.merge("005930", [_item(1, 1), _item(2, 2)], retrieved_at="t1") == 2
    assert s.merge("005930", [_item(2, 2), _item(3, 3)], retrieved_at="t2") == 1
    assert [a["link"][-1] for a in s.load("005930")] == ["1", "2", "3"]
    assert s.collected_at("005930") == "t2"
    assert s.merge("005930", [{"title": "x", "link": "", "pubDate": "bad"}], retrieved_at="t3") == 0
    assert s.save_raw("005930", []).exists()
