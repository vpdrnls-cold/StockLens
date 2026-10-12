"""Profile rankings of one decision date as JSON (CURRENT_STATUS item 92, AGENTS.md 43.6).

The survey profile (item 57) re-ranks the frozen model's scores through the item 56
path only: z(model) + lambda * profile tilt, lambda calibrated on the TRAIN period.
``scripts/recommend.py`` computes every number with the same function its
``--profile`` runs use; this module only checks and arranges them, so the viewer can
show a profile's order without the model environment.

The neutral order is the model ranking itself (quant cards, paper log); it is not
repeated here. Nothing in this file changes the paper log, the buffered strategy or
its holdings -- those stay on the neutral ranking. No prices or returns.

Standard library only: the viewer (.venv-ui, no xgboost) imports the file name and notes.
"""

from __future__ import annotations

from datetime import date
import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence

SCHEMA_VERSION = 1
DEFAULT_OUT_ROOT = Path("reports/analyst_cards")  # same folder as the quant cards
FILE_NAME = "profile_ranks.json"
PROFILE_NOTE = ("성향 반영 순위 = 모델 순위 점수 + 성향 기울기(변동성·거래량). 항목 56 검증에서 의도한 방향으로 "
                "작동하고 모델 신호를 유지하는 것만 확인했고, 수익 개선을 뜻하지 않습니다.")
STRATEGY_NOTE = "평가 대상 전략(top-10, buffer 3.0)과 그 보유 목록은 중립(모델 순위) 기준이며 성향으로 바뀌지 않습니다."
TERMS = ("contribution_model", "contribution_risk", "contribution_momentum", "contribution_volume")
SUM_TOLERANCE = 1e-9


def _row(r: Mapping[str, Any]) -> dict[str, Any]:
    out = {"stock_code": str(r["stock_code"]), "name": str(r["name"]), "rank": int(r["rank"]),
           "model_rank": int(r["model_rank"]), "personalized_score": float(r["personalized_score"])}
    out.update({t: float(r[t]) for t in TERMS})
    if not all(math.isfinite(out[k]) for k in ("personalized_score", *TERMS)):
        raise ValueError(f"{out['stock_code']}: non-finite profile score")
    if abs(sum(out[t] for t in TERMS) - out["personalized_score"]) > SUM_TOLERANCE:
        raise ValueError(f"{out['stock_code']}: contributions do not add up to the profile score")
    return out


def build_profile_ranks(
    *,
    decision_date: date,
    profiles: Mapping[str, tuple[float, Sequence[Mapping[str, Any]]]],
    fingerprint_match: bool,
) -> dict[str, Any]:
    """``profiles``: name -> (lambda, one row per stock). Rows carry stock_code, name, rank,
    model_rank, personalized_score and the four contribution terms."""
    body: dict[str, Any] = {}
    for name, (lam, rows) in profiles.items():
        if name == "neutral":
            raise ValueError("the neutral order is the model ranking (quant cards); not stored here")
        clean = sorted((_row(r) for r in rows), key=lambda r: r["rank"])
        if [r["rank"] for r in clean] != list(range(1, len(clean) + 1)):
            raise ValueError(f"{name}: ranks must be 1..n without gaps")
        body[name] = {"lambda": float(lam), "n_stocks": len(clean), "ranks": clean}
    return {
        "card": "profile_ranks",
        "schema_version": SCHEMA_VERSION,
        "layer": "recommendation",
        "decision_date": decision_date.isoformat(),
        "fingerprint_match": bool(fingerprint_match),
        "note": PROFILE_NOTE,
        "strategy_note": STRATEGY_NOTE,
        "profiles": body,
    }


def write_profile_ranks(card: dict[str, Any], out_root: Path = DEFAULT_OUT_ROOT) -> Path:
    folder = Path(out_root) / card["decision_date"].replace("-", "")
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / FILE_NAME
    path.write_text(json.dumps(card, ensure_ascii=False, indent=1, allow_nan=False), encoding="utf-8")
    return path
