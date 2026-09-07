import numpy as np
import pandas as pd


def mrmr_greedy(
    feature_target_mi: pd.DataFrame,
    feature_mi_matrix: pd.DataFrame,
    k: int
) -> list[str]:
    """
    Select top-k features using the MRMR greedy algorithm.

    Parameters
    ----------
    feature_target_mi : pd.DataFrame
        Feature-target mutual information.
        Required columns: 'feature', 'mi_score'

    feature_mi_matrix : pd.DataFrame
        Feature-feature mutual information matrix.
        The first column contains feature names.

    k : int
        Number of features to select.

    Returns
    -------
    list[str]
        Selected features in MRMR selection order.
    """

    # -------------------------
    # 1. Validate input
    # -------------------------

    if k <= 0:
        raise ValueError("k must be greater than 0.")

    required_columns = {"feature", "mi_score"}

    if not required_columns.issubset(feature_target_mi.columns):
        raise ValueError(
            "feature_target_mi must contain "
            "'feature' and 'mi_score' columns."
        )

    if k > len(feature_target_mi):
        raise ValueError(
            f"k ({k}) cannot be larger than the number of features "
            f"({len(feature_target_mi)})."
        )

    # -------------------------
    # 2. Prepare relevance
    # -------------------------

    relevance = dict(
        zip(
            feature_target_mi["feature"],
            feature_target_mi["mi_score"]
        )
    )

    features = list(relevance.keys())

    # -------------------------
    # 3. Prepare redundancy matrix
    # -------------------------

    feature_mi_matrix = feature_mi_matrix.copy()

    # The first column contains feature names.
    feature_mi_matrix = feature_mi_matrix.set_index(
        feature_mi_matrix.columns[0]
    )

    # Keep only features available in both datasets.
    missing_features = [
        feature
        for feature in features
        if feature not in feature_mi_matrix.index
        or feature not in feature_mi_matrix.columns
    ]

    if missing_features:
        raise ValueError(
            f"Features missing from MI matrix: {missing_features}"
        )

    # -------------------------
    # 4. First feature
    # -------------------------

    # When no feature has been selected yet,
    # redundancy = 0.
    first_feature = max(
        features,
        key=lambda feature: relevance[feature]
    )

    selected = [first_feature]

    remaining = [
        feature
        for feature in features
        if feature != first_feature
    ]

    # -------------------------
    # 5. Greedy MRMR selection
    # -------------------------

    while len(selected) < k:

        best_feature = None
        best_score = -np.inf

        for feature in remaining:

            # Average redundancy with already selected features.
            redundancy = np.mean([
                feature_mi_matrix.loc[feature, selected_feature]
                for selected_feature in selected
            ])

            # MRMR = relevance - redundancy
            mrmr_score = relevance[feature] - redundancy

            if mrmr_score > best_score:
                best_score = mrmr_score
                best_feature = feature

        selected.append(best_feature)
        remaining.remove(best_feature)

    return selected