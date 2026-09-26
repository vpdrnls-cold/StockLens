"""Are the signals worth anything AFTER costs? Momentum vs reversal vs ML.

CURRENT_STATUS items 31/32 found that (a) short-term price REVERSAL is the
only stable cross-sectional pattern in the top50 universe (recent winners
underperform), and (b) the "momentum" baseline used so far buys exactly the
opposite. This script puts the three side by side, per walk-forward window,
through the same execution engine and costs (T+1 open entry, T+5 close exit,
fees, 0.2% sell tax, 0.1% slippage each way), for top_n = 5 and 10:

  momentum   score = past 5-day return              (the existing baseline)
  reversal   score = -(past 5-day return)
  ml         all 19 features, per-date RANK target  (best setup of item 32)

For every strategy it reports, per 5-day holding period:
  gross      average return with all costs set to zero
  excess     gross minus the equal-weight average of every tradable stock
             that period (removes the market move: this is the alpha)
  t(excess)  mean excess / standard error (periods do not overlap)
  net        average return after costs; net_cum = compounded net return

Only train/validation dates are used -- the test period is never touched.

Every run also saves the net per-period returns, trades and the daily rank IC
of the ml/reversal scores to reports/runs/ (src/reporting/run_log.py); plot
them with scripts/plot_run.py.

    STOCKLENS_UNIVERSE=top50 PYTHONPATH=. python3 scripts/walk_forward_backtest_compare.py
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.backtest.baseline import (
    BaselineConfig,
    calculate_net_return,
    calculate_performance,
    calculate_score,
    prepare_universe,
    run_baseline_backtest,
    trades_to_dataframe,
)
from src.data.dataset import (
    TEST_END_DATE,
    TEST_START_DATE,
    TRAIN_START_DATE,
    build_combined_dataset,
    split_by_time,
)
from src.data.storage import HistoricalStorage
from src.data.universe import get_universe
from src.features.engineering import FEATURE_COLUMNS
from src.ml.cross_section import daily_rank_ic, rank_by_date
from src.ml.strategy import make_model_score_fn, predictions_for_dataset
from src.models.predict import train_model
from src.reporting.run_log import RunRecorder

RAW_SCALE_FEATURES = {
    "sma_5", "sma_20", "sma_60", "macd", "macd_signal", "macd_hist",
    "atr_14", "volume_sma_20",
}
ALL_19 = tuple(f for f in FEATURE_COLUMNS if f not in RAW_SCALE_FEATURES)
DETERMINISTIC_PARAMS = {"n_jobs": 1, "tree_method": "exact"}
TOP_NS = (5, 10)

WINDOWS = [
    ("W1 val 2012-2015", "2011-12-31", "2012-01-01", "2015-12-31"),
    ("W2 val 2016-2019", "2015-12-31", "2016-01-01", "2019-12-31"),
    ("W3 val 2020-2023H1", "2019-12-31", "2020-01-01", "2023-06-30"),
]

NET_CONFIG = BaselineConfig(
    lookback_days=5, holding_days=5,
    buy_fee=0.00015, sell_fee=0.00015, sell_tax=0.0020,
    buy_slippage=0.0010, sell_slippage=0.0010,
    allow_partial_universe=True,
)
GROSS_CONFIG = BaselineConfig(
    lookback_days=5, holding_days=5,
    buy_fee=0.0, sell_fee=0.0, sell_tax=0.0,
    buy_slippage=0.0, sell_slippage=0.0,
    allow_partial_universe=True,
)
PERIODS_PER_YEAR = 252 / 5


def load_priced_dataset() -> pd.DataFrame:
    storage = HistoricalStorage("data")
    stock_bars = {code: storage.load_daily_bars(code) for code in get_universe()}
    dataset = build_combined_dataset(stock_bars)
    dataset["trade_date"] = pd.to_datetime(dataset["trade_date"])
    dataset[list(FEATURE_COLUMNS)] = dataset[list(FEATURE_COLUMNS)].replace(
        [np.inf, -np.inf], np.nan
    )
    prices = pd.DataFrame(
        [
            {
                "trade_date": pd.Timestamp(bar.trade_date),
                "stock_code": code,
                "open_price": float(bar.open_price),
                "close_price": float(bar.close_price),
            }
            for code, bars in stock_bars.items()
            for bar in bars
        ]
    )
    return dataset.merge(prices, on=["trade_date", "stock_code"], how="left", validate="one_to_one")


def to_data_by_stock(dataset: pd.DataFrame) -> dict[str, pd.DataFrame]:
    return {
        str(code): group[["stock_code", "trade_date", "open_price", "close_price"]]
        .sort_values("trade_date")
        .reset_index(drop=True)
        for code, group in dataset.groupby("stock_code")
    }


def universe_average_gross(data_by_stock: dict[str, pd.DataFrame]) -> pd.Series:
    """Equal-weight average gross return of every tradable stock, per decision date.

    Uses the same decision grid and price-eligibility rule as the engine's
    partial-universe mode (T-5 close, T close, T+1 open, T+5 close all valid).
    """
    universe = prepare_universe(data_by_stock, how="outer")
    lookback = holding = 5
    codes = list(data_by_stock)
    opens = {c: universe[f"open_{c}"].to_numpy(float) for c in codes}
    closes = {c: universe[f"close_{c}"].to_numpy(float) for c in codes}
    dates = universe["trade_date"]
    zero_cost = GROSS_CONFIG

    result: dict[pd.Timestamp, float] = {}
    for d in range(lookback, len(universe) - holding, holding):
        returns = []
        for c in codes:
            needed = (closes[c][d - lookback], closes[c][d], opens[c][d + 1], closes[c][d + holding])
            if all(np.isfinite(v) and v > 0 for v in needed):
                returns.append(calculate_net_return(opens[c][d + 1], closes[c][d + holding], zero_cost)[0])
        if returns:
            result[dates.iloc[d]] = float(np.mean(returns))
    return pd.Series(result, dtype="float64")


def period_returns(trades, column: str) -> pd.Series:
    df = trades_to_dataframe(trades)
    if df.empty:
        return pd.Series(dtype="float64")
    df["contribution"] = df["weight"] * df[column]
    return df.groupby("decision_date")["contribution"].sum().sort_index()


def evaluate(strategy_name, score_fn, data_by_stock, benchmark, top_n) -> tuple[dict, list]:
    gross_trades = run_baseline_backtest(data_by_stock, GROSS_CONFIG, score_fn=score_fn, top_n=top_n)
    net_trades = run_baseline_backtest(data_by_stock, NET_CONFIG, score_fn=score_fn, top_n=top_n)

    gross = period_returns(gross_trades, "net_return")   # zero costs -> equals gross
    excess = (gross - benchmark.reindex(gross.index)).dropna()
    net_perf = calculate_performance(net_trades)
    n = len(excess)
    t_stat = float(excess.mean() / (excess.std(ddof=1) / np.sqrt(n))) if n > 2 else float("nan")

    row = {
        "strategy": strategy_name,
        "top_n": top_n,
        "periods": n,
        "gross": float(gross.mean()),
        "excess": float(excess.mean()),
        "t_excess": t_stat,
        "net": float(net_perf["average_trade_return"]),
        "net_cum": float(net_perf["total_return"]),
        "net_mdd": float(net_perf["max_drawdown"]),
    }
    return row, net_trades


def run(
    dataset: pd.DataFrame,
    windows=WINDOWS,
    top_ns=TOP_NS,
    recorder: RunRecorder | None = None,
) -> pd.DataFrame:
    rows = []
    for label, train_end, val_start, val_end in windows:
        splits = split_by_time(
            dataset,
            train_start=TRAIN_START_DATE, train_end=train_end,
            validation_start=val_start, validation_end=val_end,
            test_start=TEST_START_DATE, test_end=TEST_END_DATE,
        )
        print(f"\n{label}: train n={len(splits.train)}  val n={len(splits.validation)}")

        trained = train_model(
            splits.train, rank_by_date(splits.train, "target_return_5d"),
            splits.validation, rank_by_date(splits.validation, "target_return_5d"),
            feature_columns=ALL_19, params=DETERMINISTIC_PARAMS,
        )
        print(f"  ML model best_iteration={trained.best_iteration}")
        ml_predictions = predictions_for_dataset(trained, splits.validation)
        ml_score_fn = make_model_score_fn(ml_predictions)

        if recorder is not None:
            # Daily rank IC against the raw target, validation dates only.
            # momentum's IC is exactly -reversal's, so it is not stored twice.
            scored = splits.validation[["trade_date", "stock_code", "target_return_5d", "return_5d"]].copy()
            scored["trade_date"] = pd.to_datetime(scored["trade_date"])
            scored = scored.merge(ml_predictions, on=["trade_date", "stock_code"], how="left")
            scored["reversal_score"] = -scored["return_5d"]
            scored = scored.dropna(subset=["target_return_5d"])
            recorder.add_ic(label, "ml", daily_rank_ic(scored, "predicted_return"))
            recorder.add_ic(label, "reversal", daily_rank_ic(scored, "reversal_score"))

        data_by_stock = to_data_by_stock(splits.validation)
        benchmark = universe_average_gross(data_by_stock)

        strategies = {
            "momentum": calculate_score,
            "reversal": lambda u, code, i, lb: -calculate_score(u, code, i, lb),
            "ml": ml_score_fn,
        }
        for top_n in top_ns:
            for name, score_fn in strategies.items():
                row, net_trades = evaluate(name, score_fn, data_by_stock, benchmark, top_n)
                row["window"] = label
                rows.append(row)
                if recorder is not None:
                    recorder.add_trades(label, f"{name} top_n={top_n}", net_trades)

    return pd.DataFrame(rows)


def _print_table(df: pd.DataFrame) -> None:
    header = (
        f"{'strategy':<10}{'top_n':>6}{'periods':>8}{'gross/5d':>10}{'excess/5d':>11}"
        f"{'t(excess)':>10}{'net/5d':>9}{'net_cum':>10}{'net_mdd':>9}"
    )
    print(header)
    for r in df.itertuples():
        print(
            f"{r.strategy:<10}{r.top_n:>6}{r.periods:>8}{r.gross:>10.3%}{r.excess:>11.3%}"
            f"{r.t_excess:>10.2f}{r.net:>9.3%}{r.net_cum:>10.1%}{r.net_mdd:>9.1%}"
        )


def main() -> None:
    universe = get_universe()
    recorder = RunRecorder(
        "walk_forward_backtest_compare",
        meta={
            "script": "scripts/walk_forward_backtest_compare.py",
            "universe_size": len(universe),
            "top_ns": list(TOP_NS),
            "windows": [w[0] for w in WINDOWS],
            "split": "validation only",
            "returns": "net of fees, tax and slippage (NET_CONFIG)",
        },
    )
    results = run(load_priced_dataset(), recorder=recorder)
    recorder.save()

    for label in results["window"].unique():
        print("\n" + "=" * 100)
        print(label)
        print("=" * 100)
        _print_table(results[results["window"] == label])

    print("\n" + "=" * 100)
    print("AVERAGE OVER THE 3 WINDOWS (per-5-day-period figures)")
    print("=" * 100)
    avg = (
        results.groupby(["strategy", "top_n"])[["gross", "excess", "t_excess", "net", "net_cum", "net_mdd"]]
        .mean()
        .reset_index()
    )
    avg["periods"] = 0
    _print_table(avg[["strategy", "top_n", "periods", "gross", "excess", "t_excess", "net", "net_cum", "net_mdd"]])

    print(
        "\nHow to read it: `excess` is the alpha before costs. A strategy is only "
        "interesting if excess is positive in every window with t(excess) around 2 "
        "or more AND `net` (after ~0.43% round-trip cost per 5-day hold) is still "
        "positive. The round-trip cost is the hurdle each 5-day period must clear."
    )


if __name__ == "__main__":
    main()
