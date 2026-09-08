import pandas as pd

from sklearn.base import clone
from sklearn.ensemble import RandomForestRegressor
from sklearn.feature_selection import RFE
from sklearn.metrics import mean_squared_error


def run_rfe_random_forest(
    train_df: pd.DataFrame,
    valid_df: pd.DataFrame,
    features: list[str],
    target: str,
    n_features_list: list[int] = [5, 10, 15, 20, 25],
    steps: list[int | float] = [1, 2, 0.1],
    n_estimators_list: list[int] = [100, 300, 500],
    max_depth_list: list[int | None] = [None, 5, 10],
    max_features_list: list[str | float] = ["sqrt", "log2", 0.5],
    random_state: int = 42,
) -> pd.DataFrame:

    X_train = train_df[features]
    y_train = train_df[target]

    X_valid = valid_df[features]
    y_valid = valid_df[target]

    results = []

    total = (
        len(n_features_list)
        * len(steps)
        * len(n_estimators_list)
        * len(max_depth_list)
        * len(max_features_list)
    )

    experiment = 0

    for n_features in n_features_list:
        for step in steps:
            for n_estimators in n_estimators_list:
                for max_depth in max_depth_list:
                    for max_features in max_features_list:

                        experiment += 1

                        print(
                            f"[{experiment}/{total}] "
                            f"k={n_features}, "
                            f"step={step}, "
                            f"n_estimators={n_estimators}, "
                            f"max_depth={max_depth}, "
                            f"max_features={max_features}"
                        )

                        # RFE용 Random Forest
                        rf = RandomForestRegressor(
                            n_estimators=n_estimators,
                            max_depth=max_depth,
                            max_features=max_features,
                            random_state=random_state,
                            n_jobs=-1,
                        )

                        selector = RFE(
                            estimator=rf,
                            n_features_to_select=n_features,
                            step=step,
                        )

                        # RFE 수행
                        selector.fit(X_train, y_train)

                        selected_features = [
                            feature
                            for feature, selected
                            in zip(features, selector.support_)
                            if selected
                        ]

                        # 선택된 feature로 RF 재학습
                        final_model = clone(rf)

                        final_model.fit(
                            train_df[selected_features],
                            y_train,
                        )

                        # Validation 예측
                        valid_pred = final_model.predict(
                            valid_df[selected_features]
                        )

                        rmse = mean_squared_error(
                            y_valid,
                            valid_pred,
                        ) ** 0.5

                        results.append(
                            {
                                "method": "RFE + Random Forest",
                                "n_features": n_features,
                                "step": step,
                                "n_estimators": n_estimators,
                                "max_depth": max_depth,
                                "max_features": max_features,
                                "features": selected_features,
                                "rmse": rmse,
                            }
                        )

    return (
        pd.DataFrame(results)
        .sort_values("rmse")
        .reset_index(drop=True)
    )