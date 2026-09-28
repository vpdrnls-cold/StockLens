"""Per-stock attribution of the daily model's score (explanation layer, item 51).

AGENTS.md 24: an explanation must come from the same numbers that produced
the ranking. The daily model is an XGBoost tree ensemble, so its prediction
decomposes exactly into per-feature TreeSHAP contributions plus a constant:

    score(stock, T) = bias + sum_f contribution_f(stock, T)

``shap_contributions`` returns those terms from XGBoost itself
(``pred_contribs=True``) over the same boosting rounds ``predict`` uses, and
``tests/test_model_attribution.py`` checks that they add back up to the score.
Nothing here is re-estimated or approximated.

What the numbers mean: the model is trained on the per-date RANK of the 5-day
return (item 38), so a contribution moves the stock's expected cross-sectional
rank, not a return in percent. The text therefore says "raises/lowers the
ranking score" and never "expected return".
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
import xgboost as xgb

from src.models.predict import TrainedModel


@dataclass(frozen=True)
class FeatureLabel:
    name: str   # Korean label shown to the user
    kind: str   # "pct" (fraction -> %), "ratio" (x), "level" (plain number)


FEATURE_LABELS: dict[str, FeatureLabel] = {
    "return_1d": FeatureLabel("전일 대비 수익률", "pct"),
    "return_5d": FeatureLabel("최근 5일 수익률", "pct"),
    "return_10d": FeatureLabel("최근 10일 수익률", "pct"),
    "return_20d": FeatureLabel("최근 20일 수익률", "pct"),
    "intraday_return": FeatureLabel("당일 시가→종가", "pct"),
    "high_low_range": FeatureLabel("당일 고저 폭", "pct"),
    "gap": FeatureLabel("시가 갭(전일 종가 대비)", "pct"),
    "price_to_sma_5": FeatureLabel("5일 이동평균 대비 괴리", "pct"),
    "price_to_sma_20": FeatureLabel("20일 이동평균 대비 괴리", "pct"),
    "price_to_sma_60": FeatureLabel("60일 이동평균 대비 괴리", "pct"),
    "rsi_14": FeatureLabel("RSI(14)", "level"),
    "roc_10": FeatureLabel("10일 변화율", "pct"),
    "roc_20": FeatureLabel("20일 변화율", "pct"),
    "volatility_5": FeatureLabel("5일 변동성", "pct"),
    "volatility_20": FeatureLabel("20일 변동성", "pct"),
    "atr_pct": FeatureLabel("ATR(가격 대비)", "pct"),
    "macd_hist_pct": FeatureLabel("MACD 히스토그램(가격 대비)", "pct"),
    "volume_change_1d": FeatureLabel("거래량 전일 대비", "pct"),
    "volume_ratio_20": FeatureLabel("거래량(20일 평균 대비)", "ratio"),
}


def format_feature_value(feature: str, value: float) -> str:
    if value is None or not np.isfinite(value):
        return "값 없음"
    label = FEATURE_LABELS.get(feature, FeatureLabel(feature, "level"))
    if label.kind == "pct":
        return f"{value:+.1%}"
    if label.kind == "ratio":
        return f"{value:.2f}배"
    return f"{value:.1f}"


def shap_contributions(trained: TrainedModel, X: pd.DataFrame) -> pd.DataFrame:
    """Exact TreeSHAP terms per row: one column per model feature plus ``bias``.

    Uses the same boosting rounds as ``trained.model.predict`` (0 through
    ``best_iteration``), so ``contribs.sum(axis=1)`` equals the model score.
    """
    cols = list(trained.feature_columns)
    dmat = xgb.DMatrix(X[cols].astype(float), feature_names=cols, missing=np.nan)
    raw = trained.model.get_booster().predict(
        dmat, pred_contribs=True, iteration_range=(0, trained.best_iteration + 1)
    )
    return pd.DataFrame(raw, columns=cols + ["bias"], index=X.index)


@dataclass(frozen=True)
class PickExplanation:
    stock_code: str
    name: str
    rank: int
    score: float
    percentile: float
    drivers: list[tuple[str, float, float]]  # (feature, contribution, feature value)
    text: str


def explain_pick(
    *,
    stock_code: str,
    name: str,
    rank: int,
    score: float,
    percentile: float,
    n_stocks: int,
    features: pd.Series,
    contributions: pd.Series,
    top_k: int = 3,
) -> PickExplanation:
    """Sentence-level explanation from the pick's own TreeSHAP terms."""
    terms = contributions.drop(labels=["bias"], errors="ignore")
    top = terms.reindex(terms.abs().sort_values(ascending=False).index)[:top_k]
    drivers = [(f, float(c), float(features.get(f, np.nan))) for f, c in top.items()]

    title = f"{name}({stock_code})" if name and name != stock_code else stock_code
    lines = [f"[{rank}위/{n_stocks}종목] {title} — 랭킹 점수 {score:+.4f}"]
    for f, c, v in drivers:
        label = FEATURE_LABELS.get(f, FeatureLabel(f, "level")).name
        effect = "끌어올림" if c > 0 else "끌어내림"
        lines.append(f"  - {label} {format_feature_value(f, v)} → 점수 {c:+.4f} ({effect})")
    return PickExplanation(stock_code, name, rank, score, percentile, drivers, "\n".join(lines))
