"""Live reference data for the viewer (CURRENT_STATUS item 93) -- fake clients only, no network."""
from __future__ import annotations

import ast
from datetime import datetime
from pathlib import Path

import pytest

from src.api.kiwoom_client import KiwoomTokenError, StockQuote
from src.ui import live_data as ld

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("raw,points", [
    ("-2394.49", -2394.49),   # spec example: decimal, sign = direction
    ("+662593", 6625.93),     # integer -> x100 encoding (ka20006)
    ("6,625.93", 6625.93),
    ("", None), (None, None),
])
def test_parse_index_points(raw, points):
    assert ld.parse_index_points(raw) == (pytest.approx(points) if points is not None else None)


def test_index_row_level_is_absolute_and_unit_checked():
    raw = {"cur_prc": "-6501.20", "pred_pre": "-124.73", "flu_rt": "-1.88",
           "inds_cur_prc_tm": [{"tm_n": "104210", "cur_prc_n": "-6501.20"}]}
    row = ld.index_row("KOSPI", raw, reference_close=6625.93)
    assert row == {"label": "KOSPI", "level": pytest.approx(6501.20), "change": pytest.approx(-124.73),
                   "change_rate": -1.88, "tick_time": "10:42:10", "unit_ok": True}
    assert ld.index_row("KOSPI", raw, reference_close=None)["unit_ok"] is None


def test_index_row_hides_a_level_in_the_wrong_unit():
    row = ld.index_row("KOSPI", {"cur_prc": "6501", "pred_pre": "-124", "flu_rt": "-1.88"}, reference_close=6625.93)
    assert row["unit_ok"] is False and row["level"] is None and row["change"] is None
    assert row["change_rate"] == -1.88  # a percentage has no unit question


def test_stock_row_drops_the_direction_sign_of_the_price():
    q = StockQuote("005930", "삼성전자", -70000, -500, -0.71, 123456, raw={})
    assert ld.stock_row(q) == {"stock_code": "005930", "price": 70000, "change": -500,
                               "change_rate": -0.71, "volume": 123456}


@pytest.mark.parametrize("stamp,state", [
    ("2026-10-12T08:59:59+09:00", "closed"), ("2026-10-12T09:00:00+09:00", "open"),
    ("2026-10-12T15:30:00+09:00", "open"), ("2026-10-12T15:30:01+09:00", "closed"),
    ("2026-10-10T11:00:00+09:00", "closed"),  # Saturday
    ("2026-10-12T01:00:00+00:00", "open"),    # 10:00 KST given in UTC
])
def test_session_state(stamp, state):
    assert ld.session_state(datetime.fromisoformat(stamp)) == state


def _item(title, minute, link=None):
    return {"title": title, "link": link or f"https://n.news.naver.com/{minute}", "originallink": "",
            "pubDate": f"Mon, 12 Oct 2026 10:{minute:02d}:00 +0900"}


def test_live_news_filters_dedupes_and_orders():
    items = [
        _item("기아, 신형 EV 공개", 5),
        _item("현대차 노조 파업", 30),                 # does not name the stock
        _item("[포토] 기아 전시장", 20),               # noise rule
        _item("기아 3분기 실적 발표 예정", 40),
        _item("기아, 신형 EV 공개", 41, link="https://other/1"),  # same title again
        {"title": "기아 링크 없음", "pubDate": "bad"},  # unusable item
    ]
    news = ld.live_news(items, "000270", "기아")
    assert [a["title"] for a in news] == ["기아 3분기 실적 발표 예정", "기아, 신형 EV 공개"]
    assert len(ld.live_news(items * 3, "000270", "기아", limit=1)) == 1


def test_error_text_never_carries_the_message():
    secret = "https://api.kiwoom.com?appkey=SECRET123"
    err = KiwoomTokenError(f"인증 실패 {secret}", status_code=200, return_code=8050)
    assert "IP" in ld.error_text(err) and "SECRET" not in ld.error_text(err)
    real = KiwoomTokenError(f"인증에 실패했습니다[8050:IP가 등록되지 않았습니다.] {secret}", return_code=3)
    assert "IP" in ld.error_text(real) and "SECRET" not in ld.error_text(real)  # observed 2026-10-12
    other = ld.error_text(RuntimeError(secret))
    assert other == "조회 실패: RuntimeError" and "SECRET" not in other


class FakeKiwoom:
    def __init__(self):
        self.calls = []

    def get_index_quote(self, inds_cd, *, market_type):
        self.calls.append((market_type, inds_cd))
        return {"cur_prc": "+1044.52" if inds_cd == "201" else "+6625.93", "pred_pre": "0", "flu_rt": "0.00"}

    def get_current_quote(self, code):
        return StockQuote(code, "", 70000, 0, 0.0, 1, raw={})


class FakeNews:
    def __init__(self):
        self.queries = []

    def latest(self, query, *, pages):
        self.queries.append((query, pages))
        return [_item("기아 신차", 1)]


def test_fetchers_use_documented_codes_and_one_news_page():
    k = FakeKiwoom()
    rows = ld.fetch_indices(k, {"KOSPI": 6625.93, "KOSPI200": 1044.52})
    assert k.calls == [("0", "001"), ("0", "201")]
    assert [r["unit_ok"] for r in rows] == [True, True]
    assert ld.fetch_stock(k, "005930")["price"] == 70000
    n = FakeNews()
    assert [a["title"] for a in ld.fetch_news(n, "000270", "기아")] == ["기아 신차"]
    assert n.queries == [("기아", ld.NEWS_PAGES)]


def test_live_module_never_sees_decision_dates_or_paper_logs():
    # Item 93 condition 2: no return since the decision date can be computed here.
    code = (ROOT / "src" / "ui" / "live_data.py").read_text(encoding="utf-8")
    for word in ("daily_picks", "HistoricalStorage", "data/processed", "decision_date", "analyst_cards", "streamlit"):
        assert word not in code.split('"""', 2)[2], word
    tree = ast.parse(code)
    args = {a.arg for fn in ast.walk(tree) if isinstance(fn, ast.FunctionDef) for a in fn.args.args + fn.args.kwonlyargs}
    assert not {a for a in args if "date" in a or "pick" in a}
