"""Profile rankings for the viewer (CURRENT_STATUS item 92) -- synthetic day, tmp_path only."""
from __future__ import annotations

import ast
from datetime import date
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from scripts import recommend as rc
from src.analysts import profile_ranking as pr
from src.recommendation.scoring import personalize_scores

ROOT = Path(__file__).resolve().parents[1]


def _day(n: int = 12, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    codes = [f"{i:06d}" for i in range(n)]
    return pd.DataFrame({
        "trade_date": pd.Timestamp("2026-10-08"),
        "volatility_20": rng.uniform(0.01, 0.05, n),
        "price_to_sma_5": rng.normal(0, 0.02, n),
        "volume_ratio_20": rng.uniform(0.5, 2.0, n),
        "score": np.round(rng.normal(0, 0.01, n), 3),  # rounded -> ties, like the real model
    }, index=pd.Index(codes, name="stock_code"))


def test_neutral_order_is_the_model_order():
    day = _day()
    out = rc.ranked_for_profile(day, "neutral", 0.0)
    assert out["rank"].equals(rc.rank_like_engine(day["score"]))


@pytest.mark.parametrize("profile", rc.VIEWER_PROFILES)
def test_profile_order_matches_item56_scoring(profile):
    day, lam = _day(), 0.7
    out = rc.ranked_for_profile(day, profile, lam)
    sig = day.reset_index()[rc.PROFILE_SIGNAL_COLUMNS].assign(predicted_return=day["score"].to_numpy())
    ref = personalize_scores(sig, profile, lam=lam).set_index("stock_code")["personalized_score"]
    assert out["rank"].equals(rc.rank_like_engine(ref))
    assert sorted(out["rank"]) == list(range(1, len(day) + 1))
    assert not out["rank"].equals(rc.rank_like_engine(day["score"]))  # the tilt actually moves something


def test_one_ranking_function_for_cli_and_viewer():
    # Item 92 condition 1: --profile runs and profile_ranks.json share ranked_for_profile;
    # nothing else in recommend.py applies a profile or ranks by personalized_score itself.
    tree = ast.parse((ROOT / "scripts" / "recommend.py").read_text(encoding="utf-8"))
    callers = {fn.name for fn in ast.walk(tree) if isinstance(fn, ast.FunctionDef)
               for c in ast.walk(fn) if isinstance(c, ast.Call) and getattr(c.func, "id", "") == "apply_profile"}
    assert callers == {"ranked_for_profile"}
    main = next(fn for fn in tree.body if isinstance(fn, ast.FunctionDef) and fn.name == "main")
    calls = [c for c in ast.walk(main) if isinstance(c, ast.Call) and getattr(c.func, "id", "") == "ranked_for_profile"]
    assert len(calls) == 2


def _card(day: pd.DataFrame | None = None) -> dict:
    day = _day() if day is None else day
    model_rank = rc.rank_like_engine(day["score"])
    names = {c: f"종목{c}" for c in day.index}
    profiles = {p: (0.7, rc.profile_rank_rows(rc.ranked_for_profile(day, p, 0.7), model_rank, names))
                for p in rc.VIEWER_PROFILES}
    return pr.build_profile_ranks(decision_date=date(2026, 10, 8), profiles=profiles, fingerprint_match=True)


def test_card_rows_and_sums():
    card = _card()
    assert set(card["profiles"]) == set(rc.VIEWER_PROFILES) and card["layer"] == "recommendation"
    for body in card["profiles"].values():
        assert [r["rank"] for r in body["ranks"]] == list(range(1, body["n_stocks"] + 1))
        assert sorted(r["model_rank"] for r in body["ranks"]) == list(range(1, body["n_stocks"] + 1))
        for r in body["ranks"]:
            assert sum(r[t] for t in pr.TERMS) == pytest.approx(r["personalized_score"], abs=1e-12)


def test_card_rejects_bad_input():
    row = {"stock_code": "000001", "name": "a", "rank": 1, "model_rank": 1, "personalized_score": 1.0,
           "contribution_model": 1.0, "contribution_risk": 0.0, "contribution_momentum": 0.0, "contribution_volume": 0.0}
    with pytest.raises(ValueError, match="neutral"):
        pr.build_profile_ranks(decision_date=date(2026, 10, 8), profiles={"neutral": (0.0, [row])}, fingerprint_match=True)
    with pytest.raises(ValueError, match="1..n"):
        pr.build_profile_ranks(decision_date=date(2026, 10, 8), profiles={"conservative": (0.5, [{**row, "rank": 2}])},
                               fingerprint_match=True)
    with pytest.raises(ValueError, match="add up"):
        pr.build_profile_ranks(decision_date=date(2026, 10, 8),
                               profiles={"conservative": (0.5, [{**row, "personalized_score": 2.0}])}, fingerprint_match=True)
    with pytest.raises(ValueError, match="non-finite"):
        pr.build_profile_ranks(decision_date=date(2026, 10, 8),
                               profiles={"conservative": (0.5, [{**row, "contribution_risk": float("nan")}])},
                               fingerprint_match=True)


def test_write_strict_json_without_prices(tmp_path):
    path = pr.write_profile_ranks(_card(), tmp_path)
    assert path == tmp_path / "20261008" / pr.FILE_NAME
    text = path.read_text(encoding="utf-8")
    json.loads(text, parse_constant=lambda c: pytest.fail(f"non-strict JSON constant {c}"))
    for word in ("price", "return", "close", "open", "pnl"):
        assert word not in text


def test_module_uses_standard_library_only():
    # The viewer environment has no xgboost/pandas pin; it imports FILE_NAME and the notes from here.
    tree = ast.parse((ROOT / "src" / "analysts" / "profile_ranking.py").read_text(encoding="utf-8"))
    mods = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    mods |= {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    assert mods <= {"__future__", "datetime", "json", "math", "pathlib", "typing"}
