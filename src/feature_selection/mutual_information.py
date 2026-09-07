import numpy as np
import pandas as pd
from sklearn.feature_selection import mutual_info_regression


#25개 features사이의 MI matrix
#대각선 = 0, 나머지는 feature끼리의 MI score
def calculate_mutual_information(
    X: pd.DataFrame,
    y: pd.Series,
    random_state: int = 42,
) -> pd.Series:
    """
    Calculate mutual information between each feature and a continuous target.

    Parameters
    ----------
    X : pd.DataFrame
        Feature data.
    y : pd.Series
        Continuous target.
    random_state : int, default=42
        Random seed for reproducibility.

    Returns
    -------
    pd.Series
        Mutual information score for each feature.
    """
    X = X.copy()
    y = y.copy()

    if X.empty:
        raise ValueError("X must contain at least one feature.")

    if len(X) != len(y):
        raise ValueError("X and y must have the same number of samples.")

    if X.isnull().any().any() or y.isnull().any():
        raise ValueError("X and y must not contain missing values.")

    if not np.isfinite(X.to_numpy()).all():
        raise ValueError("X must contain only finite values.")

    if not np.isfinite(y.to_numpy()).all():
        raise ValueError("y must contain only finite values.")

    scores = mutual_info_regression(
        X,
        y,
        random_state=random_state,
    )

    return pd.Series(scores, index=X.columns, name="mutual_information").sort_values(
        ascending=False
    )

def calculate_feature_mutual_information(
    X: pd.DataFrame,
    random_state: int = 42,
) -> pd.DataFrame:
    """
    Calculate pairwise mutual information between features.

    Parameters
    ----------
    X : pd.DataFrame
        Feature data.
    random_state : int, default=42
        Random seed for reproducibility.

    Returns
    -------
    pd.DataFrame
        Pairwise mutual information matrix.
    """
    if X.empty:
        raise ValueError("X must contain at least one feature.")

    if X.isnull().any().any():
        raise ValueError("X must not contain missing values.")

    if not np.isfinite(X.to_numpy()).all():
        raise ValueError("X must contain only finite values.")

    features = X.columns
    n_features = len(features)

    mi_matrix = np.zeros((n_features, n_features))

    for i in range(n_features):
        for j in range(i + 1, n_features):
            mi_ij = mutual_info_regression(
                X[[features[i]]],
                X[features[j]],
                random_state=random_state,
            )[0]

            mi_matrix[i, j] = mi_ij
            mi_matrix[j, i] = mi_ij

    return pd.DataFrame(
        mi_matrix,
        index=features,
        columns=features,
    )