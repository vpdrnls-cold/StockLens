"""Reproducibility diagnostic for the cross-machine XGBoost
non-determinism documented in CURRENT_STATUS.md items 15/18/20/21:
even with ``n_jobs=1`` (AGENTS.md 25) and a fixed ``random_state=42``
(``src.models.predict.DEFAULT_PARAMS``), two machines running the same
walk-forward scripts have produced different ``best_iteration`` values
and different downstream numbers.

This script does NOT touch StockLens's own data or models -- it exists
to answer one question first, before debugging anything project-specific:
is the divergence coming from the environment/xgboost/hardware level,
or from something in StockLens's own data pipeline (feature engineering,
file read order, etc.)?

Two parts:

1. Environment fingerprint -- Python/OS/CPU architecture, and the
   xgboost/numpy/pandas versions actually installed. Worth noting up
   front: ``requirements.txt`` currently pins NONE of these
   (``pandas``, ``numpy``, ``xgboost`` with no version at all), so if
   the two machines have different versions installed, that alone --
   independent of any floating-point/hardware issue -- can change
   default behavior (e.g. XGBoost's default ``tree_method`` has
   changed across major versions).
2. A minimal synthetic XGBoost fit -- pure numpy random data (fixed
   seed), no StockLens code involved at all -- trained twice: once
   with whatever ``tree_method`` the installed xgboost defaults to
   (StockLens does not currently set this explicitly either), and once
   forcing ``tree_method="exact"`` (no histogram binning, the
   numerically simplest/most reproducible option XGBoost offers,
   though still not guaranteed bit-identical across CPU architectures
   per XGBoost's own docs). Both runs use ``n_jobs=1,
   random_state=42`` -- the exact same determinism settings this
   project already uses.

   If this synthetic, StockLens-independent example ALSO diverges
   between machines, that isolates the cause to the xgboost/hardware
   level (nothing to fix in this repo's code). If it matches but the
   real walk-forward scripts still diverge, the problem is somewhere
   in StockLens's own data pipeline instead, and that would need a
   separate investigation.

   To make "does this match or not" a yes/no instead of a
   many-decimal-places visual diff, predictions are hashed
   (sha256 of the raw float64 bytes) -- if the hash strings printed on
   two machines are identical, the outputs are bit-for-bit identical;
   if not, there is real divergence and the printed decimals show
   where.

Run identically on both machines and compare the two blocks of output
(paste both outputs side by side, or diff them):
    PYTHONPATH=. python3 scripts/diagnose_reproducibility_env.py
"""

from __future__ import annotations

import hashlib
import platform
import sys

import numpy as np


def _print_environment_fingerprint() -> None:
    import numpy
    import pandas
    import xgboost

    print("=" * 78)
    print("ENVIRONMENT FINGERPRINT")
    print("=" * 78)
    print(f"python:          {platform.python_version()} ({sys.version})")
    print(f"platform:        {platform.platform()}")
    print(f"machine (arch):  {platform.machine()}")
    print(f"processor:       {platform.processor()}")
    print(f"xgboost:         {xgboost.__version__}")
    print(f"numpy:           {numpy.__version__}")
    print(f"pandas:          {pandas.__version__}")
    try:
        info = xgboost.build_info()
        print(f"xgboost build_info: {info}")
    except Exception as exc:  # older xgboost versions lack build_info()
        print(f"xgboost build_info: unavailable ({exc})")
    print()


def _hash_array(arr: np.ndarray) -> str:
    return hashlib.sha256(np.ascontiguousarray(arr, dtype=np.float64).tobytes()).hexdigest()


def _run_synthetic_fit(tree_method: str | None) -> None:
    from xgboost import XGBRegressor

    label = tree_method if tree_method is not None else "(xgboost default, unset)"
    print(f"--- synthetic fit: tree_method={label} ---")

    # Fixed-seed synthetic data -- identical on every machine by
    # construction (numpy's Mersenne Twister with a fixed seed is
    # itself deterministic across platforms; this is not part of what
    # we're testing).
    rng = np.random.default_rng(42)
    n_train, n_val, n_features = 2000, 500, 6
    X_train = rng.normal(size=(n_train, n_features))
    true_coef = rng.normal(size=n_features)
    y_train = X_train @ true_coef + 0.1 * rng.normal(size=n_train)
    X_val = rng.normal(size=(n_val, n_features))
    y_val = X_val @ true_coef + 0.1 * rng.normal(size=n_val)

    params: dict = {
        "max_depth": 2,
        "learning_rate": 0.03,
        "subsample": 1.0,
        "colsample_bytree": 1.0,
        "n_estimators": 1000,
        "random_state": 42,
        "n_jobs": 1,
    }
    if tree_method is not None:
        params["tree_method"] = tree_method

    model = XGBRegressor(**params, eval_metric="rmse", early_stopping_rounds=30)
    model.fit(X_train, y_train, eval_set=[(X_val, y_val)], verbose=False)

    preds = model.predict(X_val)
    print(f"best_iteration:      {model.best_iteration}")
    print(f"predictions sha256:  {_hash_array(preds)}")
    print(f"predictions[:5]:     {[f'{p:.10f}' for p in preds[:5]]}")
    print(f"predictions sum:     {preds.sum():.10f}")
    print()


def main() -> None:
    _print_environment_fingerprint()

    print("=" * 78)
    print("SYNTHETIC XGBOOST DETERMINISM TEST (no StockLens data/code involved)")
    print("=" * 78)
    _run_synthetic_fit(tree_method=None)  # whatever this xgboost version defaults to
    _run_synthetic_fit(tree_method="exact")

    print(
        "Compare this whole output against the other machine's. If both "
        "'predictions sha256' lines match for a given tree_method between "
        "machines, XGBoost is bit-reproducible here and the real-data "
        "divergence must be coming from somewhere in StockLens's own "
        "pipeline instead. If they differ here too, the cause is at the "
        "xgboost/environment/hardware level, not in this repo's code."
    )


if __name__ == "__main__":
    main()
