"""Train and evaluate the Phase G daily XGBoost model.

Loads the same pre-split train/validation CSVs Feature Selection used
(via src.feature_selection.data_loading), trains on the Phase
F-selected 5-feature set, and reports validation performance against
the Phase F mean-predictor baseline.

Does NOT touch data/processed/test.csv. Per AGENTS.md section 13, the
test split stays frozen until the feature set AND the model are both
finalized -- this script is for iterating on model choice/hyperparameters
using validation only.
"""

from __future__ import annotations

from sklearn.metrics import r2_score

from src.feature_selection.data_loading import baseline_mean_metrics, load_split
from src.ml.metrics import directional_accuracy, mean_absolute_error, root_mean_squared_error
from src.models.predict import feature_importance, predict, train_model


def main() -> None:
    X_train, y_train = load_split("train")
    X_val, y_val = load_split("validation")

    trained = train_model(X_train, y_train, X_val, y_val)
    val_pred = predict(trained, X_val)

    baseline = baseline_mean_metrics(y_train, y_val)

    print("=== Phase G: Daily XGBoost model (validation) ===")
    print(f"Best iteration: {trained.best_iteration}")
    print(f"Features: {list(trained.feature_columns)}")
    print()

    print(f"{'Metric':<12}{'Model':>14}{'Baseline':>14}")
    print(
        f"{'RMSE':<12}"
        f"{root_mean_squared_error(y_val.to_numpy(), val_pred):>14.6f}"
        f"{baseline['RMSE']:>14.6f}"
    )
    print(
        f"{'MAE':<12}"
        f"{mean_absolute_error(y_val.to_numpy(), val_pred):>14.6f}"
        f"{baseline['MAE']:>14.6f}"
    )
    print(
        f"{'R2':<12}"
        f"{r2_score(y_val, val_pred):>14.6f}"
        f"{baseline['R2']:>14.6f}"
    )
    print(
        f"{'Dir. Acc.':<12}"
        f"{directional_accuracy(y_val.to_numpy(), val_pred):>14.4%}"
        f"{'--':>14}"
    )

    print()
    print("=== Feature Importance ===")
    print(feature_importance(trained).to_string(index=False))


if __name__ == "__main__":
    main()
