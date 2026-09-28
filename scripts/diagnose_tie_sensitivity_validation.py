"""Tie-break sensitivity dry run on the validation split (item 52).

Runs the same tie_sensitivity() that the forward report uses, but on the
already-used validation split (2020-01-01 ~ 2023-06-30) with the frozen daily
score only (no intraday panel needed). Checks:
  1. code-ascending net return reproduces item 45/51 (+65.0%)
  2. tie stats reproduce item 51 (~7.8 distinct scores/day, ~18.5 at/above 10th)
  3. with ties removed (tiny noise added), every stock order gives the same
     result -> the order acts only through ties

    STOCKLENS_UNIVERSE=top50 PYTHONPATH=. python scripts/diagnose_tie_sensitivity_validation.py
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from scripts import evaluate_forward_holdout as fh
from scripts.run_ml_backtest import (
    BUFFERED_CONFIG,
    TOP_N,
    _load_priced_dataset,
    _to_data_by_stock,
    train_frozen_model,
)
from src.backtest.baseline import calculate_performance
from src.backtest.buffered import run_buffered_backtest_with_turnover
from src.ml.strategy import make_model_score_fn, predictions_for_dataset

EXPECTED_CODE_ASC = 0.650  # item 45, A_all19, W3


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--n", type=int, default=fh.TIE_PERMUTATIONS, help="number of random stock orders")
    ap.add_argument("--seed", type=int, default=fh.TIE_SEED)
    ap.add_argument("--out", default="reports/tie_sensitivity_validation")
    args = ap.parse_args()

    trained, splits = train_frozen_model(_load_priced_dataset())
    print(f"frozen daily model: best_iteration={trained.best_iteration} (expected 9)")

    val = splits.validation.dropna(subset=["target_return_5d"]).copy()
    pred = predictions_for_dataset(trained, val)
    val = val.merge(pred[["trade_date", "stock_code", "predicted_return"]], on=["trade_date", "stock_code"])
    val["score_w0.0"] = val["predicted_return"]
    strat = (("daily", "score_w0.0"),)

    data_by_stock = _to_data_by_stock(val)
    score_fn = make_model_score_fn(val[["trade_date", "stock_code", "predicted_return"]])
    net, _ = run_buffered_backtest_with_turnover(data_by_stock, BUFFERED_CONFIG, score_fn=score_fn, top_n=TOP_N)
    code_asc = calculate_performance(net)["total_return"]
    res = pd.DataFrame([{"strategy": "daily", "net_cum": code_asc}])

    sens = fh.tie_sensitivity(val, strategies=strat, n=args.n, seed=args.seed)
    ties = fh.summarize_ties(sens, res, val, strategies=strat)

    # Control: break every tie with tiny noise -> the order must stop mattering.
    rng = np.random.default_rng(0)
    val["score_no_ties"] = val["predicted_return"] + rng.normal(0, 1e-6, len(val))
    ctrl = fh.tie_sensitivity(val, strategies=(("no_ties", "score_no_ties"),), n=5, seed=args.seed)
    spread = float(ctrl["net_cum"].max() - ctrl["net_cum"].min())

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    sens.to_csv(out / "validation_tie_permutations.csv", index=False, encoding="utf-8-sig")
    ties.to_csv(out / "validation_tie_sensitivity.csv", index=False, encoding="utf-8-sig")

    print("\n" + "=" * 100)
    print(f"TIE-BREAK SENSITIVITY  validation {val['trade_date'].min():%Y-%m-%d} ~ {val['trade_date'].max():%Y-%m-%d}, "
          f"top_n={TOP_N}, buffer 3.0, {args.n} orders (seed {args.seed})")
    print("=" * 100)
    print(ties.to_string(index=False, float_format=lambda x: f"{x:+.4f}"))
    print("\nper-order net_cum:")
    print(sens["net_cum"].sort_values().to_string(index=False, float_format=lambda x: f"{x:+.2%}"))
    print(f"\ncheck 1  code_asc {code_asc:+.1%} vs expected {EXPECTED_CODE_ASC:+.1%} -> "
          + ("MATCH" if abs(code_asc - EXPECTED_CODE_ASC) < 0.0015 else "MISMATCH"))
    print(f"check 3  no-tie control spread across orders = {spread:.2e} -> "
          + ("OK (order acts only through ties)" if spread < 1e-12 else "FAIL"))
    print(f"\nsaved: {out / 'validation_tie_sensitivity.csv'}, {out / 'validation_tie_permutations.csv'}")


if __name__ == "__main__":
    main()
