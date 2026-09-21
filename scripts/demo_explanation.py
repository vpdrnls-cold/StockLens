"""Manual smoke test / demo for the explanation layer
(src/explanation/recommendation.py, src/explanation/position.py).

Trains the daily model on TRAIN, then for the LAST date in VALIDATION
(test period is never touched, AGENTS.md 13):

1. Prints Top-3 recommendations, explained, for all three profiles
   (conservative / neutral / aggressive) -- so you can see how the
   contributor breakdown changes by profile for the exact same day.
2. Prints one HOLD/SELL explanation for an example held position on
   Samsung Electronics (005930), using a made-up entry price chosen to
   trigger the stop-loss rule, just to show what a SELL explanation
   looks like end to end.

This is not a new evaluation script (no performance claims) -- it only
exercises the explanation layer against real data so you can read the
actual output.

Run from the repo root:
    PYTHONPATH=. python3 scripts/demo_explanation.py
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.data.dataset import build_combined_dataset, split_by_time
from src.data.storage import HistoricalStorage
from src.explanation.position import explain_position_decision
from src.explanation.recommendation import format_recommendations_report
from src.features.engineering import FEATURE_COLUMNS
from src.ml.strategy import predictions_for_dataset
from src.models.predict import train_model
from src.portfolio.optimizer import Position, PositionSignal, evaluate_position
from src.recommendation.scoring import (
    PROFILES,
    add_predicted_return_percentile,
    personalize_scores,
    top_n_recommendations,
)

STOCK_CODES = ("000660", "005380", "005930", "035420", "035720")

SIGNAL_COLUMNS = ["trade_date", "stock_code", "volatility_20", "price_to_sma_5", "volume_ratio_20"]

# Deterministic (AGENTS.md 25) so this demo prints the same numbers on
# any machine. n_jobs=1 alone was NOT enough across different CPU
# architectures (CURRENT_STATUS.md items 15/18/20/21) -- tree_method=
# "exact" is what CURRENT_STATUS.md item 23 confirmed gives bit-
# identical results across two genuinely different real machines
# (Linux x86_64 vs macOS arm64).
DETERMINISTIC_PARAMS = {"n_jobs": 1, "tree_method": "exact"}


def _load_priced_dataset() -> pd.DataFrame:
    storage = HistoricalStorage("data")
    stock_bars = {code: storage.load_daily_bars(code) for code in STOCK_CODES}
    dataset = build_combined_dataset(stock_bars)
    dataset["trade_date"] = pd.to_datetime(dataset["trade_date"])
    dataset[list(FEATURE_COLUMNS)] = dataset[list(FEATURE_COLUMNS)].replace(
        [np.inf, -np.inf], np.nan
    )
    return dataset


def main() -> None:
    dataset = _load_priced_dataset()
    splits = split_by_time(dataset)

    print("=== Training daily model (train -> validation early stopping) ===")
    trained = train_model(
        splits.train,
        splits.train["target_return_5d"],
        splits.validation,
        splits.validation["target_return_5d"],
        params=DETERMINISTIC_PARAMS,
    )
    print(f"Best iteration: {trained.best_iteration}\n")

    predictions = predictions_for_dataset(trained, splits.validation)
    signals = splits.validation[SIGNAL_COLUMNS].merge(
        predictions, on=["trade_date", "stock_code"], validate="one_to_one"
    )

    # Cross-sectional percentile needs every stock's predicted_return on
    # the same date -- add it before slicing to a single day. Not
    # strictly required by PositionConfig's default anymore (item 25:
    # the default has no signal-reversal rule at all), but it's cheap
    # and keeps the PositionSignal below fully populated, matching what
    # a real caller with sell_percentile_threshold set would pass.
    signals = add_predicted_return_percentile(signals)

    last_date = signals["trade_date"].max()
    day_signals = signals[signals["trade_date"] == last_date]

    print("#" * 70)
    print(f"# 추천 설명 예시 ({last_date.date()}, top 3, 프로필별)")
    print("#" * 70)

    for profile_name in PROFILES:
        print(f"\n--- {profile_name} ---\n")
        scored = personalize_scores(day_signals, profile_name)
        top3 = top_n_recommendations(scored, n=3)
        print(format_recommendations_report(top3))

    print("\n" + "#" * 70)
    print("# 보유종목 HOLD/SELL 설명 예시 (005930)")
    print("#" * 70 + "\n")

    row = day_signals[day_signals["stock_code"] == "005930"].iloc[0]
    predicted_return = float(row["predicted_return"])
    predicted_return_percentile = float(row["predicted_return_percentile"])

    # Made-up entry price/atr_pct chosen only to show a stop-loss SELL
    # example -- not a real held position.
    position = Position(stock_code="005930", entry_price=70_000.0)
    signal = PositionSignal(
        current_price=64_000.0,
        predicted_return=predicted_return,
        atr_pct=0.02,
        predicted_return_percentile=predicted_return_percentile,
    )
    decision = evaluate_position(position, signal)
    print(explain_position_decision(position, decision))


if __name__ == "__main__":
    main()
