"""Data side of the web survey page (CURRENT_STATUS item 91).

The questions, scoring, warning and eligibility rules all live in
``src/recommendation/survey.py`` (item 57); this module only turns widget values
into that module's inputs. No Streamlit import, so it is tested in the main
environment; ``app/survey_page.py`` only lays it out.
"""

from __future__ import annotations

import os
from pathlib import Path

from src.recommendation.survey import QUESTIONS, SurveyResult, evaluate, needs_warning
from src.ui.viewer_data import PROFILE_PATH

PROFILE_PATH_ENV = "STOCKLENS_PROFILE_PATH"  # test runs only; normal use keeps data/user_profile.json
ACK_OPTIONS = ("예, 진행합니다", "아니오")


def profile_path(root: Path) -> Path:
    """Where the survey result is saved and read -- one place for both pages."""
    return Path(os.environ.get(PROFILE_PATH_ENV, root / PROFILE_PATH))


def unanswered(selections: dict[str, int | None]) -> list[str]:
    """Question keys without a choice yet (radios start with nothing selected)."""
    return [q.key for q in QUESTIONS if selections.get(q.key) is None]


def ack_value(choice: str | None) -> bool | None:
    """Warning radio label -> ``warning_acknowledged`` (None = not answered yet)."""
    if choice is None:
        return None
    return choice == ACK_OPTIONS[0]


def form_problem(selections: dict[str, int | None], ack_choice: str | None) -> str | None:
    """Why the form cannot be scored yet, or None when it can."""
    missing = unanswered(selections)
    if missing:
        return f"아직 답하지 않은 문항: {', '.join(missing)}"
    if needs_warning(selections) and ack_choice is None:
        return "Q3 경고에 '예' 또는 '아니오'로 답해 주세요."
    return None


def score_form(selections: dict[str, int | None], ack_choice: str | None) -> SurveyResult:
    """Same result as ``scripts/survey.py`` for the same answers. Call only when form_problem() is None."""
    problem = form_problem(selections, ack_choice)
    if problem:
        raise ValueError(problem)
    answers = {q.key: int(selections[q.key]) for q in QUESTIONS}
    ack = ack_value(ack_choice) if needs_warning(answers) else None
    return evaluate(answers, warning_acknowledged=ack)
