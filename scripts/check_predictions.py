"""Diagnostic: does the model pick a diverse set of stocks over time?

Run this on VALIDATION only, after any feature-set change, before
re-running scripts/run_ml_backtest.py (which touches the frozen test
period). If the model picks the same stock on (almost) every decision
date, that is the same cross-sectional scale-leakage symptom found
during the first Phase G evaluation -- do not spend a test-period run
checking a fix that hasn't first been sanity-checked here.

Requires data/processed/train.csv and validation.csv to already
contain atr_pct / macd_hist_pct. If they were generated before that
feature was added, re-run notebooks/feature_selection/prepare_data.ipynb
first.
"""

from __future__ import annotations

import pandas as pd

from src.features.engineering import SELECTED_FEATURES
from src.models.predict import train_model, predict

PROCESSED_DIR = "data/processed"


def main() -> None:
    train = pd.read_csv(f"{PROCESSED_DIR}/train.csv")
    validation = pd.read_csv(f"{PROCESSED_DIR}/validation.csv")

    missing = set(SELECTED_FEATURES) - set(train.columns)
    if missing:
        raise SystemExit(
            f"train.csv is missing {sorted(missing)}. Re-run "
            "notebooks/feature_selection/prepare_data.ipynb to "
            "regenerate the processed CSVs with the new features, "
            "then run this script again."
        )

    trained = train_model(
        train, train["target_return_5d"], validation, validation["target_return_5d"]
    )

    print(f"Best iteration: {trained.best_iteration}")
    print(f"Features: {list(trained.feature_columns)}")
    print()

    validation = validation.copy()
    validation["predicted_return"] = predict(trained, validation)

    picks = (
        validation.sort_values("predicted_return", ascending=False)
        .groupby("trade_date")
        .head(1)[["trade_date", "stock_code", "predicted_return"]]
    )

    print(f"Decision dates evaluated: {picks['trade_date'].nunique()}")
    print()
    print("=== Pick distribution (should NOT be dominated by one stock) ===")
    print(
        picks["stock_code"]
        .value_counts()
        .rename_axis("stock_code")
        .reset_index(name="times_picked")
        .to_string(index=False)
    )

    top_share = picks["stock_code"].value_counts(normalize=True).iloc[0]

    print()
    if top_share > 0.6:
        print(
            f"WARNING: one stock accounts for {top_share:.1%} of all picks. "
            "This is the same symptom as the original bug -- do not proceed "
            "to scripts/run_ml_backtest.py yet."
        )
    else:
        print(
            f"OK: top stock accounts for {top_share:.1%} of picks. "
            "Picks look date-dependent, not stock-identity-dependent."
        )


if __name__ == "__main__":
    main()
