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
2.  signal reversal: otherwise, if the model's signal for this stock
    has deteriorated, sell -- the reason to keep holding (an expected
    positive move) is gone.
3.  otherwise: hold.

Signal-reversal rule, two selectable variants (``PositionConfig``
picks one -- see its docstring):

- percentile (default, ``sell_percentile_threshold=0.20``): sell if
  this stock's predicted_return ranks at or below the 20th percentile
  of that day's universe (0.0 = worst that day, 1.0 = best). AGENTS.md
  22 already treats this model's output as trustworthy only for
  cross-sectional ranking (rank IC), not as an absolute quantity, and
  this variant applies that same standard here: it asks "has this
  stock fallen behind its peers today?" instead of "is the raw number
  negative?". Validated in CURRENT_STATUS.md items 20/21 via
  walk-forward on two independent machines -- see
  ``scripts/evaluate_signal_reversal_thresholds.py`` and
  ``scripts/walk_forward_signal_reversal.py``.
- absolute (opt-in, ``sell_percentile_threshold=None``): sell if
  ``predicted_return <= sell_predicted_return_threshold``. Treats the
  model's raw predicted return as a meaningful, zero-anchored number.
  CURRENT_STATUS.md item 17 found this fires on <1% of trades and,
  isolated, makes cum_return worse for no mdd benefit -- kept only for
  backward compatibility, not recommended for new code.

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

    ``sell_percentile_threshold`` selects the signal-reversal variant:

    - a float in ``[0.0, 1.0]`` (default ``0.20``): use the percentile
      rule against ``PositionSignal.predicted_return_percentile`` --
      ``evaluate_position`` then requires that field to be set.
      CURRENT_STATUS.md items 20/21 validated ``0.20`` specifically:
      it is the only threshold that improved both mdd and std_period
      over "no reversal rule" in every reliable walk-forward window,
      confirmed on two independent machines despite this project's
      known cross-machine XGBoost non-determinism (item 21) -- the
      strongest evidence behind any HOLD/SELL parameter here so far.
    - ``None``: use the old absolute rule
      (``sell_predicted_return_threshold`` against
      ``PositionSignal.predicted_return``) instead. Kept only for
      backward compatibility / explicit opt-in -- CURRENT_STATUS.md
      item 17 found it fires on <1% of trades and, isolated, makes
      cum_return worse for no mdd benefit, because this model's raw
      predicted_return is almost never negative. Do not rely on this
      variant for new code.

    Only one variant is active per call; ``sell_predicted_return_threshold``
    is simply ignored when ``sell_percentile_threshold`` is not ``None``.

    IMPORTANT for callers constructing ``PositionConfig(...)`` with
    other fields set explicitly: ``sell_percentile_threshold`` still
    defaults to ``0.20`` unless you set it yourself. A caller that
    wants the old absolute-rule behavior (e.g. to hold the
    signal-reversal rule fixed while testing something else, as
    scripts/evaluate_position_thresholds.py does for
    stop_loss_atr_multiple) must pass
    ``sell_percentile_threshold=None`` explicitly -- it will not
    happen implicitly just because ``sell_predicted_return_threshold``
    was also passed.
    """

    stop_loss_atr_multiple: float = 3.0
    sell_predicted_return_threshold: float = 0.0
    sell_percentile_threshold: float | None = 0.20


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

    ``predicted_return_percentile`` is optional and only required when
    ``PositionConfig.sell_percentile_threshold`` is set: this stock's
    ``predicted_return`` rank among that day's universe, as a fraction
    in ``[0.0, 1.0]`` (0.0 = lowest predicted_return that day, 1.0 =
    highest). Callers get this from
    ``src.recommendation.scoring.add_predicted_return_percentile`` --
    it is cross-sectional information the position layer does not
    compute itself.
    """

    current_price: float
    predicted_return: float
    atr_pct: float
    predicted_return_percentile: float | None = None


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
    if config.sell_percentile_threshold is not None:
        if not (0.0 <= config.sell_percentile_threshold <= 1.0):
            raise ValueError("sell_percentile_threshold must be within [0.0, 1.0].")
        if signal.predicted_return_percentile is None:
            raise ValueError(
                "config.sell_percentile_threshold is set but "
                "signal.predicted_return_percentile is None -- the percentile "
                "signal-reversal rule needs that day's cross-sectional rank "
                "(see src.recommendation.scoring.add_predicted_return_percentile)."
            )
        if not (0.0 <= signal.predicted_return_percentile <= 1.0):
            raise ValueError("predicted_return_percentile must be within [0.0, 1.0].")

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

    if config.sell_percentile_threshold is not None:
        if signal.predicted_return_percentile <= config.sell_percentile_threshold:
            return PositionDecision(
                decision=Decision.SELL,
                reason=(
                    f"model signal no longer favorable (percentile rule): "
                    f"predicted_return_percentile "
                    f"{signal.predicted_return_percentile:.2f} <= threshold "
                    f"{config.sell_percentile_threshold:.2f} (this stock ranks at "
                    f"or below the {config.sell_percentile_threshold:.0%} mark "
                    f"among today's universe)"
                ),
                unrealized_return=unrealized_return,
                stop_loss_threshold=stop_loss_threshold,
                predicted_return=signal.predicted_return,
            )
    elif signal.predicted_return <= config.sell_predicted_return_threshold:
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
