"""Daily ML strategy through the buffered engine -- validation check + forward holdout.

CURRENT_STATUS item 47 (pre-registered item 46, D1).

What changed vs the Phase G version (item 41)
  - Engine: ``run_buffered_backtest`` with top_n=10 and buffer_multiplier=3.0
    (item 35 grid, re-confirmed under the next_open target in item 45: net
    positive in all 3 walk-forward windows). Both values are FIXED by
    pre-registration -- there is deliberately no environment override.
  - Final evaluation period: the daily test split (2023-07-01~2026-09-16) was
    consumed by item 41 and is no longer read here at all. The only clean
    holdout is the FORWARD period (2026-09-24~, collected nightly by
    scripts/nightly_ingest.sh), shared with the intraday track (item 46). It is
    locked by ``src.data.intraday_split`` until at least 60 decision dates exist
    AND STOCKLENS_CONFIRM_INTRADAY_FORWARD=1 is set for that one run.

What runs without any flag (safe to rerun)
  1. Train the frozen daily model: train 2002-10-29~2019-12-31, early stopping
     on validation 2020-01-01~2023-06-30; per-date rank target, IC-based early
     stopping, deterministic params (items 36/38).
  2. Validation-period backtest of three strategies through the same costs:
         ml_buffered   ML score, top 10, buffer 3.0     <- the strategy to deploy
         ml_plain      ML score, top 10, full turnover  (reference)
         momentum      past 5-day return, top 10, full turnover (legacy baseline)
     This model is exactly the W3 model of the walk-forward scripts (same train
     end and validation window), so ml_buffered / ml_plain must reproduce item 45
     (A_all19, W3): buffered net_cum +65.0% / MDD -43.7%, plain net_cum -2.2%.
     A mismatch means the production path differs from the experiment path.
  3. Stop at the forward lock.

    STOCKLENS_UNIVERSE=top50 PYTHONPATH=. python scripts/run_ml_backtest.py

Forward evaluation (ONCE, after >= 60 forward decision dates; not before ~late Dec 2026)

    STOCKLENS_UNIVERSE=top50 STOCKLENS_CONFIRM_INTRADAY_FORWARD=1 PYTHONPATH=. python scripts/run_ml_backtest.py

The Phase G version (momentum vs ML on the test split, top_n=2) is in git
history before this change (item 41) if it ever needs to be reproduced.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.backtest.baseline import (
    BaselineConfig,
    calculate_performance,
    calculate_score,
    run_baseline_backtest,
)
from src.backtest.buffered import BufferedBaselineConfig, run_buffered_backtest_with_turnover
from src.data.dataset import build_combined_dataset, split_by_time
from src.data.intraday_split import IntradaySplitError, select_segment
from src.data.storage import HistoricalStorage
from src.data.universe import get_universe
from src.eval.test_lock import TestSetLockedError
from src.features.engineering import FEATURE_COLUMNS
from src.ml.cross_section import daily_rank_ic, rank_by_date, summarize_ic
from src.ml.strategy import make_model_score_fn, predictions_for_dataset
from src.models.predict import TrainedModel, train_model
from src.reporting.run_log import RunRecorder

# core5 by default; STOCKLENS_UNIVERSE=top50 selects the 50-stock universe.
STOCK_CODES = get_universe()

# Cross-machine reproducibility (AGENTS.md section 25, items 15/23-25).
DETERMINISTIC_PARAMS = {"n_jobs": 1, "tree_method": "exact"}

# Pre-registered in item 46 (D1). Not overridable on purpose.
TOP_N = 10
BUFFER_MULTIPLIER = 3.0

COST_KWARGS = dict(
    lookback_days=5,
    holding_days=5,
    buy_fee=0.00015,
    sell_fee=0.00015,
    sell_tax=0.0020,
    buy_slippage=0.0010,
    sell_slippage=0.0010,
    allow_partial_universe=len(STOCK_CODES) != 5,
)
PLAIN_CONFIG = BaselineConfig(**COST_KWARGS)
BUFFERED_CONFIG = BufferedBaselineConfig(**COST_KWARGS, buffer_multiplier=BUFFER_MULTIPLIER)

# Item 45, A_all19, W3 (same model as this script's validation run).
EXPECTED_VALIDATION = {"ml_buffered": 0.650, "ml_plain": -0.022}


def _load_priced_dataset() -> pd.DataFrame:
    storage = HistoricalStorage("data")
    stock_bars = {code: storage.load_daily_bars(code) for code in STOCK_CODES}

    dataset = build_combined_dataset(stock_bars)
    dataset["trade_date"] = pd.to_datetime(dataset["trade_date"])
    # Some top50 stocks produce +-inf features (near-zero denominators);
    # XGBoost hard-errors on inf (item 38).
    dataset[list(FEATURE_COLUMNS)] = dataset[list(FEATURE_COLUMNS)].replace(
        [np.inf, -np.inf], np.nan
    )
    prices = pd.DataFrame(
        [
            {
                "trade_date": pd.Timestamp(bar.trade_date),
                "stock_code": code,
                "open_price": float(bar.open_price),
                "close_price": float(bar.close_price),
            }
            for code, bars in stock_bars.items()
            for bar in bars
        ]
    )
    return dataset.merge(prices, on=["trade_date", "stock_code"], how="left", validate="one_to_one")


def trading_calendar() -> list[pd.Timestamp]:
    """Every bar date in the universe's price files -- lets select_segment purge exactly (item 49)."""
    storage = HistoricalStorage("data")
    return sorted({pd.Timestamp(bar.trade_date) for code in STOCK_CODES for bar in storage.load_daily_bars(code)})


def _to_data_by_stock(dataset: pd.DataFrame) -> dict[str, pd.DataFrame]:
    return {
        str(code): group[["stock_code", "trade_date", "open_price", "close_price"]]
        .sort_values("trade_date")
        .reset_index(drop=True)
        for code, group in dataset.groupby("stock_code")
    }


def train_frozen_model(dataset: pd.DataFrame) -> tuple[TrainedModel, object]:
    splits = split_by_time(dataset)
    trained = train_model(
        splits.train,
        rank_by_date(splits.train, "target_return_5d"),
        splits.validation,
        rank_by_date(splits.validation, "target_return_5d"),
        params=DETERMINISTIC_PARAMS,
        early_stopping_metric="ic",
    )
    return trained, splits


def evaluate_period(period: pd.DataFrame, trained: TrainedModel) -> tuple[pd.DataFrame, dict, float]:
    """Run the three strategies on one period. Returns (summary table, trades, mean IC)."""
    data_by_stock = _to_data_by_stock(period)
    predictions = predictions_for_dataset(trained, period)
    ml_score_fn = make_model_score_fn(predictions)

    ml_buffered, turnover = run_buffered_backtest_with_turnover(
        data_by_stock, BUFFERED_CONFIG, score_fn=ml_score_fn, top_n=TOP_N
    )
    trades = {
        "ml_buffered": ml_buffered,
        "ml_plain": run_baseline_backtest(data_by_stock, PLAIN_CONFIG, score_fn=ml_score_fn, top_n=TOP_N),
        "momentum": run_baseline_backtest(data_by_stock, PLAIN_CONFIG, score_fn=calculate_score, top_n=TOP_N),
    }

    rows = []
    for name, t in trades.items():
        perf = calculate_performance(t)
        rows.append({
            "strategy": name,
            "periods": int(perf["period_count"]),
            "net_cum": perf["total_return"],
            "avg_period": perf["average_trade_return"],
            "hit_rate": perf["win_rate"],
            "mdd": perf["max_drawdown"],
            "entries_per_period": turnover["entries_per_period"] if name == "ml_buffered" else float(TOP_N),
        })

    scored = period[["trade_date", "stock_code", "target_return_5d"]].merge(
        predictions, on=["trade_date", "stock_code"], how="left"
    ).dropna(subset=["target_return_5d"])
    ic = daily_rank_ic(scored, "predicted_return")
    return pd.DataFrame(rows), trades, ic


def _print_table(title: str, table: pd.DataFrame, ic: pd.Series) -> None:
    print("=" * 96)
    print(f"{title}   (top_n={TOP_N}, buffer={BUFFER_MULTIPLIER}, real costs)")
    print("=" * 96)
    print(f"{'strategy':<13}{'periods':>8}{'net_cum':>10}{'avg/5d':>9}{'hit':>8}{'mdd':>9}{'entries/period':>16}")
    for r in table.itertuples():
        print(
            f"{r.strategy:<13}{r.periods:>8}{r.net_cum:>10.1%}{r.avg_period:>9.3%}"
            f"{r.hit_rate:>8.1%}{r.mdd:>9.1%}{r.entries_per_period:>16.2f}"
        )
    s = summarize_ic(ic)
    print(f"ML daily rank IC: mean {s.mean_ic:+.4f}, IC>0 {s.pct_pos:.1%}, days {s.n_days}")


def main() -> None:
    dataset = _load_priced_dataset()

    print("=== Training frozen daily model (train -> validation early stopping) ===")
    trained, splits = train_frozen_model(dataset)
    print(f"Best iteration: {trained.best_iteration}")
    print()

    # --- 1. validation check (no flag needed) ---------------------------------
    table, _, ic = evaluate_period(splits.validation, trained)
    _print_table(
        f"VALIDATION {splits.validation['trade_date'].min():%Y-%m-%d} ~ "
        f"{splits.validation['trade_date'].max():%Y-%m-%d}",
        table, ic,
    )
    got = table.set_index("strategy")["net_cum"]
    ok = all(abs(got[k] - v) < 0.0015 for k, v in EXPECTED_VALIDATION.items())
    print(
        f"\nCross-check vs item 45 (A_all19, W3): ml_buffered {got['ml_buffered']:+.1%} "
        f"(expected +65.0%), ml_plain {got['ml_plain']:+.1%} (expected -2.2%) -> "
        f"{'MATCH' if ok else 'MISMATCH -- production path differs from experiment path'}"
    )
    print()

    # --- 2. forward holdout (locked) -------------------------------------------
    try:
        forward = select_segment(
            dataset, "forward", caller="run_ml_backtest.py", horizon=5, calendar=trading_calendar()
        )
    except (TestSetLockedError, IntradaySplitError) as locked:
        print(f"Forward holdout not evaluated: {locked}")
        return
    table, trades, ic = evaluate_period(forward, trained)
    _print_table(
        f"FORWARD HOLDOUT {forward['trade_date'].min():%Y-%m-%d} ~ {forward['trade_date'].max():%Y-%m-%d}",
        table, ic,
    )

    recorder = RunRecorder(
        "run_ml_backtest_forward",
        meta={
            "script": "scripts/run_ml_backtest.py",
            "split": "FORWARD holdout (confirmed via STOCKLENS_CONFIRM_INTRADAY_FORWARD)",
            "universe_size": len(STOCK_CODES),
            "top_n": TOP_N,
            "buffer_multiplier": BUFFER_MULTIPLIER,
            "best_iteration": trained.best_iteration,
        },
    )
    for name, t in trades.items():
        recorder.add_trades("forward", name, t)
    recorder.add_ic("forward", "ml", ic)
    recorder.save()


if __name__ == "__main__":
    main()
