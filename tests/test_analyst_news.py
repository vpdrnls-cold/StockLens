"""News card (CURRENT_STATUS items 75/76) -- synthetic articles, tmp_path only."""
from __future__ import annotations

from datetime import date
import json

from src.analysts import news as nw

T = date(2026, 10, 6)


def _a(ts: str, title: str, n: int, outlet: str = "news.com") -> dict:
    return {"published": ts, "title": title, "link": f"https://n.news.naver.com/{n}", "outlet": outlet}


ARTICLES = [
    _a("2026-10-06T19:59:00+09:00", "삼성전자 신제품 발표", 1),      # in window
    _a("2026-10-06T20:01:00+09:00", "삼성전자 야간 기사", 2),        # after decision time -> out
    _a("2026-10-04T00:00:00+09:00", "주말 삼성전자 소식", 3),        # T-2 00:00 -> in
    _a("2026-10-03T23:59:00+09:00", "삼성전자 지난 기사", 4),        # T-3 -> out
    _a("2026-10-05T09:00:00+09:00", "반도체 업황 점검", 5),          # in window, no title match
]


def _card(**over):
    kw = dict(stock_code="005930", name="삼성전자", decision_date=T, articles=ARTICLES,
              collected_at="2026-10-06T20:40:00+09:00")
    kw.update(over)
    return nw.build_news_card(**kw)


def test_window_ends_at_the_decision_time_and_spans_three_days() -> None:
    start, end = nw.window_bounds(T)
    assert start.isoformat() == "2026-10-04T00:00:00+09:00" and end.isoformat() == "2026-10-06T20:00:00+09:00"
    card = _card()
    assert card["n_collected_in_window"] == 3 and card["n_title_match"] == 2
    assert sorted(i["url"][-1] for i in card["issues"]) == ["1", "3"]
    assert card["collected_span"] == {"first": "2026-10-04T00:00:00+09:00", "last": "2026-10-06T19:59:00+09:00"}


def test_aliases_for_names_the_press_writes_differently() -> None:
    assert nw.search_terms("035420", "NAVER")[0] == "네이버"
    assert nw.search_terms("005930", "삼성전자") == ("삼성전자",)
    arts = [_a("2026-10-06T10:00:00+09:00", "네이버 웹툰 실적", 1), _a("2026-10-06T11:00:00+09:00", "NAVER 지도 개편", 2)]
    card = _card(stock_code="035420", name="NAVER", articles=arts)
    assert card["n_title_match"] == 2 and card["search_terms"] == ["네이버", "NAVER"]
    assert nw.title_matches("s-oil 정제마진", nw.search_terms("010950", "S-Oil"))


def test_noise_is_set_aside_not_deleted() -> None:
    assert nw.noise_category("삼성전자 주가, 10월 6일 장중 276,500원 0.18% 상승") == "주가·시황"
    assert nw.noise_category("[헬로스톡] 10/2 주목할 종목 : 삼성전자") == "종목 나열·순위 홍보"
    assert nw.noise_category("[포토] 삼성전자 신제품") == "포토·영상"
    assert nw.noise_category("삼성전자, 3분기 영업익 100조 전망") is None
    arts = [_a("2026-10-06T10:00:00+09:00", "삼성전자 주가, 장중 1% 상승", 1),
            _a("2026-10-06T11:00:00+09:00", "삼성전자, 3분기 영업익 100조 전망", 2)]
    card = _card(articles=arts)
    assert card["excluded"]["counts"] == {"주가·시황": 1}
    assert card["excluded"]["articles"][0]["url"].endswith("/1")
    assert [i["url"][-1] for i in card["issues"]] == ["2"]


def test_same_story_is_one_issue_ordered_by_outlets() -> None:
    arts = [
        _a("2026-10-06T09:00:00+09:00", "삼성전자, '갤럭시 탭 S12 시리즈·스마트태그3' 국내 출시", 1, "a.com"),
        _a("2026-10-06T09:10:00+09:00", "삼성전자, 갤럭시 탭 S12·스마트태그3 7일 국내 출시", 2, "b.com"),
        _a("2026-10-06T09:20:00+09:00", "[종합] 삼성전자 '갤럭시 탭 S12 시리즈' 국내 출시", 3, "c.com"),
        _a("2026-10-06T12:00:00+09:00", "삼성바이오 노조, 삼성전자에 첫 단체교섭 요구", 4, "a.com"),
        _a("2026-10-06T13:00:00+09:00", "삼성바이오 노조, 삼성전자에 단체교섭 요구", 5, "d.com"),
    ]
    card = _card(articles=arts)
    assert card["n_issues"] == 2
    first, second = card["issues"]
    assert (first["n_outlets"], first["n_articles"]) == (3, 3) and first["url"].endswith("/1")  # earliest is lead
    assert first["tags"] == ["신제품·기술"] and len(first["related"]) == 2
    assert (second["n_outlets"], second["tags"]) == (2, ["규제·소송·사고"])


def test_issue_cap_and_tag_limit() -> None:
    topics = ["반도체 공장 착공", "노사 임금 협상", "갤럭시 판매 호조", "배당 정책 발표", "AI 연구소 개소", "특허 분쟁 판결",
              "해외 법인 설립", "친환경 소재 도입", "스포츠 후원 계약", "채용 박람회 개최", "물류 센터 확장", "보안 취약점 패치"]
    arts = [_a(f"2026-10-06T{h:02d}:00:00+09:00", f"삼성전자, {t}", h) for h, t in enumerate(topics)]
    card = _card(articles=arts, max_issues=5)
    assert card["n_issues"] == 12 and len(card["issues"]) == 5
    assert len(nw.issue_tags("삼성전자 실적 발표 신제품 출시 계약 수주 소송")) == 2


def test_card_keys_json_no_judgment_and_write(tmp_path) -> None:
    card = _card()
    assert (card["card"], card["layer"], card["used_by_model"], card["schema_version"]) == ("news", "reference", False, 2)
    text = json.dumps(card, ensure_ascii=False, allow_nan=False)
    for word in ("호재", "악재", "긍정", "부정적", "감성"):
        assert word not in text
    path = nw.write_news_card(card, tmp_path)
    assert path == tmp_path / "20261006" / "005930_news.json"
    assert json.loads(path.read_text(encoding="utf-8")) == card


def test_empty_store() -> None:
    card = _card(articles=[], collected_at=None)
    assert card["n_collected_in_window"] == 0 and card["issues"] == [] and card["collected_span"] is None
    assert card["excluded"] == {"counts": {}, "articles": []} and card["n_issues"] == 0


def test_news_card_script_summary_line_reads_v2_cards() -> None:
    # Item 76 follow-up: scripts/news_card.py still read the v1 "articles" key and crashed.
    from scripts.news_card import summary_line

    line = summary_line(_card())
    assert line == "삼성전자(005930) 2026-10-06: 기간 내 수집 3건, 제목 일치 2건, 이슈 2개, 제외 0건"
