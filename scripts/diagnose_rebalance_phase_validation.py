"""Rebalance-phase sensitivity on all validation windows (CURRENT_STATUS item 65, diagnostic).

Why
  The engines rebalance every 5 trading days from a fixed first date, so every
  reported net return is one of 5 possible schedules. On W3 the frozen model's
  buffered net_cum ranged -9.4% ~ +65.0% by start date alone (item 65); the
  reported +65.0% was the best of the five. This checks W1 and W2 the same way.

What
  Same per-window models as item 45 / 55 (A_all19, rank target, IC early stopping,
  entry next_open, deterministic), same strategy (top-10, buffer 3.0, real costs),
  and the same ``phase_sensitivity()`` the forward report uses (start shifted by
  0..4 trading days). The universe equal-weight return (no costs) is shown per
  offset as the long-only reference. The intraday dev segment (2025-09~2026-06,
  W3 = frozen model) is reported too. test / semi_holdout / forward are never read.

Diagnostic only: no model, rule, parameter or pre-registered decision changes
with this result. Cross-check: offset 0 must reproduce item 55's R0 net_cum
(W1 +34.8%, W2 +15.9%, W3 +65.0%).

    STOCKLENS_UNIVERSE=top50 PYTHONPATH=. python scripts/diagnose_rebalance_phase_validation.py
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from scripts import evaluate_forward_holdout as fh
from scripts.walk_forward_backtest_compare import (
    ALL_19,
    DETERMINISTIC_PARAMS,
    WINDOWS,
    load_priced_dataset,
)
from src.data.dataset import TEST_END_DATE, TEST_START_DATE, TRAIN_START_DATE, split_by_time
from src.data.intraday_split import select_segment
from src.ml.cross_section import rank_by_date
from src.ml.strategy import predictions_for_dataset
from src.models.predict import train_model

CALLER = "diagnose_rebalance_phase_validation.py"
OUT = Path("reports/rebalance_phase_validation")
EXPECTED_OFFSET0 = {"W1 val 2012-2015": 0.348, "W2 val 2016-2019": 0.159, "W3 val 2020-2023H1": 0.650}
STRATEGY = (("daily", "score_w0.0"),)


def scored(part: pd.DataFrame, trained) -> pd.DataFrame:
    part = part.dropna(subset=["target_return_5d"]).copy()
    pred = predictions_for_dataset(trained, part)
    part = part.merge(pred, on=["trade_date", "stock_code"], how="left")
    part["score_w0.0"] = part["predicted_return"]
    return part


def block(label: str, part: pd.DataFrame) -> pd.DataFrame:
    phases = fh.phase_sensitivity(part, strategies=STRATEGY)  # includes univ_ew_gross / excess per offset
    phases.insert(0, "window", label)
    return phases


def main() -> None:
    dataset = load_priced_dataset()
    frames, w3_model = [], None
    for label, train_end, val_start, val_end in WINDOWS:
        assert pd.Timestamp(val_end) < pd.Timestamp(TEST_START_DATE), "validation must end before test"
        splits = split_by_time(
            dataset,
            train_start=TRAIN_START_DATE, train_end=train_end,
            validation_start=val_start, validation_end=val_end,
            test_start=TEST_START_DATE, test_end=TEST_END_DATE,
        )
        trained = train_model(
            splits.train, rank_by_date(splits.train, "target_return_5d"),
            splits.validation, rank_by_date(splits.validation, "target_return_5d"),
            feature_columns=tuple(ALL_19), params=DETERMINISTIC_PARAMS, early_stopping_metric="ic",
        )
        print(f"{label}: best_iteration={trained.best_iteration}")
        frames.append(block(label, scored(splits.validation, trained)))
        w3_model = trained  # last window = W3 = frozen deploy model

    dev = select_segment(dataset, "dev", caller=CALLER, horizon=5)
    frames.append(block("DEV 2025-09~2026-06 (report only)", scored(dev, w3_model)))
    res = pd.concat(frames, ignore_index=True)

    OUT.mkdir(parents=True, exist_ok=True)
    res.to_csv(OUT / "phase_sensitivity.csv", index=False, encoding="utf-8-sig")

    cols = ["offset", "start", "periods", "net_cum", "mdd", "hit", "entries", "univ_ew_gross", "excess_vs_univ"]
    for label, part in res.groupby("window", sort=False):
        print("\n" + "=" * 100)
        print(f"{label}   top-10, buffer 3.0, real costs; univ_ew = equal-weight universe, no costs")
        print("=" * 100)
        print(part[cols].to_string(index=False, float_format=lambda x: f"{x:+.4f}"))
        print(f"net_cum mean {part['net_cum'].mean():+.1%}  range {part['net_cum'].min():+.1%} ~ "
              f"{part['net_cum'].max():+.1%} | offsets beating univ_ew: {(part['excess_vs_univ'] > 0).sum()}/5")

    print("\ncross-check offset 0 vs item 55 R0:")
    for label, expected in EXPECTED_OFFSET0.items():
        got = res[(res["window"] == label) & (res["offset"] == 0)]["net_cum"].iloc[0]
        print(f"  {label}: {got:+.1%} vs {expected:+.1%} -> {'MATCH' if abs(got - expected) < 0.0015 else 'MISMATCH'}")
    print(f"\nsaved {OUT / 'phase_sensitivity.csv'}")


if __name__ == "__main__":
    main()
