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
    # predicted_return_percentile=0.5 is well above the default 0.20
    # percentile-reversal threshold, so the percentile rule (now the
    # default, CURRENT_STATUS.md items 20/21) doesn't fire either.
    position = Position(stock_code="A", entry_price=10_000.0)
    signal = PositionSignal(
        current_price=10_200.0,
        predicted_return=0.02,
        atr_pct=0.02,
        predicted_return_percentile=0.5,
    )

    result = evaluate_position(position, signal)

    assert result.decision == Decision.HOLD
    assert result.unrealized_return == pytest.approx(0.02)


def test_sell_on_stop_loss_even_if_model_still_predicts_a_gain() -> None:
    # atr_pct=0.02, default 3x multiple -> stop-loss threshold = -6%.
    # Price has dropped 10%, well past it, even though predicted_return
    # is still positive and predicted_return_percentile (0.9) is nowhere
    # near the reversal cutoff: risk control overrides the model signal
    # regardless of which reversal variant is configured.
    position = Position(stock_code="A", entry_price=10_000.0)
    signal = PositionSignal(
        current_price=9_000.0,
        predicted_return=0.01,
        atr_pct=0.02,
        predicted_return_percentile=0.9,
    )

    result = evaluate_position(position, signal)

    assert result.decision == Decision.SELL
    assert "stop-loss" in result.reason
    assert result.unrealized_return == pytest.approx(-0.10)
    assert result.stop_loss_threshold == pytest.approx(-0.06)


def test_sell_on_signal_reversal_absolute_rule_when_opted_in() -> None:
    # The absolute rule is opt-in since items 20/21 made the percentile
    # rule the default -- sell_percentile_threshold=None switches back
    # to it explicitly. Small unrealized loss, well above the
    # stop-loss line, but the model no longer predicts a positive
    # return for this stock.
    position = Position(stock_code="A", entry_price=10_000.0)
    signal = PositionSignal(current_price=9_900.0, predicted_return=-0.01, atr_pct=0.05)
    config = PositionConfig(sell_percentile_threshold=None)

    result = evaluate_position(position, signal, config=config)

    assert result.decision == Decision.SELL
    assert "model signal" in result.reason


def test_custom_config_changes_thresholds() -> None:
    position = Position(stock_code="A", entry_price=10_000.0)
    # -4% unrealized return; default 3x*atr_pct(0.02)=-6% would HOLD,
    # but a tighter 1x multiple makes the stop-loss threshold -2%.
    # predicted_return_percentile=0.9 keeps the (now-default) percentile
    # reversal rule from firing on its own, so this test isolates the
    # stop-loss multiplier as originally intended.
    signal = PositionSignal(
        current_price=9_600.0,
        predicted_return=0.01,
        atr_pct=0.02,
        predicted_return_percentile=0.9,
    )

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


def test_percentile_rule_sells_when_at_or_below_threshold() -> None:
    # Still above the stop-loss line and predicted_return is positive
    # (the absolute rule would HOLD), but this stock ranked in the
    # bottom 20% of its universe today.
    position = Position(stock_code="A", entry_price=10_000.0)
    signal = PositionSignal(
        current_price=9_900.0,
        predicted_return=0.005,
        atr_pct=0.05,
        predicted_return_percentile=0.15,
    )
    config = PositionConfig(sell_percentile_threshold=0.20)

    result = evaluate_position(position, signal, config=config)

    assert result.decision == Decision.SELL
    assert "percentile rule" in result.reason


def test_percentile_rule_holds_when_above_threshold() -> None:
    position = Position(stock_code="A", entry_price=10_000.0)
    signal = PositionSignal(
        current_price=9_900.0,
        predicted_return=0.005,
        atr_pct=0.05,
        predicted_return_percentile=0.50,
    )
    config = PositionConfig(sell_percentile_threshold=0.20)

    result = evaluate_position(position, signal, config=config)

    assert result.decision == Decision.HOLD


def test_percentile_rule_ignores_absolute_threshold() -> None:
    # predicted_return is negative (would trigger the absolute rule),
    # but the percentile rule is the one active and this stock still
    # ranks above the cutoff -- percentile rule wins, HOLD.
    position = Position(stock_code="A", entry_price=10_000.0)
    signal = PositionSignal(
        current_price=9_900.0,
        predicted_return=-0.01,
        atr_pct=0.05,
        predicted_return_percentile=0.80,
    )
    config = PositionConfig(sell_predicted_return_threshold=0.0, sell_percentile_threshold=0.20)

    result = evaluate_position(position, signal, config=config)

    assert result.decision == Decision.HOLD


def test_percentile_rule_requires_percentile_on_signal() -> None:
    position = Position(stock_code="A", entry_price=10_000.0)
    signal = PositionSignal(current_price=9_900.0, predicted_return=0.01, atr_pct=0.05)
    config = PositionConfig(sell_percentile_threshold=0.20)

    with pytest.raises(ValueError, match="predicted_return_percentile"):
        evaluate_position(position, signal, config=config)


def test_percentile_threshold_must_be_within_unit_interval() -> None:
    position = Position(stock_code="A", entry_price=10_000.0)
    signal = PositionSignal(
        current_price=9_900.0, predicted_return=0.01, atr_pct=0.05, predicted_return_percentile=0.5
    )
    config = PositionConfig(sell_percentile_threshold=1.5)

    with pytest.raises(ValueError, match="sell_percentile_threshold"):
        evaluate_position(position, signal, config=config)


def test_stop_loss_still_takes_priority_over_percentile_rule() -> None:
    # Deep unrealized loss past stop-loss, even though percentile is
    # high (this stock is the best in today's universe) -- stop-loss
    # is checked first regardless of the reversal variant.
    position = Position(stock_code="A", entry_price=10_000.0)
    signal = PositionSignal(
        current_price=9_000.0,
        predicted_return=0.01,
        atr_pct=0.02,
        predicted_return_percentile=1.0,
    )
    config = PositionConfig(sell_percentile_threshold=0.20)

    result = evaluate_position(position, signal, config=config)

    assert result.decision == Decision.SELL
    assert "stop-loss" in result.reason
