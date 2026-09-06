import pandas as pd
from scipy.stats import spearmanr


def spearman_correlation(
    df: pd.DataFrame,
    features: list[str],
    target: str,
) -> pd.DataFrame:
    """
    Calculate Spearman correlation between each feature and the target.

    Returns a DataFrame sorted by absolute correlation.
    """
    results = []

    for feature in features:
        corr, p_value = spearmanr(df[feature], df[target])

        results.append(
            {
                "feature": feature,
                "correlation": corr,
                "p_value": p_value,
                "abs_correlation": abs(corr),
            }
        )

    return (
        pd.DataFrame(results)
        .sort_values("abs_correlation", ascending=False)
        .reset_index(drop=True)
    )