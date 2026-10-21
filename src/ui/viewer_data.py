"""Data side of the analyst-panel viewer (CURRENT_STATUS item 70, AGENTS.md 43).

Read-only. Everything shown comes from the per-stock card JSON already written by
``scripts/recommend.py`` (quant, item 69) and ``scripts/chart_card.py`` (chart,
item 61), plus the saved survey result. Nothing is scored, ranked or re-computed
here, and no price file is read: the viewer must not show realized returns of
the paper log, which since 2026-09-24 sit inside the forward holdout.

No Streamlit import, so this module is tested in the main environment;
``app/viewer.py`` only lays these values out.
"""

from __future__ import annotations

from datetime import date
import json
from pathlib import Path
from typing import Any

from src.analysts.chart import SPEC_BY_KEY, render_text
from src.analysts.notices import RANK_LABEL, REFERENCE_RANK_NOTICE
from src.analysts.profile_ranking import FILE_NAME as PROFILE_RANKS_FILE

CARDS_ROOT = Path("reports/analyst_cards")
PROFILE_PATH = Path("data/user_profile.json")

# Expert boxes (AGENTS 43.1 / 43.6, item 70 layout change). The market expert is
# page-level (identical for every stock on a date). Per stock, the quant box is the
# recommendation layer and always comes first; the survey profile only reorders the
# reference boxes (aggressive: chart/flow first; conservative: risk events first).
QUANT_BOX = "quant"
PAGE_BOXES = ("market",)
STOCK_REFERENCE_BOXES = ("chart", "disclosure")
REFERENCE_ORDER = {
    "aggressive": ("chart", "disclosure"),
    "conservative": ("disclosure", "chart"),
    "neutral": STOCK_REFERENCE_BOXES,
}
BOX_TITLES = {
    "quant": "퀀트 전문가",
    "chart": "차트 전문가",
    "market": "시장 전문가",
    "disclosure": "공시·뉴스 전문가",
}
LAYER_LABELS = {"recommendation": RANK_LABEL, "reference": "참고 · 모델 미사용 · 순위 근거 아님"}  # item 77
CARD_KINDS = ("quant", "chart", "disclosure", "news")
PROFILE_LABELS = {"conservative": "안정형", "neutral": "중립형", "aggressive": "공격형"}
VERDICT_LABELS = {
    "consistent": "과거 경향(세 구간 일관)",
    "negligible": "경향 미미",
    "inconsistent": "일관된 경향 없음",
    "insufficient": "표본 부족",
}


READ_ERRORS = (OSError, UnicodeDecodeError, json.JSONDecodeError)  # item 99 (UI-P0-2)


def read_json(path: Path) -> Any | None:
    """Parsed JSON, or None if the file is missing or unreadable -- one broken card must
    not stop the whole page (item 99). ``unreadable_files`` reports which ones failed."""
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except READ_ERRORS:
        return None


def unreadable_files(paths: list[Path]) -> list[str]:
    """Names of existing files that cannot be read or parsed as JSON, for the page warning."""
    broken = []
    for path in paths:
        path = Path(path)
        if not path.exists():
            continue
        try:
            json.loads(path.read_text(encoding="utf-8"))
        except READ_ERRORS as error:
            broken.append(f"{path.parent.name}/{path.name} ({type(error).__name__})")
    return broken


def available_dates(root: Path = CARDS_ROOT) -> list[str]:
    """Decision dates (YYYYMMDD) that have quant cards, newest first."""
    root = Path(root)
    if not root.is_dir():
        return []
    days = [d.name for d in root.iterdir() if d.is_dir() and any(d.glob("*_quant.json"))]
    return sorted(days, reverse=True)


WEEKDAY_LABELS = ("월", "화", "수", "목", "금", "토", "일")


def date_label(day: str) -> str:
    """'20261013' -> '2026-10-13 (화)' for the decision-date picker (item 97)."""
    weekday = WEEKDAY_LABELS[date(int(day[:4]), int(day[4:6]), int(day[6:])).weekday()]
    return f"{day[:4]}-{day[4:6]}-{day[6:]} ({weekday})"


def load_day(day: str, root: Path = CARDS_ROOT) -> dict[str, dict[str, Any]]:
    """``{stock_code: {"quant": card | None, "chart": ..., "disclosure": ...}}`` for one decision date."""
    folder = Path(root) / day
    cards: dict[str, dict[str, Any]] = {}
    for path in sorted(folder.glob("*_*.json")):
        code, kind = path.stem.rsplit("_", 1)
        if kind not in CARD_KINDS:
            continue
        card = read_json(path)
        if card is None:  # item 99: shown as missing, listed by unreadable_files
            continue
        cards.setdefault(code, dict.fromkeys(CARD_KINDS))[kind] = card
    return cards


def ranking_rows(day_cards: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """One row per stock with a quant card, by the model's rank (the card's own values)."""
    rows = []
    for code, c in day_cards.items():
        q = c.get("quant")
        if not q:
            continue
        r, s = q["ranking"], q["strategy"]
        rows.append({
            "stock_code": code, "name": q["name"], "rank": r["rank"], "n_stocks": r["n_stocks"],
            "percentile": r["percentile"], "score": r["score"], "tie_size": r["tie_size"],
            "held": s["held_buffered"], "status": s["status"], "has_chart": c.get("chart") is not None,
            "has_disclosure": c.get("disclosure") is not None, "has_news": c.get("news") is not None,
        })
    return sorted(rows, key=lambda x: x["rank"])


TIE_SCORE_DIGITS = 9  # same rounding as recommend.rank_like_engine


def tie_ranges(rows: list[dict[str, Any]]) -> dict[str, tuple[int, int]]:
    """``{stock_code: (first_rank, last_rank)}`` of the group sharing its score (item 100).
    Display only: the ranks themselves (ties by stock code) are the cards' own values."""
    def score_key(row: dict[str, Any]) -> float:
        return round(float(row["score"]), TIE_SCORE_DIGITS)

    groups: dict[float, list[int]] = {}
    for r in rows:
        groups.setdefault(score_key(r), []).append(int(r["rank"]))
    return {r["stock_code"]: (min(groups[score_key(r)]), max(groups[score_key(r)])) for r in rows}


def rank_text(rank: int, tie: tuple[int, int] | None) -> str:
    """'3위', or '공동 2–8위' when the score is shared (the display order goes in its own column)."""
    if tie is None or tie[0] == tie[1]:
        return f"{rank}위"
    return f"공동 {tie[0]}–{tie[1]}위"


def rank_label(rank: int, tie: tuple[int, int] | None) -> str:
    """One-line form for selectors and metrics: '3위' or '공동 2–8위 · 표시순 3'."""
    text = rank_text(rank, tie)
    return text if text == f"{rank}위" else f"{text} · 표시순 {rank}"


def top_rows(rows: list[dict[str, Any]], n: int = 10) -> list[dict[str, Any]]:
    return rows[:n]


def held_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]] | None:
    """The buffered strategy's holdings, or None when the cards carry no holdings information."""
    if not rows or all(r["held"] is None for r in rows):
        return None
    return [r for r in rows if r["held"]]


def day_status(day_cards: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Banner text and model check, copied from the quant cards (not re-derived)."""
    quants = [c["quant"] for c in day_cards.values() if c.get("quant")]
    if not quants:
        return {"validation_status": None, "disclaimer": None, "best_iteration": None, "fingerprint_match": None}
    first = quants[0]
    return {
        "validation_status": first["validation_status"],
        "disclaimer": first["disclaimer"],
        "best_iteration": first["model"]["best_iteration"],
        "fingerprint_match": all(q["model"]["fingerprint_match"] for q in quants),
        "rule": first["strategy"]["rule"],
    }


def load_profile(path: Path = PROFILE_PATH) -> dict[str, Any] | None:
    """Saved survey result (scripts/survey.py) or None. Only ``profile``/``eligible`` are used."""
    path = Path(path)
    if not path.exists():
        return None
    data = read_json(path)
    if not isinstance(data, dict):  # item 99: a broken file counts as "no survey yet" (+ page warning)
        return None
    return {"profile": data.get("profile"), "eligible": bool(data.get("eligible")),
            "created_at": data.get("created_at", "")}


def profile_mismatch_notice(saved: dict[str, Any] | None, selected: str | None) -> str | None:
    """Sidebar warning when the viewed profile differs from the saved survey result (item 100)."""
    if not saved or not saved.get("eligible") or not saved.get("profile") or selected is None:
        return None
    if selected == saved["profile"]:
        return None
    return (f"설문 결과({PROFILE_LABELS[saved['profile']]})와 다른 성향을 보고 있습니다 — "
            "적합성 판단은 설문 결과 기준입니다.")


def box_order(profile: str | None, eligible: bool = True) -> list[str]:
    """Per-stock expert boxes: quant first, then the reference boxes in the profile's order.
    A 'not eligible' survey result gets the reference boxes only, in the neutral order (item 95)."""
    if not eligible:
        return list(STOCK_REFERENCE_BOXES)
    return [QUANT_BOX, *REFERENCE_ORDER.get(profile or "neutral", STOCK_REFERENCE_BOXES)]


def reference_stock_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Stock picker for a 'not eligible' result (item 95): code order, name/code only,
    so neither the order nor the default choice carries the model ranking."""
    return sorted(({"stock_code": r["stock_code"], "name": r["name"]} for r in rows),
                  key=lambda r: r["stock_code"])


def box_layer(key: str) -> str:
    return "recommendation" if key == QUANT_BOX else "reference"


def quant_summary(quant_card: dict[str, Any], tie: tuple[int, int] | None = None) -> str:
    """One line, card values only: rank / n (shared ranks as a range, item 100), percentile, holding state."""
    r, s = quant_card["ranking"], quant_card["strategy"]
    if s["held_buffered"] is None:
        held = "전략 보유 정보 없음"
    elif s["held_buffered"]:
        held = f"전략 보유({s['status']})"
    else:
        held = "전략 보유 아님"
    pct = "백분위 n/a" if r["percentile"] is None else f"백분위 {r['percentile']:.0%}"
    if tie is not None and tie[0] != tie[1]:
        return f"{rank_label(r['rank'], tie)} / {r['n_stocks']} · {pct} · {held}"
    return f"순위 {r['rank']} / {r['n_stocks']} · {pct} · {held}"


def chart_verdict_counts(chart_card: dict[str, Any]) -> dict[str, int]:
    """How many of the card's states fall under each base-rate verdict (no state is singled out, 43.3)."""
    counts = {v: 0 for v in VERDICT_LABELS}
    counts["none"] = 0
    for it in chart_card["states"]:
        verdict = (it.get("base_rate") or {}).get("verdict")
        counts[verdict if verdict in VERDICT_LABELS else "none"] += 1
    return counts


def chart_summary(chart_card: dict[str, Any]) -> str:
    """Counts per verdict only -- never the name of a particular state."""
    c = chart_verdict_counts(chart_card)
    parts = [f"상태 {len(chart_card['states'])}개"]
    parts += [f"{VERDICT_LABELS[v]} {c[v]}개" for v in VERDICT_LABELS]
    if c["none"]:
        parts.append(f"판정 없음 {c['none']}개")
    return " · ".join(parts)


def disclosure_summary(card: dict[str, Any]) -> str:
    """Counts only -- no good/bad reading of any filing (AGENTS 43.1/43.5)."""
    days = card["window"]["days"]
    if card["n_filings"] == 0:
        return f"최근 {days}일 공시 없음"
    return (f"최근 {days}일 공시 {card['n_filings']}건 · 정정 {card['n_corrections']}건 · "
            f"종류 {len(card['by_category'])}개")


def disclosure_rows(card: dict[str, Any]) -> list[dict[str, Any]]:
    return [{"접수일": f["rcept_dt"], "종류": f["label"], "공시": f["report_nm"],
             "정정": f["correction"] or "", "제출인": f["filer"], "원문": f["url"]} for f in card["filings"]]


TOP_ISSUES = 10  # news issues shown first; the rest are collapsed (item 76)


def news_summary(card: dict[str, Any] | None) -> str:
    """Issue count and screening counts -- a collected sample, not a market count (items 75/76)."""
    if card is None:
        return "뉴스 카드 없음"
    days = card["window"]["days"]
    if card["n_collected_in_window"] == 0:
        return f"뉴스: 최근 {days}일 수집 기사 없음"
    excluded = sum(card["excluded"]["counts"].values())
    return (f"뉴스: 최근 {days}일 이슈 {card['n_issues']}개 · 제목 일치 {card['n_title_match']}건"
            f" · 제외 {excluded}건 (수집분 기준)")


def _when(ts: str) -> str:
    return f"{ts[5:7]}/{ts[8:10]} {ts[11:16]}"


def issue_lines(card: dict[str, Any]) -> list[str]:
    """One markdown line per issue: outlets · linked lead headline · tags · time (card order)."""
    lines = []
    for i in card["issues"]:
        line = f"**{i['n_outlets']}개 매체** · {markdown_link(i['title'], i['url'])} ↗"
        if i["n_articles"] > 1:
            line += f" · 기사 {i['n_articles']}건"
        if i["tags"]:
            line += " · " + " ".join(f"`{t}`" for t in i["tags"])
        line += f" · {_when(i['last'])}"
        lines.append(line)
    return lines


def excluded_lines(card: dict[str, Any]) -> list[str]:
    return [f"{_when(a['published'])} · {a['category']} · {markdown_link(a['title'], a['url'])} ↗"
            for a in card["excluded"]["articles"]]


COLLAPSE_OVER = 10  # a disclosure group with more lines than this starts collapsed (item 73)


def markdown_link(text: str, url: str) -> str:
    """A clickable title; brackets in report names ([기재정정] ...) are escaped so the link survives."""
    safe = text.replace("\\", "\\\\").replace("[", "\\[").replace("]", "\\]")
    return f"[{safe}]({url})"


def disclosure_groups(card: dict[str, Any], collapse_over: int = COLLAPSE_OVER) -> list[dict[str, Any]]:
    """Filings grouped by type, in the card's order, one markdown line each with the title as the link."""
    groups = []
    for cat in card["by_category"]:
        lines = []
        for f in card["filings"]:
            if f["category"] != cat["category"]:
                continue
            line = f"{f['rcept_dt'][5:].replace('-', '/')} · {markdown_link(f['report_nm'], f['url'])} ↗"
            if f["correction"]:
                line += f" · 정정 {f['correction']}"
            if f["filer"]:
                line += f" · 제출인 {f['filer']}"
            lines.append(line)
        groups.append({"label": cat["label"], "count": cat["count"],
                       "expanded": cat["count"] <= collapse_over, "lines": lines})
    return groups


def load_market(day: str, root: Path = CARDS_ROOT) -> dict[str, Any] | None:
    """The page-level market card of one decision date (reports/analyst_cards/<T>/market.json)."""
    return read_json(Path(root) / day / "market.json")


PROFILE_RANK_LABEL = "성향 반영 순위"  # item 92; never "추천" (item 77)
NOT_ELIGIBLE_NOTICE = (  # item 95: the ranking layer is hidden, the reference layer stays
    "투자성향 진단 결과 '제공 불가' — 모델 순위·성향 순위·전략 보유 종목은 표시하지 않습니다. "
    "아래는 모델이 쓰지 않는 참고 정보입니다."
)


def decision_basis(day: str) -> str:
    """Label for every card-based box, so it is not mistaken for the live values (item 93)."""
    return f"판단일 {day[:4]}-{day[4:6]}-{day[6:]} 종가 기준 · 실시간 아님"


def load_profile_ranks(day: str, root: Path = CARDS_ROOT) -> dict[str, Any] | None:
    """profile_ranks.json of one decision date (item 92), or None for days before it existed."""
    return read_json(Path(root) / day / PROFILE_RANKS_FILE)


def profile_rank_rows(card: dict[str, Any] | None, profile: str | None, n: int | None = 10) -> list[dict[str, Any]] | None:
    """Top rows of one profile's stored order, or None when the profile is neutral (= model
    ranking) or the file / profile is missing. Values are the file's own (not re-ranked)."""
    if not card or not profile or profile == "neutral" or profile not in card["profiles"]:
        return None
    ranks = card["profiles"][profile]["ranks"]
    return ranks if n is None else ranks[:n]


def profile_stock_row(card: dict[str, Any] | None, profile: str | None, code: str) -> dict[str, Any] | None:
    rows = profile_rank_rows(card, profile, n=None)
    return next((r for r in rows if r["stock_code"] == code), None) if rows else None


def profile_terms_text(row: dict[str, Any]) -> str:
    """Same wording as recommend.py --profile: the z-scale terms that add up to the profile score."""
    return (f"모델 순위 점수 {row['contribution_model']:+.2f}, 변동성 조정 {row['contribution_risk']:+.2f}, "
            f"거래량 {row['contribution_volume']:+.2f} → 최종 {row['personalized_score']:+.2f} (그날 종목 간 표준화 값)")


def _pct(x: float | None, digits: int = 1) -> str:
    return "n/a" if x is None else f"{x:+.{digits}%}"


def market_summary(card: dict[str, Any]) -> str:
    """Levels and the card's own 20-day change only -- no reading of them (AGENTS 43.2)."""
    parts = []
    kospi = next((i for i in card["indices"] if i["code"] == "001"), None)
    if kospi and kospi.get("close") is not None:
        parts.append(f"KOSPI {kospi['close']:,.2f} (20일 {_pct(kospi.get('chg_20d'))})")
    ktb = next((r for r in card["rates"] if r["key"] == "ktb3y"), None)
    if ktb and ktb["value"] is not None:
        parts.append(f"{ktb['label']} {ktb['value']:.2f}%")
    if card["fx"]["value"] is not None:
        parts.append(f"원/달러 {card['fx']['value']:,.1f}")
    return " · ".join(parts) if parts else "시장 데이터 없음"


def market_index_rows(card: dict[str, Any]) -> list[dict[str, Any]]:
    return [{"지수": i["label"], "기준일": i["date"], "종가": i.get("close"), "1일": _pct(i.get("chg_1d")),
             "5일": _pct(i.get("chg_5d")), "20일": _pct(i.get("chg_20d")),
             "200일 평균 대비": _pct(i.get("ma200_gap")),
             "20일 변동성(연율)": "n/a" if i.get("vol20_ann") is None else f"{i['vol20_ann']:.1%}"}
            for i in card["indices"]]


def market_rate_rows(card: dict[str, Any]) -> list[dict[str, Any]]:
    rows = [{"금리": r["label"], "기준일": r["date"], "값(%)": r["value"],
             "20거래일 변화(bp)": None if r["chg_20d_bp"] is None else round(r["chg_20d_bp"], 1)}
            for r in card["rates"]]
    spread = card.get("term_spread_10y_3y")
    if spread:
        rows.append({"금리": "장단기 금리차(10년−3년)", "기준일": spread["dates"][-1], "값(%)": None,
                     "20거래일 변화(bp)": None, "금리차(bp)": round(spread["bp"], 1)})
    return rows


def market_flow_rows(card: dict[str, Any]) -> list[dict[str, Any]]:
    fl = card["flows"]
    rows = []
    for n in (5, 20):
        d = fl.get(f"d{n}")
        rows.append({"기간": f"최근 {n}거래일", "외국인(억원)": None if d is None else round(d["foreign_eok"]),
                     "기관(억원)": None if d is None else round(d["institution_eok"])})
    return rows


def driver_rows(quant_card: dict[str, Any], top: int | None = None) -> list[dict[str, Any]]:
    drivers = quant_card["drivers"][:top] if top else quant_card["drivers"]
    return [{"항목": d["label"], "현재 값": d["value_text"], "점수 기여": d["contribution"],
             "방향": "끌어올림" if (d["contribution"] or 0) > 0 else "끌어내림"} for d in drivers]


def chart_rows(chart_card: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for it in chart_card["states"]:
        spec = SPEC_BY_KEY[it["state"]]
        br = it["base_rate"] or {}
        rows.append({
            "항목": it["title"],
            "현재 값": "n/a" if it["value"] is None else spec.value_format.format(it["value"]),
            "구간": it["bucket"] or "분류 불가",
            "과거 판정": VERDICT_LABELS.get(br.get("verdict"), "—"),
            "평균 초과수익(%p)": None if br.get("mean_excess") is None else br["mean_excess"] * 100,
            "관측 수": br.get("n_obs"),
            "날짜 수": br.get("n_dates"),
        })
    return rows


def chart_text(chart_card: dict[str, Any]) -> str:
    """The chart card's own text (same function the CLI prints), so wording never diverges."""
    return render_text(chart_card)
