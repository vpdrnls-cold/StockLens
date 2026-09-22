"""Pre-Phase-H checklist item 2: does cutting turnover make reversal/ML net-positive?

CURRENT_STATUS.md item 33 found that, on the top50 universe, reversal and
ML both have positive *gross* and *excess* return in every walk-forward
window (t(excess) mostly 1-1.5), but after a ~0.43% round-trip cost per
5-day rebalance almost every net figure goes negative -- the strategies
are close to break-even, not obviously worthless. `run_baseline_backtest`
always closes and reopens every position every 5 days even when the same
stock is still top-ranked, so part of that cost may be unnecessary
turnover rather than a real cost of holding the signal.

This script re-evaluates reversal and ML through the turnover-reduction
buffer engine (`src.backtest.buffered.run_buffered_backtest`) across a
PRE-REGISTERED grid, fixed before looking at any result:

  buffer_multiplier: None (reference, = run_baseline_backtest), 1.5, 2.0, 3.0
  slippage (each way): 0.0010 (current default), 0.0003
  top_n: 5, 10
  strategies: reversal, ml  (momentum excluded -- item 33 already found
              its excess return negative before any cost is applied, so
              turnover reduction cannot rescue it)

Momentum-based "gross"/"excess" (cost-independent) are reported once per
(strategy, top_n, window) exactly as in walk_forward_backtest_compare.py,
for continuity with item 33. "net"/"net_cum"/"net_mdd" and the turnover
diagnostic (entries_per_period; top_n means "no buffering benefit at
all") are reported per grid cell.

Only train/validation dates are used -- the test period is never
touched (src.eval.test_lock is not even imported here, on purpose:
this script structurally cannot reach the test split).

    STOCKLENS_UNIVERSE=top50 PYTHONPATH=. python3 scripts/walk_forward_buffer_cost_grid.py
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.backtest.baseline import (
    calculate_net_return,
    calculate_performance,
    calculate_score,
    prepare_universe,
)
from src.backtest.buffered import (
    BufferedBaselineConfig,
    run_buffered_backtest_with_turnover,
)
from src.data.dataset import (
    TEST_END_DATE,
    TEST_START_DATE,
    TRAIN_START_DATE,
    build_combined_dataset,
    split_by_time,
)
from src.data.storage import HistoricalStorage
from src.data.universe import get_universe
from src.features.engineering import FEATURE_COLUMNS
from src.ml.cross_section import rank_by_date
from src.ml.strategy import make_model_score_fn, predictions_for_dataset
from src.models.predict import train_model

RAW_SCALE_FEATURES = {
    "sma_5", "sma_20", "sma_60", "macd", "macd_signal", "macd_hist",
    "atr_14", "volume_sma_20",
}
ALL_19 = tuple(f for f in FEATURE_COLUMNS if f not in RAW_SCALE_FEATURES)
DETERMINISTIC_PARAMS = {"n_jobs": 1, "tree_method": "exact"}

# --- pre-registered grid -- fixed before running, do not add cells after
# seeing results without saying so in CURRENT_STATUS.md. ---
TOP_NS = (5, 10)
BUFFER_MULTIPLIERS = (None, 1.5, 2.0, 3.0)
SLIPPAGES = (0.0010, 0.0003)
STRATEGIES = ("reversal", "ml")

WINDOWS = [
    ("W1 val 2012-2015", "2011-12-31", "2012-01-01", "2015-12-31"),
    ("W2 val 2016-2019", "2015-12-31", "2016-01-01", "2019-12-31"),
    ("W3 val 2020-2023H1", "2019-12-31", "2020-01-01", "2023-06-30"),
]

FIXED_FEE_TAX = dict(buy_fee=0.00015, sell_fee=0.00015, sell_tax=0.0020)
GROSS_CONFIG_KWARGS = dict(
    buy_fee=0.0, sell_fee=0.0, sell_tax=0.0,
    buy_slippage=0.0, sell_slippage=0.0,
    allow_partial_universe=True,
)


def load_priced_dataset() -> pd.DataFrame:
    storage = HistoricalStorage("data")
    stock_bars = {code: storage.load_daily_bars(code) for code in get_universe()}
    dataset = build_combined_dataset(stock_bars)
    dataset["trade_date"] = pd.to_datetime(dataset["trade_date"])
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
    return dataset.merge(
        prices, on=["trade_date", "stock_code"], how="left", validate="one_to_one"
    )


def to_data_by_stock(dataset: pd.DataFrame) -> dict[str, pd.DataFrame]:
    return {
        str(code): group[["stock_code", "trade_date", "open_price", "close_price"]]
        .sort_values("trade_date")
        .reset_index(drop=True)
        for code, group in dataset.groupby("stock_code")
    }


def universe_average_gross(data_by_stock: dict[str, pd.DataFrame]) -> pd.Series:
    universe = prepare_universe(data_by_stock, how="outer")
    lookback = holding = 5
    codes = list(data_by_stock)
    opens = {c: universe[f"open_{c}"].to_numpy(float) for c in codes}
    closes = {c: universe[f"close_{c}"].to_numpy(float) for c in codes}
    dates = universe["trade_date"]
    zero_cost = BufferedBaselineConfig(**GROSS_CONFIG_KWARGS)

    result: dict[pd.Timestamp, float] = {}
    for d in range(lookback, len(universe) - holding, holding):
        returns = []
        for c in codes:
            needed = (closes[c][d - lookback], closes[c][d], opens[c][d + 1], closes[c][d + holding])
            if all(np.isfinite(v) and v > 0 for v in needed):
                returns.append(calculate_net_return(opens[c][d + 1], closes[c][d + holding], zero_cost)[0])
        if returns:
            result[dates.iloc[d]] = float(np.mean(returns))
    return pd.Series(result, dtype="float64")


def gross_excess(score_fn, data_by_stock, benchmark, top_n) -> tuple[float, float, float, int]:
    """Cost-independent gross/excess, computed once (buffering can't change these)."""
    zero_cost = BufferedBaselineConfig(**GROSS_CONFIG_KWARGS)
    trades, _ = run_buffered_backtest_with_turnover(
        data_by_stock, zero_cost, score_fn=score_fn, top_n=top_n
    )
    from src.backtest.baseline import trades_to_dataframe

    df = trades_to_dataframe(trades)
    if df.empty:
        return float("nan"), float("nan"), float("nan"), 0
    df["contribution"] = df["weight"] * df["net_return"]  # zero-cost -> equals gross
    gross_series = df.groupby("decision_date")["contribution"].sum().sort_index()
    excess = (gross_series - benchmark.reindex(gross_series.index)).dropna()
    n = len(excess)
    t_stat = (
        float(excess.mean() / (excess.std(ddof=1) / np.sqrt(n))) if n > 2 else float("nan")
    )
    return float(gross_series.mean()), float(excess.mean()), t_stat, n


def evaluate_grid_cell(score_fn, data_by_stock, top_n, buffer_multiplier, slippage) -> dict:
    config = BufferedBaselineConfig(
        buy_slippage=slippage, sell_slippage=slippage,
        buffer_multiplier=buffer_multiplier,
        allow_partial_universe=True,
        **FIXED_FEE_TAX,
    )
    trades, turnover = run_buffered_backtest_with_turnover(
        data_by_stock, config, score_fn=score_fn, top_n=top_n
    )
    perf = calculate_performance(trades)
    return {
        "net": float(perf["average_trade_return"]),
        "net_cum": float(perf["total_return"]),
        "net_mdd": float(perf["max_drawdown"]),
        "entries_per_period": turnover["entries_per_period"],
        "avg_positions_held": turnover["avg_positions_held"],
        "periods": turnover["periods"],
    }


def run(dataset: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for label, train_end, val_start, val_end in WINDOWS:
        splits = split_by_time(
            dataset,
            train_start=TRAIN_START_DATE, train_end=train_end,
            validation_start=val_start, validation_end=val_end,
            test_start=TEST_START_DATE, test_end=TEST_END_DATE,
        )
        print(f"\n{label}: train n={len(splits.train)}  val n={len(splits.validation)}")

        trained = train_model(
            splits.train, rank_by_date(splits.train, "target_return_5d"),
            splits.validation, rank_by_date(splits.validation, "target_return_5d"),
            feature_columns=ALL_19, params=DETERMINISTIC_PARAMS,
        )
        print(f"  ML model best_iteration={trained.best_iteration}")
        ml_score_fn = make_model_score_fn(predictions_for_dataset(trained, splits.validation))

        data_by_stock = to_data_by_stock(splits.validation)
        benchmark = universe_average_gross(data_by_stock)

        score_fns = {
            "reversal": lambda u, code, i, lb: -calculate_score(u, code, i, lb),
            "ml": ml_score_fn,
        }

        for strategy in STRATEGIES:
            score_fn = score_fns[strategy]
            for top_n in TOP_NS:
                gross, excess, t_excess, n_periods_gross = gross_excess(
                    score_fn, data_by_stock, benchmark, top_n
                )
                for buffer_multiplier in BUFFER_MULTIPLIERS:
                    for slippage in SLIPPAGES:
                        cell = evaluate_grid_cell(
                            score_fn, data_by_stock, top_n, buffer_multiplier, slippage
                        )
                        rows.append(
                            {
                                "window": label,
                                "strategy": strategy,
                                "top_n": top_n,
                                "buffer_multiplier": buffer_multiplier,
                                "slippage": slippage,
                                "gross": gross,
                                "excess": excess,
                                "t_excess": t_excess,
                                **cell,
                            }
                        )
    return pd.DataFrame(rows)


def _print_table(df: pd.DataFrame) -> None:
    cols = [
        "strategy", "top_n", "buffer_multiplier", "slippage",
        "net", "net_cum", "net_mdd", "entries_per_period",
    ]
    header = (
        f"{'strategy':<9}{'top_n':>6}{'buffer':>8}{'slip':>7}"
        f"{'net/5d':>9}{'net_cum':>10}{'net_mdd':>9}{'entries/prd':>13}"
    )
    print(header)
    for r in df.itertuples():
        buf = "none" if pd.isna(r.buffer_multiplier) else f"{r.buffer_multiplier:.1f}x"
        print(
            f"{r.strategy:<9}{r.top_n:>6}{buf:>8}{r.slippage:>7.4f}"
            f"{r.net:>9.3%}{r.net_cum:>10.1%}{r.net_mdd:>9.1%}{r.entries_per_period:>13.2f}"
        )


def main() -> None:
    results = run(load_priced_dataset())

    for label in results["window"].unique():
        print("\n" + "=" * 100)
        print(label)
        print("=" * 100)
        _print_table(results[results["window"] == label])

    print("\n" + "=" * 100)
    print("AVERAGE OVER THE 3 WINDOWS")
    print("=" * 100)
    avg = (
        results.groupby(["strategy", "top_n", "buffer_multiplier", "slippage"], dropna=False)[
            ["gross", "excess", "t_excess", "net", "net_cum", "net_mdd", "entries_per_period"]
        ]
        .mean()
        .reset_index()
    )
    _print_table(avg)

    print(
        "\nHow to read it: buffer_multiplier=none is the reference case "
        "(identical to run_baseline_backtest -- CURRENT_STATUS.md item 33's "
        "numbers). entries_per_period below top_n means the buffer actually "
        "avoided round trips; compare its net/net_cum against the buffer=none "
        "row for the same strategy/top_n/slippage to see whether that turned "
        "a losing net figure positive. This grid was fixed before running -- "
        "if you're tempted to add a cell after seeing a result, don't; note "
        "it as a follow-up instead."
    )


if __name__ == "__main__":
    main()
