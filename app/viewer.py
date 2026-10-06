"""StockLens analyst panel viewer (CURRENT_STATUS item 70, AGENTS.md 43). Local, read-only.

Run with the separate UI environment (never install streamlit into .venv -- it is
pinned to the frozen model's environment):

    .venv-ui/bin/streamlit run app/viewer.py

Shows only what the card JSON files say (src/ui/viewer_data.py). No prices, no
returns, no re-scoring.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.ui import viewer_data as vd  # noqa: E402

st.set_page_config(page_title="StockLens 분석가 패널", layout="wide")
# Overridable for a test run with sample cards (never needed in normal use).
CARDS_ROOT = Path(os.environ.get("STOCKLENS_CARDS_ROOT", ROOT / vd.CARDS_ROOT))
PROFILE_PATH = Path(os.environ.get("STOCKLENS_PROFILE_PATH", ROOT / vd.PROFILE_PATH))


def stock_label(row: dict) -> str:
    return f"{row['rank']}위 · {row['name']} ({row['stock_code']})"


# ---------------------------------------------------------------- sidebar
st.sidebar.title("StockLens")
dates = vd.available_dates(CARDS_ROOT)
if not dates:
    st.title("StockLens 분석가 패널")
    st.info("퀀트 카드가 없습니다. 먼저 실행하세요 (18시 이후):\n\n"
            "`STOCKLENS_UNIVERSE=top50 PYTHONPATH=. .venv/bin/python scripts/recommend.py`")
    st.stop()
day = st.sidebar.selectbox("판단일", dates, format_func=lambda d: f"{d[:4]}-{d[4:6]}-{d[6:]}")

saved = vd.load_profile(PROFILE_PATH)
if saved and not saved["eligible"]:
    st.title("StockLens 분석가 패널")
    st.warning("저장된 투자성향 진단 결과가 '제공 불가'입니다. 이 전략은 지금 상황에 맞지 않아 모델 참고 순위를 보여주지 않습니다.\n\n"
               "다시 진단: `PYTHONPATH=. .venv/bin/python scripts/survey.py`")
    st.stop()
saved_profile = (saved or {}).get("profile") or "neutral"
profiles = list(vd.PROFILE_LABELS)
profile = st.sidebar.selectbox(
    "참고 박스 순서 기준 성향", profiles, index=profiles.index(saved_profile),
    format_func=lambda p: vd.PROFILE_LABELS[p] + (" (설문 결과)" if saved and p == saved_profile else ""),
)
st.sidebar.caption("성향은 종목별 참고 박스의 순서만 바꿉니다. 모델 순위는 바꾸지 않습니다 (AGENTS 43.6).")

cards = vd.load_day(day, CARDS_ROOT)
rows = vd.ranking_rows(cards)
status = vd.day_status(cards)

# ---------------------------------------------------------------- banner
st.title("StockLens 분석가 패널")
st.caption(f"판단일 {day[:4]}-{day[4:6]}-{day[6:]} 종가 기준 · 다음 거래일 시가 진입 · 5거래일 보유 · "
           f"KOSPI200 시총 상위 {rows[0]['n_stocks'] if rows else '?'}종목")
banner = f"**{vd.RANK_LABEL}** — {vd.REFERENCE_RANK_NOTICE}"  # item 77: one wording for every screen
if status["fingerprint_match"] is False:
    banner += " · ⚠ 고정 모델 지문 불일치 — 기록된 모델과 다른 모델의 순위입니다."
st.warning(banner)


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
        st.markdown(f"**{vd.BOX_TITLES['market']}** {layer_badge('market')}")
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


# ---------------------------------------------------------------- lists
left, right = st.columns(2)
with left:
    st.subheader("평가 대상 전략의 보유 종목")
    held = vd.held_rows(rows)
    if held is None:
        st.info("이 날짜의 카드에는 보유 정보가 없습니다.")
    else:
        st.dataframe([{"순위": r["rank"], "종목": f"{r['name']} ({r['stock_code']})", "상태": r["status"]} for r in held],
                     hide_index=True, width="stretch")
    st.caption(status.get("rule") or "")
with right:
    st.subheader("모델 순위 상위 10")
    st.dataframe([{"순위": r["rank"], "종목": f"{r['name']} ({r['stock_code']})",
                   "동점": f"{r['tie_size']}종목" if r["tie_size"] > 1 else "",
                   "보유": "보유" if r["held"] else ""} for r in vd.top_rows(rows)],
                 hide_index=True, width="stretch")
    st.caption("점수가 같은 종목은 종목코드 오름차순으로 순위를 정합니다(백테스트와 같은 규칙). "
               "모델 점수 종류가 적어 상위권 동점이 많습니다.")

# ---------------------------------------------------------------- per-stock expert boxes
st.divider()
default = next((i for i, r in enumerate(rows) if r["held"]), 0)
choice = st.selectbox("종목 선택 (전 종목)", rows, index=default, format_func=stock_label)
picked = cards[choice["stock_code"]]
st.header(f"{choice['name']} ({choice['stock_code']})")
st.caption("각 전문가 박스는 독립된 의견입니다. 서로 엇갈려도 합치거나 평균내지 않습니다 (AGENTS 43.5).")


def quant_detail(q: dict) -> None:
    r = q["ranking"]
    c1, c2, c3 = st.columns(3)
    c1.metric("모델 순위", f"{r['rank']} / {r['n_stocks']}")
    c2.metric("백분위", f"{r['percentile']:.0%}")
    c3.metric("랭킹 점수", f"{r['score']:+.4f}")
    st.caption(r["score_note"])
    if r["tied"]:
        st.info(f"같은 점수 {r['tie_size']}종목 — {r['tie_rule']}으로 순위를 정했습니다.")
    s = q["strategy"]
    if s["held_buffered"] is not None:
        st.write("전략 보유: " + (f"**보유 ({s['status']})**" if s["held_buffered"] else "보유 아님"))
    if s.get("note"):  # optional (item 71): holdings source on a --cards-only card
        st.caption(s["note"])
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
order = vd.box_order(profile)
if st.session_state.get("expert") not in order:
    st.session_state["expert"] = order[0]

summaries = {
    "quant": vd.quant_summary(picked["quant"]),
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
        st.markdown("#### 뉴스")
        if picked["news"]:
            news_detail(picked["news"])
        else:
            missing_card("뉴스", "news_card.py")
