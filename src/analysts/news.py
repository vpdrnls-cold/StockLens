"""News analyst card (CURRENT_STATUS item 75, AGENTS.md 43): recent headlines, no judgment.

Reference layer. Shows the newest stored headlines whose title names the company,
published before the decision time (T 20:00 KST, decision time A) within the last
3 calendar days, each with its outlet, time and link. It does not read sentiment
or call anything good or bad news (nothing validated supports that, 43.1/43.5),
and it does not count articles as a signal: the search API only pages back about
1,000 articles, so for a large company the stored set is a recent sample, not a
record (the card shows the time span actually collected).

Item 76 (rule-based "issues"): headlines are first screened for noise -- automated
price/market-move pieces, stock lists and ranking promos, photos, appointments and
obituaries, columns -- which are kept aside, not deleted. The rest are grouped into
issues by title similarity, and issues are ordered by how many different outlets
covered them ("widely covered", not "good" or "bad"). Keyword tags name the kind
of event. All rules below are fixed text patterns, so every placement can be explained.

``NEWS_ALIASES`` lists, for the few stocks the press calls differently, the names
used in headlines; the first one is the search query. Other stocks use their
universe name. Generic names (LG, SK, 두산, HD현대, 기아) can still match related
companies or ordinary words -- the card says so.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
import json
from pathlib import Path
import re
from typing import Any, Iterable, Mapping

KST = timezone(timedelta(hours=9))
DECISION_TIME_KST = time(20, 0)  # decision time A (item 46): after T's session, before T+1
WINDOW_DAYS = 3
MAX_ISSUES = 30           # issues kept in the card (the viewer shows the top 10 first)
MAX_RELATED = 5           # other headlines of the same issue kept per issue
MAX_EXCLUDED_LISTED = 100
SIMILARITY_THRESHOLD = 0.20  # item 76: chosen on the collected 2026-10-06 headlines (see CURRENT_STATUS)
SCHEMA_VERSION = 2
# Noise screen (item 76): first matching rule wins; matched headlines are set aside, not deleted.
NOISE_RULES: tuple[tuple[str, str], ...] = (
    ("주가·시황", r"특징주|장중|\d+(\.\d+)?\s?%\s?(상승|하락|급등|급락|올라|내려|오름|내림)|급등|급락|강세|약세|보합|상한가|하한가"
                  r"|시가총액\s?\d|52주|순매수|순매도|주가[,·]\s|주가는|주가가|주가 \d|주가\s?(상승|하락|급등|급락)"
                  r"|코스피\s?\d|코스닥\s?\d|마감 시황|\[시황\]|\[마켓|증시 전망|\d{3,4}선\s?(안착|돌파|회복|붕괴|탈환|문턱)"),
    ("종목 나열·순위 홍보", r"주목할 종목|관련주|테마주|추천주|수혜주|종목\s?:|TOP\s?\d|브랜드평판|브랜드 평판"),
    ("포토·영상", r"\[포토\]|\[사진\]|\[영상\]|\[화보\]|\[포토뉴스\]|\[PHOTO\]"),
    ("인사·부고", r"\[인사\]|\[부고\]|부고|별세|인사발령|정기 인사|임원 인사|승진 인사"),
    ("칼럼·사설", r"\[칼럼\]|\[사설\]|\[기고\]|\[시론\]|\[기자수첩\]|\[데스크|\[오피니언\]|\[논단\]|\[취재수첩\]"),
)
# Event-kind tags from headline keywords (at most two per issue); they name a kind, not a reading.
ISSUE_TAGS: tuple[tuple[str, str], ...] = (
    ("실적·판매", r"실적|영업이익|영업익|매출|잠정|어닝|순이익|흑자|적자|판매|수출|점유율"),
    ("수주·계약·투자", r"수주|계약|공급|투자|증설|공장|협력|협약|MOU|맞손|파트너|합작"),
    ("자본", r"자사주|배당|증자|소각|주주환원|주주제안|CB|전환사채"),
    ("M&A·지배구조", r"인수|합병|M&A|지분|매각|지배구조|최대주주|경영권"),
    ("규제·소송·사고", r"소송|과징금|제재|수사|리콜|사고|노조|파업|조사|압수수색|고발|검찰|공정위|오염|초과|위반"),
    ("신제품·기술", r"출시|신제품|공개|개발|선보|론칭|기술"),
    ("증권사 의견", r"목표가|목표주가|투자의견|리포트|매수 유지"),
)
_LEAD_TAG_RE = re.compile(r"^\s*(\[[^\]]*\]|【[^】]*】|<[^>]*>)\s*")
NEWS_ALIASES: dict[str, tuple[str, ...]] = {
    "035420": ("네이버", "NAVER"),
    "373220": ("LG에너지솔루션", "LG엔솔"),
    "207940": ("삼성바이오로직스", "삼성바이오"),
    "015760": ("한국전력", "한전"),
    "018260": ("삼성SDS", "삼성에스디에스"),
    "005490": ("포스코홀딩스", "POSCO홀딩스"),
    "010950": ("에쓰오일", "S-Oil", "S-OIL"),
}
CAVEATS = (
    "같은 사건 기사는 제목이 비슷하면 하나의 이슈로 묶고, 보도한 매체 수가 많은 순서로 보여 줍니다(많이 보도됨 ≠ 좋고 나쁨). 묶기는 제목 글자 유사도 기준이라 드물게 다른 사건이 합쳐지거나 같은 사건이 나뉠 수 있습니다.",
    "주가·시황 자동기사, 종목 나열·순위 홍보, 포토, 인사·부고, 칼럼은 제외 목록으로 따로 둡니다(지우지 않음).",
    "제목에 종목명이 들어간 기사만 보여 줍니다. 짧거나 흔한 이름(LG, SK, 두산, 기아 등)은 다른 회사나 일반 단어 기사가 섞일 수 있습니다.",
    "검색 API가 최근 약 1,000건까지만 주기 때문에 기사가 많은 종목은 일부만 모입니다 — 기사 수는 비교 지표가 아닙니다.",
    "기사의 좋고 나쁨은 판단하지 않습니다 — 이를 뒷받침하는 검증된 근거가 없습니다.",
)
DEFAULT_OUT_ROOT = Path("reports/analyst_cards")


def search_terms(stock_code: str, name: str) -> tuple[str, ...]:
    """Names to match in headlines; the first is the search query."""
    return NEWS_ALIASES.get(stock_code, (name,))


def title_matches(title: str, terms: Iterable[str]) -> bool:
    low = title.lower()
    return any(t.lower() in low for t in terms)


def window_bounds(decision_date: date, days: int = WINDOW_DAYS) -> tuple[datetime, datetime]:
    """[start of T-(days-1), T 20:00 KST] -- nothing published after the decision time."""
    end = datetime.combine(decision_date, DECISION_TIME_KST, tzinfo=KST)
    start = datetime.combine(decision_date - timedelta(days=days - 1), time(0, 0), tzinfo=KST)
    return start, end


def noise_category(title: str) -> str | None:
    for category, pattern in NOISE_RULES:
        if re.search(pattern, title):
            return category
    return None


def issue_tags(title: str, limit: int = 2) -> list[str]:
    return [tag for tag, pattern in ISSUE_TAGS if re.search(pattern, title)][:limit]


def _signature(title: str, terms: Iterable[str]) -> set[str]:
    """Character bigrams of the title without the company name, lead tags and punctuation."""
    t = title
    while True:
        stripped = _LEAD_TAG_RE.sub("", t)
        if stripped == t:
            break
        t = stripped
    for term in terms:
        t = re.sub(re.escape(term), "", t, flags=re.IGNORECASE)
    t = re.sub(r"[^가-힣A-Za-z0-9]", "", t)
    return {t[i:i + 2] for i in range(len(t) - 1)} or {t}


def cluster_issues(articles: list[dict[str, Any]], terms: Iterable[str],
                   threshold: float = SIMILARITY_THRESHOLD) -> list[list[dict[str, Any]]]:
    """Group headlines (oldest first) into issues: join the issue with the most similar member
    headline if that Jaccard similarity is >= threshold. Ordered by distinct outlets, then size,
    then most recent headline."""
    terms = tuple(terms)
    issues: list[dict[str, Any]] = []
    for art in sorted(articles, key=lambda a: a["published"]):
        sig = _signature(art["title"], terms)
        best, best_sim = None, 0.0
        for issue in issues:
            sim = max(len(sig & m) / len(sig | m) for m in issue["sigs"])
            if sim > best_sim:
                best, best_sim = issue, sim
        if best is not None and best_sim >= threshold:
            best["arts"].append(art)
            best["sigs"].append(sig)
        else:
            issues.append({"arts": [art], "sigs": [sig]})
    groups = [i["arts"] for i in issues]
    groups.sort(key=lambda g: max(a["published"] for a in g), reverse=True)  # tie-break: most recent first
    groups.sort(key=lambda g: (len({a.get("outlet", "") for a in g}), len(g)), reverse=True)  # stable
    return groups


def build_news_card(
    *,
    stock_code: str,
    name: str,
    decision_date: date,
    articles: Iterable[Mapping[str, Any]],
    collected_at: str | None,
    days: int = WINDOW_DAYS,
    max_issues: int = MAX_ISSUES,
) -> dict[str, Any]:
    terms = search_terms(stock_code, name)
    start, end = window_bounds(decision_date, days)
    stored = sorted((dict(a) for a in articles), key=lambda a: a["published"])
    in_window = [a for a in stored if start <= datetime.fromisoformat(a["published"]) <= end]
    matched = [a for a in in_window if title_matches(a["title"], terms)]
    excluded = [(noise_category(a["title"]), a) for a in matched]
    kept = [a for cat, a in excluded if cat is None]
    excluded = [(cat, a) for cat, a in excluded if cat is not None]
    counts: dict[str, int] = {}
    for cat, _ in excluded:
        counts[cat] = counts.get(cat, 0) + 1

    def item(a: Mapping[str, Any]) -> dict[str, Any]:
        return {"published": a["published"], "outlet": a.get("outlet", ""), "title": a["title"], "url": a["link"]}

    groups = cluster_issues(kept, terms)
    issues = []
    for group in groups[:max_issues]:
        lead = group[0]  # earliest headline of the issue
        issues.append({
            **item(lead),
            "first": group[0]["published"], "last": max(a["published"] for a in group),
            "n_articles": len(group), "n_outlets": len({a.get("outlet", "") for a in group}),
            "tags": issue_tags(lead["title"]),
            "related": [item(a) for a in sorted(group[1:], key=lambda a: a["published"], reverse=True)[:MAX_RELATED]],
        })
    span = {"first": in_window[0]["published"], "last": in_window[-1]["published"]} if in_window else None
    return {
        "card": "news", "layer": "reference", "used_by_model": False,
        "stock_code": stock_code, "name": name, "decision_date": decision_date.isoformat(),
        "schema_version": SCHEMA_VERSION,
        "search_terms": list(terms),
        "window": {"start": start.isoformat(), "end": end.isoformat(), "days": days},
        "collected_at": collected_at,
        "collected_span": span,  # what the stored sample actually covers inside the window
        "n_collected_in_window": len(in_window),
        "n_title_match": len(matched),
        "n_issues": len(groups),
        "issues": issues,
        "excluded": {
            "counts": counts,
            "articles": [{**item(a), "category": cat} for cat, a in
                         sorted(excluded, key=lambda x: x[1]["published"], reverse=True)[:MAX_EXCLUDED_LISTED]],
        },
        "caveats": list(CAVEATS),
    }


def write_news_card(card: dict[str, Any], out_root: Path = DEFAULT_OUT_ROOT) -> Path:
    folder = Path(out_root) / card["decision_date"].replace("-", "")
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{card['stock_code']}_news.json"
    path.write_text(json.dumps(card, ensure_ascii=False, indent=1, allow_nan=False), encoding="utf-8")
    return path
