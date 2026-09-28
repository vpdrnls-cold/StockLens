"""Do the 5-day daily-bar decomposition features improve the ML model? (Phase H plan step 2)

Background
  - Since 2026-09-24 the target is ``close(t+5) / open(t+1) - 1`` (``entry="next_open"``,
    src/data/dataset.py), which is exactly what the backtest engine realizes.
  - The entry-timing IC check (scripts/entry_timing_ic.py, Notion "Entry timing IC on
    top-50 universe") found that under this target the 5-day aggregates of the daily
    bar decomposition carry signal that the current 19 features don't hold directly:
        gap_sum_5       sum of the last 5 overnight gaps      (open / prev close - 1)
        intraday_sum_5  sum of the last 5 open->close returns (close / open - 1)
        range_mean_5    mean of the last 5 high/low ranges    (high / low - 1)
    gap_sum_5 in particular: beta-neutral IC -0.034 (t -7.3) in train and -0.041
    (t -3.9) in validation.

Question
  Adding those three to the 19 scale-free features (22 total): does the ML model's
  out-of-sample cross-sectional IC and its after-cost backtest improve?

Fixed setup (all as adopted in items 36/38; nothing is tuned here)
  - top50 universe, the same 3 walk-forward windows as every walk-forward script
  - per-date rank target, early_stopping_metric="ic", n_jobs=1, tree_method="exact"
  - A = ALL_19 (current),  B = ALL_19 + the 3 features above
  - backtest: top_n=10, real costs (fees, 0.2% tax, 0.1% slippage each way),
    no buffer and buffer_multiplier=3.0 (the item 35 candidate)

Pre-registered decision rule (written before running)
  Adopt B only if val IC(B) > val IC(A) in ALL 3 windows AND the 3-window average
  buffered net_cum of B is not lower than A. Otherwise keep the 19 features.

Caveat (selection bias): gap_sum_5 was picked partly after seeing validation IC in the
entry-timing check. Its train-period t (-7.3) supports it independently, but a pass
here is weaker evidence than a feature chosen from train alone.

Only train/validation dates are used -- the test period is never touched.

    STOCKLENS_UNIVERSE=top50 PYTHONPATH=. python scripts/experiment_decomposition_features.py
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from scripts.walk_forward_backtest_compare import (
    ALL_19,
    DETERMINISTIC_PARAMS,
    NET_CONFIG,
    WINDOWS,
    evaluate,
    load_priced_dataset,
    to_data_by_stock,
    universe_average_gross,
)
from src.backtest.baseline import calculate_performance
from src.backtest.buffered import BufferedBaselineConfig, run_buffered_backtest
from src.data.dataset import TEST_END_DATE, TEST_START_DATE, TRAIN_START_DATE, split_by_time
from src.ml.cross_section import daily_rank_ic, rank_by_date, summarize_ic
from src.ml.strategy import make_model_score_fn, predictions_for_dataset
from src.models.predict import train_model

DECOMP_5D = ("gap_sum_5", "intraday_sum_5", "range_mean_5")
FEATURE_SETS = {
    "A_all19": tuple(ALL_19),
    "B_all19+decomp": tuple(ALL_19) + DECOMP_5D,
}
TOP_N = 10
BUFFER = 3.0
BUFFERED_NET_CONFIG = BufferedBaselineConfig(
    **{f: getattr(NET_CONFIG, f) for f in NET_CONFIG.__dataclass_fields__},
    buffer_multiplier=BUFFER,
)


def add_decomposition_features(dataset: pd.DataFrame) -> pd.DataFrame:
    """Per-stock 5-day aggregates; each row uses only its own and the 4 previous rows."""
    df = dataset.sort_values(["stock_code", "trade_date"]).copy()
    g = df.groupby("stock_code", sort=False)
    df["gap_sum_5"] = g["gap"].transform(lambda s: s.rolling(5, min_periods=5).sum())
    df["intraday_sum_5"] = g["intraday_return"].transform(lambda s: s.rolling(5, min_periods=5).sum())
    df["range_mean_5"] = g["high_low_range"].transform(lambda s: s.rolling(5, min_periods=5).mean())
    df[list(DECOMP_5D)] = df[list(DECOMP_5D)].replace([np.inf, -np.inf], np.nan)
    return df.reset_index(drop=True)


def run(dataset: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for label, train_end, val_start, val_end in WINDOWS:
        splits = split_by_time(
            dataset,
            train_start=TRAIN_START_DATE, train_end=train_end,
            validation_start=val_start, validation_end=val_end,
            test_start=TEST_START_DATE, test_end=TEST_END_DATE,
        )
        print(f"\n{label}: train n={len(splits.train)}  val n={len(splits.validation)}")
        data_by_stock = to_data_by_stock(splits.validation)
        benchmark = universe_average_gross(data_by_stock)

        for name, features in FEATURE_SETS.items():
            trained = train_model(
                splits.train, rank_by_date(splits.train, "target_return_5d"),
                splits.validation, rank_by_date(splits.validation, "target_return_5d"),
                feature_columns=features, params=DETERMINISTIC_PARAMS,
                early_stopping_metric="ic",
            )
            preds = predictions_for_dataset(trained, splits.validation)

            scored = splits.validation[["trade_date", "stock_code", "target_return_5d"]].copy()
            scored["trade_date"] = pd.to_datetime(scored["trade_date"])
            scored = scored.merge(preds, on=["trade_date", "stock_code"], how="left")
            scored = scored.dropna(subset=["target_return_5d"])
            ic = summarize_ic(daily_rank_ic(scored, "predicted_return"))

            score_fn = make_model_score_fn(preds)
            plain, _ = evaluate(name, score_fn, data_by_stock, benchmark, TOP_N)
            buffered = calculate_performance(
                run_buffered_backtest(data_by_stock, BUFFERED_NET_CONFIG, score_fn=score_fn, top_n=TOP_N)
            )
            print(f"  {name:<16} best_iteration={trained.best_iteration:<4} val_ic={ic.mean_ic:+.4f}")

            rows.append({
                "window": label,
                "features": name,
                "best_iter": trained.best_iteration,
                "val_ic": ic.mean_ic,
                "pct_pos": ic.pct_pos,
                "coverage": ic.coverage,
                "excess": plain["excess"],
                "t_excess": plain["t_excess"],
                "net_cum": plain["net_cum"],
                "buf_net_cum": float(buffered["total_return"]),
                "buf_mdd": float(buffered["max_drawdown"]),
            })
    return pd.DataFrame(rows)


def _print(df: pd.DataFrame) -> None:
    print(
        f"{'features':<16}{'best_it':>8}{'val_ic':>9}{'%ic>0':>8}{'cover':>8}"
        f"{'excess/5d':>11}{'t(exc)':>8}{'net_cum':>9}{'buf_net_cum':>13}{'buf_mdd':>9}"
    )
    for r in df.itertuples():
        print(
            f"{r.features:<16}{r.best_iter:>8}{r.val_ic:>+9.4f}{r.pct_pos:>8.1%}{r.coverage:>8.1%}"
            f"{r.excess:>11.3%}{r.t_excess:>8.2f}{r.net_cum:>9.1%}{r.buf_net_cum:>13.1%}{r.buf_mdd:>9.1%}"
        )


def main() -> None:
    dataset = add_decomposition_features(load_priced_dataset())
    results = run(dataset)

    for label in results["window"].unique():
        print("\n" + "=" * 100)
        print(f"{label}   (top_n={TOP_N}, buffer={BUFFER})")
        print("=" * 100)
        _print(results[results["window"] == label])

    wide = results.pivot(index="window", columns="features", values="val_ic")
    ic_up_all = bool((wide["B_all19+decomp"] > wide["A_all19"]).all())
    buf = results.groupby("features")["buf_net_cum"].mean()
    buf_ok = bool(buf["B_all19+decomp"] >= buf["A_all19"])

    print("\n" + "=" * 100)
    print("PRE-REGISTERED DECISION")
    print("=" * 100)
    print(f"val IC(B) > IC(A) in all 3 windows : {ic_up_all}")
    for w, r in wide.iterrows():
        print(f"    {w:<20} A {r['A_all19']:+.4f}  B {r['B_all19+decomp']:+.4f}  "
              f"diff {r['B_all19+decomp'] - r['A_all19']:+.4f}")
    print(f"avg buffered net_cum B >= A       : {buf_ok}  "
          f"(A {buf['A_all19']:+.1%}, B {buf['B_all19+decomp']:+.1%})")
    print(f"=> {'ADOPT B (22 features)' if ic_up_all and buf_ok else 'KEEP A (19 features)'}")


if __name__ == "__main__":
    main()
