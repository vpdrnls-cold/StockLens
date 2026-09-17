"""Check whether the 3 personalization profiles actually produce
differentiated, explainable behavior -- per AGENTS.md 9: "Do not
hard-code these as arbitrary weights and call them scientifically
valid. Use backtesting and experiments to determine whether
profile-specific ranking improves useful outcomes."

This is NOT another attempt to beat the rule-based baseline (Phase G
already answered that question -- see CURRENT_STATUS.md item 15). The
goal here is narrower: given the SAME daily model predictions,
does re-ranking by profile actually shift the resulting portfolio's
risk/return shape in the direction AGENTS.md 9 describes (conservative
= lower volatility of returns, aggressive = more momentum/volume
concentration), or is it just noise?

Runs on VALIDATION only (test period untouched, per AGENTS.md 13).

Run from the repo root:
    PYTHONPATH=. python3 scripts/evaluate_personalization.py
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.backtest.baseline import (
    BaselineConfig,
    calculate_performance,
    run_baseline_backtest,
    trades_to_dataframe,
)
from src.data.dataset import build_combined_dataset, split_by_time
from src.data.storage import HistoricalStorage
from src.features.engineering import FEATURE_COLUMNS
from src.ml.strategy import predictions_for_dataset
from src.models.predict import train_model
from src.recommendation.scoring import PROFILES, make_profile_score_fn, personalize_scores

STOCK_CODES = ("000660", "005380", "005930", "035420", "035720")

CONFIG = BaselineConfig(
    lookback_days=5,
    holding_days=5,
    buy_fee=0.00015,
    sell_fee=0.00015,
    sell_tax=0.0020,
    buy_slippage=0.0010,
    sell_slippage=0.0010,
)
TOP_N = 2

SIGNAL_COLUMNS = [
    "trade_date",
    "stock_code",
    "volatility_20",
    "price_to_sma_5",
    "volume_ratio_20",
]


def _load_priced_dataset() -> pd.DataFrame:
    storage = HistoricalStorage("data")

    stock_bars = {
        stock_code: storage.load_daily_bars(stock_code) for stock_code in STOCK_CODES
    }

    dataset = build_combined_dataset(stock_bars)
    dataset["trade_date"] = pd.to_datetime(dataset["trade_date"])
    # volume_change_1d can divide by zero on a zero-volume day; XGBoost
    # handles NaN natively but not inf (see CURRENT_STATUS.md /
    # scripts/feature_selection_ic_rerun.py for the same fix).
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


def _period_return_stats(trades: list) -> tuple[float, float]:
    """(mean, std) of per-decision-date portfolio returns -- the same
    grouping calculate_performance uses internally, exposed here
    because "volatility of realized returns" is exactly what a
    conservative profile is supposed to reduce, and
    calculate_performance doesn't report it directly.
    """
    if not trades:
        return float("nan"), float("nan")

    trades_df = trades_to_dataframe(trades)
    period_returns = trades_df.groupby("decision_date").apply(
        lambda group: float((group["weight"] * group["net_return"]).sum())
    )
    return float(period_returns.mean()), float(period_returns.std())


def main() -> None:
    dataset = _load_priced_dataset()
    splits = split_by_time(dataset)

    print("=== Training daily model (train -> validation early stopping) ===")
    trained = train_model(
        splits.train,
        splits.train["target_return_5d"],
        splits.validation,
        splits.validation["target_return_5d"],
    )
    print(f"Best iteration: {trained.best_iteration}")
    print()

    predictions = predictions_for_dataset(trained, splits.validation)
    signals = splits.validation[SIGNAL_COLUMNS].merge(
        predictions, on=["trade_date", "stock_code"], validate="one_to_one"
    )

    data_by_stock = _to_data_by_stock(splits.validation)

    print(f"=== Personalization comparison on VALIDATION (top_n={TOP_N}) ===\n")
    print(
        f"{'profile':<14}{'cum_return':>12}{'hit_rate':>10}{'mdd':>10}"
        f"{'avg_period':>12}{'std_period':>12}"
    )

    for name, profile in PROFILES.items():
        scored = personalize_scores(signals, profile)
        score_fn = make_profile_score_fn(scored)
        trades = run_baseline_backtest(
            data_by_stock, config=CONFIG, score_fn=score_fn, top_n=TOP_N
        )
        perf = calculate_performance(trades)
        avg_period, std_period = _period_return_stats(trades)

        print(
            f"{name:<14}{perf['total_return']:>11.2%} "
            f"{perf['win_rate']:>9.2%} {perf['max_drawdown']:>9.2%} "
            f"{avg_period:>11.4%} {std_period:>11.4%}"
        )

    print(
        "\nInterpretation: 'neutral' should match the plain ML-scored "
        "strategy exactly (personalized_score == predicted_return). "
        "If 'conservative' does not show a lower std_period than "
        "'neutral', or 'aggressive' does not show a different "
        "(typically higher) std_period, the current weights are not "
        "actually differentiating risk the way AGENTS.md 9 describes, "
        "and should be revisited before being treated as more than a "
        "first guess."
    )


if __name__ == "__main__":
    main()
