"""Walk-forward robustness check for the HOLD/SELL stop-loss multiplier.

Background: scripts/evaluate_position_thresholds.py found that on the
current default validation window (2020-01~2023-06), tightening
``PositionConfig.stop_loss_atr_multiple`` from the hard-coded default
3.0x to 1.5x improved cum_return/mdd/std_period versus "no early
exit", while 1.0x made things worse than no exit rule at all
(CURRENT_STATUS.md item 17). That is a single-split result, and
AGENTS.md 13 / item 15's precedent (Wrapper feature-selection winners
that only held up in 1 of 3 time windows) is explicit that a
single-split winner is not trustworthy on its own.

This script repeats the same stop-loss grid across the SAME three
non-overlapping train/validation windows scripts/walk_forward_wrapper.py
already used for the feature-selection robustness check, so the
windows themselves are not new/cherry-picked. The real TEST period
(2023-07 on) is never touched, in any window (AGENTS.md 13).

For each window, both the "no early exit" baseline and the stop-loss
grid reuse the exact same decision grid, top_n=2 model-scored stock
selection, and cost assumptions as evaluate_position_thresholds.py --
only the exit rule differs.

Run from the repo root (takes a few minutes: 3 windows x 1 model fit
each, backtest grid is cheap):
    PYTHONPATH=. python3 scripts/walk_forward_position_thresholds.py
"""

from __future__ import annotations

from collections import defaultdict

import numpy as np
import pandas as pd

from src.backtest.baseline import calculate_performance, prepare_universe, run_baseline_backtest
from src.data.dataset import TEST_END_DATE, TEST_START_DATE, TRAIN_START_DATE, split_by_time
from src.ml.strategy import make_model_score_fn, predictions_for_dataset
from src.models.predict import train_model
from src.portfolio.optimizer import PositionConfig

from scripts.evaluate_position_thresholds import (
    CONFIG,
    SIGNAL_COLUMNS,
    TOP_N,
    _load_priced_dataset,
    _period_return_stats,
    _to_data_by_stock,
    simulate_exit_rule,
)

# Same three windows as scripts/walk_forward_wrapper.py, same reasoning:
# expanding train window, non-overlapping validation windows, real test
# period never touched.
WINDOWS = [
    ("Window 1: train ..2011-12-31 / val 2012-2015", "2011-12-31", "2012-01-01", "2015-12-31"),
    ("Window 2: train ..2015-12-31 / val 2016-2019", "2015-12-31", "2016-01-01", "2019-12-31"),
    ("Window 3: train ..2019-12-31 / val 2020-2023.06 (current default)", "2019-12-31", "2020-01-01", "2023-06-30"),
]

STOP_LOSS_GRID = (1.0, 1.5, 2.0, 3.0, 4.0, 6.0)

# Deterministic: same fix as walk_forward_wrapper.py / AGENTS.md 25 --
# XGBoost's histogram-tree multithreading is not bitwise-reproducible
# across machines with n_jobs=-1. n_jobs=1 alone still wasn't enough
# cross-machine (CURRENT_STATUS.md items 18/20/21) -- tree_method=
# "exact" is what item 23 confirmed gives bit-identical results across
# two genuinely different real machines (Linux x86_64 vs macOS arm64).
DETERMINISTIC_PARAMS = {"n_jobs": 1, "tree_method": "exact"}


def _row_metrics(trades, holding_days, exit_reasons) -> dict:
    perf = calculate_performance(trades)
    avg_period, std_period = _period_return_stats(trades)
    n = len(exit_reasons)
    stop_loss_pct = exit_reasons.count("stop_loss") / n if n else float("nan")
    return {
        "cum_return": perf["total_return"],
        "mdd": perf["max_drawdown"],
        "std_period": std_period,
        "avg_hold_d": float(np.mean(holding_days)) if holding_days else float("nan"),
        "stop_loss_pct": stop_loss_pct,
        "n_trades": n,
    }


def main() -> None:
    dataset = _load_priced_dataset()

    # window_label -> multiple_or_"baseline" -> metrics dict
    all_results: dict[str, dict] = {}

    for label, train_end, val_start, val_end in WINDOWS:
        print("\n" + "=" * 100)
        print(label)
        print("=" * 100)

        splits = split_by_time(
            dataset,
            train_start=TRAIN_START_DATE,
            train_end=train_end,
            validation_start=val_start,
            validation_end=val_end,
            test_start=TEST_START_DATE,
            test_end=TEST_END_DATE,
        )
        print(
            f"  train: {splits.train['trade_date'].min().date()} ~ "
            f"{splits.train['trade_date'].max().date()}  (n={len(splits.train)})"
        )
        print(
            f"  val:   {splits.validation['trade_date'].min().date()} ~ "
            f"{splits.validation['trade_date'].max().date()}  (n={len(splits.validation)})"
        )

        trained = train_model(
            splits.train,
            splits.train["target_return_5d"],
            splits.validation,
            splits.validation["target_return_5d"],
            params=DETERMINISTIC_PARAMS,
        )
        print(f"  best_iteration={trained.best_iteration}")

        predictions = predictions_for_dataset(trained, splits.validation)
        signals = splits.validation[SIGNAL_COLUMNS].merge(
            predictions, on=["trade_date", "stock_code"], validate="one_to_one"
        )
        predictions_lookup = {
            (row.trade_date, row.stock_code): row.predicted_return
            for row in signals.itertuples(index=False)
        }
        atr_lookup = {
            (row.trade_date, row.stock_code): row.atr_pct
            for row in signals.itertuples(index=False)
        }

        data_by_stock = _to_data_by_stock(splits.validation)
        universe = prepare_universe(data_by_stock)
        stock_codes = list(data_by_stock.keys())

        window_results: dict = {}

        baseline_score_fn = make_model_score_fn(predictions)
        baseline_trades = run_baseline_backtest(
            data_by_stock, config=CONFIG, score_fn=baseline_score_fn, top_n=TOP_N
        )
        window_results["baseline"] = _row_metrics(
            baseline_trades,
            [CONFIG.holding_days] * len(baseline_trades),
            ["max_holding_reached"] * len(baseline_trades),
        )

        print(
            f"\n  {'config':<16}{'cum_return':>12}{'mdd':>10}{'std_period':>12}"
            f"{'avg_hold_d':>10}{'stop_loss%':>11}{'n':>6}"
        )
        m = window_results["baseline"]
        print(
            f"  {'baseline':<16}{m['cum_return']:>11.2%} {m['mdd']:>9.2%} "
            f"{m['std_period']:>11.4%}{m['avg_hold_d']:>10.2f}{m['stop_loss_pct']:>10.1%} "
            f"{m['n_trades']:>6}"
        )

        for multiple in STOP_LOSS_GRID:
            # sell_percentile_threshold=None pins this to the absolute
            # reversal rule so the grid isolates only the stop-loss
            # multiplier, matching this script's original, documented
            # meaning (CURRENT_STATUS.md item 18) -- the class default
            # became the percentile rule in items 20/21.
            cfg = PositionConfig(
                stop_loss_atr_multiple=multiple,
                sell_predicted_return_threshold=0.0,
                sell_percentile_threshold=None,
            )
            result = simulate_exit_rule(
                universe, predictions_lookup, atr_lookup, stock_codes, CONFIG, cfg, TOP_N
            )
            metrics = _row_metrics(result.trades, result.holding_days, result.exit_reasons)
            window_results[multiple] = metrics
            print(
                f"  {f'{multiple:g}x':<16}{metrics['cum_return']:>11.2%} {metrics['mdd']:>9.2%} "
                f"{metrics['std_period']:>11.4%}{metrics['avg_hold_d']:>10.2f}"
                f"{metrics['stop_loss_pct']:>10.1%}{metrics['n_trades']:>6}"
            )

        all_results[label] = window_results

    # ------------------------------------------------------------------
    print("\n" + "=" * 100)
    print("SUMMARY ACROSS WINDOWS")
    print("=" * 100)
    print(
        "\nFor each multiple: how many of the 3 windows show it beating that "
        "window's own baseline on mdd and on std_period (higher = more stable), "
        "plus the average delta (negative = improvement for mdd, which is "
        "already negative; negative = improvement for std_period too)."
    )
    print(
        f"\n{'multiple':<10}{'mdd_wins':>10}{'avg_mdd_delta':>16}"
        f"{'std_wins':>10}{'avg_std_delta':>16}{'avg_cum_delta':>16}"
    )

    for multiple in STOP_LOSS_GRID:
        mdd_deltas = []
        std_deltas = []
        cum_deltas = []
        for label in all_results:
            baseline = all_results[label]["baseline"]
            row = all_results[label][multiple]
            mdd_deltas.append(row["mdd"] - baseline["mdd"])
            std_deltas.append(row["std_period"] - baseline["std_period"])
            cum_deltas.append(row["cum_return"] - baseline["cum_return"])

        mdd_wins = sum(1 for d in mdd_deltas if d > 0)  # mdd is negative; improvement = less negative = larger value
        std_wins = sum(1 for d in std_deltas if d < 0)  # lower volatility = improvement

        print(
            f"{f'{multiple:g}x':<10}{mdd_wins:>9}/3{np.mean(mdd_deltas):>15.4%}"
            f"{std_wins:>9}/3{np.mean(std_deltas):>15.4%}{np.mean(cum_deltas):>16.4%}"
        )

    print(
        "\nInterpretation: a multiple that wins on mdd and/or std_period in "
        "2-3/3 windows is a real, stable risk-reduction effect. A multiple "
        "that only wins in 1/3 (e.g. only in the current default window) "
        "is very likely the same kind of window-specific noise item 15 "
        "already found for feature selection, and should not be adopted "
        "as the new default on this evidence alone."
    )


if __name__ == "__main__":
    main()
