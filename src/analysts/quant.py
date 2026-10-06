"""Quant analyst card: the recommendation layer's record as JSON (CURRENT_STATUS item 69, AGENTS.md 43).

The chart card (``src/analysts/chart.py``) is reference information. This card is the
other side of the panel: the frozen daily model's own ranking of one stock on one
decision date, with the exact TreeSHAP terms that produced the score (AGENTS.md 24).

Nothing is computed here. ``build_quant_card`` only arranges values that
``scripts/recommend.py`` has already computed (score, rank, tie size, percentile,
TreeSHAP contributions, fingerprint check, buffered holdings), so the card cannot
disagree with the console output or the paper-trading log. No sentence is
generated beyond fixed labels (AGENTS.md 43.4: numbers come from code).

Keys shared with the chart card: card, layer, used_by_model, stock_code, name,
decision_date. A viewer can read both card types the same way.
"""

from __future__ import annotations

from datetime import date
import json
import math
from pathlib import Path
from typing import Any, Mapping

from src.explanation.model_attribution import FEATURE_LABELS, format_feature_value

SCHEMA_VERSION = 1
SCORE_NOTE = "5일 뒤 수익률 순위에 대한 모델의 상대 점수 — 예상 수익률(%) 아님"
TIE_RULE = "점수 동점이면 종목코드 오름차순"
VALIDATION_STATUS = "forward 평가(2027-01) 전 — 표본 밖 성과 미확인"
NOT_ADVICE = "투자 권유 아님"
DEFAULT_OUT_ROOT = Path("reports/analyst_cards")


def _num(x: Any) -> float | None:
    """Finite float, else None (same rule as the chart card's _clean, for JSON without NaN)."""
    if x is None:
        return None
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def build_quant_card(
    *,
    stock_code: str,
    name: str,
    decision_date: date,
    rank: int,
    n_stocks: int,
    percentile: float,
    score: float,
    tie_size: int,
    features: Mapping[str, Any],
    contributions: Mapping[str, Any],
    best_iteration: int,
    fingerprint_match: bool,
    held_buffered: bool | None,
    held_status: str | None,
    top_n: int,
    buffer_multiplier: float,
    holdings_note: str | None = None,
) -> dict[str, Any]:
    """Arrange already-computed values for one stock into the quant card dict.

    ``contributions`` holds one TreeSHAP term per model feature plus ``bias``
    (``src.explanation.model_attribution.shap_contributions`` row). ``held_buffered``
    and ``held_status`` are None when the run has no buffered holdings (profile runs).
    ``holdings_note`` (optional, item 71) says where the holdings came from on a
    --cards-only run; it adds ``strategy.note`` without changing schema_version.
    """
    terms = {f: float(c) for f, c in contributions.items() if f != "bias"}
    bias = float(contributions["bias"])
    ordered = sorted(terms, key=lambda f: abs(terms[f]), reverse=True)
    drivers = []
    for f in ordered:
        raw = features.get(f)
        value = _num(raw)
        drivers.append({
            "feature": f,
            "label": FEATURE_LABELS[f].name if f in FEATURE_LABELS else f,
            "value": value,
            "value_text": format_feature_value(f, value if value is not None else float("nan")),
            "contribution": _num(terms[f]),
        })
    total = bias + sum(terms.values())

    if held_buffered is None:
        held_status = None

    strategy = {
        "held_buffered": None if held_buffered is None else bool(held_buffered),
        "status": held_status,
        "rule": (f"top-{top_n} 동일가중, 이미 보유한 종목은 {int(buffer_multiplier * top_n)}위 안이면 유지"
                 f"(buffer {buffer_multiplier}), T+1 시가 진입·5거래일 보유"),
    }
    if holdings_note is not None:
        strategy["note"] = holdings_note

    return {
        "card": "quant", "layer": "recommendation", "used_by_model": True,
        "stock_code": stock_code, "name": name, "decision_date": decision_date.isoformat(),
        "schema_version": SCHEMA_VERSION,
        "model": {"best_iteration": int(best_iteration), "fingerprint_match": bool(fingerprint_match)},
        "ranking": {
            "rank": int(rank), "n_stocks": int(n_stocks), "percentile": _num(percentile),
            "score": _num(score), "score_note": SCORE_NOTE,
            "tie_size": int(tie_size), "tied": int(tie_size) > 1, "tie_rule": TIE_RULE,
        },
        "drivers": drivers,  # all features, |contribution| descending -> the first three are the top 3
        "bias": _num(bias),
        "shap_check": {"sum_minus_score": _num(total - float(score))},
        "strategy": strategy,
        "validation_status": VALIDATION_STATUS,
        "disclaimer": NOT_ADVICE,
    }


def write_quant_card(card: dict[str, Any], out_root: Path = DEFAULT_OUT_ROOT) -> Path:
    """Save as <out_root>/<YYYYMMDD>/<code>_quant.json, next to the chart card of the same day."""
    folder = Path(out_root) / card["decision_date"].replace("-", "")
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{card['stock_code']}_quant.json"
    path.write_text(json.dumps(card, ensure_ascii=False, indent=1, allow_nan=False), encoding="utf-8")
    return path
