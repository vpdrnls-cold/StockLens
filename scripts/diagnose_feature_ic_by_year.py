"""Standalone cross-sectional IC of every feature, year by year (no model).

Answers: is a feature's relationship with the next 5-day return stable in
sign and size over time, or does it flip / fade? A stable sign in the
expected direction is what a model could exploit; a sign that flips by
regime is what makes Wrapper "winners" differ between validation windows.

Only dates up to VALIDATION_END_DATE are used -- the test period is never
touched (AGENTS.md 13).

    STOCKLENS_UNIVERSE=top50 PYTHONPATH=. python3 scripts/diagnose_feature_ic_by_year.py
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.data.dataset import VALIDATION_END_DATE, build_combined_dataset
from src.data.storage import HistoricalStorage
from src.data.universe import get_universe
from src.features.engineering import FEATURE_COLUMNS
from src.ml.cross_section import daily_rank_ic

RAW_SCALE_FEATURES = {
    "sma_5", "sma_20", "sma_60", "macd", "macd_signal", "macd_hist",
    "atr_14", "volume_sma_20",
}
CANDIDATES = tuple(f for f in FEATURE_COLUMNS if f not in RAW_SCALE_FEATURES)
FIRST_YEAR = 2003

PERIODS = [
    ("2003-11", "2003-01-01", "2011-12-31"),
    ("W1 12-15", "2012-01-01", "2015-12-31"),
    ("W2 16-19", "2016-01-01", "2019-12-31"),
    ("W3 20-23H1", "2020-01-01", VALIDATION_END_DATE),
]


def load_dataset() -> pd.DataFrame:
    storage = HistoricalStorage("data")
    stock_bars = {code: storage.load_daily_bars(code) for code in get_universe()}
    dataset = build_combined_dataset(stock_bars)
    dataset["trade_date"] = pd.to_datetime(dataset["trade_date"])
    dataset[list(FEATURE_COLUMNS)] = dataset[list(FEATURE_COLUMNS)].replace(
        [np.inf, -np.inf], np.nan
    )
    return dataset


def main() -> None:
    dataset = load_dataset()
    dataset = dataset[
        (dataset["trade_date"] >= f"{FIRST_YEAR}-01-01")
        & (dataset["trade_date"] <= VALIDATION_END_DATE)
    ]

    ic_by_feature = {
        feature: daily_rank_ic(dataset, feature).fillna(0.0) for feature in CANDIDATES
    }
    years = sorted(dataset["trade_date"].dt.year.unique())

    stocks_per_day = dataset.groupby("trade_date")["stock_code"].nunique()
    print("Stocks per date (median) by year: " + "  ".join(
        f"{y}:{int(stocks_per_day[stocks_per_day.index.year == y].median())}" for y in years
    ))

    print("\nMean daily rank IC x100, by calendar year (5-day forward return)")
    header = f"{'feature':<18}" + "".join(f"{y % 100:>6}" for y in years) + f"{'  yrs>0':>8}"
    print(header)
    rows = []
    for feature, ics in ic_by_feature.items():
        yearly = ics.groupby(ics.index.year).mean() * 100
        positive = int((yearly > 0).sum())
        rows.append((feature, yearly, positive))
        cells = "".join(f"{yearly.get(y, float('nan')):>6.1f}" for y in years)
        print(f"{feature:<18}{cells}{positive:>4}/{len(years)}")

    print("\nMean daily rank IC x100, by period (same windows as walk_forward_wrapper)")
    print(f"{'feature':<18}" + "".join(f"{label:>12}" for label, _, _ in PERIODS) + f"{'same sign':>11}")
    for feature, ics in ic_by_feature.items():
        means = []
        for _, start, end in PERIODS:
            window = ics[(ics.index >= start) & (ics.index <= end)]
            means.append(window.mean() * 100)
        same_sign = all(m > 0 for m in means) or all(m < 0 for m in means)
        print(
            f"{feature:<18}" + "".join(f"{m:>12.2f}" for m in means)
            + f"{'yes' if same_sign else 'no':>11}"
        )

    print(
        "\nRead this as: with ~40 stocks a daily IC has a standard deviation of "
        "about 0.16, and 5-day forward returns overlap, so a YEARLY mean IC "
        "(x100) has a standard error of about 2 and a 4-year PERIOD mean about "
        "1. Cells within +-4 (yearly) or +-2 (period) are noise; look for a "
        "sign that repeats across years and periods."
    )


if __name__ == "__main__":
    main()
