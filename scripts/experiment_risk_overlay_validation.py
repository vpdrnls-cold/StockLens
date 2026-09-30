"""Portfolio risk overlay on the validation windows (CURRENT_STATUS item 55, pre-registered).

Question
  The deploy path (frozen daily ML, top-10, buffer 3.0) has MDD around -44%
  (item 47). Keeping stock selection unchanged, does scaling total exposure
  cut MDD while keeping return-per-risk?

Candidates (fixed in item 55, see src/portfolio/risk_overlay.py)
  R0 e=1 | R1 vol target (20d, sigma* = train median) | R2 MA200 trend, low 0.5 | R3 = R1*R2

Data
  Walk-forward W1 (2012-2015), W2 (2016-2019), W3 (2020-2023H1) -- the same
  windows and model setup as item 45 (A_all19, rank target, IC early stopping,
  entry next_open, top-10, buffer 3.0). The market proxy for each window uses
  prices up to that window's validation end only; the script asserts it never
  reaches the daily test period. The intraday dev segment (2025-09~2026-06,
  W3 model = the frozen deploy model) is REPORTED ONLY, not used for the decision.
  test / semi_holdout / forward are never read.

Decision (pre-registered)
  Rk passes iff in ALL 3 windows: MDD(Rk) - MDD(R0) >= 5%p AND Calmar(Rk) >= Calmar(R0).
  Among passing: highest mean Calmar; within 0.05 -> simpler (R2 -> R1 -> R3). None -> R0.

Cross-check: W3 R0 net_cum must equal item 45/47 ml_buffered (+65.0%).

    STOCKLENS_UNIVERSE=top50 PYTHONPATH=. python scripts/experiment_risk_overlay_validation.py
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from scripts.walk_forward_backtest_compare import (
    ALL_19,
    DETERMINISTIC_PARAMS,
    NET_CONFIG,
    WINDOWS,
    load_priced_dataset,
    to_data_by_stock,
)
from src.backtest.buffered import BufferedBaselineConfig, run_buffered_backtest
from src.data.dataset import TEST_END_DATE, TEST_START_DATE, TRAIN_START_DATE, split_by_time
from src.data.intraday_split import select_segment
from src.data.storage import HistoricalStorage
from src.data.universe import get_universe
from src.ml.cross_section import rank_by_date
from src.ml.strategy import make_model_score_fn, predictions_for_dataset
from src.models.predict import train_model
from src.portfolio.risk_overlay import (
    CANDIDATES,
    MDD_MARGIN,
    apply_exposure,
    candidate_exposures,
    decide,
    period_returns,
    realized_vol,
    risk_metrics,
    sigma_star_from_train,
    universe_ew_index,
)

TOP_N = 10
BUFFER = 3.0
BUFFERED_NET_CONFIG = BufferedBaselineConfig(
    **{f: getattr(NET_CONFIG, f) for f in NET_CONFIG.__dataclass_fields__},
    buffer_multiplier=BUFFER,
)
EXPECTED_W3_R0 = 0.650  # item 45 / 47
DEV_END = "2026-06-30"
OUT_DIR = Path("reports/risk_overlay")
CALLER = "experiment_risk_overlay_validation.py"


def load_prices() -> pd.DataFrame:
    storage = HistoricalStorage("data")
    return pd.DataFrame(
        [
            {"trade_date": pd.Timestamp(b.trade_date), "stock_code": code, "close_price": float(b.close_price)}
            for code in get_universe()
            for b in storage.load_daily_bars(code)
        ]
    )


def market_index(prices: pd.DataFrame, cutoff: str) -> pd.Series:
    """Proxy index built from prices up to ``cutoff`` only."""
    return universe_ew_index(prices[prices["trade_date"] <= pd.Timestamp(cutoff)])


def evaluate_block(label: str, period: pd.DataFrame, trained, index: pd.Series, sigma_star: float) -> list[dict]:
    preds = predictions_for_dataset(trained, period)
    trades = run_buffered_backtest(
        to_data_by_stock(period), BUFFERED_NET_CONFIG, score_fn=make_model_score_fn(preds), top_n=TOP_N
    )
    base = period_returns(trades)
    rows = []
    for name, e in candidate_exposures(index, base.index, sigma_star).items():
        m = risk_metrics(apply_exposure(base, e))
        rows.append({"window": label, "candidate": name, "sigma_star": sigma_star, **m})
    return rows


def main() -> None:
    dataset = load_priced_dataset()
    prices = load_prices()
    rows, w3_model, w3_sigma = [], None, None

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
            feature_columns=tuple(ALL_19), params=DETERMINISTIC_PARAMS,
            early_stopping_metric="ic",
        )
        index = market_index(prices, val_end)
        assert index.index.max() < pd.Timestamp(TEST_START_DATE)
        sigma_star = sigma_star_from_train(realized_vol(index), TRAIN_START_DATE, train_end)
        print(f"{label}: best_iteration={trained.best_iteration}, sigma*={sigma_star:.1%}")
        rows += evaluate_block(label, splits.validation, trained, index, sigma_star)
        w3_model, w3_sigma = trained, sigma_star  # last window = W3 = frozen deploy model

    results = pd.DataFrame(rows)

    # --- report only: intraday dev segment with the frozen (W3) model -----------
    dev = select_segment(dataset, "dev", caller=CALLER, horizon=5)
    dev_rows = evaluate_block("DEV 2025-09~2026-06 (report only)", dev, w3_model, market_index(prices, DEV_END), w3_sigma)
    dev_results = pd.DataFrame(dev_rows)

    cols = ["candidate", "periods", "net_cum", "ann_return", "ann_vol", "sharpe", "mdd", "calmar",
            "hit_rate", "avg_exposure", "reduced_share", "change_cost_total"]
    for label, part in list(results.groupby("window", sort=False)) + [(dev_results["window"].iloc[0], dev_results)]:
        print("\n" + "=" * 118)
        print(f"{label}   (top_n={TOP_N}, buffer={BUFFER}, real costs)")
        print("=" * 118)
        print(f"{'cand':<6}{'n':>5}{'net_cum':>10}{'ann_ret':>9}{'ann_vol':>9}{'sharpe':>8}{'mdd':>9}"
              f"{'calmar':>8}{'hit':>7}{'avg_e':>7}{'e<1':>7}{'chg_cost':>10}")
        for r in part[cols].itertuples():
            print(f"{r.candidate:<6}{int(r.periods):>5}{r.net_cum:>10.1%}{r.ann_return:>9.1%}{r.ann_vol:>9.1%}"
                  f"{r.sharpe:>8.2f}{r.mdd:>9.1%}{r.calmar:>8.2f}{r.hit_rate:>7.1%}{r.avg_exposure:>7.2f}"
                  f"{r.reduced_share:>7.1%}{r.change_cost_total:>10.2%}")

    w3_r0 = results[(results["window"] == WINDOWS[-1][0]) & (results["candidate"] == "R0")]["net_cum"].iloc[0]
    match = abs(w3_r0 - EXPECTED_W3_R0) < 0.0015
    print(f"\nCross-check W3 R0 net_cum {w3_r0:+.1%} vs item 45/47 +65.0% -> {'MATCH' if match else 'MISMATCH'}")

    verdict = decide(results)
    print("\n" + "=" * 118)
    print("PRE-REGISTERED DECISION (item 55)")
    print("=" * 118)
    mdd = results.pivot(index="window", columns="candidate", values="mdd")
    cal = results.pivot(index="window", columns="candidate", values="calmar")
    for k in ("R2", "R1", "R3"):
        d = (mdd[k] - mdd["R0"]).map(lambda x: f"{x:+.1%}").tolist()
        c = [f"{a:.2f}/{b:.2f}" for a, b in zip(cal[k], cal["R0"])]
        print(f"{k}: MDD gain vs R0 {d} (need >= +{MDD_MARGIN:.0%}p all) | Calmar k/R0 {c} "
              f"| mean Calmar {verdict['mean_calmar'][k]:.2f} -> {'PASS' if verdict['passed'][k] else 'fail'}")
    print(f"=> ADOPT {verdict['adopt']}" + ("" if verdict["adopt"] != "R0" else "  (no candidate passed)"))
    if not match:
        print("WARNING: R0 does not reproduce item 45 -- fix the pipeline before reading the decision.")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    pd.concat([results, dev_results]).to_csv(OUT_DIR / "validation_results.csv", index=False)
    print(f"\nsaved {OUT_DIR / 'validation_results.csv'}")
    assert set(results["candidate"]) == set(CANDIDATES)


if __name__ == "__main__":
    main()
