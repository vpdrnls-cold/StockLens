from itertools import combinations

import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_squared_error
from sklearn.feature_selection import RFE
from xgboost import XGBRegressor

#선택된 5개 feature -> Train 데이터로 RandomForest 학습 -> Validation 데이터로 RMSE 계산
def evaluate_subset(
    train_df: pd.DataFrame,
    valid_df: pd.DataFrame,
    features: list[str],
    target: str,
    model,
) -> float:
    """
    Train the model on the selected features and return validation RMSE.
    """

    X_train = train_df[features]
    y_train = train_df[target]

    X_valid = valid_df[features]
    y_valid = valid_df[target]

    model.fit(X_train, y_train)

    pred = model.predict(X_valid)

    rmse = mean_squared_error(y_valid, pred) ** 0.5

    return rmse

from sklearn.base import clone


def rfe_random_forest(
    train_df: pd.DataFrame,
    valid_df: pd.DataFrame,
    features: list[str],
    target: str,
    random_state: int = 42,
) -> pd.DataFrame:
    """
    RFE + Random Forest feature selection.

    Evaluates feature subsets from 1 to len(features)
    using validation RMSE.
    """

    results = []

    for k in range(1, len(features) + 1):
        model = RandomForestRegressor(
            n_estimators=300,
            random_state=random_state,
            n_jobs=-1,
        )

        selector = RFE(
            estimator=model,
            n_features_to_select=k,
            step=1,
        )

        X_train = train_df[features]
        y_train = train_df[target]

        X_valid = valid_df[features]
        y_valid = valid_df[target]

        selector.fit(X_train, y_train)

        selected_features = [
            feature
            for feature, selected in zip(features, selector.support_)
            if selected
        ]

        selected_model = clone(model)

        rmse = evaluate_subset(
            train_df=train_df,
            valid_df=valid_df,
            features=selected_features,
            target=target,
            model=selected_model,
        )

        results.append(
            {
                "method": "RFE + Random Forest",
                "n_features": k,
                "features": selected_features,
                "rmse": rmse,
            }
        )

def rfe_xgboost(
    train_df: pd.DataFrame,
    valid_df: pd.DataFrame,
    features: list[str],
    target: str,
    random_state: int = 42,
) -> pd.DataFrame:
    """
    RFE + XGBoost feature selection.

    Evaluates feature subsets from 1 to len(features)
    using validation RMSE.
    """

    results = []

    for k in range(1, len(features) + 1):
        model = XGBRegressor(
            n_estimators=300,
            max_depth=3,
            learning_rate=0.05,
            random_state=random_state,
            n_jobs=-1,
            objective="reg:squarederror",
        )

        selector = RFE(
            estimator=model,
            n_features_to_select=k,
            step=1,
        )

        X_train = train_df[features]
        y_train = train_df[target]

        X_valid = valid_df[features]

        selector.fit(X_train, y_train)

        selected_features = [
            feature
            for feature, selected in zip(features, selector.support_)
            if selected
        ]

        selected_model = clone(model)

        rmse = evaluate_subset(
            train_df=train_df,
            valid_df=valid_df,
            features=selected_features,
            target=target,
            model=selected_model,
        )

        results.append(
            {
                "method": "RFE + XGBoost",
                "n_features": k,
                "features": selected_features,
                "rmse": rmse,
            }
        )
    

    return pd.DataFrame(results)