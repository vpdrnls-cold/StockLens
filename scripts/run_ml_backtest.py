"""Phase G final evaluation: ML strategy vs. rule-based baseline.

This is the first script in the project that touches
``data/processed`` test-period data through the *backtest* engine.
Per AGENTS.md section 13 ("Never use the final test period to
repeatedly make design decisions"), this script is meant to be run
ONCE the feature set (Phase F) and model (Phase G hyperparameters) are
already frozen -- not as a loop for tuning. If you change the model
after looking at this script's output, you are no longer doing an
out-of-sample evaluation.

Both strategies below run through the exact same execution engine
(src.backtest.baseline.run_baseline_backtest): T+1 open entry,
T+holding_days close exit, identical fees/tax/slippage. Only the
stock-picking rule (score_fn) differs, so the comparison is
apples-to-apples.

The ML model is trained on the per-date RANK of target_return_5d (not
the raw value) with early stopping on cross-sectional rank IC (not
RMSE) -- see the comment above the train_model() call for why
(CURRENT_STATUS.md item 38, the pre-Phase-H checklist's target/early-
stopping adoption decision).
"""

from __future__ import annotations

import os

import numpy as np
import pandas as pd

from src.backtest.baseline import (
    BaselineConfig,
    calculate_performance,
    calculate_score,
    run_baseline_backtest,
    trades_to_dataframe,
)
from src.data.dataset import build_combined_dataset, split_by_time
from src.data.storage import HistoricalStorage
from src.data.universe import get_universe
from src.features.engineering import FEATURE_COLUMNS, SELECTED_FEATURES
from src.eval.test_lock import confirm_final_test_use
from src.ml.cross_section import daily_rank_ic, rank_by_date
from src.ml.strategy import make_model_score_fn, predictions_for_dataset
from src.models.predict import train_model
from src.reporting.run_log import RunRecorder

# core5 by default; STOCKLENS_UNIVERSE=top50 selects the 50-stock universe
# (see src/data/universe.py).
STOCK_CODES = get_universe()

# This script's whole purpose is to produce the ML-vs-baseline numbers
# that decide whether Phase H is warranted -- those numbers must not
# depend on which machine ran them. n_jobs=-1 + the default tree_method
# is NOT reproducible across machines/thread counts for this reason
# (AGENTS.md section 25, CURRENT_STATUS.md items 15/23-25). This was
# never pinned here before (the script pre-dates that discovery and had
# not been run end to end on top50 until item 38), unlike every
# walk-forward diagnostic script since item 23.
DETERMINISTIC_PARAMS = {"n_jobs": 1, "tree_method": "exact"}

CONFIG = BaselineConfig(
    lookback_days=5,
    holding_days=5,
    buy_fee=0.00015,
    sell_fee=0.00015,
    sell_tax=0.0020,
    buy_slippage=0.0010,
    sell_slippage=0.0010,
    # Stocks listed at different times (top50) need the partial-universe engine;
    # core5 keeps the original behavior so recorded results stay reproducible.
    allow_partial_universe=len(STOCK_CODES) != 5,
)

# All-in on the single top pick (top_n=1) concentrates 100% of capital
# in one prediction/momentum score being right. TOP_N>1 equal-weights
# the top N picks each period instead, trading away some upside for
# materially less single-stock blowup risk. Both the momentum baseline
# and the ML strategy use the same TOP_N so the comparison stays
# apples-to-apples.
# With 50 stocks, 2 picks is very concentrated: try STOCKLENS_TOP_N=5 or 10.
TOP_N = int(os.environ.get("STOCKLENS_TOP_N", "2"))


def _load_priced_dataset() -> pd.DataFrame:
    storage = HistoricalStorage("data")

    stock_bars = {
        stock_code: storage.load_daily_bars(stock_code)
        for stock_code in STOCK_CODES
    }

    dataset = build_combined_dataset(stock_bars)
    dataset["trade_date"] = pd.to_datetime(dataset["trade_date"])
    # A handful of top50 stocks produce +-inf feature values (e.g. a
    # near-zero moving average denominator) that core5 never hit -- this
    # script pre-dates the top50 universe (item 28) and was never
    # actually run against it end to end until now. Every top50
    # walk-forward diagnostic script (items 30+) already does this same
    # replacement; XGBoost otherwise hard-errors on inf input.
    dataset[list(FEATURE_COLUMNS)] = dataset[list(FEATURE_COLUMNS)].replace(
        [np.inf, -np.inf], np.nan
    )

    prices = [
        {
            "trade_date": pd.Timestamp(bar.trade_date),
            "stock_code": stock_code,
            "open_price": float(bar.open_price),
            "close_price": float(bar.close_price),
        }
        for stock_code, bars in stock_bars.items()
        for bar in bars
    ]

    return dataset.merge(
        pd.DataFrame(prices),
        on=["trade_date", "stock_code"],
        how="left",
        validate="one_to_one",
    )


def _to_data_by_stock(dataset: pd.DataFrame) -> dict[str, pd.DataFrame]:
    return {
        str(stock_code): (
            group[["stock_code", "trade_date", "open_price", "close_price"]]
            .sort_values("trade_date")
            .reset_index(drop=True)
        )
        for stock_code, group in dataset.groupby("stock_code")
    }


def _print_performance(label: str, trades: list, initial_capital: float = 10_000_000.0) -> None:
    perf = calculate_performance(trades, initial_capital=initial_capital)

    print(f"--- {label} ---")
    print(f"Rebalance periods:  {int(perf['period_count'])}")
    print(f"Positions opened:   {int(perf['trade_count'])}")
    print(f"Cumulative Return:  {perf['total_return']:.4%}")
    print(f"Average Return:     {perf['average_trade_return']:.4%}")
    print(f"Hit Rate:           {perf['win_rate']:.4%}")
    print(f"Maximum Drawdown:   {perf['max_drawdown']:.4%}")
    print()


def main() -> None:
    dataset = _load_priced_dataset()
    splits = split_by_time(dataset)

    # Target: per-date rank of target_return_5d, not the raw value.
    # Early stopping: cross-sectional rank IC, not RMSE.
    # Adopted as the production default per CURRENT_STATUS.md item 38
    # (pre-Phase-H checklist item 5), on the combined evidence of items
    # 32/36/37: the rank target is more stable across all 3 walk-forward
    # windows than the raw target, IC-based early stopping rescues the
    # cases where RMSE-based stopping collapses to a near-untrained model
    # without hurting the cases that were already fine, and a classification
    # reframing (item 38) was strictly worse or equal in every window --
    # so this combination, not raw+rmse, is what Phase G's actual
    # ML-vs-baseline comparison (below) should use.
    print("=== Training daily model (train -> validation early stopping) ===")
    trained = train_model(
        splits.train,
        rank_by_date(splits.train, "target_return_5d"),
        splits.validation,
        rank_by_date(splits.validation, "target_return_5d"),
        params=DETERMINISTIC_PARAMS,
        early_stopping_metric="ic",
    )
    print(f"Best iteration: {trained.best_iteration}")
    print(f"Features: {list(trained.feature_columns)}")
    print()

    confirm_final_test_use("run_ml_backtest.py")

    print("=== Running FINAL evaluation on the untouched test period ===")
    print(
        f"Test period: {splits.test['trade_date'].min()} ~ "
        f"{splits.test['trade_date'].max()}"
    )
    print()

    data_by_stock = _to_data_by_stock(splits.test)

    print(f"=== Diversification: top_n={TOP_N} (equal-weight) ===")
    print()

    # Rule-based momentum baseline (calculate_score is the default
    # score_fn; passed explicitly here just for clarity).
    baseline_trades = run_baseline_backtest(
        data_by_stock, config=CONFIG, score_fn=calculate_score, top_n=TOP_N
    )

    # ML-scored strategy: same engine, predictions instead of momentum.
    # Note: since the model is trained on the rank target now, these are
    # rank-scale scores (roughly in (-0.5, 0.5)), not return magnitudes --
    # score_fn only needs relative ordering to pick top_n, so this is
    # fine, but the "predicted_return" column name is a slight misnomer
    # inherited from src.ml.strategy's original raw-target design.
    predictions = predictions_for_dataset(trained, splits.test)
    model_score_fn = make_model_score_fn(predictions)
    model_trades = run_baseline_backtest(
        data_by_stock, config=CONFIG, score_fn=model_score_fn, top_n=TOP_N
    )

    _print_performance("Rule-based momentum baseline", baseline_trades)
    _print_performance("ML-scored strategy (XGBoost)", model_trades)

    print("=== ML strategy trades ===")
    print(trades_to_dataframe(model_trades).to_string(index=False))

    # Keep the time series of this (already confirmed) test run so it can be
    # plotted later with scripts/plot_run.py WITHOUT re-running this script --
    # re-running it is a new test access; re-plotting a saved run is not.
    scored = splits.test[["trade_date", "stock_code", "target_return_5d"]].copy()
    scored["trade_date"] = pd.to_datetime(scored["trade_date"])
    scored = scored.merge(predictions, on=["trade_date", "stock_code"], how="left")
    scored = scored.dropna(subset=["target_return_5d"])

    recorder = RunRecorder(
        "run_ml_backtest_test",
        meta={
            "script": "scripts/run_ml_backtest.py",
            "split": "TEST (confirmed via STOCKLENS_CONFIRM_FINAL_TEST)",
            "universe_size": len(STOCK_CODES),
            "top_n": TOP_N,
            "best_iteration": trained.best_iteration,
        },
    )
    recorder.add_trades("test", "momentum", baseline_trades)
    recorder.add_trades("test", "ml", model_trades)
    recorder.add_ic("test", "ml", daily_rank_ic(scored, "predicted_return"))
    recorder.save()


if __name__ == "__main__":
    main()
