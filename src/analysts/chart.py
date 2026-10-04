"""Chart analyst card: current state + historical base rates (CURRENT_STATUS item 61).

Reference layer only (AGENTS.md 43): nothing here feeds the model score, the
rank, or reports/daily_picks/. The card shows, for a fixed set of
pre-registered states, what happened after that state in OUR data during the
validation windows -- not technical-analysis opinions.

Base-rate rules (item 61, fixed before any number was computed):
- period 2012-01-01 ~ VALIDATION_END_DATE, last ``horizon`` dates purged so no
  label uses a price after VALIDATION_END_DATE; test/forward never read;
- outcome = target_return_5d minus the same day's universe mean (excess);
- every state is always shown; "표본 부족" when n < 100 (or < 30 in a window);
  "일관된 경향 없음" when the window means disagree in sign.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import math
from typing import Any, Iterable, Sequence

import numpy as np
import pandas as pd

from src.backtest.baseline import BaselineConfig
from src.data.dataset import TARGET_COLUMN, VALIDATION_END_DATE

BASE_RATE_START = "2012-01-01"
WINDOWS: tuple[tuple[str, str, str], ...] = (
    ("W1", "2012-01-01", "2015-12-31"),
    ("W2", "2016-01-01", "2019-12-31"),
    ("W3", "2020-01-01", VALIDATION_END_DATE),
)
MIN_OBS = 100
MIN_OBS_PER_WINDOW = 30
# Item 63 (post-hoc amendment, decided AFTER seeing item 61 results): a
# same-sign mean smaller than this is shown as "경향 미미", not as a tendency.
MIN_EFFECT = 0.001
EXCESS_COLUMN = "excess_return_5d"


@dataclass(frozen=True)
class StateSpec:
    key: str
    title: str
    column: str
    kind: str  # "bins" (fixed edges, left-closed) or "quintile" (within date)
    edges: tuple[float, ...] = ()
    labels: tuple[str, ...] = ()
    value_format: str = "{:.2f}"


QUINTILE_LABELS = ("Q1", "Q2", "Q3", "Q4", "Q5")

STATE_SPECS: tuple[StateSpec, ...] = (
    StateSpec("rsi", "RSI(14)", "rsi_14", "bins", (30.0, 70.0),
              ("과매도(<30)", "중립(30~70)", "과매수(≥70)"), "{:.1f}"),
    StateSpec("sma60", "60일선 대비", "price_to_sma_60", "bins", (-0.10, 0.0, 0.10),
              ("−10% 미만", "−10~0%", "0~+10%", "+10% 이상"), "{:+.1%}"),
    StateSpec("ret20", "20일 수익률 상대 위치", "return_20d", "quintile",
              labels=("Q1(최약)", "Q2", "Q3", "Q4", "Q5(최강)"), value_format="{:+.1%}"),
    StateSpec("volume", "거래량(20일 평균 대비)", "volume_ratio_20", "bins", (0.7, 1.5, 3.0),
              ("한산(<0.7)", "보통(0.7~1.5)", "증가(1.5~3)", "급증(≥3)"), "{:.2f}배"),
    StateSpec("vol20", "변동성(20일) 상대 위치", "volatility_20", "quintile",
              labels=("Q1(최저)", "Q2", "Q3", "Q4", "Q5(최고)"), value_format="{:.2%}"),
)
SPEC_BY_KEY = {s.key: s for s in STATE_SPECS}


def _bin_labels(values: pd.Series, spec: StateSpec) -> pd.Series:
    """Left-closed bins: edges (30, 70) -> [-inf,30) [30,70) [70,inf)."""
    arr = values.to_numpy(dtype=float)
    ok = np.isfinite(arr)
    out = pd.Series(index=values.index, dtype=object)
    idx = np.searchsorted(np.asarray(spec.edges), arr[ok], side="right")
    out[ok] = [spec.labels[i] for i in idx]
    return out


def _quintile_labels(values: pd.Series, dates: pd.Series, spec: StateSpec) -> pd.Series:
    clean = values.where(np.isfinite(values.astype(float)))
    pct = clean.groupby(dates).rank(pct=True, method="average")
    q = np.ceil(pct * 5).clip(1, 5)
    out = pd.Series(index=values.index, dtype=object)
    ok = q.notna()
    out[ok] = [spec.labels[int(v) - 1] for v in q[ok]]
    return out


def classify_states(df: pd.DataFrame) -> pd.DataFrame:
    """One ``state_<key>`` column per spec. Quintiles are within ``trade_date``."""
    out = pd.DataFrame(index=df.index)
    for spec in STATE_SPECS:
        values = df[spec.column].astype(float)
        if spec.kind == "bins":
            out[f"state_{spec.key}"] = _bin_labels(values, spec)
        else:
            out[f"state_{spec.key}"] = _quintile_labels(values, df["trade_date"], spec)
    return out


def window_of(ts: pd.Timestamp) -> str | None:
    for name, start, end in WINDOWS:
        if pd.Timestamp(start) <= ts <= pd.Timestamp(end):
            return name
    return None


def base_rate_frame(dataset: pd.DataFrame, horizon: int = 5) -> pd.DataFrame:
    """Rows usable for base rates: validation windows only, end purged.

    The dataset is cut by date FIRST; the last ``horizon`` trade dates are then
    dropped because their label reaches past VALIDATION_END_DATE.
    """
    df = dataset.copy()
    df["trade_date"] = pd.to_datetime(df["trade_date"])
    df = df[(df["trade_date"] >= pd.Timestamp(BASE_RATE_START))
            & (df["trade_date"] <= pd.Timestamp(VALIDATION_END_DATE))]
    dates = sorted(df["trade_date"].unique())
    if horizon > 0:
        dates = dates[:-horizon]
    df = df[df["trade_date"].isin(dates)]
    df = df[df[TARGET_COLUMN].notna() & np.isfinite(df[TARGET_COLUMN].astype(float))]
    df[EXCESS_COLUMN] = df[TARGET_COLUMN] - df.groupby("trade_date")[TARGET_COLUMN].transform("mean")
    df = pd.concat([df, classify_states(df)], axis=1)
    df["window"] = df["trade_date"].map(window_of)
    return df.reset_index(drop=True)


def _verdict(n: int, window_n: dict[str, int], window_mean: dict[str, float], mean: float) -> str:
    if n < MIN_OBS or any(window_n[w] < MIN_OBS_PER_WINDOW for w, _, _ in WINDOWS):
        return "insufficient"
    signs = {np.sign(window_mean[w]) for w, _, _ in WINDOWS}
    if len(signs) != 1 or 0 in signs:
        return "inconsistent"
    return "negligible" if abs(mean) < MIN_EFFECT else "consistent"


def compute_base_rates(frame: pd.DataFrame) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for spec in STATE_SPECS:
        col = f"state_{spec.key}"
        for label in spec.labels:
            sub = frame[frame[col] == label]
            ex = sub[EXCESS_COLUMN]
            window_n = {w: int((sub["window"] == w).sum()) for w, _, _ in WINDOWS}
            window_mean = {
                w: float(sub.loc[sub["window"] == w, EXCESS_COLUMN].mean()) if window_n[w] else float("nan")
                for w, _, _ in WINDOWS
            }
            n = int(len(sub))
            rows.append({
                "state": spec.key, "bucket": label, "n_obs": n,
                "n_dates": int(sub["trade_date"].nunique()),
                "mean_excess": float(ex.mean()) if n else float("nan"),
                "median_excess": float(ex.median()) if n else float("nan"),
                "hit_rate": float((ex > 0).mean()) if n else float("nan"),
                **{f"n_{w}": window_n[w] for w, _, _ in WINDOWS},
                **{f"mean_{w}": window_mean[w] for w, _, _ in WINDOWS},
                "verdict": _verdict(n, window_n, window_mean, float(ex.mean()) if n else float("nan")),
            })
    return rows


def flow_summary(flows: Iterable[Any], asof: date, lookbacks: Sequence[int] = (5, 20)) -> dict[str, Any]:
    """Foreign / institution (8-category sum) net buy over the last N flow days <= asof.

    Display only (item 61). Amounts in 억원; ratio = net buy / trade value.
    """
    days = sorted((d for d in flows if d.trade_date <= asof), key=lambda d: d.trade_date)
    out: dict[str, Any] = {"last_flow_date": days[-1].trade_date.isoformat() if days else None}
    for n in lookbacks:
        recent = days[-n:]
        if len(recent) < n:
            out[f"d{n}"] = None
            continue
        value = sum(d.trade_value_million_krw for d in recent)
        foreign = sum(d.foreign for d in recent)
        inst = sum(d.institution_total for d in recent)
        out[f"d{n}"] = {
            "foreign_eok": foreign / 100.0, "institution_eok": inst / 100.0,
            "foreign_ratio": foreign / value if value else None,
            "institution_ratio": inst / value if value else None,
        }
    return out


def _clean(x: Any) -> Any:
    if isinstance(x, float) and not math.isfinite(x):
        return None
    return x


def build_card(code: str, name: str, decision_date: date, features: pd.Series, states: pd.Series,
               base_rates: list[dict[str, Any]], flows: dict[str, Any], meta: dict[str, Any]) -> dict[str, Any]:
    by_key = {(r["state"], r["bucket"]): r for r in base_rates}
    items = []
    for spec in STATE_SPECS:  # every state, always (item 61)
        bucket = states.get(f"state_{spec.key}")
        value = features.get(spec.column)
        rate = by_key.get((spec.key, bucket)) if isinstance(bucket, str) else None
        items.append({
            "state": spec.key, "title": spec.title, "feature": spec.column,
            "value": _clean(float(value)) if value is not None and pd.notna(value) else None,
            "bucket": bucket if isinstance(bucket, str) else None,
            "base_rate": {k: _clean(v) for k, v in rate.items()} if rate else None,
        })
    return {
        "card": "chart", "layer": "reference", "used_by_model": False,
        "stock_code": code, "name": name, "decision_date": decision_date.isoformat(),
        "states": items, "flows": flows, "base_rate_meta": meta,
    }


def _pp(x: float | None) -> str:
    return "n/a" if x is None else f"{x * 100:+.2f}%p"


def _sign(x: float | None) -> str:
    return "?" if x is None else ("+" if x > 0 else ("−" if x < 0 else "0"))


def render_text(card: dict[str, Any]) -> str:
    meta = card.get("base_rate_meta", {})
    lines = [
        f"[차트 카드] {card['name']}({card['stock_code']}) · 판단일 {card['decision_date']} 종가 기준",
        "  참고 정보 — 모델 점수·순위에 쓰이지 않음",
    ]
    for it in card["states"]:
        spec = SPEC_BY_KEY[it["state"]]
        value = "n/a" if it["value"] is None else spec.value_format.format(it["value"])
        head = f"  · {it['title']}: {value} → {it['bucket'] or '분류 불가'}"
        br = it["base_rate"]
        if br is None:
            lines.append(head)
            continue
        windows = " ".join(f"{w}{_sign(br.get(f'mean_{w}'))}" for w, _, _ in WINDOWS)
        if br["verdict"] == "insufficient":
            tail = f"과거 통계: 표본 부족 (n={br['n_obs']})"
        elif br["verdict"] == "negligible":
            tail = (f"과거 통계: 경향 미미 (평균 {_pp(br['mean_excess'])}, |평균| < {MIN_EFFECT * 100:.1f}%p, "
                    f"n={br['n_obs']})")
        elif br["verdict"] == "inconsistent":
            tail = f"과거 통계: 일관된 경향 없음 ({windows}, n={br['n_obs']})"
        else:
            tail = (f"과거 5일 초과수익 평균 {_pp(br['mean_excess'])}, 플러스 {br['hit_rate']:.0%} "
                    f"(세 구간 일관 {windows}, n={br['n_obs']}, 날짜 {br['n_dates']})")
        lines.append(f"{head}\n      {tail}")
    fl = card.get("flows") or {}
    if fl.get("last_flow_date"):
        parts = []
        for n in (5, 20):
            d = fl.get(f"d{n}")
            if d:
                parts.append(f"{n}일 외국인 {d['foreign_eok']:+,.0f}억 · 기관 {d['institution_eok']:+,.0f}억")
        lines.append(f"  · 수급(~{fl['last_flow_date']}, 표시만): " + (" / ".join(parts) or "기간 부족"))
    cfg = BaselineConfig()
    round_trip = cfg.buy_fee + cfg.sell_fee + cfg.sell_tax + cfg.buy_slippage + cfg.sell_slippage
    lines.append(
        f"  참고: 백테스트 가정 왕복 거래비용 약 {round_trip:.2%}(수수료·세금·슬리피지) — 이보다 작은 차이는 비용을 넘지 못함."
    )
    lines.append(
        f"  읽는 법: 그 상태였던 날 뒤 5거래일(T+1 시가→T+5 종가) 수익률 − 같은 날 유니버스 평균. "
        f"기간 {meta.get('period', '?')}, 유니버스 {meta.get('universe', '?')}(현재 기준 종목 → 생존편향). "
        "과거 통계이지 예측이 아니며, 상태들끼리 겹치므로 독립 근거로 읽지 말 것."
    )
    return "\n".join(lines)
