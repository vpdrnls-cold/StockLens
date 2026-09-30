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

import math
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
    """One named, explainable TILT DIRECTION for the personalization layer (item 56).

    personalized_score =
          z(predicted_return)
        - lam * risk_weight     * z(volatility_20)
        + lam * momentum_weight * z(price_to_sma_5)
        + lam * volume_weight   * z(volume_ratio_20)

    ``z`` is the per-date standardized cross-sectional rank
    (``standardized_rank``), so every term is unit-free and on the same
    scale as the model term. The weights are a DIRECTION (unit norm, from
    AGENTS.md 9's examples); the STRENGTH ``lam`` is not a free parameter
    either: ``calibrate_lambda`` picks it on the TRAIN period so that the
    personalized ranking keeps a mean rank correlation of
    ``TARGET_MODEL_CORR`` with the model ranking -- personalization tilts
    the model signal, it does not replace it. No returns are used.

    ``risk_weight`` > 0 penalizes volatility, < 0 rewards it.
    """

    name: str
    risk_weight: float
    momentum_weight: float
    volume_weight: float

    @property
    def is_neutral(self) -> bool:
        return self.risk_weight == 0 and self.momentum_weight == 0 and self.volume_weight == 0


_INV_SQRT2 = 1.0 / math.sqrt(2.0)

# Pre-registered in item 56 (2026-09-30, before any result). Aggressive has no
# short-term momentum on purpose: the frozen model is effectively a short-term
# reversal model (item 49), so a momentum tilt just reverses the model signal
# (rank corr -0.25 in the item 56 diagnosis). Aggressive = tolerate volatility
# + unusual volume.
PROFILES: dict[str, RiskProfile] = {
    "conservative": RiskProfile("conservative", risk_weight=1.0, momentum_weight=0.0, volume_weight=0.0),
    "neutral": RiskProfile("neutral", risk_weight=0.0, momentum_weight=0.0, volume_weight=0.0),
    "aggressive": RiskProfile("aggressive", risk_weight=-_INV_SQRT2, momentum_weight=0.0, volume_weight=_INV_SQRT2),
}

TARGET_MODEL_CORR = 0.8  # item 56, rho*
LAMBDA_SEARCH_MAX = 20.0


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


def standardized_rank(df: pd.DataFrame, column: str, date_col: str = "trade_date") -> pd.Series:
    """Per-date cross-sectional rank (ties averaged), standardized to mean 0 / std 1.

    A date where every value is tied (or a single stock) gets 0.0 for all rows.
    Uses only that date's cross-section -- never another date's values.
    """
    r = df.groupby(date_col)[column].rank(method="average")
    g = r.groupby(df[date_col])
    mean, std = g.transform("mean"), g.transform(lambda x: x.std(ddof=0))
    z = (r - mean) / std
    return z.where(std > 0, 0.0).fillna(0.0)


def _components(signals: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame({
        "z_model": standardized_rank(signals, "predicted_return"),
        "z_vol": standardized_rank(signals, "volatility_20"),
        "z_mom": standardized_rank(signals, "price_to_sma_5"),
        "z_volume": standardized_rank(signals, "volume_ratio_20"),
    }, index=signals.index)


def _tilt(comp: pd.DataFrame, p: RiskProfile) -> pd.Series:
    return -p.risk_weight * comp["z_vol"] + p.momentum_weight * comp["z_mom"] + p.volume_weight * comp["z_volume"]


def mean_rank_corr(a: pd.Series, b: pd.Series, dates: pd.Series) -> float:
    """Mean over dates of the Spearman correlation between ``a`` and ``b`` (NaN dates dropped)."""
    frame = pd.DataFrame({"d": dates.to_numpy(), "a": a.to_numpy(), "b": b.to_numpy()})
    frame["ra"] = frame.groupby("d")["a"].rank()
    frame["rb"] = frame.groupby("d")["b"].rank()
    corr = frame.groupby("d")[["ra", "rb"]].corr().xs("ra", level=1)["rb"]
    return float(corr.dropna().mean())


def calibrate_lambda(
    train_signals: pd.DataFrame,
    profile: RiskProfile | str,
    target: float = TARGET_MODEL_CORR,
    *,
    iterations: int = 40,
) -> float:
    """Tilt strength so that mean rank corr(personalized, model) == ``target`` on ``train_signals``.

    Pass TRAIN-period signals only (item 56). Uses no returns or targets.
    Neutral -> 0.0. The correlation falls from 1 at lam=0 as lam grows, so a
    bisection on [0, LAMBDA_SEARCH_MAX] is enough.
    """
    p = resolve_profile(profile)
    if p.is_neutral:
        return 0.0
    comp = _components(train_signals)
    tilt = _tilt(comp, p)
    dates = train_signals["trade_date"]

    def corr_at(lam: float) -> float:
        return mean_rank_corr(comp["z_model"] + lam * tilt, comp["z_model"], dates)

    lo, hi = 0.0, LAMBDA_SEARCH_MAX
    if corr_at(hi) > target:
        raise ValueError(f"target corr {target} not reachable with lambda <= {hi}")
    for _ in range(iterations):
        mid = (lo + hi) / 2
        if corr_at(mid) > target:
            lo = mid
        else:
            hi = mid
    # The rank correlation is a step function of lam; return the largest lam
    # found whose correlation is still >= target (never over-tilts).
    return lo


def personalize_scores(
    signals: pd.DataFrame,
    profile: RiskProfile | str,
    lam: float | None = None,
) -> pd.DataFrame:
    """Turn objective model signals into one profile's personalized score (item 56).

    ``signals`` must have one row per (trade_date, stock_code) with at
    least ``REQUIRED_SIGNAL_COLUMNS``. ``lam`` is required for any
    non-neutral profile -- take it from ``calibrate_lambda`` on the train
    period, never pick it by hand. Returns a copy with
    ``personalized_score`` (unit-free, z scale), the model term
    ``contribution_model`` and per-term contributions
    (``contribution_risk``, ``contribution_momentum``,
    ``contribution_volume``) for the explanation layer (AGENTS.md 24).
    """
    missing = REQUIRED_SIGNAL_COLUMNS - set(signals.columns)
    if missing:
        raise ValueError(f"signals is missing required columns: {sorted(missing)}")

    if signals.empty:
        raise ValueError("signals must not be empty.")

    resolved = resolve_profile(profile)
    if resolved.is_neutral:
        lam = 0.0
    elif lam is None:
        raise ValueError("lam is required for a non-neutral profile (use calibrate_lambda on train).")
    elif lam < 0:
        raise ValueError("lam must be >= 0")

    comp = _components(signals)
    result = signals.copy()
    result["contribution_model"] = comp["z_model"]
    result["contribution_risk"] = -lam * resolved.risk_weight * comp["z_vol"]
    result["contribution_momentum"] = lam * resolved.momentum_weight * comp["z_mom"]
    result["contribution_volume"] = lam * resolved.volume_weight * comp["z_volume"]
    result["personalized_score"] = (
        result["contribution_model"]
        + result["contribution_risk"]
        + result["contribution_momentum"]
        + result["contribution_volume"]
    )
    result["profile"] = resolved.name
    result["lambda"] = float(lam)

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
