"""Position-level HOLD/SELL decision layer.

This is the original roadmap's "Phase 4: 동적 투자 판단(상승확률·목표가·
위험가 기반 HOLD/SELL/BUY 로직)" concept, scoped correctly per
CURRENT_STATUS.md's "User Feedback / Outcome Learning" section:

    "Do NOT immediately change the market prediction model after one
    successful or failed trade. User behavior is noisy. Market
    prediction and user-preference learning should remain
    conceptually separate."

So this module NEVER retrains or otherwise touches
``src.models.predict``. It only takes:

- a ``Position`` the user says they already hold (stock + entry
  price), and
- a ``PositionSignal``: the SAME already-computed daily
  prediction/signal for that stock that the recommendation layer
  uses for everyone else, on the current decision date,

and applies transparent, explainable rules to decide HOLD vs SELL for
that one position:

1.  stop-loss: if the position's unrealized return has fallen through
    a threshold sized by that stock's OWN recent volatility
    (``atr_pct``), sell regardless of what the model currently
    predicts. This is a risk-control rule, not a signal.
2.  signal reversal: otherwise, if the model no longer predicts a
    positive forward return for this stock, sell -- the reason to
    keep holding (an expected positive move) is gone.
3.  otherwise: hold.

Every decision carries the numbers that produced it (AGENTS.md 24,
Explainability) -- never a bare HOLD/SELL with no justification.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Decision(str, Enum):
    HOLD = "HOLD"
    SELL = "SELL"


@dataclass(frozen=True)
class PositionConfig:
    """Thresholds for the HOLD/SELL rules. Defaults are a starting
    point, not a validated result -- see the module docstring's note
    on AGENTS.md 9's "do not hard-code and call it scientifically
    valid" principle, which applies here just as much as to
    personalization weights.
    """

    stop_loss_atr_multiple: float = 3.0
    sell_predicted_return_threshold: float = 0.0


@dataclass(frozen=True)
class Position:
    """A position the user says they hold. No purchase timestamp is
    required by this layer -- only the price, which is all the
    stop-loss rule needs.
    """

    stock_code: str
    entry_price: float


@dataclass(frozen=True)
class PositionSignal:
    """The latest, already-computed daily signal for one stock.

    This is exactly the same kind of row the recommendation layer
    consumes for every stock (predicted_return from
    src.models.predict, atr_pct from src.features.engineering) --
    nothing new is computed for this layer, and nothing here triggers
    retraining.
    """

    current_price: float
    predicted_return: float
    atr_pct: float


@dataclass(frozen=True)
class PositionDecision:
    decision: Decision
    reason: str
    unrealized_return: float
    stop_loss_threshold: float
    predicted_return: float


def evaluate_position(
    position: Position,
    signal: PositionSignal,
    config: PositionConfig | None = None,
) -> PositionDecision:
    """Decide HOLD or SELL for one already-held position.

    Raises ValueError on non-positive prices or a negative
    ``atr_pct`` -- these would indicate a data problem upstream, not a
    real trading state.
    """
    config = config or PositionConfig()

    if position.entry_price <= 0:
        raise ValueError("entry_price must be positive.")
    if signal.current_price <= 0:
        raise ValueError("current_price must be positive.")
    if signal.atr_pct < 0:
        raise ValueError("atr_pct must not be negative.")

    unrealized_return = signal.current_price / position.entry_price - 1.0
    stop_loss_threshold = -config.stop_loss_atr_multiple * signal.atr_pct

    if unrealized_return <= stop_loss_threshold:
        return PositionDecision(
            decision=Decision.SELL,
            reason=(
                f"stop-loss triggered: unrealized return "
                f"{unrealized_return:+.2%} <= threshold "
                f"{stop_loss_threshold:+.2%} "
                f"({config.stop_loss_atr_multiple:g}x current ATR%)"
            ),
            unrealized_return=unrealized_return,
            stop_loss_threshold=stop_loss_threshold,
            predicted_return=signal.predicted_return,
        )

    if signal.predicted_return <= config.sell_predicted_return_threshold:
        return PositionDecision(
            decision=Decision.SELL,
            reason=(
                f"model signal no longer favorable: predicted_return "
                f"{signal.predicted_return:+.4f} <= threshold "
                f"{config.sell_predicted_return_threshold:+.4f}"
            ),
            unrealized_return=unrealized_return,
            stop_loss_threshold=stop_loss_threshold,
            predicted_return=signal.predicted_return,
        )

    return PositionDecision(
        decision=Decision.HOLD,
        reason=(
            f"unrealized return {unrealized_return:+.2%} is above the "
            f"stop-loss threshold {stop_loss_threshold:+.2%} and the "
            f"model still predicts a positive return "
            f"({signal.predicted_return:+.4f})"
        ),
        unrealized_return=unrealized_return,
        stop_loss_threshold=stop_loss_threshold,
        predicted_return=signal.predicted_return,
    )
