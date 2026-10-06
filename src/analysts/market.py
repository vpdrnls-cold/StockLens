"""Market analyst card (CURRENT_STATUS item 74, AGENTS.md 43.2): the environment, not a pick.

Market variables are the same for every stock on a date, so this card describes
the environment on the decision date T and never ranks or recommends a stock. It
holds descriptive statistics only -- recent changes, distance from the 200-day
average, realized volatility, rate levels and changes, KRW/USD, and the net
buying of the top50 universe -- each with the date of the value it uses. No
outlook, no "risk on/off" verdict, no historical base rate (that would need its
own pre-registration).

Every number uses data dated on or before T only
(tests/test_analyst_market.py checks that changing later values changes nothing).
"""

from __future__ import annotations

from datetime import date
import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence

SCHEMA_VERSION = 1
TRADING_DAYS = 252
INDEX_LABELS = {"001": "KOSPI", "201": "KOSPI200"}
RATE_KEYS = ("ktb3y", "ktb10y", "corp_aa3y", "cd91")
FX_KEY = "usdkrw"
FLOW_SCOPE = "KOSPI200 시가총액 상위 50종목 합계 — 시장 전체가 아님"
FX_NOTE = "매매기준율은 전 영업일 거래로 정해지는 값입니다."
CAVEATS = (
    "현재 시장 환경을 숫자로 설명할 뿐, 앞으로의 방향을 예측하지 않습니다.",
    "종목 추천과 무관합니다 — 모델 점수·순위에 쓰이지 않습니다.",
    "과거 같은 상황 뒤에 무슨 일이 있었는지(과거 통계)는 아직 넣지 않았습니다.",
)
DEFAULT_OUT_ROOT = Path("reports/analyst_cards")


def _finite(x: float | None) -> float | None:
    return x if x is not None and math.isfinite(x) else None


def _upto(points: Sequence[tuple[date, float]], asof: date) -> list[tuple[date, float]]:
    return sorted((p for p in points if p[0] <= asof), key=lambda p: p[0])


def index_stats(closes: Sequence[tuple[date, float]], asof: date) -> dict[str, Any] | None:
    """Close, 1/5/20-day change, gap to the 200-day mean, 20-day realized vol (annualized)."""
    pts = _upto(closes, asof)
    if not pts:
        return None
    c = [v for _, v in pts]

    def change(n: int) -> float | None:
        return c[-1] / c[-1 - n] - 1.0 if len(c) > n and c[-1 - n] > 0 else None

    rets = [c[i] / c[i - 1] - 1.0 for i in range(len(c) - 20, len(c))] if len(c) > 20 else []
    vol = None
    if len(rets) == 20:
        mean = sum(rets) / 20
        vol = math.sqrt(sum((r - mean) ** 2 for r in rets) / 19) * math.sqrt(TRADING_DAYS)
    ma200 = sum(c[-200:]) / 200 if len(c) >= 200 else None
    return {
        "date": pts[-1][0].isoformat(), "close": c[-1],
        "chg_1d": _finite(change(1)), "chg_5d": _finite(change(5)), "chg_20d": _finite(change(20)),
        "ma200_gap": _finite(c[-1] / ma200 - 1.0) if ma200 else None,
        "vol20_ann": _finite(vol),
    }


def series_stats(points: Sequence[Mapping[str, Any]], asof: date, lags: Sequence[int]) -> dict[str, Any] | None:
    """Latest value on/before ``asof`` and its change against ``n`` observations earlier."""
    pts = _upto([(date.fromisoformat(p["date"]), float(p["value"])) for p in points], asof)
    if not pts:
        return None
    v = [x for _, x in pts]
    out: dict[str, Any] = {"date": pts[-1][0].isoformat(), "value": v[-1]}
    for n in lags:
        out[f"prev_{n}"] = v[-1 - n] if len(v) > n else None
    return out


def flow_totals(flows_by_stock: Mapping[str, Sequence[tuple[date, int, int]]], asof: date,
                lookbacks: Sequence[int] = (5, 20)) -> dict[str, Any]:
    """Foreign / institution net buying summed over the stocks, last N flow dates on/before ``asof`` (억원)."""
    per_date: dict[date, list[int]] = {}
    stocks_on: dict[date, int] = {}
    for rows in flows_by_stock.values():
        for d, foreign, inst in rows:
            if d <= asof:
                tot = per_date.setdefault(d, [0, 0])
                tot[0] += foreign
                tot[1] += inst
                stocks_on[d] = stocks_on.get(d, 0) + 1
    dates = sorted(per_date)
    out: dict[str, Any] = {"scope": FLOW_SCOPE, "last_date": dates[-1].isoformat() if dates else None,
                           "n_stocks_last_date": stocks_on[dates[-1]] if dates else 0}
    for n in lookbacks:
        recent = dates[-n:]
        out[f"d{n}"] = None if len(recent) < n else {
            "foreign_eok": sum(per_date[d][0] for d in recent) / 100.0,
            "institution_eok": sum(per_date[d][1] for d in recent) / 100.0,
        }
    return out


def build_market_card(
    *,
    decision_date: date,
    index_closes: Mapping[str, Sequence[tuple[date, float]]],
    ecos: Mapping[str, Sequence[Mapping[str, Any]]],
    ecos_labels: Mapping[str, str],
    flows_by_stock: Mapping[str, Sequence[tuple[date, int, int]]],
) -> dict[str, Any]:
    indices = []
    for code, label in INDEX_LABELS.items():
        stats = index_stats(index_closes.get(code, []), decision_date)
        indices.append({"code": code, "label": label, **(stats or {"date": None})})

    rates = []
    for key in RATE_KEYS:
        s = series_stats(ecos.get(key, []), decision_date, lags=(20,))
        rates.append({
            "key": key, "label": ecos_labels.get(key, key),
            "date": s["date"] if s else None, "value": s["value"] if s else None,
            "chg_20d_bp": _finite((s["value"] - s["prev_20"]) * 100) if s and s["prev_20"] is not None else None,
        })
    by_key = {r["key"]: r for r in rates}
    spread = None
    if by_key["ktb10y"]["value"] is not None and by_key["ktb3y"]["value"] is not None:
        spread = {"bp": _finite((by_key["ktb10y"]["value"] - by_key["ktb3y"]["value"]) * 100),
                  "dates": [by_key["ktb3y"]["date"], by_key["ktb10y"]["date"]]}

    fx_s = series_stats(ecos.get(FX_KEY, []), decision_date, lags=(5, 20))
    fx = {"label": ecos_labels.get(FX_KEY, FX_KEY), "note": FX_NOTE,
          "date": fx_s["date"] if fx_s else None, "value": fx_s["value"] if fx_s else None}
    for n in (5, 20):
        prev = fx_s.get(f"prev_{n}") if fx_s else None
        fx[f"chg_{n}d"] = _finite(fx_s["value"] / prev - 1.0) if prev else None

    return {
        "card": "market", "layer": "reference", "used_by_model": False,
        "decision_date": decision_date.isoformat(), "schema_version": SCHEMA_VERSION,
        "indices": indices, "rates": rates, "term_spread_10y_3y": spread, "fx": fx,
        "flows": flow_totals(flows_by_stock, decision_date),
        "caveats": list(CAVEATS),
    }


def write_market_card(card: dict[str, Any], out_root: Path = DEFAULT_OUT_ROOT) -> Path:
    folder = Path(out_root) / card["decision_date"].replace("-", "")
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "market.json"
    path.write_text(json.dumps(card, ensure_ascii=False, indent=1, allow_nan=False), encoding="utf-8")
    return path
