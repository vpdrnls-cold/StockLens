"""Cross-sectional holdout: the frozen daily model on 150 unseen KOSPI200 stocks (CURRENT_STATUS item 79).

Pre-registered (item 79) BEFORE any of these stocks' returns were looked at. Run it
exactly once. A second run (or a new metric on the same stocks) is a new look.

Question
  Does the frozen daily model's ranking signal (best_iteration 9, fingerprint in
  config/frozen_daily_model.json) also appear in stocks it never saw -- the 150
  KOSPI200 constituents outside top50 (2026-10-04 composition)? This is stock
  generalization only. It does NOT answer whether the signal holds in the future
  (that is the forward holdout's job, item 78).

What is fixed (item 79)
  - The model is not retrained or tuned: it is trained exactly as in
    run_ml_backtest.py on top50 train + validation early stopping, and the run
    stops BEFORE any extra stock is read if its fingerprint does not match.
  - Ranking is within the 150 stocks only; dates with fewer than MIN_STOCKS
    scored + labeled stocks are dropped.
  - Bars are cut at TEST_END_DATE (2026-09-16) before the dataset is built, so no
    label reads a later price and nothing from the forward period is touched.
  - Periods: P = test-period dates (2023-07-01~2026-09-16) -> the ONLY verdict;
    W3 / W1 / W2 are reported only (their dates were used by the model on top50).
  - Verdict on P: mean daily rank IC > 0 and t > 1.65 -> "generalization supported";
    IC > 0, t <= 1.65 -> "direction only"; IC <= 0 -> "generalization failed".
    t = mean IC / (std of daily IC / sqrt(days / 5)) (5-day label overlap).
  - Returns (buffered top-10, buffer 3.0, real costs, 5 rebalance start offsets,
    vs the same 150-stock equal-weight universe) are reported, never used for the verdict.
  - top50 test rows are never scored here.

Decisions behind this run (item 79, 2026-10-06, 재훈): item 68's "extra stocks
unused this cycle" is lifted for this one check, and the test-period dates may be
read for the extra stocks only (STOCKLENS_CONFIRM_FINAL_TEST=1, this run only).

    STOCKLENS_UNIVERSE=top50 STOCKLENS_CONFIRM_FINAL_TEST=1 PYTHONPATH=. \\
        .venv/bin/python scripts/evaluate_cross_sectional_holdout.py
"""

from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from scripts import evaluate_forward_holdout as fh
from scripts.run_ml_backtest import (
    BUFFER_MULTIPLIER,
    STOCK_CODES,
    TOP_N,
    _load_priced_dataset,
    frozen_model_fingerprint,
    train_frozen_model,
)
from src.data.dataset import (
    TEST_END_DATE,
    TEST_START_DATE,
    VALIDATION_END_DATE,
    VALIDATION_START_DATE,
    build_combined_dataset,
)
from src.data.storage import HistoricalStorage
from src.data.universe import KOSPI200_UNIVERSE_PATH, get_universe, load_universe_file
from src.eval.test_lock import TestSetLockedError, confirm_final_test_use
from src.features.engineering import FEATURE_COLUMNS
from src.ml.cross_section import daily_rank_ic, summarize_ic
from src.ml.strategy import predictions_for_dataset

CALLER = "evaluate_cross_sectional_holdout.py"
DEFAULT_OUT = "reports/cross_sectional_holdout"
SUMMARY_FILE = "summary.csv"
MIN_STOCKS = 50  # item 79: dates with fewer scored + labeled stocks are dropped
HORIZON = 5
T_THRESHOLD = 1.65
SCORE_COL = "score"
VERDICT_PERIOD = "P"
# (name, start, end, role) -- fixed in item 79. W1/W2 match walk_forward_backtest_compare.WINDOWS.
PERIODS = (
    ("P", TEST_START_DATE, TEST_END_DATE, "verdict"),
    ("W3", VALIDATION_START_DATE, VALIDATION_END_DATE, "report"),
    ("W1", "2012-01-01", "2015-12-31", "report"),
    ("W2", "2016-01-01", "2019-12-31", "report"),
)
CAP_TOP_GROUP = 50  # item 79 (4): the 50 largest of the 150 vs the remaining 100 (2026-10-04 market cap)


def holdout_codes(all_codes=None, top50=None) -> tuple[str, ...]:
    """KOSPI200 (2026-10-04) minus top50, in the kospi200 file order (market cap, descending)."""
    all_codes = tuple(all_codes if all_codes is not None else get_universe("kospi200"))
    excluded = set(top50 if top50 is not None else get_universe("top50"))
    return tuple(c for c in all_codes if c not in excluded)


def cap_groups(codes: tuple[str, ...], top: int = CAP_TOP_GROUP) -> dict[str, str]:
    """code -> 'cap_top50of150' / 'cap_rest100' by order in ``codes`` (largest first)."""
    return {c: ("cap_top50of150" if i < top else "cap_rest100") for i, c in enumerate(codes)}


def t_stat(ics: pd.Series, horizon: int = HORIZON) -> float:
    """Mean IC over its standard error with days/horizon effective samples (item 79)."""
    filled = ics.fillna(0.0)
    n = len(filled)
    if n < 2:
        return float("nan")
    sd = float(filled.std(ddof=1))
    if not np.isfinite(sd) or sd == 0.0:
        return float("nan")
    return float(filled.mean()) / (sd / np.sqrt(n / horizon))


def verdict(mean_ic: float, t: float, threshold: float = T_THRESHOLD) -> str:
    if not np.isfinite(mean_ic) or mean_ic <= 0:
        return "generalization_failed"
    if np.isfinite(t) and t > threshold:
        return "generalization_supported"
    return "direction_only"


def eligible(part: pd.DataFrame, min_stocks: int = MIN_STOCKS) -> tuple[pd.DataFrame, int]:
    """Rows on dates with >= ``min_stocks`` scored + labeled stocks, and how many dates were dropped."""
    part = part.dropna(subset=[SCORE_COL, "target_return_5d"])
    counts = part.groupby("trade_date")["stock_code"].transform("count")
    kept = part[counts >= min_stocks]
    dropped = int(part["trade_date"].nunique() - kept["trade_date"].nunique())
    return kept, dropped


def period_rows(df: pd.DataFrame, start: str, end: str) -> pd.DataFrame:
    d = pd.to_datetime(df["trade_date"])
    return df[(d >= pd.Timestamp(start)) & (d <= pd.Timestamp(end))]


def truncate_bars(bars, end: str = TEST_END_DATE):
    """Bars on or before ``end`` -- applied before the dataset is built (no label past ``end``)."""
    last = date.fromisoformat(end)
    return [b for b in bars if b.trade_date <= last]


def load_holdout_dataset(codes: tuple[str, ...], storage: HistoricalStorage | None = None,
                         end: str = TEST_END_DATE) -> tuple[pd.DataFrame, list[str]]:
    """Feature/label dataset + open/close prices for ``codes``, bars cut at ``end`` (default TEST_END_DATE).

    ``end`` is overridden only by scripts/run_next_cycle_grid.py (item 84 dev end).

    Stocks whose (cut) history is too short to build a dataset are skipped and returned.
    """
    storage = storage or HistoricalStorage("data")
    parts, prices, skipped = [], [], []
    for code in codes:
        bars = truncate_bars(storage.load_daily_bars(code), end)
        try:
            part = build_combined_dataset({code: bars}) if bars else pd.DataFrame()
        except ValueError:
            part = pd.DataFrame()
        if part.empty:
            skipped.append(code)
            continue
        parts.append(part)
        prices.extend(
            {"trade_date": pd.Timestamp(b.trade_date), "stock_code": code,
             "open_price": float(b.open_price), "close_price": float(b.close_price)}
            for b in bars
        )
    dataset = pd.concat(parts, ignore_index=True)
    dataset["trade_date"] = pd.to_datetime(dataset["trade_date"])
    dataset[list(FEATURE_COLUMNS)] = dataset[list(FEATURE_COLUMNS)].replace([np.inf, -np.inf], np.nan)
    dataset = dataset.merge(pd.DataFrame(prices), on=["trade_date", "stock_code"], how="left", validate="one_to_one")
    if pd.to_datetime(dataset["trade_date"]).max() > pd.Timestamp(end):
        raise AssertionError(f"holdout dataset reaches past {end}")
    return dataset, skipped


def ic_block(name: str, role: str, part: pd.DataFrame, dropped: int) -> tuple[dict, pd.Series]:
    ic = daily_rank_ic(part, SCORE_COL, "target_return_5d")
    s = summarize_ic(ic)
    filled = ic.fillna(0.0)
    t = t_stat(ic)
    row = {
        "period": name, "role": role,
        "start": pd.to_datetime(part["trade_date"]).min(), "end": pd.to_datetime(part["trade_date"]).max(),
        "days": s.n_days, "dropped_dates": dropped,
        "stocks_per_day": float(part.groupby("trade_date").size().mean()),
        "mean_ic": s.mean_ic, "ic_pos": s.pct_pos, "ic_sd": float(filled.std(ddof=1)), "t": t,
        "verdict": verdict(s.mean_ic, t) if role == "verdict" else "",
    }
    return row, ic


def yearly_ic(ic: pd.Series) -> pd.DataFrame:
    """Mean IC by half-year for 2023, then by calendar year (info only)."""
    idx = pd.to_datetime(ic.index)
    label = np.where(idx.year == 2023, "2023H2", idx.year.astype(str))
    filled = ic.fillna(0.0)
    g = filled.groupby(label)
    return pd.DataFrame({"mean_ic": g.mean(), "days": g.size(), "t": ic.groupby(label).apply(t_stat)})


def cap_split_ic(part: pd.DataFrame, groups: dict[str, str]) -> pd.DataFrame:
    """Mean IC within each market-cap group (ranks recomputed inside the group, info only)."""
    rows = []
    for g in sorted(set(groups.values())):
        sub = part[part["stock_code"].map(groups) == g]
        ic = daily_rank_ic(sub, SCORE_COL, "target_return_5d")
        s = summarize_ic(ic)
        rows.append({"group": g, "stocks": int(sub["stock_code"].nunique()), "days": s.n_days,
                     "mean_ic": s.mean_ic, "t": t_stat(ic)})
    return pd.DataFrame(rows)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=DEFAULT_OUT)
    args = ap.parse_args(argv)
    out = Path(args.out)

    if (out / SUMMARY_FILE).exists():
        print(f"STOP: {out / SUMMARY_FILE} exists -- this check runs once (item 79). Nothing was read.")
        return 3
    if set(STOCK_CODES) != set(get_universe("top50")):
        print("STOP: run with STOCKLENS_UNIVERSE=top50 (the frozen model is trained on top50). Nothing was read.")
        return 2

    trained, _ = train_frozen_model(_load_priced_dataset())
    fingerprint = frozen_model_fingerprint(trained)
    print(f"frozen daily model: best_iteration={trained.best_iteration}, fingerprint {fingerprint[:16]}...")
    if not fh.frozen_model_ok(trained.best_iteration, fingerprint):
        print("STOP: not the pre-registered frozen model. The extra stocks were NOT read, so the one look is not spent.")
        return 4

    try:
        confirm_final_test_use(CALLER)
    except TestSetLockedError as locked:
        print(f"STOP: {locked}\nThe extra stocks were NOT read.")
        return 5

    codes = holdout_codes()
    if set(codes) & set(STOCK_CODES) or len(codes) != 150:
        raise AssertionError(f"holdout universe must be 150 stocks disjoint from top50, got {len(codes)}")
    dataset, skipped = load_holdout_dataset(codes)
    preds = predictions_for_dataset(trained, dataset)
    df = dataset.merge(preds.rename(columns={"predicted_return": SCORE_COL}), on=["trade_date", "stock_code"], how="left")
    print(f"holdout stocks: {len(codes) - len(skipped)} built, skipped (history too short): {skipped or 'none'}")

    rows, phase_tables, verdict_part, verdict_ic = [], [], None, None
    for name, start, end, role in PERIODS:
        part, dropped = eligible(period_rows(df, start, end))
        if part.empty:
            rows.append({"period": name, "role": role, "days": 0, "verdict": "no_data" if role == "verdict" else ""})
            continue
        row, ic = ic_block(name, role, part, dropped)
        rows.append(row)
        phases = fh.phase_sensitivity(part, strategies=(("daily", SCORE_COL),))
        phases.insert(0, "period", name)
        phase_tables.append(phases)
        if role == "verdict":
            verdict_part, verdict_ic = part, ic

    summary = pd.DataFrame(rows)
    phases = pd.concat(phase_tables, ignore_index=True) if phase_tables else pd.DataFrame()
    phase_summary = (
        phases.groupby("period")[["net_cum", "univ_ew_gross", "excess_vs_univ", "mdd"]].agg(["mean", "min", "max"])
        if not phases.empty else pd.DataFrame()
    )

    out.mkdir(parents=True, exist_ok=True)
    phases.to_csv(out / "phase_sensitivity.csv", index=False, encoding="utf-8-sig")
    if verdict_part is not None:
        yearly_ic(verdict_ic).to_csv(out / "yearly_ic_P.csv", encoding="utf-8-sig")
        cap_split_ic(verdict_part, cap_groups(codes)).to_csv(out / "cap_split_ic_P.csv", index=False, encoding="utf-8-sig")
    summary.to_csv(out / SUMMARY_FILE, index=False, encoding="utf-8-sig")  # written last = the one-run marker

    print("\n" + "=" * 100)
    print(f"CROSS-SECTIONAL HOLDOUT (once)   150 unseen KOSPI200 stocks, frozen model, top_n={TOP_N}, buffer={BUFFER_MULTIPLIER}")
    print("=" * 100)
    print(summary.to_string(index=False, float_format=lambda x: f"{x:+.4f}"))
    if verdict_part is not None:
        print("\nP by year (info only):")
        print(yearly_ic(verdict_ic).to_string(float_format=lambda x: f"{x:+.4f}"))
        print("\nP by market-cap group (info only):")
        print(cap_split_ic(verdict_part, cap_groups(codes)).to_string(index=False, float_format=lambda x: f"{x:+.4f}"))
    print("\nbuffered top-10 net vs 150-stock equal weight (no costs), 5 start offsets (info only):")
    print(phase_summary.to_string(float_format=lambda x: f"{x:+.4f}"))
    v = summary.loc[summary["role"] == "verdict", "verdict"].iloc[0]
    print("\n" + "=" * 100)
    print(f"PRE-REGISTERED VERDICT (item 79, period P): {v}")
    print("Limit: stock generalization only -- not evidence that the signal holds in the future (forward holdout).")
    print("No change to the frozen model, the production path or the forward rules follows from this result.")
    print(f"saved: {out}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
