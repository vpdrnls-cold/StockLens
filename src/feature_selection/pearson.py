import pandas as pd


def calculate_pearson(features, target):
    result = features.corrwith(target, method="pearson")

    result = result.rename("pearson").reset_index()
    result = result.rename(columns={"index": "feature"})

    result["abs_pearson"] = result["pearson"].abs()
    result = result.sort_values("abs_pearson", ascending=False)

    return result

def calculate_feature_correlation(features):
    correlation_matrix = features.corr(method="pearson")

    return correlation_matrix