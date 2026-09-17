"""Does switching XGBoost's tree_method to "exact" (for cross-machine
bit-reproducibility -- see scripts/diagnose_reproducibility_env.py and
scripts/verify_exact_tree_method_reproducibility.py, both confirmed on
two very different real machines) actually cost anything in prediction
quality or backtest performance versus the current implicit default
("hist")?

This is not a determinism check -- it's the AGENTS.md 9 check that has
to happen before adopting tree_method="exact" as this project's actual
DEFAULT_PARAMS, since it measurably changes what the model learns (the
real-data verification script already found best_iteration jump from
56 to 116 on the current default validation window -- that is a model
behavior change, not just a determinism setting).

Compares, on VALIDATION only (test period untouched, AGENTS.md 13),
both trained with n_jobs=1 (AGENTS.md 25):
    (a) current default: tree_method unset (installed xgboost's default,
        "hist" for any reasonably recent version)
    (b) tree_method="exact"
on two things:
    1. cross-sectional rank IC (the metric CURRENT_STATUS.md item 14
       established as what actually matters for a ranking strategy --
       reuses scripts/feature_selection_ic_rerun.py's cross_sectional_ic).
    2. the actual top_n=2 backtest (same universe/costs as
       scripts/evaluate_position_thresholds.py's 'no_early_exit
       (baseline)' row) -- cum_return/hit_rate/mdd.

Run from the repo root:
    PYTHONPATH=. python3 scripts/compare_tree_method_hist_vs_exact.py
"""

from __future__ import annotations

from src.backtest.baseline import calculate_performance, run_baseline_backtest
from src.data.dataset import split_by_time
from src.ml.strategy import make_model_score_fn, predictions_for_dataset
from src.models.predict import DEFAULT_PARAMS, train_model

from scripts.evaluate_position_thresholds import CONFIG, TOP_N, _load_priced_dataset, _to_data_by_stock
from scripts.feature_selection_ic_rerun import cross_sectional_ic

CONFIGS = {
    "current default (tree_method unset)": {},
    "tree_method=exact": {"tree_method": "exact"},
}


def main() -> None:
    dataset = _load_priced_dataset()
    splits = split_by_time(dataset)
    data_by_stock = _to_data_by_stock(splits.validation)

    print(
        f"{'config':<32}{'best_iter':>10}{'val_xsec_IC':>14}{'%days>0':>10}"
        f"{'cum_return':>12}{'hit_rate':>10}{'mdd':>10}"
    )

    for label, extra_params in CONFIGS.items():
        params = {**DEFAULT_PARAMS, "n_jobs": 1, **extra_params}
        trained = train_model(
            splits.train,
            splits.train["target_return_5d"],
            splits.validation,
            splits.validation["target_return_5d"],
            params=params,
        )

        predictions = predictions_for_dataset(trained, splits.validation)
        val = splits.validation.merge(
            predictions, on=["trade_date", "stock_code"], validate="one_to_one"
        )
        mean_ic, pct_pos, n = cross_sectional_ic(val, "predicted_return")

        score_fn = make_model_score_fn(predictions)
        trades = run_baseline_backtest(data_by_stock, config=CONFIG, score_fn=score_fn, top_n=TOP_N)
        perf = calculate_performance(trades)

        print(
            f"{label:<32}{trained.best_iteration:>10}{mean_ic:>+13.4f} "
            f"{pct_pos:>9.2%}{perf['total_return']:>11.2%} "
            f"{perf['win_rate']:>9.2%}{perf['max_drawdown']:>9.2%}"
        )

    print(
        "\nInterpretation: if tree_method=exact's IC/cum_return/mdd are "
        "comparable to (not clearly worse than) the current default, the "
        "reproducibility benefit (bit-identical across totally different "
        "machines, vs the current hist default's divergence) is worth "
        "adopting as this project's actual default despite the ~10x "
        "slower training (still well under a few seconds per fit on this "
        "dataset size). If it is clearly worse, tree_method=exact should "
        "be scoped to validation/robustness-checking scripts only, not "
        "the production default."
    )


if __name__ == "__main__":
    main()
