"""Real-data follow-up to scripts/diagnose_reproducibility_env.py.

The synthetic test in that script found: with the installed xgboost's
default tree_method (almost certainly "hist" on both machines, just
different versions/architectures), predictions diverged between
machines (different sha256). With tree_method="exact" forced, the two
machines -- Linux x86_64/GCC vs macOS arm64/Clang, different xgboost/
numpy/pandas versions, nothing else pinned -- produced a BIT-IDENTICAL
sha256. That isolates the cross-machine non-determinism documented in
CURRENT_STATUS.md items 15/18/20/21 to XGBoost's histogram-based tree
building (floating-point summation order in quantile-binned histograms
is not guaranteed identical across CPU architectures/compilers; XGBoost
's own docs say so), not to anything in StockLens's own code.

That result was on synthetic, StockLens-independent data. Before
proposing tree_method="exact" as this project's actual default (which
would be a real change to model behavior, not just a determinism
setting -- AGENTS.md 9 applies), this script re-runs the exact same
determinism check against the REAL StockLens dataset and the model's
real feature/target columns, on a single train/validation split (not
the full walk-forward grid -- this script only answers "is training on
our real data reproducible with tree_method=exact", not "does this
change any backtest conclusion").

Run identically on both machines and compare the printed hash + timing:
    PYTHONPATH=. python3 scripts/verify_exact_tree_method_reproducibility.py
"""

from __future__ import annotations

import hashlib
import time

import numpy as np

from src.data.dataset import split_by_time
from src.models.predict import DEFAULT_PARAMS, train_model

from scripts.evaluate_position_thresholds import _load_priced_dataset


def _hash_array(arr: np.ndarray) -> str:
    return hashlib.sha256(np.ascontiguousarray(arr, dtype=np.float64).tobytes()).hexdigest()


def _run(label: str, extra_params: dict) -> None:
    dataset = _load_priced_dataset()
    splits = split_by_time(dataset)

    params = {**DEFAULT_PARAMS, "n_jobs": 1, **extra_params}

    start = time.perf_counter()
    trained = train_model(
        splits.train,
        splits.train["target_return_5d"],
        splits.validation,
        splits.validation["target_return_5d"],
        params=params,
    )
    elapsed = time.perf_counter() - start

    preds = trained.model.predict(splits.validation[list(trained.feature_columns)])

    print(f"--- {label} ---")
    print(f"params (deltas from DEFAULT_PARAMS): {extra_params}")
    print(f"best_iteration:      {trained.best_iteration}")
    print(f"predictions sha256:  {_hash_array(preds)}")
    print(f"predictions[:5]:     {[f'{p:.10f}' for p in preds[:5]]}")
    print(f"train time:          {elapsed:.1f}s")
    print()


def main() -> None:
    print("=" * 78)
    print("REAL-DATA REPRODUCIBILITY CHECK (StockLens dataset, single split)")
    print("=" * 78)
    _run("current default (n_jobs=1, tree_method unset)", {})
    _run("tree_method=exact (n_jobs=1)", {"tree_method": "exact"})
    print(
        "Compare 'predictions sha256' for each row against the other machine's "
        "output. Matching hashes under tree_method=exact on real StockLens data "
        "would confirm the synthetic-data finding holds for this project's "
        "actual pipeline, not just the toy example."
    )


if __name__ == "__main__":
    main()
