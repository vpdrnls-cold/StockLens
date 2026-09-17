from __future__ import annotations

import pytest

from src.portfolio.optimizer import (
    Decision,
    Position,
    PositionConfig,
    PositionSignal,
    evaluate_position,
)


def test_hold_when_within_stop_loss_and_signal_still_positive() -> None:
    position = Position(stock_code="A", entry_price=10_000.0)
    signal = PositionSignal(current_price=10_200.0, predicted_return=0.02, atr_pct=0.02)

    result = evaluate_position(position, signal)

    assert result.decision == Decision.HOLD
    assert result.unrealized_return == pytest.approx(0.02)


def test_sell_on_stop_loss_even_if_model_still_predicts_a_gain() -> None:
    # atr_pct=0.02, default 3x multiple -> stop-loss threshold = -6%.
    # Price has dropped 10%, well past it, even though predicted_return
    # is still positive: risk control overrides the model signal.
    position = Position(stock_code="A", entry_price=10_000.0)
    signal = PositionSignal(current_price=9_000.0, predicted_return=0.01, atr_pct=0.02)

    result = evaluate_position(position, signal)

    assert result.decision == Decision.SELL
    assert "stop-loss" in result.reason
    assert result.unrealized_return == pytest.approx(-0.10)
    assert result.stop_loss_threshold == pytest.approx(-0.06)


def test_sell_on_signal_reversal_when_still_above_stop_loss() -> None:
    # Small unrealized loss, well above the stop-loss line, but the
    # model no longer predicts a positive return for this stock.
    position = Position(stock_code="A", entry_price=10_000.0)
    signal = PositionSignal(current_price=9_900.0, predicted_return=-0.01, atr_pct=0.05)

    result = evaluate_position(position, signal)

    assert result.decision == Decision.SELL
    assert "model signal" in result.reason


def test_custom_config_changes_thresholds() -> None:
    position = Position(stock_code="A", entry_price=10_000.0)
    # -4% unrealized return; default 3x*atr_pct(0.02)=-6% would HOLD,
    # but a tighter 1x multiple makes the stop-loss threshold -2%.
    signal = PositionSignal(current_price=9_600.0, predicted_return=0.01, atr_pct=0.02)

    default_result = evaluate_position(position, signal)
    assert default_result.decision == Decision.HOLD

    tight_result = evaluate_position(
        position, signal, config=PositionConfig(stop_loss_atr_multiple=1.0)
    )
    assert tight_result.decision == Decision.SELL


def test_rejects_non_positive_entry_price() -> None:
    signal = PositionSignal(current_price=100.0, predicted_return=0.01, atr_pct=0.02)
    with pytest.raises(ValueError, match="entry_price"):
        evaluate_position(Position(stock_code="A", entry_price=0.0), signal)


def test_rejects_non_positive_current_price() -> None:
    signal = PositionSignal(current_price=0.0, predicted_return=0.01, atr_pct=0.02)
    with pytest.raises(ValueError, match="current_price"):
        evaluate_position(Position(stock_code="A", entry_price=100.0), signal)


def test_rejects_negative_atr_pct() -> None:
    signal = PositionSignal(current_price=100.0, predicted_return=0.01, atr_pct=-0.01)
    with pytest.raises(ValueError, match="atr_pct"):
        evaluate_position(Position(stock_code="A", entry_price=100.0), signal)
