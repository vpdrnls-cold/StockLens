"""Analyst panel page (CURRENT_STATUS items 70/91, AGENTS.md 43). Local, read-only.

Opened through the router ``app/viewer.py``. Shows only what the card JSON files
say (src/ui/viewer_data.py). No prices, no returns, no re-scoring.
"""

from __future__ import annotations

from datetime import datetime
import os
from pathlib import Path

import streamlit as st

from src.ui import data_status as ds
from src.ui import formatting as fmt
from src.ui import live_data as ld
from src.ui import survey_form as sf
from src.ui import viewer_data as vd

ROOT = Path(__file__).resolve().parents[1]
# Overridable for a test run with sample cards (never needed in normal use).
CARDS_ROOT = Path(os.environ.get("STOCKLENS_CARDS_ROOT", ROOT / vd.CARDS_ROOT))
PROFILE_PATH = sf.profile_path(ROOT)
SURVEY_PAGE = "survey_page.py"


# ---------------------------------------------------------------- live reference data (item 93)
# Called only when the page renders or "새로고침" is pressed; results (and errors, so a
# failing token endpoint is not hammered) are cached. Nothing is saved.
@st.cache_resource(show_spinner=False)
def kiwoom_client():
    from src.api.kiwoom_client import KiwoomClient
    return KiwoomClient.from_env()


@st.cache_resource(show_spinner=False)
def news_client():
    from src.api.naver_news_client import NaverNewsClient
    return NaverNewsClient.from_env(sleep_seconds=0)


def _live_call(fetch, client_factory, *args):
    stamp = datetime.now(ld.KST)
    try:
        return fetch(client_factory(), *args), None, stamp
    except Exception as error:  # shown as type/return code only (ld.error_text), never the message
        client_factory.clear()  # next refresh starts with a new client / token
        return None, ld.error_text(error), stamp


@st.cache_data(ttl=ld.QUOTE_TTL_SECONDS, show_spinner=False)
def live_indices(reference_closes: tuple[tuple[str, float | None], ...]):
    return _live_call(ld.fetch_indices, kiwoom_client, dict(reference_closes))


@st.cache_data(ttl=ld.QUOTE_TTL_SECONDS, show_spinner=False)
def live_stock(stock_code: str):
    return _live_call(ld.fetch_stock, kiwoom_client, stock_code)


@st.cache_data(ttl=ld.NEWS_TTL_SECONDS, show_spinner=False)
def live_news(stock_code: str, name: str):
    return _live_call(ld.fetch_news, news_client, stock_code, name)


def live_caption(stamp: datetime) -> str:
    return (f"실시간 참고 · 조회 {stamp:%m-%d %H:%M:%S} KST · {ld.SESSION_LABELS[ld.session_state(stamp)]} · "
            "모델 미사용 · 판단일 카드와 다른 시점의 값")


def stock_label(row: dict) -> str:
    return f"{vd.rank_label(row['rank'], ties.get(row['stock_code']))} · {row['name']} ({row['stock_code']})"


# ---------------------------------------------------------------- sidebar
st.sidebar.title("StockLens")
dates = vd.available_dates(CARDS_ROOT)
if not dates:
    st.title("StockLens")
    st.info("퀀트 카드가 없습니다. 먼저 실행하세요 (18시 이후):\n\n"
            "`STOCKLENS_UNIVERSE=top50 PYTHONPATH=. .venv/bin/python scripts/recommend.py`")
    st.stop()
day = st.sidebar.selectbox("판단일", dates, format_func=vd.date_label)
st.sidebar.caption(f"카드가 있는 판단일 {len(dates)}개 ({vd.date_label(dates[-1])} ~ {vd.date_label(dates[0])}). "
                   "과거 날짜를 고르면 그날 종가 기준 순위·카드를 봅니다(항목 97).")

saved = vd.load_profile(PROFILE_PATH)
# Item 95: a 'not eligible' result hides the ranking layer only; the reference layer stays.
eligible = saved is None or saved["eligible"]
if saved is None:
    st.sidebar.page_link(SURVEY_PAGE, label="투자성향 진단 (아직 안 함)", icon="📝")
if eligible:
    saved_profile = (saved or {}).get("profile") or "neutral"
    profiles = list(vd.PROFILE_LABELS)
    profile = st.sidebar.selectbox(
        "투자성향", profiles, index=profiles.index(saved_profile),
        format_func=lambda p: vd.PROFILE_LABELS[p] + (" (설문 결과)" if saved and p == saved_profile else ""),
    )
    mismatch = vd.profile_mismatch_notice(saved, profile)  # item 100 (audit UI-P1-4)
    if mismatch:
        st.sidebar.warning(mismatch)
    st.sidebar.caption("성향은 '성향 반영 순위' 표와 참고 박스 순서에만 쓰입니다. 모델 순위·평가 대상 전략·"
                       "보유 목록은 바꾸지 않습니다 (AGENTS 43.6, 항목 92).")
else:
    profile = None
    st.sidebar.page_link(SURVEY_PAGE, label="투자성향 다시 진단하기 (현재 '제공 불가')", icon="📝")

cards = vd.load_day(day, CARDS_ROOT)
rows = vd.ranking_rows(cards)
ties = vd.tie_ranges(rows)  # item 100: shared scores shown as a range (display only)
status = vd.day_status(cards)
profile_ranks = vd.load_profile_ranks(day, CARDS_ROOT) if eligible else None

# ---------------------------------------------------------------- banner
st.title("StockLens")
st.caption(f"판단일 {day[:4]}-{day[4:6]}-{day[6:]} 종가 기준 · "
           + ("다음 거래일 시가 진입 · 5거래일 보유 · " if eligible else "")
           + f"KOSPI200 시총 상위 {rows[0]['n_stocks'] if rows else '?'}종목")


# ---------------------------------------------------------------- data status (item 99, audit UI-P0-1/P0-2)
def data_status_bar() -> None:
    lines = ds.status_lines(day, dates[0], ds.last_nightly_run(ROOT / ds.LOG_DIR), status["fingerprint_match"],
                            datetime.now(ld.KST))
    if any(line.problem for line in lines):
        st.warning("  \n".join(("⚠ " if line.problem else "") + line.text for line in lines))
    else:
        st.caption("데이터 상태 · " + " · ".join(line.text for line in lines))
    broken = vd.unreadable_files([*sorted((CARDS_ROOT / day).glob("*.json")), PROFILE_PATH])
    if broken:
        st.warning(f"읽지 못한 파일 {len(broken)}개 — 없는 것으로 표시합니다: " + ", ".join(broken[:5])
                   + (f" 외 {len(broken) - 5}개" if len(broken) > 5 else ""))


data_status_bar()
if eligible:
    banner = f"**{vd.RANK_LABEL}** — {vd.REFERENCE_RANK_NOTICE}"  # item 77: one wording for every screen
    if status["fingerprint_match"] is False:
        banner += " · ⚠ 고정 모델 지문 불일치 — 기록된 모델과 다른 모델의 순위입니다."
    st.warning(banner)
else:
    st.warning(vd.NOT_ELIGIBLE_NOTICE)
    st.page_link(SURVEY_PAGE, label="투자성향 다시 진단하기", icon="📝")


def layer_badge(key: str) -> str:
    # Box colour marks the layer only (recommendation vs reference), never a good/bad reading (AGENTS 43.5).
    layer = vd.box_layer(key)
    colour = "blue" if layer == "recommendation" else "gray"
    return f":{colour}-background[{vd.LAYER_LABELS[layer]}]"


# ---------------------------------------------------------------- page-level expert (same for every stock)
market = vd.load_market(day, CARDS_ROOT)
with st.container(border=True):
    head, button = st.columns([5, 1])
    with head:
        st.markdown(f"**{vd.BOX_TITLES['market']}** · {vd.decision_basis(day)} {layer_badge('market')}")
        st.write(vd.market_summary(market) if market else "이 판단일의 시장 카드가 없습니다.")
    market_open = st.session_state.get("market_open", False)
    with button:
        if st.button("접기 ▲" if market_open else "자세히", key="open_market", width="stretch"):
            st.session_state["market_open"] = not market_open
            st.rerun()
    if market_open:
        if market is None:
            st.code("STOCKLENS_UNIVERSE=top50 PYTHONPATH=. .venv/bin/python scripts/market_card.py")
        else:
            st.markdown("**지수**")
            st.dataframe(vd.market_index_rows(market), hide_index=True, width="stretch")
            st.markdown("**금리**")
            st.dataframe(vd.market_rate_rows(market), hide_index=True, width="stretch")
            fx = market["fx"]
            st.markdown(f"**환율** — {fx['label']} {fx['value']:,.1f}원 ({fx['date']}) · "
                        f"5일 {vd._pct(fx.get('chg_5d'), 2)} · 20일 {vd._pct(fx.get('chg_20d'), 2)}"
                        if fx["value"] is not None else "**환율** — 데이터 없음")
            st.caption(fx["note"])
            st.markdown(f"**대형주 수급** — {market['flows']['scope']} (마지막 {market['flows']['last_date']})")
            st.dataframe(vd.market_flow_rows(market), hide_index=True, width="stretch")
            for c in market["caveats"]:
                st.caption("· " + c)


# ---------------------------------------------------------------- lists (ranking layer)
def ranking_lists() -> None:
    show_profile = profile != "neutral"
    left, right, *extra = st.columns(3 if show_profile else 2)
    with left:
        st.subheader("평가 대상 전략의 보유 종목")
        held = vd.held_rows(rows)
        if held is None:
            st.info("이 날짜의 카드에는 보유 정보가 없습니다.")
        else:
            st.dataframe([{"순위": vd.rank_text(r["rank"], ties.get(r["stock_code"])), "표시순": r["rank"],
                           "종목": f"{r['name']} ({r['stock_code']})", "상태": r["status"]} for r in held],
                         hide_index=True, width="stretch")
        st.caption(status.get("rule") or "")
    with right:
        st.subheader("모델 순위 상위 10")
        st.dataframe([{"순위": vd.rank_text(r["rank"], ties.get(r["stock_code"])), "표시순": r["rank"],
                       "종목": f"{r['name']} ({r['stock_code']})",
                       "보유": "보유" if r["held"] else ""} for r in vd.top_rows(rows)],
                     hide_index=True, width="stretch")
        st.caption("점수가 같은 종목은 '공동 순위'로 표시합니다. 표시순은 동점을 종목코드 오름차순으로 푼 순서로, "
                   "백테스트·전략 보유 판단(30위 안)이 쓰는 순위입니다. 모델 점수 종류가 적어 상위권 동점이 많습니다.")
    if show_profile:
        with extra[0]:
            st.subheader(f"{vd.PROFILE_RANK_LABEL} 상위 10 · {vd.PROFILE_LABELS[profile]}")
            top_profile = vd.profile_rank_rows(profile_ranks, profile)
            if top_profile is None:
                st.info("이 판단일에는 성향 순위 파일이 없습니다(항목 92 이전 판단일). 생성:")
                st.code(f"STOCKLENS_UNIVERSE=top50 PYTHONPATH=. .venv/bin/python scripts/recommend.py "
                        f"--cards-only --date {day[:4]}-{day[4:6]}-{day[6:]}")
            else:
                st.dataframe([{"순위": r["rank"], "종목": f"{r['name']} ({r['stock_code']})",
                               "모델 순위": vd.rank_text(r["model_rank"], ties.get(r["stock_code"]))}
                              for r in top_profile], hide_index=True, width="stretch")
                st.caption(f"{profile_ranks['note']} {profile_ranks['strategy_note']} "
                           f"성향 반영 강도 λ={profile_ranks['profiles'][profile]['lambda']:.3f}.")


if eligible:
    ranking_lists()

# ---------------------------------------------------------------- per-stock expert boxes
st.divider()
if eligible:
    default = next((i for i, r in enumerate(rows) if r["held"]), 0)
    choice = st.selectbox("종목 선택 (전 종목)", rows, index=default, format_func=stock_label)
else:  # item 95: code order, no rank, first stock by default
    choice = st.selectbox("종목 선택 (전 종목, 종목코드 순)", vd.reference_stock_rows(rows), index=0,
                          format_func=lambda r: f"{r['name']} ({r['stock_code']})")
picked = cards[choice["stock_code"]]
st.header(f"{choice['name']} ({choice['stock_code']})")
st.caption(f"아래 전문가 박스는 {vd.decision_basis(day)}. 현재가·최신 뉴스는 맨 아래 '실시간 참고' 구획에 있습니다. "
           "각 박스는 독립된 의견입니다. 서로 엇갈려도 합치거나 평균내지 않습니다 (AGENTS 43.5).")


def quant_detail(q: dict) -> None:
    r = q["ranking"]
    c1, c2, c3 = st.columns(3)
    tie = ties.get(q["stock_code"])
    c1.metric("모델 순위", f"{vd.rank_text(r['rank'], tie)} / {r['n_stocks']}")
    c2.metric("백분위", f"{r['percentile']:.0%}")
    c3.metric("랭킹 점수", f"{r['score']:+.4f}")
    st.caption(r["score_note"])
    if r["tied"]:
        st.info(f"같은 점수 {r['tie_size']}종목 — {r['tie_rule']}으로 푼 표시순 {r['rank']}위 "
                "(백테스트·전략 보유 판단에 쓰는 순위).")
    s = q["strategy"]
    if s["held_buffered"] is not None:
        st.write("전략 보유: " + (f"**보유 ({s['status']})**" if s["held_buffered"] else "보유 아님"))
    if s.get("note"):  # optional (item 71): holdings source on a --cards-only card
        st.caption(s["note"])
    p_row = vd.profile_stock_row(profile_ranks, profile, q["stock_code"])
    if p_row is not None:
        st.write(f"{vd.PROFILE_RANK_LABEL}({vd.PROFILE_LABELS[profile]}): **{p_row['rank']} / {r['n_stocks']}** — "
                 + vd.profile_terms_text(p_row))
    st.markdown("**순위를 만든 근거 (TreeSHAP 상위 3)** — 이 종목 점수를 실제로 움직인 항목과 현재 값")
    st.dataframe(vd.driver_rows(q, top=3), hide_index=True, width="stretch")
    st.markdown("**전체 항목 기여**")
    st.dataframe(vd.driver_rows(q), hide_index=True, width="stretch")
    st.caption(f"기준값(bias) {q['bias']:+.4f} + 항목 기여의 합 = 랭킹 점수 "
               f"(차이 {q['shap_check']['sum_minus_score']:+.1e})")


def chart_detail(ch: dict) -> None:
    st.dataframe(vd.chart_rows(ch), hide_index=True, width="stretch")
    st.markdown("**차트 카드 원문 (수급·읽는 법 포함)**")
    st.text(vd.chart_text(ch))


def disclosure_detail(dc: dict) -> None:
    st.caption(f"기간 {dc['window']['start']} ~ {dc['window']['end']} · 공시 목록 수집 {dc['data_through'] or '기록 없음'}"
               " · 공시 제목을 누르면 DART 원문이 새 탭에서 열립니다.")
    groups = vd.disclosure_groups(dc)
    if not groups:
        st.write("이 기간에 접수된 공시가 없습니다.")
    for g in groups:
        with st.expander(f"{g['label']} {g['count']}건", expanded=g["expanded"]):
            st.markdown("\n".join(f"- {line}" for line in g["lines"]))
    for c in dc["caveats"]:
        st.caption("· " + c)


def news_detail(nc: dict) -> None:
    span = nc["collected_span"]
    st.caption(f"검색어 {', '.join(nc['search_terms'])} · 기간 {nc['window']['start'][:16]} ~ {nc['window']['end'][:16]} · "
               + (f"수집된 기사 범위 {span['first'][5:16]} ~ {span['last'][5:16]} ({nc['n_collected_in_window']}건)"
                  if span else "이 기간 수집된 기사 없음")
               + " · 제목을 누르면 기사가 새 탭에서 열립니다.")
    lines = vd.issue_lines(nc)
    if lines:
        st.markdown("**많이 보도된 이슈** (보도 매체 수 순 — 많이 보도됨 ≠ 좋고 나쁨)")
        st.markdown("\n".join(f"{n}. {line}" for n, line in enumerate(lines[:vd.TOP_ISSUES], 1)))
        rest = lines[vd.TOP_ISSUES:]
        if rest or nc["n_issues"] > len(lines):
            with st.expander(f"나머지 이슈 {nc['n_issues'] - vd.TOP_ISSUES}개"):
                st.markdown("\n".join(f"- {line}" for line in rest))
                if nc["n_issues"] > len(lines):
                    st.caption(f"카드에는 상위 {len(lines)}개 이슈만 저장됩니다.")
    else:
        st.write("제목에 종목명이 들어간 이슈가 없습니다.")
    counts = nc["excluded"]["counts"]
    if counts:
        label = " · ".join(f"{k} {v}" for k, v in counts.items())
        with st.expander(f"제외한 기사 {sum(counts.values())}건 ({label})"):
            st.markdown("\n".join(f"- {line}" for line in vd.excluded_lines(nc)))
    for c in nc["caveats"]:
        st.caption("· " + c)


def missing_card(kind: str, script: str) -> None:
    st.write(f"이 종목의 {kind} 카드가 없습니다. 생성:")
    st.code(f"STOCKLENS_UNIVERSE=top50 PYTHONPATH=. .venv/bin/python scripts/{script} --from-picks 50")


# Item 73: boxes show the summary only; "자세히" picks which expert's detail fills the
# full-width area below (one at a time), so tables and link lists are never squeezed.
order = vd.box_order(profile, eligible)
if st.session_state.get("expert") not in order:
    st.session_state["expert"] = order[0]

summaries = {
    "quant": vd.quant_summary(picked["quant"], ties.get(choice["stock_code"])) if eligible else "",
    "chart": vd.chart_summary(picked["chart"]) if picked["chart"] else "차트 카드 없음",
    "disclosure": (vd.disclosure_summary(picked["disclosure"]) if picked["disclosure"] else "공시 카드 없음")
    + "  \n" + vd.news_summary(picked["news"]),
}
for key, col in zip(order, st.columns(len(order))):
    with col, st.container(border=True):
        st.markdown(f"**{vd.BOX_TITLES[key]}**")
        st.markdown(layer_badge(key))
        st.write(summaries[key])
        selected = st.session_state["expert"] == key
        if st.button("자세히 ▼" if selected else "자세히", key=f"open_{key}",
                     type="primary" if selected else "secondary", width="stretch"):
            st.session_state["expert"] = key
            st.rerun()

expert = st.session_state["expert"]
with st.container(border=True):
    st.subheader(f"{vd.BOX_TITLES[expert]} · 상세")
    st.markdown(layer_badge(expert))
    if expert == "quant":
        quant_detail(picked["quant"])
    elif expert == "chart":
        if picked["chart"]:
            chart_detail(picked["chart"])
        else:
            missing_card("차트", "chart_card.py")
    elif expert == "disclosure":
        st.markdown("#### 공시")
        if picked["disclosure"]:
            disclosure_detail(picked["disclosure"])
        else:
            missing_card("공시", "disclosure_card.py")
        st.markdown("#### 뉴스 (판단일 카드)")
        st.caption("최신 뉴스(실시간)는 맨 아래 '실시간 참고' 구획에 있습니다.")
        if picked["news"]:
            news_detail(picked["news"])
        else:
            missing_card("뉴스", "news_card.py")


# ---------------------------------------------------------------- live reference section (item 100, audit UI-P1-3)
# Everything that is NOT as of the decision date sits here, below the card-based layers.
def live_change(r: dict, digits: int = 2, unit: str = "") -> None:
    st.markdown(fmt.change_markdown(r["change"], r["change_rate"], digits, unit) or ":gray[등락 정보 없음]")


def live_index_columns() -> None:
    refs = tuple((i["label"], i["close"]) for i in (market or {}).get("indices", []))
    indices, live_error, stamp = live_indices(refs)
    st.caption(live_caption(stamp))
    if live_error:
        st.write(live_error)
        return
    for col, r in zip(st.columns(len(indices)), indices):
        with col:
            if r["level"] is None:
                st.metric(r["label"], "단위 확인 필요" if r["unit_ok"] is False else "값 없음")
            else:
                st.metric(r["label"], f"{r['level']:,.2f}")
            live_change(r)
    ticks = sorted({r["tick_time"] for r in indices if r["tick_time"]})
    if ticks:
        st.caption("마지막 체결 " + ", ".join(ticks) + " · 등락은 전일 종가 대비(키움 제공 값)")


def live_stock_quote() -> None:
    quote, quote_error, quote_stamp = live_stock(choice["stock_code"])
    if quote_error:
        st.caption(f"현재가: {quote_error}")
    elif quote["price"] is not None:
        st.metric(f"{choice['name']} 현재가", f"{quote['price']:,}원")
        live_change(quote, digits=0, unit="원")
        st.caption(live_caption(quote_stamp) + " · 등락은 전일 종가 대비")


def live_news_list() -> None:
    articles, news_error, news_stamp = live_news(choice["stock_code"], choice["name"])
    st.markdown(f"**{choice['name']} 최신 뉴스**")
    st.caption(live_caption(news_stamp) + " · 제목에 종목명이 있는 기사만, 시황·포토·인사·칼럼 제외(뉴스 카드와 같은 규칙)")
    if news_error:
        st.write(news_error)
    elif not articles:
        st.write("최근 기사 중 제목에 종목명이 들어간 기사가 없습니다.")
    else:
        st.markdown("\n".join(f"- {a['published'][5:16].replace('T', ' ')} · "
                               f"{vd.markdown_link(a['title'], a['link'])} · {a['outlet']}" for a in articles))


st.divider()
with st.container(border=True):
    head, button = st.columns([5, 1])
    with head:
        st.subheader("실시간 참고")
        st.markdown(f"{layer_badge('market')} :gray[판단일 카드와 다른 시점의 값 · 순위·카드에 쓰이지 않음]")
    with button:
        if st.button("새로고침", key="live_refresh", width="stretch"):
            live_indices.clear()
            live_stock.clear()
            live_news.clear()
    live_index_columns()
    st.divider()
    live_stock_quote()
    live_news_list()
