import numpy as np
import pandas as pd

from sklearn.linear_model import ElasticNet
from sklearn.metrics import (
    mean_squared_error,
    mean_absolute_error,
    r2_score,
)


def run_elastic_net(
    X_train,
    X_val,
    y_train,
    y_val,
    alpha,
    l1_ratio,
    feature_names=None,
    max_iter=10000,
):
    """
    Run Elastic Net feature selection and evaluate validation performance.

    Parameters
    ----------
    X_train : pd.DataFrame
        Training features.
    X_val : pd.DataFrame
        Validation features.
    y_train : pd.Series or np.ndarray
        Training target.
    y_val : pd.Series or np.ndarray
        Validation target.
    alpha : float
        Regularization strength.
    l1_ratio : float
        L1/L2 mixing parameter.
        1.0 = Lasso, 0.0 = Ridge.
    feature_names : list[str], optional
        Feature names. If None, uses X_train column names.
    max_iter : int
        Maximum number of iterations.

    Returns
    -------
    dict
        Elastic Net results including selected features and metrics.
    """

    if feature_names is None:
        feature_names = list(X_train.columns)

    model = ElasticNet(
        alpha=alpha,
        l1_ratio=l1_ratio,
        max_iter=max_iter,
        random_state=42,
    )

    model.fit(X_train, y_train)

    coefficients = model.coef_

    selected_features = [
        feature
        for feature, coef in zip(feature_names, coefficients)
        if not np.isclose(coef, 0.0, atol=1e-8)
    ]

    y_pred = model.predict(X_val)

    mse = mean_squared_error(y_val, y_pred)
    rmse = np.sqrt(mse)
    mae = mean_absolute_error(y_val, y_pred)
    r2 = r2_score(y_val, y_pred)

    return {
        "alpha": alpha,
        "l1_ratio": l1_ratio,
        "n_selected_features": len(selected_features),
        "selected_features": selected_features,
        "MSE": mse,
        "RMSE": rmse,
        "MAE": mae,
        "R2": r2,
    }