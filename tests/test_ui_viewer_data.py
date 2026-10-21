"""Analyst-panel viewer data side (CURRENT_STATUS item 70) -- synthetic cards, tmp_path only."""
from __future__ import annotations

from datetime import date
import json
from pathlib import Path

from src.analysts import quant
from src.ui import viewer_data as vd

ROOT = Path(__file__).resolve().parents[1]
APP_PAGES = sorted((ROOT / "app").glob("*.py"))  # router + every page (item 91)


def _quant(code: str, rank: int, held: bool | None, status: str | None = None, tie: int = 1) -> dict:
    return quant.build_quant_card(
        stock_code=code, name=f"종목{code}", decision_date=date(2026, 10, 6), rank=rank, n_stocks=3,
        percentile=1 - rank / 3, score=0.01 / rank, tie_size=tie,
        features={"price_to_sma_5": -0.02}, contributions={"price_to_sma_5": 0.01 / rank - 0.001, "bias": 0.001},
        best_iteration=9, fingerprint_match=True, held_buffered=held, held_status=status,
        top_n=10, buffer_multiplier=3.0,
    )


def _write_day(root: Path, cards: list[dict], chart_codes=()) -> None:
    for c in cards:
        quant.write_quant_card(c, root)
    for code in chart_codes:
        (root / "20261006" / f"{code}_chart.json").write_text(json.dumps({"card": "chart", "states": []}), encoding="utf-8")


def test_dates_and_day_loading(tmp_path) -> None:
    _write_day(tmp_path, [_quant("000002", 2, False), _quant("000001", 1, True, "유지")], chart_codes=["000001"])
    (tmp_path / "20261005").mkdir()  # no quant cards -> not listed
    assert vd.available_dates(tmp_path) == ["20261006"]
    day = vd.load_day("20261006", tmp_path)
    assert day["000001"]["chart"] is not None and day["000002"]["chart"] is None


def test_rows_come_straight_from_the_cards(tmp_path) -> None:
    _write_day(tmp_path, [_quant("000003", 3, True, "신규"), _quant("000001", 1, True, "유지"),
                          _quant("000002", 2, False, tie=2)])
    rows = vd.ranking_rows(vd.load_day("20261006", tmp_path))
    assert [r["stock_code"] for r in rows] == ["000001", "000002", "000003"]
    assert [r["stock_code"] for r in vd.held_rows(rows)] == ["000001", "000003"]
    assert [r["status"] for r in vd.held_rows(rows)] == ["유지", "신규"]
    assert vd.top_rows(rows, 2)[1]["tie_size"] == 2


def test_no_holdings_information_is_reported_as_none(tmp_path) -> None:
    _write_day(tmp_path, [_quant("000001", 1, None)])
    assert vd.held_rows(vd.ranking_rows(vd.load_day("20261006", tmp_path))) is None


def test_status_banner_is_copied_from_cards(tmp_path) -> None:
    _write_day(tmp_path, [_quant("000001", 1, True, "유지")])
    s = vd.day_status(vd.load_day("20261006", tmp_path))
    assert s["validation_status"] == quant.VALIDATION_STATUS and s["disclaimer"] == quant.NOT_ADVICE
    assert s["fingerprint_match"] is True and s["best_iteration"] == 9


def test_box_order_quant_first_profile_only_reorders_reference_boxes() -> None:
    for p in (None, "neutral", "aggressive", "conservative"):
        order = vd.box_order(p)
        assert order[0] == "quant" and sorted(order[1:]) == sorted(vd.STOCK_REFERENCE_BOXES)
        assert "market" not in order  # page-level, identical for every stock
    assert vd.box_order("aggressive")[1] == "chart"
    assert vd.box_order("conservative")[1] == "disclosure"
    assert vd.PAGE_BOXES == ("market",)
    assert vd.box_layer("quant") == "recommendation"
    assert {vd.box_layer(k) for k in (*vd.STOCK_REFERENCE_BOXES, *vd.PAGE_BOXES)} == {"reference"}



def test_not_eligible_hides_the_ranking_layer_only() -> None:
    # Item 95: reference boxes stay (neutral order), the quant box goes.
    assert vd.box_order("aggressive", eligible=False) == list(vd.STOCK_REFERENCE_BOXES)
    assert vd.box_order(None, eligible=False) == list(vd.STOCK_REFERENCE_BOXES)
    assert "quant" not in vd.box_order("conservative", eligible=False)
    assert vd.box_order("aggressive") == vd.box_order("aggressive", eligible=True)
    assert "추천" not in vd.NOT_ELIGIBLE_NOTICE and "참고 정보" in vd.NOT_ELIGIBLE_NOTICE


def test_reference_stock_rows_carry_no_ranking(tmp_path) -> None:
    _write_day(tmp_path, [_quant("000300", 1, True, "new"), _quant("000100", 2, False), _quant("000200", 3, True, "kept")])
    rows = vd.ranking_rows(vd.load_day("20261006", tmp_path))
    picked = vd.reference_stock_rows(rows)
    assert [r["stock_code"] for r in picked] == ["000100", "000200", "000300"]  # code order, not rank order
    assert all(set(r) == {"stock_code", "name"} for r in picked)
    assert rows[0]["stock_code"] == "000300"  # input untouched


def _chart_card(verdicts: list[str | None]) -> dict:
    return {"card": "chart", "states": [
        {"state": f"s{i}", "title": f"상태이름{i}", "value": 1.0, "bucket": "b",
         "base_rate": None if v is None else {"verdict": v}} for i, v in enumerate(verdicts)
    ]}


def test_chart_summary_counts_only_and_names_no_state() -> None:
    card = _chart_card(["consistent", "negligible", "inconsistent", "inconsistent", None])
    counts = vd.chart_verdict_counts(card)
    assert sum(counts.values()) == len(card["states"])
    assert counts["inconsistent"] == 2 and counts["none"] == 1
    text = vd.chart_summary(card)
    assert "상태 5개" in text and "일관된 경향 없음 2개" in text and "판정 없음 1개" in text
    assert not any(it["title"] in text for it in card["states"])


def test_quant_summary_matches_card_numbers() -> None:
    card = _quant("000001", 2, True, "신규")
    r = card["ranking"]
    text = vd.quant_summary(card)
    assert text == f"순위 {r['rank']} / {r['n_stocks']} · 백분위 {r['percentile']:.0%} · 전략 보유(신규)"
    assert vd.quant_summary(_quant("000001", 1, False)).endswith("전략 보유 아님")
    assert vd.quant_summary(_quant("000001", 1, None)).endswith("전략 보유 정보 없음")


def test_every_expert_has_a_card_now() -> None:
    # items 72/74/75: disclosure, market and news all have cards -- no "준비 중" placeholders left
    assert not hasattr(vd, "NOT_BUILT") and not hasattr(vd, "NEWS_NOT_BUILT")
    assert vd.CARD_KINDS == ("quant", "chart", "disclosure", "news")


def _news_card(articles: list[dict]) -> dict:
    from src.analysts import news as nw

    return nw.build_news_card(stock_code="000001", name="종목", decision_date=date(2026, 10, 6),
                              articles=articles, collected_at="2026-10-06T20:40:00+09:00")


def test_news_summary_issue_and_excluded_lines(tmp_path) -> None:
    from src.analysts import news as nw

    arts = [{"published": "2026-10-06T10:05:00+09:00", "title": "[단독] 종목 신공장 착공", "link": "https://n.news.naver.com/1",
             "outlet": "a.com"},
            {"published": "2026-10-06T10:30:00+09:00", "title": "종목, 신공장 착공", "link": "https://n.news.naver.com/3",
             "outlet": "b.com"},
            {"published": "2026-10-06T11:00:00+09:00", "title": "종목 주가, 장중 2% 상승", "link": "https://n.news.naver.com/2",
             "outlet": ""}]
    card = _news_card(arts)
    assert vd.news_summary(card) == "뉴스: 최근 3일 이슈 1개 · 제목 일치 3건 · 제외 1건 (수집분 기준)"
    assert vd.news_summary(_news_card([])) == "뉴스: 최근 3일 수집 기사 없음"
    assert vd.news_summary(None) == "뉴스 카드 없음"
    assert vd.issue_lines(card) == [
        "**2개 매체** · [\\[단독\\] 종목 신공장 착공](https://n.news.naver.com/1) ↗ · 기사 2건 · `수주·계약·투자` · 10/06 10:30"]
    assert vd.excluded_lines(card) == ["10/06 11:00 · 주가·시황 · [종목 주가, 장중 2% 상승](https://n.news.naver.com/2) ↗"]
    _write_day(tmp_path, [_quant("000001", 1, True, "유지")])
    nw.write_news_card(card, tmp_path)
    assert vd.load_day("20261006", tmp_path)["000001"]["news"]["card"] == "news"


def _market_card() -> dict:
    from src.analysts import market as mk

    days = [date(2026, 9, 1) + __import__("datetime").timedelta(days=i) for i in range(40)]
    return mk.build_market_card(
        decision_date=date(2026, 10, 6),
        index_closes={"001": [(d, 3000.0 + i) for i, d in enumerate(days)]},
        ecos={"ktb3y": [{"date": d.isoformat(), "value": 3.0} for d in days],
              "usdkrw": [{"date": d.isoformat(), "value": 1350.0} for d in days]},
        ecos_labels={"ktb3y": "국고채 3년", "usdkrw": "원/달러 매매기준율"}, flows_by_stock={})


def test_market_summary_values_only(tmp_path) -> None:
    from src.analysts import market as mk

    card = _market_card()
    text = vd.market_summary(card)
    assert text.startswith("KOSPI 3,035.00 (20일 ") and "국고채 3년 3.00%" in text and "원/달러 1,350.0" in text
    assert not any(w in text for w in ("위험", "양호", "강세", "약세", "전망"))
    mk.write_market_card(card, tmp_path)
    assert vd.load_market("20261006", tmp_path) == card
    assert vd.load_market("20261005", tmp_path) is None
    assert len(vd.market_index_rows(card)) == 2 and len(vd.market_flow_rows(card)) == 2


def _disclosure_card(filings: list[dict]) -> dict:
    from src.analysts import disclosure as ds

    return ds.build_disclosure_card(stock_code="000001", name="종목", decision_date=date(2026, 10, 6),
                                    filings=filings, data_through="2026-10-06T20:40:00+09:00")


def test_disclosure_summary_counts_only() -> None:
    card = _disclosure_card([
        {"rcept_dt": "20261006", "report_nm": "[기재정정]현금ㆍ현물배당결정", "rcept_no": "1", "flr_nm": "x"},
        {"rcept_dt": "20261001", "report_nm": "임원ㆍ주요주주특정증권등소유상황보고서", "rcept_no": "2", "flr_nm": "y"},
    ])
    text = vd.disclosure_summary(card)
    assert text == "최근 30일 공시 2건 · 정정 1건 · 종류 2개"
    assert not any(w in text for w in ("호재", "악재", "긍정", "부정", "배당", "임원"))
    assert vd.disclosure_summary(_disclosure_card([])) == "최근 30일 공시 없음"
    rows = vd.disclosure_rows(card)
    assert rows[0]["원문"].endswith("rcpNo=1") and rows[0]["정정"] == "[기재정정]"


def test_load_day_reads_disclosure_cards(tmp_path) -> None:
    from src.analysts import disclosure as ds

    _write_day(tmp_path, [_quant("000001", 1, True, "유지")])
    card = _disclosure_card([])
    card["decision_date"] = "2026-10-06"
    ds.write_disclosure_card(card, tmp_path)
    day = vd.load_day("20261006", tmp_path)
    assert day["000001"]["disclosure"]["card"] == "disclosure"
    assert vd.ranking_rows(day)[0]["has_disclosure"] is True


def test_load_profile(tmp_path) -> None:
    assert vd.load_profile(tmp_path / "missing.json") is None
    p = tmp_path / "user_profile.json"
    p.write_text(json.dumps({"eligible": False, "profile": None}), encoding="utf-8")
    assert vd.load_profile(p)["eligible"] is False


def test_driver_rows_keep_card_order() -> None:
    card = _quant("000001", 1, True, "유지")
    rows = vd.driver_rows(card, top=3)
    assert rows[0]["항목"] == card["drivers"][0]["label"]
    assert rows[0]["현재 값"] == card["drivers"][0]["value_text"]


def test_viewer_never_reads_prices_or_returns() -> None:
    # Item 70 condition 2: the paper log's realized returns since 2026-09-24 are forward holdout.
    forbidden = ("HistoricalStorage", "data/processed/historical", "close_price", "open_price",
                 "target_return", "ka10080", "ka10081", "daily_picks", "calculate_performance", "backtest")
    for path in (ROOT / "src" / "ui" / "viewer_data.py", ROOT / "src" / "ui" / "survey_form.py", *APP_PAGES):
        code = path.read_text(encoding="utf-8")
        hits = [w for w in forbidden if w in code]
        assert not hits, f"{path.name} references {hits}"


def test_markdown_link_escapes_brackets_in_titles() -> None:
    link = vd.markdown_link("[기재정정]현금ㆍ현물배당결정", "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=1")
    assert link == "[\\[기재정정\\]현금ㆍ현물배당결정](https://dart.fss.or.kr/dsaf001/main.do?rcpNo=1)"


def test_disclosure_groups_follow_card_order_and_collapse_big_groups() -> None:
    filings = [{"rcept_dt": "20261006", "report_nm": "[기재정정]현금ㆍ현물배당결정", "rcept_no": "1", "flr_nm": "회사"}]
    filings += [{"rcept_dt": "20261002", "report_nm": "투자설명서(일괄신고)", "rcept_no": str(100 + i), "flr_nm": ""}
                for i in range(12)]
    card = _disclosure_card(filings)
    groups = vd.disclosure_groups(card)
    assert [(g["label"], g["count"]) for g in groups] == [(c["label"], c["count"]) for c in card["by_category"]]
    assert sum(len(g["lines"]) for g in groups) == card["n_filings"]
    big = next(g for g in groups if g["count"] == 12)
    small = next(g for g in groups if g["count"] == 1)
    assert big["expanded"] is False and small["expanded"] is True
    assert small["lines"][0].startswith("10/06 · [\\[기재정정\\]") and "rcpNo=1)" in small["lines"][0]
    assert "정정 [기재정정]" in small["lines"][0]


def test_viewer_has_no_bare_conditional_expressions() -> None:
    # Item 73: Streamlit "magic" prints the value of a bare expression statement, so
    # `a() if x else b()` on its own line showed `None` on the page. Use if/else blocks.
    import ast

    for path in APP_PAGES:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        bare = [n.lineno for n in ast.walk(tree) if isinstance(n, ast.Expr) and isinstance(n.value, ast.IfExp)]
        assert not bare, f"{path.name}: bare conditional expressions at lines {bare}"


def test_app_page_list_covers_the_router() -> None:
    # Item 91: the guards above scan app/*.py; every routed page must be one of those files.
    import re

    router = (ROOT / "app" / "viewer.py").read_text(encoding="utf-8")
    routed = set(re.findall(r'st\.Page\("([^"]+)"', router))
    assert routed and routed == {p.name for p in APP_PAGES} - {"viewer.py"}


def _profile_ranks_file(root: Path) -> dict:
    from src.analysts import profile_ranking as pr

    def rows(order):
        return [{"stock_code": c, "name": f"종목{c}", "rank": i, "model_rank": m, "personalized_score": 0.5 - i / 10,
                 "contribution_model": 0.5 - i / 10, "contribution_risk": 0.0, "contribution_momentum": 0.0,
                 "contribution_volume": 0.0} for i, (c, m) in enumerate(order, 1)]

    card = pr.build_profile_ranks(decision_date=date(2026, 10, 6), fingerprint_match=True, profiles={
        "conservative": (0.4, rows([("000003", 3), ("000001", 1), ("000002", 2)])),
        "aggressive": (0.6, rows([("000002", 2), ("000001", 1), ("000003", 3)])),
    })
    pr.write_profile_ranks(card, root)
    return card


def test_profile_ranks_are_read_as_stored(tmp_path) -> None:
    # Item 92: the viewer shows the stored order; neutral = model ranking (no profile table).
    assert vd.load_profile_ranks("20261006", tmp_path) is None
    assert vd.profile_rank_rows(None, "conservative") is None
    _write_day(tmp_path, [_quant("000001", 1, True, "신규")])
    _profile_ranks_file(tmp_path)
    assert set(vd.load_day("20261006", tmp_path)) == {"000001"}  # the ranks file is not a stock card
    card = vd.load_profile_ranks("20261006", tmp_path)
    assert vd.profile_rank_rows(card, "neutral") is None
    assert [r["stock_code"] for r in vd.profile_rank_rows(card, "conservative")] == ["000003", "000001", "000002"]
    assert [r["rank"] for r in vd.profile_rank_rows(card, "aggressive", n=2)] == [1, 2]
    row = vd.profile_stock_row(card, "conservative", "000001")
    assert row["rank"] == 2 and row["model_rank"] == 1
    assert vd.profile_stock_row(card, "neutral", "000001") is None
    assert "최종 +0.30" in vd.profile_terms_text(row)


def test_decision_basis_label() -> None:
    # Item 93 follow-up: card boxes say they are the decision date's close, not live values.
    assert vd.decision_basis("20261008") == "판단일 2026-10-08 종가 기준 · 실시간 아님"


def test_date_label_shows_weekday_for_the_date_picker() -> None:
    assert vd.date_label("20261013") == "2026-10-13 (화)"
    assert vd.date_label("20261002") == "2026-10-02 (금)"


def test_one_broken_card_does_not_stop_the_day(tmp_path: Path) -> None:
    # Item 99 (UI-P0-2): the broken file is treated as missing and reported by name.
    day = tmp_path / "20261013"
    day.mkdir()
    (day / "005930_quant.json").write_text('{"ok": 1}', encoding="utf-8")
    (day / "005930_chart.json").write_text('{"broken": ', encoding="utf-8")
    (day / "market.json").write_bytes(b"\xff\xfe")
    cards = vd.load_day("20261013", tmp_path)
    assert cards["005930"]["quant"] == {"ok": 1} and cards["005930"]["chart"] is None
    assert vd.load_market("20261013", tmp_path) is None
    assert vd.load_profile_ranks("20261013", tmp_path) is None  # missing file
    broken = vd.unreadable_files(sorted(day.glob("*.json")))
    assert broken == ["20261013/005930_chart.json (JSONDecodeError)", "20261013/market.json (UnicodeDecodeError)"]


def test_broken_profile_counts_as_no_survey(tmp_path: Path) -> None:
    path = tmp_path / "user_profile.json"
    path.write_text("{not json", encoding="utf-8")
    assert vd.load_profile(path) is None
    assert vd.unreadable_files([path, tmp_path / "missing.json"]) == [f"{tmp_path.name}/user_profile.json (JSONDecodeError)"]


def _rank_rows(scores: list[float]) -> list[dict]:
    return [{"stock_code": f"{k:06d}", "rank": k, "score": s} for k, s in enumerate(scores, 1)]


def test_tie_ranges_group_equal_scores_and_leave_input_unchanged() -> None:
    # Item 100 (UI-P1-2): display only; ranks are the cards' own values.
    rows = _rank_rows([0.5, 0.3, 0.3, 0.3 + 1e-12, 0.1])
    before = [dict(r) for r in rows]
    ties = vd.tie_ranges(rows)
    assert ties == {"000001": (1, 1), "000002": (2, 4), "000003": (2, 4), "000004": (2, 4), "000005": (5, 5)}
    assert rows == before


def test_rank_text_and_label() -> None:
    assert vd.rank_text(3, (3, 3)) == "3위" and vd.rank_text(3, None) == "3위"
    assert vd.rank_text(3, (2, 8)) == "공동 2–8위"
    assert vd.rank_label(3, (2, 8)) == "공동 2–8위 · 표시순 3"
    assert vd.rank_label(1, (1, 1)) == "1위"


def test_quant_summary_shows_shared_rank_range() -> None:
    card = {"ranking": {"rank": 3, "n_stocks": 50, "percentile": 0.96},
            "strategy": {"held_buffered": True, "status": "신규"}}
    assert vd.quant_summary(card) == "순위 3 / 50 · 백분위 96% · 전략 보유(신규)"
    assert vd.quant_summary(card, (2, 8)) == "공동 2–8위 · 표시순 3 / 50 · 백분위 96% · 전략 보유(신규)"


def test_profile_mismatch_notice() -> None:
    saved = {"profile": "conservative", "eligible": True}
    assert vd.profile_mismatch_notice(saved, "conservative") is None
    assert vd.profile_mismatch_notice(saved, "aggressive").startswith("설문 결과(안정형)와 다른 성향")
    assert vd.profile_mismatch_notice(None, "aggressive") is None
    assert vd.profile_mismatch_notice({"profile": None, "eligible": False}, None) is None
