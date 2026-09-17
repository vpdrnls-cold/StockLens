"""Human-readable explanations for the HOLD/SELL position layer.

Companion to ``src.explanation.recommendation`` -- same AGENTS.md 24
principle (never fabricate, only format numbers that already exist).
Every number used here already lives on the ``PositionDecision`` that
``src.portfolio.optimizer.evaluate_position()`` returns
(``unrealized_return``, ``stop_loss_threshold``, ``predicted_return``,
and the ``reason`` string that already encodes *which* rule fired).
This module never re-derives or re-checks those numbers -- it only
turns the already-decided ``PositionDecision`` into a Korean sentence.

Output is Korean for the same reason as
``src.explanation.recommendation``: this is user-facing text, not a
developer-facing log message (``PositionDecision.reason`` stays
English/machine-oriented for that reason, and tests already assert
against its English wording -- this module wraps it rather than
replacing it).
"""

from __future__ import annotations

from src.portfolio.optimizer import Decision, Position, PositionDecision


def explain_position_decision(position: Position, decision: PositionDecision) -> str:
    """Format one ``PositionDecision`` as a Korean sentence.

    ``decision`` must already be the result of
    ``evaluate_position(position, signal, config)`` for the same
    ``position`` -- this function does not call ``evaluate_position``
    itself, so it cannot disagree with the decision it explains.
    """
    is_sell = decision.decision == Decision.SELL
    label = "매도(SELL)" if is_sell else "보유(HOLD)"

    header = (
        f"[{label}] {position.stock_code} — "
        f"보유수익률 {decision.unrealized_return:+.2%}, "
        f"손절선 {decision.stop_loss_threshold:+.2%}, "
        f"모델 예측수익률 {decision.predicted_return:+.2%}"
    )

    if is_sell and "stop-loss" in decision.reason:
        body = (
            f"보유수익률({decision.unrealized_return:+.2%})이 손절선"
            f"({decision.stop_loss_threshold:+.2%}) 아래로 떨어져 손절 규칙이 "
            f"발동했습니다. 모델 예측수익률({decision.predicted_return:+.2%})과 "
            f"무관하게 리스크 관리 규칙이 우선 적용됩니다."
        )
    elif is_sell and "percentile rule" in decision.reason:
        body = (
            f"손절선({decision.stop_loss_threshold:+.2%})에는 아직 도달하지 "
            f"않았지만(현재 보유수익률 {decision.unrealized_return:+.2%}), 이 종목의 "
            f"예측수익률({decision.predicted_return:+.2%})이 오늘 유니버스 내 다른 "
            f"종목들 대비 하위권으로 떨어져 매도 신호가 발생했습니다."
        )
    elif is_sell:
        body = (
            f"손절선({decision.stop_loss_threshold:+.2%})에는 아직 도달하지 "
            f"않았지만(현재 보유수익률 {decision.unrealized_return:+.2%}), 모델이 더 "
            f"이상 양의 수익률을 예측하지 않아(예측수익률 "
            f"{decision.predicted_return:+.2%}) 매도 신호가 발생했습니다."
        )
    else:
        body = (
            f"보유수익률({decision.unrealized_return:+.2%})이 손절선"
            f"({decision.stop_loss_threshold:+.2%})보다 위에 있고, 모델도 여전히 "
            f"양의 수익률({decision.predicted_return:+.2%})을 예측하고 있어 보유를 "
            f"유지합니다."
        )

    return f"{header}\n  {body}"
