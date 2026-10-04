"""Paper-log holdings replay (CURRENT_STATUS item 66)."""
from __future__ import annotations

import pandas as pd
import pytest

from src.backtest.buffered import BufferedBaselineConfig, _build_held_timeline
from src.portfolio import paper_holdings as ph


def _codes(n: int) -> list[str]:
    return [f"{k:06d}" for k in range(n)]


def test_first_step_is_plain_top_n() -> None:
    steps = ph.replay_holdings([(pd.Timestamp("2026-10-02"), _codes(8))], top_n=3, buffer_multiplier=2.0)
    assert steps[0].held == frozenset(_codes(3))
    assert steps[0].carried == frozenset()


def test_held_stock_kept_inside_buffer_and_dropped_outside() -> None:
    codes = _codes(10)
    day1 = codes                                   # holds 0,1,2
    day2 = codes[3:6] + codes[:3] + codes[6:]      # 0,1,2 now rank 4-6 (within 2*3=6) -> kept
    day3 = codes[3:] + codes[:3]                   # 0,1,2 now rank 8-10 (> 6) -> replaced
    steps = ph.replay_holdings(
        [(pd.Timestamp("2026-10-02"), day1), (pd.Timestamp("2026-10-09"), day2), (pd.Timestamp("2026-10-16"), day3)],
        top_n=3, buffer_multiplier=2.0,
    )
    assert steps[1].held == frozenset(codes[:3]) and steps[1].entered == frozenset()
    assert steps[2].held == frozenset(codes[3:6]) and steps[2].carried == frozenset()


def test_replay_order_does_not_depend_on_input_order() -> None:
    r = [(pd.Timestamp("2026-10-09"), _codes(6)[::-1]), (pd.Timestamp("2026-10-02"), _codes(6))]
    steps = ph.replay_holdings(r, top_n=2, buffer_multiplier=2.0)
    assert [s.trade_date for s in steps] == sorted(d for d, _ in r)


def test_replay_matches_the_backtest_engine_timeline() -> None:
    # Same rankings through the engine's own pass-1 and through the replay -> same held sets.
    dates = pd.bdate_range("2030-01-01", periods=40)
    codes = _codes(12)
    scores = {(d, c): float((i * 7 + int(c)) % 5) for i, d in enumerate(dates) for c in codes}
    data = {
        c: pd.DataFrame({"stock_code": c, "trade_date": dates, "open_price": 100.0, "close_price": 100.0})
        for c in codes
    }

    def score_fn(universe, code, idx, lookback):
        return scores[(universe.iloc[idx]["trade_date"], code)]

    cfg = BufferedBaselineConfig(allow_partial_universe=True, buffer_multiplier=2.0)
    _, _, held_tl, _, meta_tl, _, _ = _build_held_timeline(data, cfg, score_fn, top_n=3)
    rankings = [
        (m["decision_date"], sorted(m["scores"], key=m["scores"].get, reverse=True))
        for m in meta_tl if m is not None
    ]
    steps = ph.replay_holdings(rankings, top_n=3, buffer_multiplier=2.0)
    assert [set(s.held) for s in steps] == [h for h, m in zip(held_tl, meta_tl) if m is not None]


def test_load_logged_rankings_only_before_date(tmp_path) -> None:
    for day, order in (("20261002", ["000002", "000001"]), ("20261009", ["000001", "000002"])):
        pd.DataFrame({"trade_date": [f"{day[:4]}-{day[4:6]}-{day[6:]}"] * 2, "rank": [1, 2],
                      "stock_code": order}).to_csv(tmp_path / f"{day}.csv", index=False)
    (tmp_path / "notes.csv").write_text("x\n1\n")
    got = ph.load_logged_rankings(tmp_path, before=pd.Timestamp("2026-10-09"))
    assert got == [(pd.Timestamp("2026-10-02"), ["000002", "000001"])]


def test_schedule_gaps() -> None:
    d = [pd.Timestamp(x) for x in ("2026-10-02", "2026-10-09", "2026-10-23")]
    assert ph.schedule_gaps(d) == [(d[1], d[2])]


def test_too_few_ranked_stocks_rejected() -> None:
    with pytest.raises(ValueError):
        ph.replay_holdings([(pd.Timestamp("2026-10-02"), _codes(2))], top_n=3, buffer_multiplier=2.0)
