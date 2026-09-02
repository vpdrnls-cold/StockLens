"""Leakage-safe preprocessing for StockLens ML datasets."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
from sklearn.preprocessing import StandardScaler

from src.features.engineering import FEATURE_COLUMNS


@dataclass
class FeaturePreprocessor:
    """Standardize features using statistics learned from training data only."""

    scaler: StandardScaler

    def fit(self, train: pd.DataFrame) -> FeaturePreprocessor:
        """Fit preprocessing parameters using training data only."""
        self.scaler.fit(train[list(FEATURE_COLUMNS)])
        return self

    def transform(self, data: pd.DataFrame) -> pd.DataFrame:
        """Transform features using already-fitted training parameters."""
        transformed = data.copy()

        transformed[list(FEATURE_COLUMNS)] = self.scaler.transform(
            data[list(FEATURE_COLUMNS)]
        )

        return transformed

    def fit_transform(self, train: pd.DataFrame) -> pd.DataFrame:
        """Fit on training data and transform it."""
        self.fit(train)
        return self.transform(train)


def create_preprocessor() -> FeaturePreprocessor:
    """Create a new unfitted feature preprocessor."""
    return FeaturePreprocessor(
        scaler=StandardScaler()
    )