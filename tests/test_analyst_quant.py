"""Quant analyst card (CURRENT_STATUS item 69) -- synthetic inputs, no network, no model training."""
from __future__ import annotations

from datetime import date
import json

import pytest

from scripts.recommend import should_write_cards
from src.analysts import quant

FEATURES = {"price_to_sma_5": -0.031, "return_20d": 0.12, "volume_ratio_20": float("nan"), "rsi_14": float("inf")}
CONTRIBS = {"price_to_sma_5": 0.0045, "return_20d": -0.0012, "volume_ratio_20": 0.0003, "rsi_14": -0.0021, "bias": 0.0001}
SCORE = sum(CONTRIBS.values())


def _card(**over):
    kw = dict(
        stock_code="005930", name="삼성전자", decision_date=date(2026, 10, 2), rank=4, n_stocks=50,
        percentile=0.82, score=SCORE, tie_size=15, features=FEATURES, contributions=CONTRIBS,
        best_iteration=9, fingerprint_match=True, held_buffered=True, held_status="유지",
        top_n=10, buffer_multiplier=3.0,
    )
    kw.update(over)
    return quant.build_quant_card(**kw)


def test_shares_the_chart_card_keys_and_is_the_recommendation_layer() -> None:
    card = _card()
    for key in ("card", "layer", "used_by_model", "stock_code", "name", "decision_date"):
        assert key in card
    assert card["card"] == "quant" and card["layer"] == "recommendation" and card["used_by_model"] is True
    assert card["decision_date"] == "2026-10-02"
    assert card["schema_version"] == 1


def test_drivers_add_back_to_the_score_and_are_sorted_by_size() -> None:
    card = _card()
    total = card["bias"] + sum(d["contribution"] for d in card["drivers"])
    assert total == pytest.approx(card["ranking"]["score"], abs=1e-9)
    assert abs(card["shap_check"]["sum_minus_score"]) < 1e-9
    sizes = [abs(d["contribution"]) for d in card["drivers"]]
    assert sizes == sorted(sizes, reverse=True)
    assert [d["feature"] for d in card["drivers"]][0] == "price_to_sma_5"
    assert len(card["drivers"]) == len(CONTRIBS) - 1  # every feature, not only the top 3


def test_non_finite_values_become_none_and_json_is_strict() -> None:
    card = _card()
    by_feature = {d["feature"]: d for d in card["drivers"]}
    assert by_feature["volume_ratio_20"]["value"] is None
    assert by_feature["rsi_14"]["value"] is None
    assert by_feature["rsi_14"]["value_text"] == "값 없음"
    json.dumps(card, allow_nan=False)  # must not raise


def test_ties_and_missing_holdings() -> None:
    card = _card(tie_size=15)
    assert card["ranking"]["tied"] is True and card["ranking"]["tie_rule"] == quant.TIE_RULE
    no_hold = _card(held_buffered=None, held_status="유지")
    assert no_hold["strategy"]["held_buffered"] is None and no_hold["strategy"]["status"] is None
    single = _card(tie_size=1)
    assert single["ranking"]["tied"] is False


def test_write_and_read_back(tmp_path) -> None:
    card = _card()
    path = quant.write_quant_card(card, tmp_path)
    assert path == tmp_path / "20261002" / "005930_quant.json"
    assert json.loads(path.read_text(encoding="utf-8")) == card


def test_cards_only_for_a_saving_neutral_run() -> None:
    assert should_write_cards("neutral", no_save=False) is True
    assert should_write_cards("neutral", no_save=True) is False
    assert should_write_cards("conservative", no_save=False) is False
    assert should_write_cards("aggressive", no_save=True) is False


def test_holdings_note_is_optional_and_keeps_schema_version() -> None:
    assert "note" not in _card()["strategy"]
    card = _card(holdings_note="로그에 보유 기록 없음 — 이전 로그를 재생한 보유")
    assert card["strategy"]["note"].startswith("로그에 보유 기록 없음")
    assert card["schema_version"] == 1
    json.dumps(card, allow_nan=False)
