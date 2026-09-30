from __future__ import annotations

import pandas as pd
import pytest

from src.recommendation.scoring import (
    PROFILES,
    TARGET_MODEL_CORR,
    RiskProfile,
    calibrate_lambda,
    mean_rank_corr,
    standardized_rank,
    add_predicted_return_percentile,
    make_profile_score_fn,
    personalize_scores,
    resolve_profile,
    top_n_recommendations,
)


def _signals() -> pd.DataFrame:
    """Two decision dates, three stocks. Stock A has the highest raw
    predicted_return but also the highest volatility and no momentum;
    stock B has slightly lower predicted_return but low volatility;
    stock C has moderate predicted_return, strong momentum, and
    unusually high volume.
    """
    rows = [
        # trade_date, stock_code, predicted_return, volatility_20, price_to_sma_5, volume_ratio_20
        ("2024-01-02", "A", 0.03, 0.05, 0.00, 1.0),
        ("2024-01-02", "B", 0.02, 0.01, 0.00, 1.0),
        ("2024-01-02", "C", 0.015, 0.02, 0.05, 2.0),
        ("2024-01-09", "A", 0.01, 0.05, 0.00, 1.0),
        ("2024-01-09", "B", 0.02, 0.01, 0.00, 1.0),
        ("2024-01-09", "C", 0.005, 0.02, 0.05, 2.0),
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


def test_resolve_profile_by_name_and_object() -> None:
    assert resolve_profile("neutral") is PROFILES["neutral"]

    custom = RiskProfile("custom", risk_weight=1.0, momentum_weight=0.0, volume_weight=0.0)
    assert resolve_profile(custom) is custom


def test_resolve_profile_rejects_unknown_name() -> None:
    with pytest.raises(ValueError, match="Unknown profile"):
        resolve_profile("does-not-exist")


def test_neutral_profile_keeps_model_ranking() -> None:
    scored = personalize_scores(_signals(), "neutral")

    for _, day in scored.groupby("trade_date"):
        assert list(day["personalized_score"].rank()) == list(day["predicted_return"].rank())
    assert (scored["contribution_risk"] == 0.0).all()
    assert (scored["contribution_momentum"] == 0.0).all()
    assert (scored["contribution_volume"] == 0.0).all()
    assert (scored["lambda"] == 0.0).all()


def test_non_neutral_profile_requires_lambda() -> None:
    with pytest.raises(ValueError, match="lam is required"):
        personalize_scores(_signals(), "conservative")
    with pytest.raises(ValueError):
        personalize_scores(_signals(), "conservative", lam=-1.0)


def test_conservative_profile_penalizes_the_highest_volatility_stock() -> None:
    scored = personalize_scores(_signals(), "conservative", lam=1.0)

    day = scored[scored["trade_date"] == "2024-01-02"].set_index("stock_code")

    # A has the highest predicted_return but also the highest volatility_20
    # -- conservative should knock it below B.
    assert day.loc["B", "personalized_score"] > day.loc["A", "personalized_score"]
    assert day.loc["A", "contribution_risk"] < 0


def test_aggressive_profile_rewards_volatility_and_volume_but_not_momentum() -> None:
    scored = personalize_scores(_signals(), "aggressive", lam=1.0)

    day = scored[scored["trade_date"] == "2024-01-02"].set_index("stock_code")

    # item 56: no momentum tilt (conflicts with the reversal model)
    assert (scored["contribution_momentum"] == 0.0).all()
    assert day.loc["A", "contribution_risk"] > 0  # highest volatility is rewarded
    assert day.loc["C", "contribution_volume"] > 0  # unusual volume is rewarded


def test_profile_directions_are_preregistered_unit_vectors() -> None:
    import math

    for p in PROFILES.values():
        norm = math.sqrt(p.risk_weight**2 + p.momentum_weight**2 + p.volume_weight**2)
        assert norm == pytest.approx(0.0 if p.is_neutral else 1.0)
    assert PROFILES["aggressive"].momentum_weight == 0.0
    assert PROFILES["conservative"].risk_weight == 1.0
    assert TARGET_MODEL_CORR == 0.8


def test_standardized_rank_is_per_date_and_scale_free() -> None:
    df = _signals()
    z = standardized_rank(df, "volume_ratio_20")
    for _, idx in df.groupby("trade_date").groups.items():
        assert z[idx].mean() == pytest.approx(0.0)
    # multiplying a column by 1000 does not change z
    df2 = df.assign(volume_ratio_20=df["volume_ratio_20"] * 1000)
    pd.testing.assert_series_equal(z, standardized_rank(df2, "volume_ratio_20"))
    # all tied -> 0
    df3 = df.assign(volume_ratio_20=1.0)
    assert (standardized_rank(df3, "volume_ratio_20") == 0.0).all()


def _random_signals(n_dates: int = 60, n_stocks: int = 30, seed: int = 1) -> pd.DataFrame:
    import numpy as np

    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2015-01-01", periods=n_dates)
    return pd.DataFrame({
        "trade_date": np.repeat(dates, n_stocks),
        "stock_code": np.tile([f"{i:06d}" for i in range(n_stocks)], n_dates),
        "predicted_return": rng.normal(size=n_dates * n_stocks),
        "volatility_20": rng.lognormal(size=n_dates * n_stocks),
        "price_to_sma_5": rng.normal(size=n_dates * n_stocks),
        "volume_ratio_20": rng.lognormal(size=n_dates * n_stocks),
    })


def test_calibrate_lambda_hits_target_without_using_returns() -> None:
    train = _random_signals()
    assert "target_return_5d" not in train.columns  # calibration never sees outcomes
    assert calibrate_lambda(train, "neutral") == 0.0
    for name in ("conservative", "aggressive"):
        lam = calibrate_lambda(train, name)
        scored = personalize_scores(train, name, lam=lam)
        corr = mean_rank_corr(scored["personalized_score"], scored["predicted_return"], scored["trade_date"])
        assert TARGET_MODEL_CORR <= corr < TARGET_MODEL_CORR + 0.01
        assert lam > 0


def test_personalize_scores_rejects_missing_columns() -> None:
    incomplete = _signals().drop(columns=["volatility_20"])

    with pytest.raises(ValueError, match="missing required columns"):
        personalize_scores(incomplete, "neutral")


def test_personalize_scores_rejects_empty_input() -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        personalize_scores(_signals().iloc[0:0], "neutral")


def test_top_n_recommendations_ranks_within_each_date() -> None:
    scored = personalize_scores(_signals(), "neutral")
    top2 = top_n_recommendations(scored, n=2)

    day = top2[top2["trade_date"] == "2024-01-02"]
    assert list(day.sort_values("rank")["stock_code"]) == ["A", "B"]
    assert list(day["rank"]) == [1, 2]


def test_top_n_recommendations_returns_fewer_rows_if_universe_is_smaller() -> None:
    scored = personalize_scores(_signals(), "neutral")
    top10 = top_n_recommendations(scored, n=10)

    assert len(top10[top10["trade_date"] == "2024-01-02"]) == 3


def test_top_n_recommendations_requires_personalized_score_column() -> None:
    with pytest.raises(ValueError, match="personalized_score"):
        top_n_recommendations(_signals(), n=2)


def test_make_profile_score_fn_matches_personalized_score() -> None:
    scored = personalize_scores(_signals(), "aggressive", lam=1.0)
    score_fn = make_profile_score_fn(scored)

    universe = pd.DataFrame({"trade_date": pd.to_datetime(["2024-01-02"])})
    expected = scored[
        (scored["trade_date"] == "2024-01-02") & (scored["stock_code"] == "C")
    ]["personalized_score"].iloc[0]

    assert score_fn(universe, "C", 0, lookback_days=5) == pytest.approx(expected)


def test_make_profile_score_fn_raises_on_unknown_key() -> None:
    scored = personalize_scores(_signals(), "neutral")
    score_fn = make_profile_score_fn(scored)

    universe = pd.DataFrame({"trade_date": pd.to_datetime(["2099-01-01"])})
    with pytest.raises(KeyError):
        score_fn(universe, "A", 0, lookback_days=5)


def test_add_predicted_return_percentile_ranks_within_each_date() -> None:
    result = add_predicted_return_percentile(_signals())

    day = result[result["trade_date"] == "2024-01-02"].set_index("stock_code")
    # A (0.03) > B (0.02) > C (0.015) that day -> A highest percentile.
    assert day.loc["A", "predicted_return_percentile"] == pytest.approx(1.0)
    assert day.loc["C", "predicted_return_percentile"] == pytest.approx(1.0 / 3.0)
    assert day.loc["A", "predicted_return_percentile"] > day.loc["B", "predicted_return_percentile"]
    assert day.loc["B", "predicted_return_percentile"] > day.loc["C", "predicted_return_percentile"]


def test_add_predicted_return_percentile_is_independent_per_date() -> None:
    result = add_predicted_return_percentile(_signals())

    # On 2024-01-09, B (0.02) is now the highest, unlike 2024-01-02 --
    # each date's ranking must not leak into another date's.
    day = result[result["trade_date"] == "2024-01-09"].set_index("stock_code")
    assert day.loc["B", "predicted_return_percentile"] == pytest.approx(1.0)


def test_add_predicted_return_percentile_rejects_missing_columns() -> None:
    incomplete = _signals().drop(columns=["predicted_return"])

    with pytest.raises(ValueError, match="missing required columns"):
        add_predicted_return_percentile(incomplete)


def test_add_predicted_return_percentile_rejects_empty_input() -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        add_predicted_return_percentile(_signals().iloc[0:0])
