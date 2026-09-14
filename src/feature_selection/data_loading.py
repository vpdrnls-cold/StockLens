"""Shared, leakage-safe data loading for feature selection experiments.

Every feature-selection method (filter / wrapper / embedded) must load
data through this module instead of reading
``data/processed/ml_dataset.csv`` directly.

Reading ``ml_dataset.csv`` gives you every row across train, validation,
and test combined, with no boundary between them. Any statistic computed
on it (correlation, mutual information, a fitted model, ...) is
contaminated with information from periods that are supposed to be
unseen. This module reads only the pre-split
``train.csv`` / ``validation.csv`` / ``test.csv`` files produced by
``notebooks/feature_selection/prepare_data.ipynb``, so it is structurally
impossible to accidentally pull in the wrong period.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

PROCESSED_DIR = Path("data/processed")


def find_project_root(marker: str = "AGENTS.md") -> Path:
    """Walk upward from the current directory until ``marker`` is found.

    Several notebooks in this project have guessed the repo root as
    ``Path.cwd().parents[n]`` with a hard-coded ``n``, which breaks
    silently whenever the notebook is moved or run from a different
    working directory (this has already caused at least two path bugs
    in the feature-selection notebooks). Searching upward for a marker
    file that only exists at the repo root avoids that entire class of
    bug.
    """
    current = Path.cwd().resolve()
    for candidate in (current, *current.parents):
        if (candidate / marker).exists():
            return candidate
    raise FileNotFoundError(
        f"Could not find project root (looked for {marker!r} starting "
        f"from {current})."
    )

TARGET_COLUMN = "target_return_5d"
ID_COLUMNS = ["stock_code", "trade_date"]

_VALID_SPLITS = ("train", "validation", "test")


def _feature_columns(df: pd.DataFrame) -> list[str]:
    return [
        column
        for column in df.columns
        if column not in ID_COLUMNS + [TARGET_COLUMN]
    ]


def load_split(
    split: str,
    *,
    processed_dir: Path = PROCESSED_DIR,
) -> tuple[pd.DataFrame, pd.Series]:
    """Load one split as ``(X, y)``.

    Parameters
    ----------
    split : {"train", "validation", "test"}
        Which pre-split CSV to load. Feature selection (fitting a
        selector, computing correlation/MI, choosing hyperparameters)
        must only ever use ``"train"``. ``"validation"`` is for
        comparing methods/configs after selection. ``"test"`` must not
        be touched until the final feature set and final model are
        both frozen.
    """
    if split not in _VALID_SPLITS:
        raise ValueError(
            f"split must be one of {_VALID_SPLITS}, got {split!r}."
        )

    path = processed_dir / f"{split}.csv"
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found. Run notebooks/feature_selection/"
            "prepare_data.ipynb first."
        )

    df = pd.read_csv(path)

    if TARGET_COLUMN not in df.columns:
        raise ValueError(
            f"{path} is missing target column {TARGET_COLUMN!r}."
        )

    feature_columns = _feature_columns(df)

    X = df[feature_columns].copy()
    y = df[TARGET_COLUMN].copy()

    # Cheap guard so a future refactor can't silently reintroduce the
    # target (or stock_code/trade_date) as a feature column.
    assert TARGET_COLUMN not in X.columns, "Target leaked into features."
    assert not set(ID_COLUMNS) & set(X.columns), "ID column leaked into features."

    return X, y


def load_train_val_test() -> tuple[
    tuple[pd.DataFrame, pd.Series],
    tuple[pd.DataFrame, pd.Series],
    tuple[pd.DataFrame, pd.Series],
]:
    """Convenience wrapper returning ``(X, y)`` for all three splits."""
    return load_split("train"), load_split("validation"), load_split("test")


def baseline_mean_metrics(y_train: pd.Series, y_eval: pd.Series) -> dict:
    """Metrics for the "predict the train mean for everything" baseline.

    Every feature-selection method should be compared against this, not
    just against each other. With a low signal-to-noise target like
    ``target_return_5d``, a config that uses zero features (e.g. Lasso
    collapsing every coefficient to 0) is mathematically identical to
    this baseline -- so this makes that visible in the comparison table
    instead of looking like an unexplained top result.
    """
    from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

    y_pred = pd.Series(y_train.mean(), index=y_eval.index)

    mse = mean_squared_error(y_eval, y_pred)

    return {
        "method": "Baseline (predict train mean)",
        "n_selected_features": 0,
        "selected_features": [],
        "RMSE": mse ** 0.5,
        "MAE": mean_absolute_error(y_eval, y_pred),
        "R2": r2_score(y_eval, y_pred),
    }
