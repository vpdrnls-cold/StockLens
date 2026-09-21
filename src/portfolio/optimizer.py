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
2.  signal reversal (opt-in, off by default -- see below): otherwise,
    if the model's signal for this stock has deteriorated, sell -- the
    reason to keep holding (an expected positive move) is gone.
3.  otherwise: hold.

Signal-reversal rule, two selectable variants, BOTH off by default
(``PositionConfig`` picks one via explicit opt-in -- see its
docstring):

- absolute (``sell_predicted_return_threshold=<float>``): sell if
  ``predicted_return <= sell_predicted_return_threshold``. Treats the
  model's raw predicted return as a meaningful, zero-anchored number.
  CURRENT_STATUS.md item 17 found this fires on <1% of trades and,
  isolated, makes cum_return worse for no mdd benefit -- not
  recommended, kept only for callers that explicitly want it.
- percentile (``sell_percentile_threshold=<float in [0,1]>``): sell if
  this stock's predicted_return ranks at or below that percentile of
  that day's universe (0.0 = worst that day, 1.0 = best). AGENTS.md 22
  already treats this model's output as trustworthy only for
  cross-sectional ranking (rank IC), not as an absolute quantity, and
  this variant applies that same standard here. CURRENT_STATUS.md
  items 20/21 validated ``0.20`` under XGBoost's default (non-
  reproducible) ``hist`` tree_method and it briefly WAS this project's
  default (item 22) -- but item 25 re-ran the same walk-forward check
  under ``tree_method="exact"`` (confirmed bit-identical across two
  genuinely different real machines, item 23) and found it no longer
  wins mdd in every reliable window (only 1 of 2). Walked back to
  opt-in-only, not recommended, pending a threshold that actually
  survives reproducible validation.

Neither variant has survived validation as an improvement over
stop-loss alone -- the default (both thresholds ``None``) is stop-loss
only, the one rule in this module actually backed by a robust,
now-reproducible walk-forward result (CURRENT_STATUS.md items 18/24).

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

    The default config (both reversal fields ``None``) is stop-loss
    only -- no signal-reversal rule fires at all. This is deliberate,
    not an oversight: CURRENT_STATUS.md item 17 found the absolute
    rule harmful when isolated, and item 25 found the percentile rule
    (briefly this project's default in item 22) does not survive
    walk-forward once cross-machine reproducibility is actually fixed
    (item 23/24). Neither variant is currently recommended; both exist
    as explicit opt-ins for future investigation, not as the
    out-of-the-box behavior.

    ``sell_percentile_threshold`` (default ``None``) selects the
    percentile variant when set: a float in ``[0.0, 1.0]`` -- sell if
    this stock's ``PositionSignal.predicted_return_percentile`` (which
    ``evaluate_position`` then requires to be set) is at or below that
    threshold.

    ``sell_predicted_return_threshold`` (default ``None``) selects the
    absolute variant when set, but ONLY if ``sell_percentile_threshold``
    is ``None`` -- percentile takes priority if both are set. Sell if
    ``PositionSignal.predicted_return <= sell_predicted_return_threshold``.

    If both are ``None`` (the default), no signal-reversal rule is
    evaluated at all -- only the stop-loss check can produce a SELL.
    """

    stop_loss_atr_multiple: float = 3.0
    sell_predicted_return_threshold: float | None = None
    sell_percentile_threshold: float | None = None


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
    elif (
        config.sell_predicted_return_threshold is not None
        and signal.predicted_return <= config.sell_predicted_return_threshold
    ):
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
