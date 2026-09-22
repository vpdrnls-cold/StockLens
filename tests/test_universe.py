from __future__ import annotations

import json

import pytest

from src.data import universe
from src.data.universe import (
    CORE_STOCKS,
    UniverseError,
    get_universe,
    is_common_stock_code,
    normalize_stock_code,
    save_universe_file,
    select_top_by_market_cap,
    load_universe_file,
)


def test_default_universe_is_core5(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(universe.UNIVERSE_ENV_VAR, raising=False)
    assert get_universe() == CORE_STOCKS
    assert len(CORE_STOCKS) == 5


def test_unknown_universe_is_rejected() -> None:
    with pytest.raises(UniverseError, match="Unknown universe"):
        get_universe("nope")


def test_top50_without_generated_file_explains_how_to_create_it(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(universe._UNIVERSE_FILES, "top50", tmp_path / "missing.json")
    with pytest.raises(UniverseError, match="build_universe.py"):
        get_universe("top50")


def test_env_var_selects_universe_file(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "u.json"
    stocks = select_top_by_market_cap(
        [{"code": "005930", "name": "A", "market_cap_eok": 10},
         {"code": "000660", "name": "B", "market_cap_eok": 20}],
        2,
    )
    save_universe_file(path, stocks, name="t", as_of="2026-09-21", source="test")
    monkeypatch.setitem(universe._UNIVERSE_FILES, "top50", path)
    monkeypatch.setenv(universe.UNIVERSE_ENV_VAR, "top50")

    assert get_universe() == ("000660", "005930")
    assert [s.code for s in load_universe_file(path)] == ["000660", "005930"]
    assert json.loads(path.read_text(encoding="utf-8"))["as_of"] == "2026-09-21"


def test_select_top_drops_preferred_duplicates_and_missing_caps() -> None:
    candidates = [
        {"code": "005930", "name": "삼성전자", "market_cap_eok": 5000},
        {"code": "005935", "name": "삼성전자우", "market_cap_eok": 900},   # preferred
        {"code": "000660_NX", "name": "SK하이닉스", "market_cap_eok": 4000},  # suffix
        {"code": "000660", "name": "SK하이닉스", "market_cap_eok": 4000},    # duplicate
        {"code": "035420", "name": "NAVER", "market_cap_eok": None},        # no cap
        {"code": "005380", "name": "현대차", "market_cap_eok": 3000},
    ]
    top = select_top_by_market_cap(candidates, 5)
    assert [s.code for s in top] == ["005930", "000660", "005380"]
    assert [s.code for s in select_top_by_market_cap(candidates, 2)] == ["005930", "000660"]


def test_code_helpers() -> None:
    assert normalize_stock_code(" 005930_NX ") == "005930"
    assert is_common_stock_code("005930")
    assert is_common_stock_code("0126Z0")
    assert not is_common_stock_code("005935")
    assert not is_common_stock_code("5930")
