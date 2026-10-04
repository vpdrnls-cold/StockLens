"""Chart analyst card (item 61): states, base-rate period/purge, card rules. No network."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd

from src.analysts import chart
from src.data.dataset import TARGET_COLUMN, VALIDATION_END_DATE


def _dataset(seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2011-06-01", "2023-09-29")
    codes = [f"{i:06d}" for i in range(10)]
    idx = pd.MultiIndex.from_product([dates, codes], names=["trade_date", "stock_code"])
    n = len(idx)
    df = pd.DataFrame({
        "rsi_14": rng.uniform(10, 90, n),
        "price_to_sma_60": rng.normal(0, 0.1, n),
        "return_20d": rng.normal(0, 0.08, n),
        "volume_ratio_20": rng.lognormal(0, 0.5, n),
        "volatility_20": rng.uniform(0.01, 0.04, n),
        TARGET_COLUMN: rng.normal(0, 0.05, n),
    }, index=idx).reset_index()
    return df


def test_bins_are_left_closed_and_nan_safe() -> None:
    df = pd.DataFrame({"trade_date": pd.Timestamp("2020-01-02"),
                       "rsi_14": [29.99, 30.0, 69.99, 70.0, np.nan],
                       "price_to_sma_60": [-0.2, -0.1, 0.0, 0.1, np.inf],
                       "return_20d": [1, 2, 3, 4, 5.0], "volume_ratio_20": [0.5, 0.7, 1.5, 3.0, np.nan],
                       "volatility_20": [5, 4, 3, 2, 1.0]})
    st = chart.classify_states(df)
    assert st["state_rsi"].tolist()[:4] == ["과매도(<30)", "중립(30~70)", "중립(30~70)", "과매수(≥70)"]
    assert pd.isna(st["state_rsi"].iloc[4])
    assert st["state_sma60"].tolist()[:4] == ["−10% 미만", "−10~0%", "0~+10%", "+10% 이상"]
    assert pd.isna(st["state_sma60"].iloc[4])  # inf -> unclassified
    assert st["state_volume"].tolist()[:4] == ["한산(<0.7)", "보통(0.7~1.5)", "증가(1.5~3)", "급증(≥3)"]


def test_quintiles_are_within_date() -> None:
    df = pd.DataFrame({"trade_date": [pd.Timestamp("2020-01-02")] * 5 + [pd.Timestamp("2020-01-03")] * 5,
                       "return_20d": [1, 2, 3, 4, 5, 100, 200, 300, 400, 500.0],
                       "rsi_14": 50.0, "price_to_sma_60": 0.0, "volume_ratio_20": 1.0, "volatility_20": 0.02})
    st = chart.classify_states(df)
    assert st["state_ret20"].tolist() == ["Q1(최약)", "Q2", "Q3", "Q4", "Q5(최강)"] * 2


def test_base_rate_frame_stays_in_validation_and_purges_end() -> None:
    frame = chart.base_rate_frame(_dataset(), horizon=5)
    end = pd.Timestamp(VALIDATION_END_DATE)
    in_range = sorted(d for d in pd.bdate_range(chart.BASE_RATE_START, end))
    assert frame["trade_date"].min() == in_range[0]  # 2011 rows dropped
    assert frame["trade_date"].max() == in_range[-6]  # last 5 dates purged
    assert set(frame["window"].dropna()) == {"W1", "W2", "W3"} and frame["window"].notna().all()
    # excess is zero-mean within each date
    assert frame.groupby("trade_date")[chart.EXCESS_COLUMN].mean().abs().max() < 1e-12


def test_future_values_do_not_change_base_rates() -> None:
    base = _dataset()
    changed = base.copy()
    after = changed["trade_date"] > pd.Timestamp(VALIDATION_END_DATE)
    changed.loc[after, [TARGET_COLUMN, "rsi_14", "return_20d"]] = 999.0
    a = chart.compute_base_rates(chart.base_rate_frame(base))
    b = chart.compute_base_rates(chart.base_rate_frame(changed))
    assert a == b


def test_verdicts() -> None:
    frame = pd.DataFrame({
        "trade_date": pd.to_datetime(["2013-01-02"] * 60 + ["2017-01-02"] * 60 + ["2021-01-04"] * 60),
        "window": ["W1"] * 60 + ["W2"] * 60 + ["W3"] * 60,
        chart.EXCESS_COLUMN: [0.01] * 120 + [-0.01] * 60,
    })
    for spec in chart.STATE_SPECS:
        frame[f"state_{spec.key}"] = spec.labels[0]
    rows = {(r["state"], r["bucket"]): r for r in chart.compute_base_rates(frame)}
    assert rows[("rsi", "과매도(<30)")]["verdict"] == "inconsistent"
    assert rows[("rsi", "중립(30~70)")]["verdict"] == "insufficient"  # n = 0
    frame[chart.EXCESS_COLUMN] = 0.01
    rows = {(r["state"], r["bucket"]): r for r in chart.compute_base_rates(frame)}
    assert rows[("rsi", "과매도(<30)")]["verdict"] == "consistent"
    frame[chart.EXCESS_COLUMN] = 0.0005  # same sign everywhere but below MIN_EFFECT (item 63)
    rows = {(r["state"], r["bucket"]): r for r in chart.compute_base_rates(frame)}
    assert rows[("rsi", "과매도(<30)")]["verdict"] == "negligible"


@dataclass
class _Flow:
    trade_date: date
    trade_value_million_krw: int
    foreign: int
    institution_total: int


def test_flow_summary_uses_only_days_up_to_asof() -> None:
    flows = [_Flow(date(2026, 9, d), 1000, 100, -50) for d in range(1, 26)]
    s = chart.flow_summary(flows, date(2026, 9, 10), lookbacks=(5, 20))
    assert s["last_flow_date"] == "2026-09-10"
    assert s["d5"] == {"foreign_eok": 5.0, "institution_eok": -2.5, "foreign_ratio": 0.1, "institution_ratio": -0.05}
    assert s["d20"] is None  # only 10 days available


def test_card_always_shows_every_state_and_is_reference_only() -> None:
    frame = chart.base_rate_frame(_dataset())
    rates = chart.compute_base_rates(frame)
    row = frame.iloc[0]
    card = chart.build_card("000000", "테스트", date(2026, 10, 2), row, row, rates, {"last_flow_date": None}, {})
    assert [s["state"] for s in card["states"]] == [s.key for s in chart.STATE_SPECS]
    assert card["used_by_model"] is False and card["layer"] == "reference"
    text = chart.render_text(card)
    assert "모델 점수·순위에 쓰이지 않음" in text


def test_negligible_is_rendered_as_negligible() -> None:
    frame = chart.base_rate_frame(_dataset())
    rates = chart.compute_base_rates(frame)
    for r in rates:
        r["verdict"] = "negligible"
    row = frame.iloc[0]
    card = chart.build_card("000000", "테스트", date(2026, 10, 2), row, row, rates, {"last_flow_date": None}, {})
    text = chart.render_text(card)
    assert "경향 미미" in text and "과거 경향" not in text and "왕복 거래비용" in text
