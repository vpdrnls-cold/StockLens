"""Market card (CURRENT_STATUS item 74) -- synthetic series, tmp_path only."""
from __future__ import annotations

from datetime import date, timedelta
import json
import math

import pytest

from src.analysts import market as mk

T = date(2026, 10, 2)


def _days(n: int, end: date = T) -> list[date]:
    out, d = [], end
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d -= timedelta(days=1)
    return sorted(out)


def _closes(n: int = 260, growth: float = 0.001) -> list[tuple[date, float]]:
    return [(d, 100.0 * (1 + growth) ** i) for i, d in enumerate(_days(n))]


def _ecos(n: int = 30, start: float = 3.0, step: float = 0.01) -> list[dict]:
    return [{"date": d.isoformat(), "value": start + step * i} for i, d in enumerate(_days(n))]


def _card(**over):
    kw = dict(
        decision_date=T,
        index_closes={"001": _closes(), "201": _closes(growth=0.0)},
        ecos={"ktb3y": _ecos(), "ktb10y": _ecos(start=3.5), "corp_aa3y": _ecos(start=4.0), "cd91": _ecos(start=3.2),
              "usdkrw": _ecos(start=1300.0, step=1.0)},
        ecos_labels={"ktb3y": "국고채 3년", "usdkrw": "원/달러"},
        flows_by_stock={"000001": [(d, 100, -50) for d in _days(25)], "000002": [(d, 100, 0) for d in _days(25)]},
    )
    kw.update(over)
    return mk.build_market_card(**kw)


def test_index_stats_known_answers() -> None:
    s = mk.index_stats(_closes(growth=0.01), T)
    assert s["chg_1d"] == pytest.approx(0.01)
    assert s["chg_20d"] == pytest.approx(1.01 ** 20 - 1)
    assert s["vol20_ann"] == pytest.approx(0.0, abs=1e-12)  # constant daily return -> zero volatility
    c = [v for _, v in _closes(growth=0.01)]
    assert s["ma200_gap"] == pytest.approx(c[-1] / (sum(c[-200:]) / 200) - 1)


def test_short_history_gives_none() -> None:
    s = mk.index_stats(_closes(n=15), T)
    assert s["chg_20d"] is None and s["ma200_gap"] is None and s["vol20_ann"] is None
    assert s["chg_5d"] is not None


def test_rates_fx_spread_and_flows() -> None:
    card = _card()
    ktb3 = next(r for r in card["rates"] if r["key"] == "ktb3y")
    assert ktb3["value"] == pytest.approx(3.29) and ktb3["chg_20d_bp"] == pytest.approx(20.0)
    assert card["term_spread_10y_3y"]["bp"] == pytest.approx(50.0)
    assert card["fx"]["chg_5d"] == pytest.approx(1329.0 / 1324.0 - 1)
    assert card["flows"]["d5"] == {"foreign_eok": 10.0, "institution_eok": -2.5}
    assert card["flows"]["n_stocks_last_date"] == 2


def test_values_after_t_are_never_used() -> None:
    later = [(T + timedelta(days=k), 10_000.0) for k in range(1, 30)]
    base = _card()
    leaked = _card(
        index_closes={"001": _closes() + later, "201": _closes(growth=0.0) + later},
        ecos={**{k: _ecos() + [{"date": (T + timedelta(days=3)).isoformat(), "value": 99.0}]
                 for k in ("ktb3y", "ktb10y", "corp_aa3y", "cd91", "usdkrw")}},
        flows_by_stock={"000001": [(d, 100, -50) for d in _days(25)] + [(T + timedelta(days=1), 10**9, 10**9)],
                        "000002": [(d, 100, 0) for d in _days(25)]},
    )
    assert leaked["indices"] == base["indices"] and leaked["flows"] == base["flows"]
    assert all(r["date"] <= T.isoformat() for r in leaked["rates"])


def test_card_keys_json_and_no_judgment(tmp_path) -> None:
    card = _card()
    assert (card["card"], card["layer"], card["used_by_model"]) == ("market", "reference", False)
    assert "stock_code" not in card
    text = json.dumps(card, ensure_ascii=False, allow_nan=False)
    for word in ("위험", "양호", "매수 신호", "매도 신호", "강세장", "약세장", "전망"):
        assert word not in text
    path = mk.write_market_card(card, tmp_path)
    assert path == tmp_path / "20261002" / "market.json"
    assert json.loads(path.read_text(encoding="utf-8")) == card


def test_missing_series_are_none() -> None:
    card = _card(ecos={}, index_closes={}, flows_by_stock={})
    assert all(r["value"] is None for r in card["rates"]) and card["fx"]["value"] is None
    assert card["term_spread_10y_3y"] is None and card["flows"]["d5"] is None
    assert all(i["date"] is None for i in card["indices"])
    assert not any(isinstance(v, float) and math.isnan(v) for v in card["fx"].values())
