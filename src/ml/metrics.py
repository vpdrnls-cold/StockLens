"""Evaluation metrics for StockLens."""

from __future__ import annotations

import numpy as np


def mean_absolute_error(
    actual: np.ndarray,
    predicted: np.ndarray,
) -> float:
    """Calculate mean absolute error."""

    if len(actual) != len(predicted):
        raise ValueError("actual and predicted must have the same length.")

    if len(actual) == 0:
        raise ValueError("actual and predicted must not be empty.")

    return float(np.mean(np.abs(actual - predicted)))


def root_mean_squared_error(
    actual: np.ndarray,
    predicted: np.ndarray,
) -> float:
    """Calculate root mean squared error."""

    if len(actual) != len(predicted):
        raise ValueError("actual and predicted must have the same length.")

    if len(actual) == 0:
        raise ValueError("actual and predicted must not be empty.")

    return float(np.sqrt(np.mean((actual - predicted) ** 2)))


def directional_accuracy(
    actual: np.ndarray,
    predicted: np.ndarray,
) -> float:
    """Calculate the proportion of correctly predicted return directions."""

    if len(actual) != len(predicted):
        raise ValueError("actual and predicted must have the same length.")

    if len(actual) == 0:
        raise ValueError("actual and predicted must not be empty.")

    actual_direction = np.sign(actual)
    predicted_direction = np.sign(predicted)

    return float(np.mean(actual_direction == predicted_direction))