"""Personalization / re-ranking layer (AGENTS.md sections 9 and 10).

This module sits strictly downstream of the daily prediction model
(``src.models.predict``): it takes the model's *objective*
``predicted_return`` for each (trade_date, stock_code) plus a handful
of already-computed, scale-free technical features, and re-weights
them into a *personalized* score according to a named risk profile.

Per AGENTS.md 9 ("The user profile should influence recommendation
ranking, not corrupt the underlying factual market signals"), this
module:

- never retrains or otherwise touches the prediction model,
- never invents new features -- every term below is already one of
  ``src.features.engineering.FEATURE_COLUMNS``,
- treats its default weights as a first guess, not a validated
  result. AGENTS.md 9 explicitly warns "Do not hard-code these as
  arbitrary weights and call them scientifically valid. Use
  backtesting and experiments to determine whether profile-specific
  ranking improves useful outcomes." See
  ``scripts/evaluate_personalization.py`` for that check.

Profile definitions follow the conservative / neutral / aggressive
examples given in AGENTS.md 9 directly:

    Conservative: favor lower risk, favor stability, penalize extreme
    volatility.

    Neutral: balance expected return and risk (== the plain model
    score, unchanged).

    Aggressive: tolerate higher volatility, weight short-term
    momentum more, consider unusual volume.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

# Columns this module reads. All of these already exist in
# FEATURE_COLUMNS (src.features.engineering) -- nothing new is
# computed here.
REQUIRED_SIGNAL_COLUMNS = {
    "trade_date",
    "stock_code",
    "predicted_return",
    "volatility_20",
    "price_to_sma_5",
    "volume_ratio_20",
}


@dataclass(frozen=True)
class RiskProfile:
    """One named, explainable weighting for the personalization layer.

    personalized_score =
        predicted_return
        + momentum_weight * price_to_sma_5
        + volume_weight * (volume_ratio_20 - 1.0)
        - risk_weight * volatility_20

    ``volume_ratio_20`` is centered at 1.0 (today's volume relative to
    its 20-day average), so ``volume_ratio_20 - 1.0`` is 0 for
    "normal" volume and positive for unusually high volume, matching
    AGENTS.md 9's "consider unusual volume" for aggressive profiles.

    These starting weights are illustrative, not tuned. Treat any
    change to them as a design decision requiring a validation-split
    backtest comparison (AGENTS.md 13), same as feature selection.
    """

    name: str
    risk_weight: float
    momentum_weight: float
    volume_weight: float


PROFILES: dict[str, RiskProfile] = {
    "conservative": RiskProfile(
        name="conservative",
        risk_weight=2.0,
        momentum_weight=0.0,
        volume_weight=0.0,
    ),
    "neutral": RiskProfile(
        name="neutral",
        risk_weight=0.0,
        momentum_weight=0.0,
        volume_weight=0.0,
    ),
    "aggressive": RiskProfile(
        name="aggressive",
        risk_weight=0.0,
        momentum_weight=1.0,
        volume_weight=0.5,
    ),
}


def resolve_profile(profile: RiskProfile | str) -> RiskProfile:
    """Accept either a RiskProfile or one of the PROFILES keys by name."""
    if isinstance(profile, RiskProfile):
        return profile

    try:
        return PROFILES[profile]
    except KeyError as exc:
        raise ValueError(
            f"Unknown profile '{profile}'. Known profiles: {sorted(PROFILES)}"
        ) from exc


def personalize_scores(
    signals: pd.DataFrame,
    profile: RiskProfile | str,
) -> pd.DataFrame:
    """Turn objective model signals into one profile's personalized score.

    ``signals`` must have one row per (trade_date, stock_code) with at
    least ``REQUIRED_SIGNAL_COLUMNS``. Returns a copy with an added
    ``personalized_score`` column plus per-term contribution columns
    (``contribution_risk``, ``contribution_momentum``,
    ``contribution_volume``) for the explanation layer (AGENTS.md 24)
    -- every personalized score should be traceable back to which
    factor moved it, not just a bare number.
    """
    missing = REQUIRED_SIGNAL_COLUMNS - set(signals.columns)
    if missing:
        raise ValueError(f"signals is missing required columns: {sorted(missing)}")

    if signals.empty:
        raise ValueError("signals must not be empty.")

    resolved = resolve_profile(profile)

    result = signals.copy()
    result["contribution_risk"] = -resolved.risk_weight * result["volatility_20"]
    result["contribution_momentum"] = (
        resolved.momentum_weight * result["price_to_sma_5"]
    )
    result["contribution_volume"] = resolved.volume_weight * (
        result["volume_ratio_20"] - 1.0
    )
    result["personalized_score"] = (
        result["predicted_return"]
        + result["contribution_risk"]
        + result["contribution_momentum"]
        + result["contribution_volume"]
    )
    result["profile"] = resolved.name

    return result


def top_n_recommendations(scored: pd.DataFrame, *, n: int = 5) -> pd.DataFrame:
    """Rank ``personalized_score`` within each trade_date and keep the top n.

    Returns rows sorted by (trade_date, rank), with a ``rank`` column
    (1 = highest score that date). A date with fewer than ``n`` stocks
    simply returns all of them, ranked.
    """
    if "personalized_score" not in scored.columns:
        raise ValueError(
            "scored must already have a 'personalized_score' column "
            "(call personalize_scores first)."
        )

    if n <= 0:
        raise ValueError("n must be positive.")

    ranked = scored.copy()
    ranked["rank"] = (
        ranked.groupby("trade_date")["personalized_score"]
        .rank(method="first", ascending=False)
        .astype(int)
    )

    return (
        ranked[ranked["rank"] <= n]
        .sort_values(["trade_date", "rank"])
        .reset_index(drop=True)
    )


def make_profile_score_fn(scored: pd.DataFrame) -> "callable":
    """Build a score_fn compatible with
    ``src.backtest.baseline.run_baseline_backtest``, backed by a
    precomputed ``personalized_score`` column (from
    ``personalize_scores``).

    Mirrors ``src.ml.strategy.make_model_score_fn`` exactly, so the
    same backtest engine (T+1 open entry, T+holding close exit, fees,
    tax, slippage) can be reused to compare profiles against each
    other and against the plain (unpersonalized) model score.
    """
    if "personalized_score" not in scored.columns:
        raise ValueError(
            "scored must already have a 'personalized_score' column "
            "(call personalize_scores first)."
        )

    lookup = {
        (row.trade_date, row.stock_code): row.personalized_score
        for row in scored.itertuples(index=False)
    }

    def score_fn(
        universe: pd.DataFrame,
        stock_code: str,
        decision_index: int,
        lookback_days: int,
    ) -> float:
        decision_date = universe.iloc[decision_index]["trade_date"]

        key = (decision_date, stock_code)

        if key not in lookup:
            raise KeyError(
                f"No personalized score available for {stock_code} on "
                f"{decision_date.date()}."
            )

        return lookup[key]

    return score_fn


def add_predicted_return_percentile(signals: pd.DataFrame) -> pd.DataFrame:
    """Add a ``predicted_return_percentile`` column: each row's
    cross-sectional rank of ``predicted_return`` within its own
    ``trade_date``, as a fraction in ``(0.0, 1.0]`` (1.0 = the highest
    predicted_return that day, close to ``1/n`` = the lowest, ties
    averaged).

    This is the cross-sectional counterpart to the raw
    ``predicted_return`` column, for consumers that should judge a
    stock's signal *relative to that day's universe* rather than
    against an absolute, zero-anchored threshold -- see
    ``src.portfolio.optimizer.PositionConfig.sell_percentile_threshold``
    and AGENTS.md 22's cross-sectional rank IC principle (this model's
    output is only validated as a relative ranking signal, not as an
    absolute quantity).

    ``signals`` must have ``trade_date`` and ``predicted_return``
    columns; a date with a single stock gets percentile 1.0 (trivially
    "the best" in a universe of one) rather than a division-by-zero
    error.
    """
    required = {"trade_date", "predicted_return"}
    missing = required - set(signals.columns)
    if missing:
        raise ValueError(f"signals is missing required columns: {sorted(missing)}")

    if signals.empty:
        raise ValueError("signals must not be empty.")

    result = signals.copy()
    result["predicted_return_percentile"] = result.groupby("trade_date")[
        "predicted_return"
    ].rank(pct=True)

    return result
