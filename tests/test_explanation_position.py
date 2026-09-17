from __future__ import annotations

from src.explanation.position import explain_position_decision
from src.portfolio.optimizer import (
    Position,
    PositionConfig,
    PositionSignal,
    evaluate_position,
)


def test_hold_explanation_mentions_hold_and_both_numbers() -> None:
    # predicted_return_percentile=0.5 is well above the default 0.20
    # percentile-reversal threshold (CURRENT_STATUS.md items 20/21), so
    # it doesn't fire here either.
    position = Position(stock_code="A", entry_price=10_000.0)
    signal = PositionSignal(
        current_price=10_200.0, predicted_return=0.02, atr_pct=0.02, predicted_return_percentile=0.5
    )

    decision = evaluate_position(position, signal)
    text = explain_position_decision(position, decision)

    assert "[보유(HOLD)]" in text
    assert "A" in text
    assert "2.00%" in text  # unrealized_return


def test_stop_loss_sell_explanation_mentions_stop_loss() -> None:
    # predicted_return_percentile is required by evaluate_position's
    # validation even though stop-loss is what actually decides this
    # case -- 0.9 is far from the reversal cutoff so it stays that way.
    position = Position(stock_code="A", entry_price=10_000.0)
    signal = PositionSignal(
        current_price=9_000.0, predicted_return=0.01, atr_pct=0.02, predicted_return_percentile=0.9
    )

    decision = evaluate_position(position, signal)
    text = explain_position_decision(position, decision)

    assert "[매도(SELL)]" in text
    assert "손절" in text
    # Must not claim signal reversal when the real trigger was stop-loss.
    assert "더 이상 양의 수익률" not in text


def test_signal_reversal_sell_explanation_mentions_model_signal() -> None:
    # The absolute rule is opt-in since items 20/21 made the percentile
    # rule the default -- sell_percentile_threshold=None switches back
    # to it explicitly so this test still exercises the absolute-rule
    # explanation wording.
    position = Position(stock_code="A", entry_price=10_000.0)
    signal = PositionSignal(current_price=9_900.0, predicted_return=-0.01, atr_pct=0.05)
    config = PositionConfig(sell_percentile_threshold=None)

    decision = evaluate_position(position, signal, config=config)
    text = explain_position_decision(position, decision)

    assert "[매도(SELL)]" in text
    assert "더 이상 양의 수익률" in text
    # Must not claim stop-loss when the real trigger was signal reversal.
    assert "손절 규칙이" not in text


def test_explanation_reflects_custom_config_thresholds() -> None:
    # predicted_return_percentile=0.9 keeps the (now-default) percentile
    # reversal rule from firing on its own, so this test isolates the
    # stop-loss multiplier as originally intended.
    position = Position(stock_code="A", entry_price=10_000.0)
    signal = PositionSignal(
        current_price=9_600.0, predicted_return=0.01, atr_pct=0.02, predicted_return_percentile=0.9
    )

    default_decision = evaluate_position(position, signal)
    assert "[보유(HOLD)]" in explain_position_decision(position, default_decision)

    tight_decision = evaluate_position(
        position, signal, config=PositionConfig(stop_loss_atr_multiple=1.0)
    )
    tight_text = explain_position_decision(position, tight_decision)
    assert "[매도(SELL)]" in tight_text
    assert "-2.00%" in tight_text  # stop_loss_threshold = -1.0 * atr_pct(0.02)
