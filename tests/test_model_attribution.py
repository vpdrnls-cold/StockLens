"""Explanation layer for the live recommendation CLI (CURRENT_STATUS item 51)."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from scripts.recommend import rank_like_engine
from src.explanation.model_attribution import explain_pick, format_feature_value, shap_contributions
from src.models.predict import predict, train_model

FEATS = ("return_5d", "price_to_sma_5", "volume_ratio_20")


def _trained():
    rng = np.random.default_rng(0)
    n = 400
    X = pd.DataFrame({f: rng.normal(size=n) for f in FEATS})
    y = pd.Series(-0.5 * X["return_5d"] + 0.2 * X["price_to_sma_5"] + rng.normal(scale=0.5, size=n))
    return train_model(X[:300], y[:300], X[300:], y[300:], feature_columns=FEATS,
                       params={"n_jobs": 1, "tree_method": "exact"}), X


def test_shap_terms_add_up_to_the_model_score() -> None:
    trained, X = _trained()
    contribs = shap_contributions(trained, X)
    assert list(contribs.columns) == [*FEATS, "bias"]
    np.testing.assert_allclose(contribs.sum(axis=1).to_numpy(), predict(trained, X), atol=1e-5)


def test_explanation_lists_the_largest_terms_with_values() -> None:
    contribs = pd.Series({"return_5d": 0.004, "price_to_sma_5": -0.009, "volume_ratio_20": 0.0001, "bias": 0.1})
    feats = pd.Series({"return_5d": -0.031, "price_to_sma_5": 0.012, "volume_ratio_20": 1.8})
    exp = explain_pick(stock_code="005930", name="삼성전자", rank=1, score=0.01, percentile=1.0,
                       n_stocks=50, features=feats, contributions=contribs, top_k=2)
    assert [d[0] for d in exp.drivers] == ["price_to_sma_5", "return_5d"]
    assert "삼성전자(005930)" in exp.text and "-3.1%" in exp.text and "끌어내림" in exp.text
    assert "bias" not in exp.text


def test_value_formatting() -> None:
    assert format_feature_value("return_5d", 0.0523) == "+5.2%"
    assert format_feature_value("volume_ratio_20", 1.5) == "1.50배"
    assert format_feature_value("rsi_14", 71.26) == "71.3"
    assert format_feature_value("rsi_14", float("nan")) == "값 없음"


def test_ties_are_broken_by_lower_stock_code_like_the_engine() -> None:
    scores = pd.Series({"005930": 0.1, "000660": 0.2, "000270": 0.1, "035420": 0.05})
    assert rank_like_engine(scores).to_dict() == {"005930": 3, "000660": 1, "000270": 2, "035420": 4}
