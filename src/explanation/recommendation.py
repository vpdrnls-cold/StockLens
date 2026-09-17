"""Human-readable explanations for the recommendation layer.

Per AGENTS.md section 10 ("Recommendation is not the same as
Prediction"), the pipeline has a distinct Explanation Layer downstream
of Recommendation. Per AGENTS.md section 24 (Explainability): "The
explanation must be generated from the same signals/features/scores
that affected ranking" and explanations must never be fabricated after
the fact.

This module computes nothing new. It only formats the columns
``src.recommendation.scoring.personalize_scores`` /
``top_n_recommendations`` already produced --
``predicted_return``, ``contribution_risk``, ``contribution_momentum``,
``contribution_volume``, ``personalized_score``, ``rank``, ``profile``
-- into sentences a user can read. If a number does not already exist
on the row, it does not appear in the explanation.

Output text is Korean: unlike the rest of this codebase (docstrings,
identifiers, tests -- all English), this is the one layer whose output
is meant to reach the end user directly rather than a developer, and
StockLens' users and universe (KRX-listed stocks) are Korean.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

REQUIRED_COLUMNS = {
    "trade_date",
    "stock_code",
    "rank",
    "profile",
    "predicted_return",
    "personalized_score",
    "contribution_risk",
    "contribution_momentum",
    "contribution_volume",
}

# Contributions smaller than this (in the same units as personalized_score,
# e.g. 0.0005 = 0.05%p) are treated as "not meaningfully active" and left
# out of the sentence. This keeps a profile whose weight for that term is
# exactly 0.0 (e.g. neutral's risk_weight) -- or merely negligible for
# that stock/date -- from generating a contributor line that says nothing
# ("risk contribution: +0.00%p").
_CONTRIBUTION_EPSILON = 0.0005

_CONTRIBUTOR_LABELS = {
    "contribution_momentum": "모멘텀",
    "contribution_volume": "거래량",
    "contribution_risk": "리스크 페널티",
}

# Fixed display order when magnitudes tie (rare, e.g. both exactly 0
# handled by the epsilon filter already, but keeps output deterministic).
_CONTRIBUTOR_ORDER = ("contribution_momentum", "contribution_volume", "contribution_risk")


@dataclass(frozen=True)
class RecommendationExplanation:
    """One recommendation's explanation.

    ``contributors`` is the same information as ``text`` but structured
    (label, value) pairs sorted by |value| descending -- kept separate
    from the formatted sentence so a future UI can render it as e.g. a
    bar chart without re-parsing text.
    """

    stock_code: str
    trade_date: pd.Timestamp
    rank: int
    profile: str
    predicted_return: float
    personalized_score: float
    contributors: list[tuple[str, float]]
    text: str


def explain_recommendation(row: pd.Series) -> RecommendationExplanation:
    """Turn one row of ``top_n_recommendations()`` output into a
    ``RecommendationExplanation``.

    Raises ``ValueError`` if the row is missing any column this
    explanation depends on -- an explanation must never guess at a
    number it wasn't given (AGENTS.md 24).
    """
    missing = REQUIRED_COLUMNS - set(row.index)
    if missing:
        raise ValueError(f"row is missing required columns: {sorted(missing)}")

    contributors = [
        (_CONTRIBUTOR_LABELS[col], float(row[col]))
        for col in _CONTRIBUTOR_ORDER
        if abs(float(row[col])) >= _CONTRIBUTION_EPSILON
    ]
    contributors.sort(key=lambda item: abs(item[1]), reverse=True)

    return RecommendationExplanation(
        stock_code=str(row["stock_code"]),
        trade_date=row["trade_date"],
        rank=int(row["rank"]),
        profile=str(row["profile"]),
        predicted_return=float(row["predicted_return"]),
        personalized_score=float(row["personalized_score"]),
        contributors=contributors,
        text=_format_text(row, contributors),
    )


def _format_text(row: pd.Series, contributors: list[tuple[str, float]]) -> str:
    date_str = pd.Timestamp(row["trade_date"]).date().isoformat()

    header = (
        f"[{int(row['rank'])}위] {row['stock_code']} ({date_str}, {row['profile']} 프로필) "
        f"— 모델 예측수익률 {row['predicted_return']:+.2%}, "
        f"개인화 점수 {row['personalized_score']:+.2%}"
    )

    if not contributors:
        return header + " (개인화 조정 없음: 이 프로필의 가중치가 전부 0이거나 신호가 미미함)"

    lines = [header + ":"]
    for label, value in contributors:
        lines.append(f"  - {label} 기여: {value:+.2%}p")

    return "\n".join(lines)


def explain_recommendations(recommendations: pd.DataFrame) -> list[RecommendationExplanation]:
    """Explain every row of a ``top_n_recommendations()`` result, in the
    order the rows are given (``top_n_recommendations`` already sorts by
    (trade_date, rank))."""
    return [explain_recommendation(row) for _, row in recommendations.iterrows()]


def format_recommendations_report(recommendations: pd.DataFrame) -> str:
    """Render a full Top-N report as one multi-line string, one
    recommendation's explanation per paragraph."""
    return "\n\n".join(
        explanation.text for explanation in explain_recommendations(recommendations)
    )
