"""Compare the two signal-reversal variants on
``src.portfolio.optimizer.PositionConfig``: the original absolute
threshold (``sell_predicted_return_threshold``) versus the new
percentile-based one (``sell_percentile_threshold``, see that module's
docstring and CURRENT_STATUS.md item 17/19).

Background: scripts/evaluate_position_thresholds.py found that the
absolute rule (predicted_return <= 0.0) fires on only ~0.6% of trades
in validation, because this model's raw predicted_return is almost
never negative (mean +0.41%, 99.7%+ of rows > 0 -- see
CURRENT_STATUS.md item 17). It also found that isolating the rule
("stop_loss=3.0x only" vs "default (3.0x atr, thr=0.0)") makes
cum_return *worse*, with an *identical* mdd -- i.e. the absolute rule
currently adds no risk-reduction and actively costs return. AGENTS.md
22 already treats this model's output as trustworthy only for
cross-sectional ranking (rank IC), not as an absolute quantity, which
is exactly the standard the percentile rule applies here.

This script holds stop_loss_atr_multiple at the walk-forward-validated
default (3.0x, CURRENT_STATUS.md item 18) and varies only the
reversal rule:
    - "stop_loss_only": reversal rule off entirely (both
      thresholds effectively disabled) -- the cleanest baseline for
      "is either reversal variant adding anything beyond the stop-loss
      rule alone?"
    - "absolute_thr=0.0": the original/current default.
    - a grid of percentile thresholds (bottom 10/20/30/40/50% of that
      day's 5-stock universe).

Runs on VALIDATION only (test period untouched, AGENTS.md 13). Reuses
the exact same decision grid / top_n=2 selection / costs as
scripts/evaluate_position_thresholds.py -- only the reversal rule
changes between rows.

Run from the repo root:
    PYTHONPATH=. python3 scripts/evaluate_signal_reversal_thresholds.py
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.backtest.baseline import prepare_universe
from src.data.dataset import split_by_time
from src.ml.strategy import predictions_for_dataset
from src.models.predict import train_model
from src.portfolio.optimizer import PositionConfig
from src.recommendation.scoring import add_predicted_return_percentile

from scripts.evaluate_position_thresholds import (
    CONFIG,
    SIGNAL_COLUMNS,
    STOP_LOSS_DISABLED,
    TOP_N,
    _load_priced_dataset,
    _print_row,
    _to_data_by_stock,
    simulate_exit_rule,
)

# Validated in CURRENT_STATUS.md item 18 (walk-forward, 2/2 reliable
# windows) -- held fixed here so this script isolates the reversal
# rule alone.
STOP_LOSS_ATR_MULTIPLE = 3.0

PERCENTILE_GRID = (0.1, 0.2, 0.3, 0.4, 0.5)

# Large enough that predicted_return <= threshold essentially never
# fires within a 5-day window -- de facto "reversal rule off", same
# constant as scripts/evaluate_position_thresholds.py's REVERSAL_DISABLED.
REVERSAL_DISABLED = -1.0


def main() -> None:
    dataset = _load_priced_dataset()
    splits = split_by_time(dataset)

    print("=== Training daily model (train -> validation early stopping) ===")
    trained = train_model(
        splits.train,
        splits.train["target_return_5d"],
        splits.validation,
        splits.validation["target_return_5d"],
        # deterministic, AGENTS.md 25 -- n_jobs=1 alone isn't
        # cross-machine reproducible (CURRENT_STATUS.md items 15/18/20/
        # 21); tree_method="exact" is (item 23, confirmed bit-identical
        # on Linux x86_64 vs macOS arm64).
        params={"n_jobs": 1, "tree_method": "exact"},
    )
    print(f"Best iteration: {trained.best_iteration}\n")

    predictions = predictions_for_dataset(trained, splits.validation)
    signals = splits.validation[SIGNAL_COLUMNS].merge(
        predictions, on=["trade_date", "stock_code"], validate="one_to_one"
    )
    # Cross-sectional percentile needs every stock's predicted_return
    # for each date -- `signals` already has all 5 stocks x all dates
    # (not just the top_n picks), so this covers every day the walk
    # forward loop will look up.
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

    print(f"=== Signal-reversal rule comparison on VALIDATION (top_n={TOP_N}, stop_loss={STOP_LOSS_ATR_MULTIPLE:g}x fixed) ===\n")
    print(
        f"{'config':<28}{'cum_return':>12}{'hit_rate':>10}{'mdd':>10}"
        f"{'avg_period':>12}{'std_period':>12}{'avg_hold_d':>10}"
        f"{'stop_loss':>10}{'reversal':>10}{'max_hold':>10}"
    )

    # 1) Stop-loss only -- reversal rule off entirely.
    # sell_percentile_threshold=None: this row exists to isolate "no
    # reversal rule at all" -- without pinning it explicitly it would
    # silently become the percentile rule now that PositionConfig's
    # class default is 0.20 (CURRENT_STATUS.md items 20/21).
    stop_only_cfg = PositionConfig(
        stop_loss_atr_multiple=STOP_LOSS_ATR_MULTIPLE,
        sell_predicted_return_threshold=REVERSAL_DISABLED,
        sell_percentile_threshold=None,
    )
    stop_only_result = simulate_exit_rule(
        universe, predictions_lookup, atr_lookup, stock_codes, CONFIG, stop_only_cfg, TOP_N
    )
    _print_row(
        "stop_loss_only (no reversal)",
        stop_only_result.trades,
        stop_only_result.holding_days,
        stop_only_result.exit_reasons,
    )

    # 2) Original/pre-item-20 default: absolute threshold 0.0 -- pinned
    #    explicitly (sell_percentile_threshold=None) so this row keeps
    #    testing the absolute rule this script's docstring describes,
    #    independent of the percentile rule now being the class default.
    absolute_cfg = PositionConfig(
        stop_loss_atr_multiple=STOP_LOSS_ATR_MULTIPLE,
        sell_predicted_return_threshold=0.0,
        sell_percentile_threshold=None,
    )
    absolute_result = simulate_exit_rule(
        universe, predictions_lookup, atr_lookup, stock_codes, CONFIG, absolute_cfg, TOP_N
    )
    _print_row(
        "absolute_thr=0.0 (current)",
        absolute_result.trades,
        absolute_result.holding_days,
        absolute_result.exit_reasons,
    )

    # 3) Percentile grid.
    for pct in PERCENTILE_GRID:
        cfg = PositionConfig(
            stop_loss_atr_multiple=STOP_LOSS_ATR_MULTIPLE,
            sell_percentile_threshold=pct,
        )
        result = simulate_exit_rule(
            universe,
            predictions_lookup,
            atr_lookup,
            stock_codes,
            CONFIG,
            cfg,
            TOP_N,
            percentile_lookup=percentile_lookup,
        )
        _print_row(
            f"percentile<={pct:.0%}",
            result.trades,
            result.holding_days,
            result.exit_reasons,
        )

    print(
        "\nInterpretation: compare every row's mdd/std_period/cum_return "
        "against 'stop_loss_only (no reversal)' -- that row isolates what "
        "the stop-loss rule alone already achieves (CURRENT_STATUS.md item "
        "18's validated 3.0x). A reversal variant is only worth adding if "
        "it improves on that baseline; if 'absolute_thr=0.0' and every "
        "percentile row are worse or unchanged, the honest conclusion is "
        "that this model's signal is not reliable enough for a reversal "
        "rule in EITHER form yet, and the HOLD/SELL layer should ship with "
        "stop-loss only until a better-calibrated model exists."
    )


if __name__ == "__main__":
    main()
