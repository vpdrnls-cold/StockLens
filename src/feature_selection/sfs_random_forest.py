"""Sequential Feature Selection (forward) + Random Forest.

Mirrors the design of ``rfe_random_forest.py``: feature selection is
fit on the train split only, and every reported metric comes from a
prediction on the validation split that the selector never saw.

Internal cross-validation during the forward search uses
``TimeSeriesSplit`` rather than a random/shuffled ``KFold``. On
chronologically ordered data, a shuffled KFold (or an unshuffled KFold,
which still forms blocks that can sit *after* the block being scored)
lets the search see future rows while being scored against earlier
ones. TimeSeriesSplit only ever trains on the past relative to each
validation fold, which is the correct constraint for this project's
time-series data.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from sklearn.ensemble import RandomForestRegressor
from sklearn.feature_selection import SequentialFeatureSelector
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import TimeSeriesSplit


def run_sfs_random_forest(
    train_df: pd.DataFrame,
    valid_df: pd.DataFrame,
    features: list[str],
    target: str,
    n_features_list: list[int] = [5, 10, 15, 20],
    tol_list: list[float] = [0, 0.001, 0.005],
    n_splits: int = 5,
    random_state: int = 42,
) -> pd.DataFrame:
    """Run forward SFS + Random Forest across a grid of configs.

    Feature selection (``sfs.fit``) and the internal CV scoring used to
    drive it only ever see ``train_df``. The reported RMSE/MAE/R2 for
    each configuration come from a model refit on the selected features
    (train only) and evaluated once on ``valid_df``.
    """

    X_train = train_df[features]
    y_train = train_df[target]

    X_valid = valid_df[features]
    y_valid = valid_df[target]

    cv = TimeSeriesSplit(n_splits=n_splits)

    results = []

    total = len(n_features_list) * len(tol_list)
    experiment = 0

    for n_features in n_features_list:
        for tol in tol_list:
            experiment += 1
            print(
                f"[{experiment}/{total}] "
                f"n_features={n_features}, tol={tol}"
            )

            rf = RandomForestRegressor(
                n_estimators=100,
                random_state=random_state,
                n_jobs=-1,
            )

            sfs = SequentialFeatureSelector(
                estimator=rf,
                n_features_to_select=n_features,
                direction="forward",
                tol=tol,
                scoring="neg_mean_squared_error",
                cv=cv,
                n_jobs=-1,
            )

            # Fit selection on TRAIN ONLY.
            sfs.fit(X_train, y_train)

            selected_features = [
                feature
                for feature, selected in zip(features, sfs.get_support())
                if selected
            ]

            # Refit the final model on train with the selected features,
            # then evaluate once on the held-out validation split.
            final_model = RandomForestRegressor(
                n_estimators=100,
                random_state=random_state,
                n_jobs=-1,
            )
            final_model.fit(train_df[selected_features], y_train)

            valid_pred = final_model.predict(valid_df[selected_features])

            mse = mean_squared_error(y_valid, valid_pred)
            rmse = np.sqrt(mse)
            mae = mean_absolute_error(y_valid, valid_pred)
            r2 = r2_score(y_valid, valid_pred)

            results.append(
                {
                    "method": "SFS + Random Forest",
                    "n_features_to_select": n_features,
                    "tol": tol,
                    "n_selected_features": len(selected_features),
                    "selected_features": selected_features,
                    "RMSE": rmse,
                    "MAE": mae,
                    "R2": r2,
                }
            )

    return (
        pd.DataFrame(results)
        .sort_values("RMSE")
        .reset_index(drop=True)
    )
