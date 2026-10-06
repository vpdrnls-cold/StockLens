"""Post-hoc diagnostics of the cross-sectional holdout (CURRENT_STATUS item 81)."""
from __future__ import annotations

from dataclasses import replace

import numpy as np
import pandas as pd
import pytest

from scripts import diagnose_cross_sectional_holdout as dx

S = dx.SCORE


def _part(n_stocks: int = 30, n_days: int = 80, seed: int = 0, tie: bool = False) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2024-01-01", periods=n_days)
    rows = []
    for i in range(n_stocks):
        close = 10_000 * np.exp(np.cumsum(rng.normal(0, 0.02, n_days)))
        open_ = close * np.exp(rng.normal(0, 0.005, n_days))
        for d in range(n_days):
            rows.append({"trade_date": dates[d], "stock_code": f"{i:06d}", "open_price": open_[d], "close_price": close[d],
                         S: (round(rng.normal(), 0) if tie else rng.normal()),
                         "target_return_5d": (close[min(d + 5, n_days - 1)] / open_[min(d + 1, n_days - 1)] - 1.0)})
    return pd.DataFrame(rows)


@pytest.fixture(autouse=True)
def _partial(monkeypatch):
    monkeypatch.setattr(dx.fh, "BUFFERED_CONFIG", replace(dx.fh.BUFFERED_CONFIG, allow_partial_universe=True))


def test_buckets_and_ties() -> None:
    p = pd.DataFrame({"trade_date": pd.Timestamp("2024-01-02"), "stock_code": [f"{i:06d}" for i in range(20)],
                      S: list(range(20)), "target_return_5d": 0.0})
    b = dx.add_buckets(p)
    assert b["bucket"].value_counts().sort_index().tolist() == [2] * 10
    assert b.loc[b[S] == 19, "bucket"].item() == 10 and b.loc[b[S] == 0, "bucket"].item() == 1
    p[S] = [1.0] * 10 + [2.0] * 10
    assert dx.add_buckets(p).groupby(S)["bucket"].nunique().tolist() == [1, 1]  # ties share a bucket


def test_engine_top_n_breaks_ties_by_lower_code() -> None:
    p = pd.DataFrame({"trade_date": pd.Timestamp("2024-01-02"), "stock_code": ["000003", "000001", "000002"], S: [1.0, 1.0, 0.0]})
    assert set(p.loc[dx.engine_top_n(p, top_n=1), "stock_code"]) == {"000001"}


def test_bucket_table_long_short_is_top_minus_bottom() -> None:
    a = dx.bucket_table(_part()).set_index("group")
    assert a.loc["long_short(top10%-bottom10%)", "ret_5d"] == pytest.approx(a.loc["top10%", "ret_5d"] - a.loc["bottom10%", "ret_5d"])
    assert {f"D{k}" for k in range(1, 11)} <= set(a.index)


def test_holdings_match_engine_turnover() -> None:
    part = _part()
    per, summ = dx.holdings_table(part)
    assert (per["kept"] + per["new"] == per["held"]).all()
    scores = part[["trade_date", "stock_code", S]].rename(columns={S: "predicted_return"})
    _, turnover = dx.fh.run_buffered_backtest_with_turnover(
        dx.fh._to_data_by_stock(part), dx.fh.BUFFERED_CONFIG, score_fn=dx.make_model_score_fn(scores), top_n=dx.fh.TOP_N)
    assert summ["new"].item() == pytest.approx(turnover["entries_per_period"])
    assert summ["replacements_total"].item() == int(per["new"].sum())


def test_contribution_adds_up() -> None:
    tdf, data, tl, bench = dx.offset_trades(_part(), 0)
    per, st = dx.contribution_table(tdf, {})
    assert st["sum_contrib_net"] == pytest.approx(float((tdf["weight"] * tdf["net_return"]).sum()))
    assert st["sum_contrib_move"] - st["sum_contrib_cost"] == pytest.approx(st["sum_contrib_net"])
    assert st["stocks_negative"] + st["stocks_positive"] <= st["stocks_held"]


def test_regime_rows_cover_all_periods() -> None:
    part = _part(n_days=300)
    tdf, data, tl, bench = dx.offset_trades(part, 0)
    ic = dx.daily_rank_ic(part, S, "target_return_5d")
    d = dx.regime_rows(tdf, data, tl, bench, ic)
    assert d["periods"].sum() == tdf["decision_date"].nunique()
    assert (d["excess"] == d["top10_net"] - d["bench_ew_gross"]).all()
    assert (d["mdd_daily"] <= d["mdd_period"] + 1e-12).all()


def _no_call(*_a, **_k):
    raise AssertionError("must not be called")


class _T:
    best_iteration = 9


def test_guards_stop_before_extra_stocks(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(dx.xh, "STOCK_CODES", ("000660",))
    assert dx.main(["--out", str(tmp_path)]) == 2
    monkeypatch.setattr(dx.xh, "STOCK_CODES", dx.xh.get_universe("top50"))
    monkeypatch.setattr(dx.xh, "_load_priced_dataset", lambda: None)
    monkeypatch.setattr(dx.xh, "train_frozen_model", lambda _d: (_T(), None))
    monkeypatch.setattr(dx.xh, "frozen_model_fingerprint", lambda _t: "0" * 64)
    monkeypatch.setattr(dx.xh, "load_holdout_dataset", _no_call)
    monkeypatch.setenv("STOCKLENS_CONFIRM_FINAL_TEST", "1")
    assert dx.main(["--out", str(tmp_path)]) == 4
    monkeypatch.setattr(dx.fh, "frozen_model_ok", lambda *_a: True)
    monkeypatch.delenv("STOCKLENS_CONFIRM_FINAL_TEST")
    assert dx.main(["--out", str(tmp_path)]) == 5
