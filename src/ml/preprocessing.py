"""Leakage-safe preprocessing for StockLens ML datasets."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

import pandas as pd
from sklearn.preprocessing import StandardScaler

from src.features.engineering import FEATURE_COLUMNS


@dataclass
class FeaturePreprocessor:
    """Standardize features using statistics learned from training data only."""

    scaler: StandardScaler
    feature_columns: Sequence[str] = field(default_factory=lambda: FEATURE_COLUMNS)

    def fit(self, train: pd.DataFrame) -> FeaturePreprocessor:
        """Fit preprocessing parameters using training data only."""
        self.scaler.fit(train[list(self.feature_columns)])
        return self

    def transform(self, data: pd.DataFrame) -> pd.DataFrame:
        """Transform features using already-fitted training parameters."""
        transformed = data.copy()

        transformed[list(self.feature_columns)] = self.scaler.transform(
            data[list(self.feature_columns)]
        )

        return transformed

    def fit_transform(self, train: pd.DataFrame) -> pd.DataFrame:
        """Fit on training data and transform it."""
        self.fit(train)
        return self.transform(train)


def create_preprocessor(
    feature_columns: Sequence[str] = FEATURE_COLUMNS,
) -> FeaturePreprocessor:
    """Create a new unfitted feature preprocessor.

    Pass ``feature_columns=SELECTED_FEATURES`` (from
    ``src.features.engineering``) once you're working with the
    Phase F-selected feature set rather than the full 25.
    """
    return FeaturePreprocessor(
        scaler=StandardScaler(),
        feature_columns=feature_columns,
    )