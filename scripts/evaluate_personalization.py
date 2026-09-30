"""Profile re-ranking on the validation windows (CURRENT_STATUS item 56, pre-registered).

Question
  After moving every term to the unit-free per-date standardized-rank scale
  and calibrating each profile's tilt strength on TRAIN so that it keeps a
  mean rank correlation of 0.8 with the model ranking: do the profiles
  (1) behave in the intended direction and (2) keep the model signal?
  This is NOT an attempt to beat anything on return -- profile return
  differences are risk preferences, not better/worse.

Profiles (fixed in item 56, src/recommendation/scoring.py)
  conservative  penalize volatility_20
  neutral       model ranking unchanged (lambda = 0)
  aggressive    reward volatility_20 + unusual volume_ratio_20 (no momentum)

Setup
  Walk-forward W1 (2012-2015), W2 (2016-2019), W3 (2020-2023H1); same model
  as items 45/55 (A_all19, rank target, IC early stopping, entry next_open);
  deploy engine (top-10, buffer 3.0, real costs). Lambda per profile from
  that window's TRAIN rows only (in-sample model scores; no returns used).
  Intraday dev (2025-09~2026-06, W3 model and lambda) is REPORTED ONLY.
  test / semi_holdout / forward are never read.

Decision (pre-registered, all 3 windows)
  conservative passes iff  hold_vol(cons) < hold_vol(neutral)
                           AND period-return std(cons) < std(neutral)
                           AND model rank corr >= 0.7 AND IC >= 0
  aggressive passes iff    hold_vol(aggr) > hold_vol(neutral)
                           AND model rank corr >= 0.7 AND IC >= 0
  hold_vol = mean volatility_20 of the held stocks over all periods.

Cross-check: neutral in W3 must reproduce item 45/47 ml_buffered (+65.0%).

    STOCKLENS_UNIVERSE=top50 PYTHONPATH=. python scripts/evaluate_personalization.py
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from scripts.walk_forward_backtest_compare import (
    ALL_19,
    DETERMINISTIC_PARAMS,
    NET_CONFIG,
    WINDOWS,
    load_priced_dataset,
    to_data_by_stock,
)
from src.backtest.baseline import calculate_performance, trades_to_dataframe
from src.backtest.buffered import BufferedBaselineConfig, run_buffered_backtest_with_turnover
from src.data.dataset import TEST_END_DATE, TEST_START_DATE, TRAIN_START_DATE, split_by_time
from src.data.intraday_split import select_segment
from src.ml.cross_section import daily_rank_ic, rank_by_date, summarize_ic
from src.ml.strategy import predictions_for_dataset
from src.models.predict import train_model
from src.portfolio.risk_overlay import PERIODS_PER_YEAR, period_returns
from src.recommendation.scoring import (
    PROFILES,
    calibrate_lambda,
    make_profile_score_fn,
    mean_rank_corr,
    personalize_scores,
)

TOP_N = 10
BUFFER = 3.0
BUFFERED_NET_CONFIG = BufferedBaselineConfig(
    **{f: getattr(NET_CONFIG, f) for f in NET_CONFIG.__dataclass_fields__},
    buffer_multiplier=BUFFER,
)
MIN_MODEL_CORR = 0.7
MIN_IC = 0.0
EXPECTED_W3_NEUTRAL = 0.650  # item 45 / 47
SIGNAL_COLUMNS = ["trade_date", "stock_code", "volatility_20", "price_to_sma_5", "volume_ratio_20"]
OUT_DIR = Path("reports/personalization")
CALLER = "evaluate_personalization.py"


def signals_for(trained, rows: pd.DataFrame) -> pd.DataFrame:
    preds = predictions_for_dataset(trained, rows)
    sig = rows[SIGNAL_COLUMNS + ["target_return_5d"]].copy()
    sig["trade_date"] = pd.to_datetime(sig["trade_date"])
    return sig.merge(preds, on=["trade_date", "stock_code"], validate="one_to_one")


def top_sets(scored: pd.DataFrame, col: str, n: int = TOP_N) -> pd.Series:
    ordered = scored.sort_values(["trade_date", col, "stock_code"], ascending=[True, False, True])
    return ordered.groupby("trade_date")["stock_code"].apply(lambda s: set(s.head(n)))


def evaluate_block(label: str, period: pd.DataFrame, trained, lambdas: dict[str, float]) -> list[dict]:
    sig = signals_for(trained, period)
    data_by_stock = to_data_by_stock(period)
    vol_lookup = sig.set_index(["trade_date", "stock_code"])["volatility_20"]
    neutral_top = None
    rows = []
    for name in PROFILES:
        scored = personalize_scores(sig, name, lam=lambdas[name])
        trades, turnover = run_buffered_backtest_with_turnover(
            data_by_stock, BUFFERED_NET_CONFIG, score_fn=make_profile_score_fn(scored), top_n=TOP_N
        )
        perf = calculate_performance(trades)
        pr = period_returns(trades)
        tdf = trades_to_dataframe(trades)
        keys = list(zip(pd.to_datetime(tdf["decision_date"]), tdf["stock_code"]))
        hold_vol = float(vol_lookup.reindex(keys).mean())
        std = float(pr.std(ddof=1))
        ic = summarize_ic(daily_rank_ic(scored.dropna(subset=["target_return_5d"]), "personalized_score"))
        tops = top_sets(scored, "personalized_score")
        if name == "neutral":
            neutral_top = tops
        rows.append({
            "window": label,
            "profile": name,
            "lambda": lambdas[name],
            "net_cum": perf["total_return"],
            "sharpe": float(pr.mean() / std * np.sqrt(PERIODS_PER_YEAR)) if std > 0 else float("nan"),
            "mdd": perf["max_drawdown"],
            "hit_rate": perf["win_rate"],
            "period_std": std,
            "hold_vol": hold_vol,
            "ic": ic.mean_ic,
            "model_corr": mean_rank_corr(scored["personalized_score"], scored["predicted_return"], scored["trade_date"]),
            "entries_per_period": turnover["entries_per_period"],
            "_tops": tops,
        })
    for r in rows:
        common = r["_tops"].index.intersection(neutral_top.index)
        r["top10_overlap"] = float(np.mean([len(r["_tops"][d] & neutral_top[d]) / TOP_N for d in common]))
        del r["_tops"]
    return rows


def decide(results: pd.DataFrame) -> dict[str, bool]:
    w = {k: results.pivot(index="window", columns="profile", values=k)
         for k in ("hold_vol", "period_std", "model_corr", "ic")}
    keep = lambda p: bool(((w["model_corr"][p] >= MIN_MODEL_CORR) & (w["ic"][p] >= MIN_IC)).all())
    return {
        "conservative": bool(
            (w["hold_vol"]["conservative"] < w["hold_vol"]["neutral"]).all()
            and (w["period_std"]["conservative"] < w["period_std"]["neutral"]).all()
            and keep("conservative")
        ),
        "aggressive": bool((w["hold_vol"]["aggressive"] > w["hold_vol"]["neutral"]).all() and keep("aggressive")),
    }


def main() -> None:
    dataset = load_priced_dataset()
    rows, w3 = [], None
    for label, train_end, val_start, val_end in WINDOWS:
        assert pd.Timestamp(val_end) < pd.Timestamp(TEST_START_DATE)
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
        train_sig = signals_for(trained, splits.train).drop(columns=["target_return_5d"])  # no outcomes
        lambdas = {name: calibrate_lambda(train_sig, name) for name in PROFILES}
        print(f"{label}: best_iteration={trained.best_iteration}, "
              + ", ".join(f"lambda[{k}]={v:.3f}" for k, v in lambdas.items()))
        rows += evaluate_block(label, splits.validation, trained, lambdas)
        w3 = (trained, lambdas)

    results = pd.DataFrame(rows)
    dev = select_segment(dataset, "dev", caller=CALLER, horizon=5)
    dev_results = pd.DataFrame(evaluate_block("DEV 2025-09~2026-06 (report only)", dev, *w3))

    for label, part in list(results.groupby("window", sort=False)) + [(dev_results["window"].iloc[0], dev_results)]:
        print("\n" + "=" * 124)
        print(f"{label}   (top_n={TOP_N}, buffer={BUFFER}, real costs)")
        print("=" * 124)
        print(f"{'profile':<14}{'lambda':>7}{'net_cum':>10}{'sharpe':>8}{'mdd':>9}{'hit':>7}{'std/5d':>9}"
              f"{'hold_vol':>10}{'IC':>9}{'corr_m':>8}{'top10∩N':>9}{'entries':>9}")
        for r in part.itertuples():
            print(f"{r.profile:<14}{r._3:>7.3f}{r.net_cum:>10.1%}{r.sharpe:>8.2f}{r.mdd:>9.1%}{r.hit_rate:>7.1%}"
                  f"{r.period_std:>9.2%}{r.hold_vol:>10.4f}{r.ic:>+9.4f}{r.model_corr:>8.2f}"
                  f"{r.top10_overlap:>9.0%}{r.entries_per_period:>9.2f}")

    w3_neutral = results[(results["window"] == WINDOWS[-1][0]) & (results["profile"] == "neutral")]["net_cum"].iloc[0]
    match = abs(w3_neutral - EXPECTED_W3_NEUTRAL) < 0.0015
    print(f"\nCross-check W3 neutral net_cum {w3_neutral:+.1%} vs item 45/47 +65.0% -> {'MATCH' if match else 'MISMATCH'}")

    verdict = decide(results)
    print("\n" + "=" * 124)
    print("PRE-REGISTERED DECISION (item 56)")
    print("=" * 124)
    piv = {k: results.pivot(index="window", columns="profile", values=k) for k in ("hold_vol", "period_std", "model_corr", "ic")}
    for p in ("conservative", "aggressive"):
        hv = [f"{a:.4f}/{b:.4f}" for a, b in zip(piv["hold_vol"][p], piv["hold_vol"]["neutral"])]
        sd = [f"{a:.2%}/{b:.2%}" for a, b in zip(piv["period_std"][p], piv["period_std"]["neutral"])]
        print(f"{p}: hold_vol p/neutral {hv} | std p/neutral {sd} | model corr "
              f"{[round(x, 2) for x in piv['model_corr'][p]]} (>= {MIN_MODEL_CORR}) | IC "
              f"{[round(x, 4) for x in piv['ic'][p]]} (>= 0) -> {'PASS' if verdict[p] else 'fail'}")
    print("(conservative also needs std below neutral in every window; aggressive has no std condition)")
    enabled = ["neutral"] + [p for p, ok in verdict.items() if ok]
    print(f"=> profiles enabled for recommend.py: {enabled}")
    if not match:
        print("WARNING: neutral does not reproduce item 45 -- fix the pipeline before reading the decision.")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    pd.concat([results, dev_results]).to_csv(OUT_DIR / "validation_results.csv", index=False)
    print(f"\nsaved {OUT_DIR / 'validation_results.csv'}")


if __name__ == "__main__":
    main()
