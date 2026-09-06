import pandas as pd
from scipy.stats import spearmanr


def calculate_spearman(features, target):
    result = features.apply(
        lambda x: spearmanr(x, target).statistic
    )

    result = result.rename("spearman").reset_index()
    result = result.rename(columns={"index": "feature"})

    result["abs_spearman"] = result["spearman"].abs()
    result = result.sort_values("abs_spearman", ascending=False)

    return result


def calculate_feature_correlation(features):
    correlation_matrix = features.corr(method="spearman")

    return correlation_matrix