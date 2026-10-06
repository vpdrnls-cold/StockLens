"""Questionnaire -> profile mapping (CURRENT_STATUS item 57)."""

from __future__ import annotations

import pytest

from src.recommendation import survey as sv


def A(*one_based: int) -> dict[str, int]:
    """Answers as 1-based option numbers for Q1..Q6."""
    return {q.key: i - 1 for q, i in zip(sv.QUESTIONS, one_based)}


def test_design_constants_are_fixed():
    assert sv.CONSERVATIVE_MAX == 0.4 and sv.NEUTRAL_MAX == 0.7
    assert sv.AGGRESSIVE_MIN_EXPERIENCE == 2
    assert [q.key for q in sv.QUESTIONS] == ["Q1", "Q2", "Q3", "Q4", "Q5", "Q6"]
    assert [len(q.options) for q in sv.QUESTIONS] == [4, 4, 5, 4, 4, 4]


@pytest.mark.parametrize("answers,reason", [
    (A(1, 4, 5, 4, 4, 4), "Q1"),  # money needed within a month
    (A(4, 1, 5, 4, 4, 4), "Q2"),  # loss would hit living costs
    (A(4, 4, 1, 4, 4, 4), "Q3"),  # cannot accept any loss
])
def test_disqualifying_options(answers, reason):
    r = sv.evaluate(answers)
    assert not r.eligible and r.profile is None
    assert any(x.startswith(reason) for x in r.reasons)


def test_ten_percent_requires_acknowledgement_and_is_capped():
    answers = A(4, 4, 2, 4, 4, 4)  # everything maximal except Q3 = max 10%
    assert sv.needs_warning(answers)
    assert not sv.evaluate(answers).eligible
    assert not sv.evaluate(answers, warning_acknowledged=False).eligible
    r = sv.evaluate(answers, warning_acknowledged=True)
    assert r.eligible and r.profile == "conservative"
    assert r.warning_shown and r.warning_acknowledged is True
    # tolerance alone would have allowed neutral: (0+3+3)/9 = 0.67
    assert r.tolerance == pytest.approx(6 / 9)


def test_min_of_capacity_and_tolerance_decides():
    # capacity max (1.0), tolerance low -> tolerance binds
    r = sv.evaluate(A(4, 4, 3, 1, 1, 4))  # tolerance (1+0+0)/9
    assert r.binding == "tolerance" and r.profile == "conservative"
    # tolerance max, capacity minimal (2/6) -> capacity binds
    r = sv.evaluate(A(2, 2, 5, 4, 4, 4))
    assert r.binding == "capacity" and r.score == pytest.approx(2 / 6) and r.profile == "conservative"


def test_profile_boundaries():
    # capacity 1.0; tolerance chosen to hit each band
    assert sv.evaluate(A(4, 4, 3, 2, 2, 4)).profile == "conservative"  # (1+1+1)/9 = 0.33
    assert sv.evaluate(A(4, 4, 4, 2, 2, 4)).profile == "neutral"  # (2+1+1)/9 = 0.44
    assert sv.evaluate(A(4, 4, 4, 3, 3, 4)).profile == "neutral"  # (2+2+2)/9 = 0.67
    assert sv.evaluate(A(4, 4, 5, 3, 3, 4)).profile == "aggressive"  # (3+2+2)/9 = 0.78, exp 3y+
    assert sv.evaluate(A(4, 4, 5, 3, 3, 3)).profile == "aggressive"  # experience 1~3y is enough


def test_aggressive_needs_experience():
    r = sv.evaluate(A(4, 4, 5, 4, 4, 2))  # s = 1.0 but < 1 year
    assert r.profile == "neutral"
    assert any("1년 미만" in x for x in r.reasons)


def test_invalid_answers_rejected():
    with pytest.raises(ValueError, match="missing"):
        sv.evaluate({"Q1": 0})
    bad = A(4, 4, 5, 4, 4, 4)
    bad["Q3"] = 5
    with pytest.raises(ValueError, match="out of range"):
        sv.evaluate(bad)


def test_save_load_roundtrip_and_version(tmp_path):
    r = sv.evaluate(A(3, 3, 4, 3, 3, 3))
    p = sv.save(r, tmp_path / "p.json")
    back = sv.load(p)
    assert back.profile == r.profile and back.answers == r.answers
    p.write_text(p.read_text(encoding="utf-8").replace(sv.SURVEY_VERSION, "old"), encoding="utf-8")
    with pytest.raises(ValueError, match="version"):
        sv.load(p)


def test_explain_mentions_numbers_and_limits():
    text = sv.explain(sv.evaluate(A(4, 4, 3, 2, 2, 4)))
    assert "안정형" in text and "손실이 작다는 보장은 없습니다" in text
    assert "모델 참고 순위를 제공하지 않습니다" in sv.explain(sv.evaluate(A(1, 4, 5, 4, 4, 4)))
