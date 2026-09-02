import numpy as np
import pytest

from src.ml.metrics import (
    directional_accuracy,
    mean_absolute_error,
    root_mean_squared_error,
)


def test_mean_absolute_error() -> None:
    actual = np.array([0.10, 0.20, -0.10])
    predicted = np.array([0.20, 0.10, -0.05])

    assert mean_absolute_error(actual, predicted) == pytest.approx(
        0.0833333333
    )


def test_root_mean_squared_error() -> None:
    actual = np.array([0.10, 0.20, -0.10])
    predicted = np.array([0.20, 0.10, -0.05])

    assert root_mean_squared_error(actual, predicted) == pytest.approx(
        0.08660254
    )


def test_directional_accuracy() -> None:
    actual = np.array([0.10, -0.20, 0.05, -0.01])
    predicted = np.array([0.20, -0.10, -0.05, 0.03])

    assert directional_accuracy(actual, predicted) == pytest.approx(0.5)


def test_metrics_reject_mismatched_lengths() -> None:
    actual = np.array([0.1, 0.2])
    predicted = np.array([0.1])

    with pytest.raises(ValueError):
        mean_absolute_error(actual, predicted)

    with pytest.raises(ValueError):
        root_mean_squared_error(actual, predicted)

    with pytest.raises(ValueError):
        directional_accuracy(actual, predicted)


def test_metrics_reject_empty_arrays() -> None:
    actual = np.array([])
    predicted = np.array([])

    with pytest.raises(ValueError):
        mean_absolute_error(actual, predicted)

    with pytest.raises(ValueError):
        root_mean_squared_error(actual, predicted)

    with pytest.raises(ValueError):
        directional_accuracy(actual, predicted)