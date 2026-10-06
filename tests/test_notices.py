"""User-facing wording of the model ranking (CURRENT_STATUS item 77)."""
from __future__ import annotations

import ast
from pathlib import Path

from src.analysts import notices
from src.recommendation import survey

ROOT = Path(__file__).resolve().parents[1]
SCREENS = ("app/viewer.py", "src/ui/viewer_data.py", "scripts/recommend.py", "scripts/survey.py",
           "src/recommendation/survey.py", "src/analysts/quant.py")


def _string_constants(path: Path) -> list[str]:
    """String literals that are not docstrings."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    docstrings = {id(n.body[0].value) for n in ast.walk(tree)
                  if isinstance(n, (ast.Module, ast.FunctionDef, ast.ClassDef)) and n.body
                  and isinstance(n.body[0], ast.Expr) and isinstance(n.body[0].value, ast.Constant)}
    return [n.value for n in ast.walk(tree)
            if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in docstrings]


def test_no_screen_calls_the_ranking_a_recommendation() -> None:
    hits = {f: [s for s in _string_constants(ROOT / f) if "추천" in s] for f in SCREENS}
    assert not any(hits.values()), {f: h for f, h in hits.items() if h}


def test_notice_states_the_known_facts() -> None:
    text = notices.REFERENCE_RANK_NOTICE
    for fact in ("참고 순위", "표본 밖 성과는 아직 확인되지 않았", "2027년 1월", "시장 평균보다 낮았", "투자 권유가 아닙니다"):
        assert fact in text
    assert "시장 평균보다 낮았습니다" in survey.RISK_NOTICE and "참고 순위" in survey.RISK_NOTICE
