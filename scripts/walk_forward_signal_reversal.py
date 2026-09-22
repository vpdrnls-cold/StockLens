"""Walk-forward robustness check for the percentile-based signal-reversal
rule (src.portfolio.optimizer.PositionConfig.sell_percentile_threshold).

Background: scripts/evaluate_signal_reversal_thresholds.py found, on
the single current-default validation window (2020-01~2023-06), that
percentile<=40% clearly beat "stop-loss only" -- better cum_return
(-38.35% vs -39.99%), much better mdd (-50.96% vs -63.30%) and
std_period (2.99% vs 3.90%). Per CURRENT_STATUS.md item 18's own
lesson (the stop-loss multiplier's single-split "winner", 1.5x, did
not survive walk-forward -- the original untested 3.0x default did),
a single-split winner here must not be trusted without the same
check.

Repeats the percentile grid across the same three non-overlapping
windows scripts/walk_forward_wrapper.py and
scripts/walk_forward_position_thresholds.py already used. The real
TEST period (2023-07 on) is never touched, in any window.

Run from the repo root (a few minutes: 3 windows x 1 model fit each):
    PYTHONPATH=. python3 scripts/walk_forward_signal_reversal.py
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.backtest.baseline import calculate_performance, prepare_universe
from src.data.dataset import TEST_END_DATE, TEST_START_DATE, TRAIN_START_DATE, split_by_time
from src.ml.strategy import predictions_for_dataset
from src.models.predict import train_model
from src.portfolio.optimizer import PositionConfig
from src.recommendation.scoring import add_predicted_return_percentile

from scripts.evaluate_position_thresholds import (
    CONFIG,
    SIGNAL_COLUMNS,
    TOP_N,
    _load_priced_dataset,
    _period_return_stats,
    _to_data_by_stock,
    simulate_exit_rule,
)
from scripts.evaluate_signal_reversal_thresholds import PERCENTILE_GRID, REVERSAL_DISABLED

# Same three windows as walk_forward_wrapper.py / walk_forward_position_thresholds.py.
WINDOWS = [
    ("Window 1: train ..2011-12-31 / val 2012-2015", "2011-12-31", "2012-01-01", "2015-12-31"),
    ("Window 2: train ..2015-12-31 / val 2016-2019", "2015-12-31", "2016-01-01", "2019-12-31"),
    ("Window 3: train ..2019-12-31 / val 2020-2023.06 (current default)", "2019-12-31", "2020-01-01", "2023-06-30"),
]

# Validated in CURRENT_STATUS.md item 18.
STOP_LOSS_ATR_MULTIPLE = 3.0

# n_jobs=1 alone did not give cross-machine reproducibility (this is
# exactly the script that surfaced that in items 20/21) --
# tree_method="exact" is what item 23 confirmed gives bit-identical
# results across two genuinely different real machines (Linux x86_64
# vs macOS arm64).
DETERMINISTIC_PARAMS = {"n_jobs": 1, "tree_method": "exact"}

# A window whose model stopped after fewer than this many boosting rounds
# is treated as near-untrained (CURRENT_STATUS.md items 18/24/25: Window 1
# gave best_iteration=0 under tree_method="hist" and =1 under "exact", and
# the old ``== 0`` check missed the latter). Healthy windows stopped at
# 47~116 rounds, so 10 leaves a wide margin on both sides.
MIN_RELIABLE_BEST_ITERATION = 10


def _row_metrics(trades, holding_days, exit_reasons) -> dict:
    perf = calculate_performance(trades)
    avg_period, std_period = _period_return_stats(trades)
    n = len(exit_reasons)
    reversal_pct = exit_reasons.count("signal_reversal") / n if n else float("nan")
    return {
        "cum_return": perf["total_return"],
        "mdd": perf["max_drawdown"],
        "std_period": std_period,
        "avg_hold_d": float(np.mean(holding_days)) if holding_days else float("nan"),
        "reversal_pct": reversal_pct,
        "n_trades": n,
    }


def main() -> None:
    dataset = _load_priced_dataset()

    all_results: dict[str, dict] = {}
    window_best_iterations: dict[str, int] = {}

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
        window_best_iterations[label] = trained.best_iteration
        if trained.best_iteration < MIN_RELIABLE_BEST_ITERATION:
            print(
                f"  ⚠ best_iteration={trained.best_iteration} < "
                f"{MIN_RELIABLE_BEST_ITERATION} -- near-untrained model (same "
                "anomaly as CURRENT_STATUS.md item 18's Window1). Treat this "
                "window's numbers as unreliable, reference only."
            )

        predictions = predictions_for_dataset(trained, splits.validation)
        signals = splits.validation[SIGNAL_COLUMNS].merge(
            predictions, on=["trade_date", "stock_code"], validate="one_to_one"
        )
        signals = add_predicted_return_percentile(signals)

        predictions_lookup = {
            (row.trade_date, row.stock_code): row.predicted_return
            for row in signals.itertuples(index=False)
        }
        atr_lookup = {
            (row.trade_date, row.stock_code): row.atr_pct
            for row in signals.itertuples(index=False)
        }
        percentile_lookup = {
            (row.trade_date, row.stock_code): row.predicted_return_percentile
            for row in signals.itertuples(index=False)
        }

        data_by_stock = _to_data_by_stock(splits.validation)
        universe = prepare_universe(data_by_stock)
        stock_codes = list(data_by_stock.keys())

        window_results: dict = {}

        # sell_percentile_threshold=None: this baseline exists to isolate
        # "no reversal rule at all" -- without pinning it explicitly it
        # would silently become the percentile rule now that
        # PositionConfig's class default is 0.20 (items 20/21).
        stop_only_cfg = PositionConfig(
            stop_loss_atr_multiple=STOP_LOSS_ATR_MULTIPLE,
            sell_predicted_return_threshold=REVERSAL_DISABLED,
            sell_percentile_threshold=None,
        )
        stop_only_result = simulate_exit_rule(
            universe, predictions_lookup, atr_lookup, stock_codes, CONFIG, stop_only_cfg, TOP_N
        )
        window_results["baseline"] = _row_metrics(
            stop_only_result.trades, stop_only_result.holding_days, stop_only_result.exit_reasons
        )

        print(
            f"\n  {'config':<20}{'cum_return':>12}{'mdd':>10}{'std_period':>12}"
            f"{'avg_hold_d':>10}{'reversal%':>10}{'n':>6}"
        )
        m = window_results["baseline"]
        print(
            f"  {'stop_loss_only':<20}{m['cum_return']:>11.2%} {m['mdd']:>9.2%} "
            f"{m['std_period']:>11.4%}{m['avg_hold_d']:>10.2f}{m['reversal_pct']:>9.1%} "
            f"{m['n_trades']:>6}"
        )

        for pct in PERCENTILE_GRID:
            cfg = PositionConfig(
                stop_loss_atr_multiple=STOP_LOSS_ATR_MULTIPLE, sell_percentile_threshold=pct
            )
            result = simulate_exit_rule(
                universe, predictions_lookup, atr_lookup, stock_codes, CONFIG, cfg, TOP_N,
                percentile_lookup=percentile_lookup,
            )
            metrics = _row_metrics(result.trades, result.holding_days, result.exit_reasons)
            window_results[pct] = metrics
            print(
                f"  {f'pct<={pct:.0%}':<20}{metrics['cum_return']:>11.2%} {metrics['mdd']:>9.2%} "
                f"{metrics['std_period']:>11.4%}{metrics['avg_hold_d']:>10.2f}"
                f"{metrics['reversal_pct']:>9.1%}{metrics['n_trades']:>6}"
            )

        all_results[label] = window_results

    # ------------------------------------------------------------------
    print("\n" + "=" * 100)
    print("SUMMARY ACROSS WINDOWS")
    print("=" * 100)
    unreliable = [
        label
        for label, it in window_best_iterations.items()
        if it < MIN_RELIABLE_BEST_ITERATION
    ]
    if unreliable:
        print(
            f"\n⚠ Excluding from the vote count "
            f"(best_iteration < {MIN_RELIABLE_BEST_ITERATION}): {unreliable}"
        )
    reliable_labels = [label for label in all_results if label not in unreliable]

    print(
        f"\nAcross the {len(reliable_labels)} reliable window(s): how many show each "
        "percentile beating that window's own stop_loss_only baseline on mdd and on "
        "std_period, plus the average delta."
    )
    print(
        f"\n{'percentile':<12}{'mdd_wins':>10}{'avg_mdd_delta':>16}"
        f"{'std_wins':>10}{'avg_std_delta':>16}{'avg_cum_delta':>16}"
    )

    for pct in PERCENTILE_GRID:
        mdd_deltas, std_deltas, cum_deltas = [], [], []
        for label in reliable_labels:
            baseline = all_results[label]["baseline"]
            row = all_results[label][pct]
            mdd_deltas.append(row["mdd"] - baseline["mdd"])
            std_deltas.append(row["std_period"] - baseline["std_period"])
            cum_deltas.append(row["cum_return"] - baseline["cum_return"])

        mdd_wins = sum(1 for d in mdd_deltas if d > 0)
        std_wins = sum(1 for d in std_deltas if d < 0)
        n = len(reliable_labels)

        print(
            f"{f'<={pct:.0%}':<12}{mdd_wins:>9}/{n}{np.mean(mdd_deltas):>15.4%}"
            f"{std_wins:>9}/{n}{np.mean(std_deltas):>15.4%}{np.mean(cum_deltas):>16.4%}"
        )

    print(
        "\nInterpretation: same standard as CURRENT_STATUS.md item 18 -- a "
        "percentile that wins on mdd/std_period in every reliable window is a "
        "real effect; one that only wins in the current-default window "
        "(Window 3) is very likely the same kind of window-specific result "
        "item 18 already found for the stop-loss multiplier, and should not "
        "be adopted as the new default on this evidence alone."
    )


if __name__ == "__main__":
    main()
