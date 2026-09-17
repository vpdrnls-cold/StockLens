from __future__ import annotations

import pandas as pd
import pytest

from src.explanation.recommendation import (
    explain_recommendation,
    explain_recommendations,
    format_recommendations_report,
)
from src.recommendation.scoring import personalize_scores, top_n_recommendations


def _signals() -> pd.DataFrame:
    """Same shape as tests/test_recommendation_scoring.py's fixture:
    stock A has the highest predicted_return but highest volatility and
    no momentum; stock C has more moderate predicted_return but strong
    momentum and unusually high volume.
    """
    rows = [
        ("2024-01-02", "A", 0.03, 0.05, 0.00, 1.0),
        ("2024-01-02", "B", 0.02, 0.01, 0.00, 1.0),
        ("2024-01-02", "C", 0.015, 0.02, 0.05, 2.0),
    ]
    df = pd.DataFrame(
        rows,
        columns=[
            "trade_date",
            "stock_code",
            "predicted_return",
            "volatility_20",
            "price_to_sma_5",
            "volume_ratio_20",
        ],
    )
    df["trade_date"] = pd.to_datetime(df["trade_date"])
    return df


def _top_n(profile: str, n: int = 3) -> pd.DataFrame:
    scored = personalize_scores(_signals(), profile)
    return top_n_recommendations(scored, n=n)


def test_explain_recommendation_rejects_missing_columns() -> None:
    row = _top_n("neutral").iloc[0].drop("personalized_score")

    with pytest.raises(ValueError, match="missing required columns"):
        explain_recommendation(row)


def test_neutral_profile_has_no_active_contributors() -> None:
    # neutral's weights are all 0.0, so every contribution column is
    # exactly 0.0 and none should clear the epsilon filter.
    row = _top_n("neutral").iloc[0]
    explanation = explain_recommendation(row)

    assert explanation.contributors == []
    assert "개인화 조정 없음" in explanation.text


def test_aggressive_profile_surfaces_momentum_and_volume_contributors() -> None:
    top = _top_n("aggressive")
    row = top[top["stock_code"] == "C"].iloc[0]

    explanation = explain_recommendation(row)

    labels = [label for label, _ in explanation.contributors]
    assert "모멘텀" in labels
    assert "거래량" in labels
    # aggressive's risk_weight is 0.0, so no risk penalty line.
    assert "리스크 페널티" not in labels


def test_contributors_sorted_by_magnitude_descending() -> None:
    top = _top_n("aggressive")
    row = top[top["stock_code"] == "C"].iloc[0]

    explanation = explain_recommendation(row)
    magnitudes = [abs(value) for _, value in explanation.contributors]

    assert magnitudes == sorted(magnitudes, reverse=True)


def test_conservative_profile_surfaces_risk_penalty_for_high_volatility_stock() -> None:
    top = _top_n("conservative")
    row = top[top["stock_code"] == "A"].iloc[0]  # A has the highest volatility_20

    explanation = explain_recommendation(row)

    labels = [label for label, _ in explanation.contributors]
    assert "리스크 페널티" in labels
    # It's a penalty, so it must be negative.
    risk_value = dict(explanation.contributors)["리스크 페널티"]
    assert risk_value < 0


def test_text_reports_rank_stock_code_and_predicted_return() -> None:
    top = _top_n("neutral")
    row = top[top["stock_code"] == "A"].iloc[0]  # neutral ranks by raw predicted_return -> A is #1

    explanation = explain_recommendation(row)

    assert explanation.rank == 1
    assert "A" in explanation.text
    assert "3.00%" in explanation.text  # predicted_return = 0.03


def test_explain_recommendations_preserves_row_order() -> None:
    top = _top_n("neutral")
    explanations = explain_recommendations(top)

    assert [e.stock_code for e in explanations] == list(top["stock_code"])
    assert [e.rank for e in explanations] == list(top["rank"])


def test_format_recommendations_report_joins_all_explanations() -> None:
    top = _top_n("neutral", n=2)
    report = format_recommendations_report(top)

    assert report.count("위]") == 2  # one "[N위]" header per recommendation
    assert "\n\n" in report
