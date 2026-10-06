"""Post-hoc diagnostics of the item 79 cross-sectional holdout, period P (CURRENT_STATUS item 81).

POST-HOC: item 79's verdict ("generalization supported") is already recorded and does
not change. These diagnostics were requested after seeing item 79's result (재훈,
2026-10-06) to understand why a positive IC came with a losing top-10 strategy. Their
definitions are fixed in item 81 before this script was first run. Nothing here is
evidence for a design choice: any idea it suggests must be pre-registered and tested on
the next cycle's dev / forward2. The 150 stocks' data up to 2026-09-16 were already
spent by item 79; this run reads the same rows again and nothing else (no forward, no
top50 test rows).

  A  score vs realized 5-day forward return: score deciles (per-date rank, ties averaged),
     top 10% / top 20% / bottom 10%, long-short (top 10% - bottom 10%), the engine's
     top-10 pick; raw and date-demeaned returns, no costs.
  B  buffer holdings (reported schedule, offset 0): per period held / kept / new / dropped,
     ranks of kept vs new, score change of kept names, holding lengths, net return of
     kept vs new positions.
  C  per-stock contribution (offset 0 and the 5-offset mean): sum over periods of
     weight * return, split into price move (exit/entry - 1) and costs; concentration.
  D  regime by 2023H2 / 2024 / 2025 / 2026: IC, buffered top-10 net, 150-stock equal
     weight (no costs), excess, entries per period, period and daily MDD (5-offset mean).

    STOCKLENS_UNIVERSE=top50 STOCKLENS_CONFIRM_FINAL_TEST=1 PYTHONPATH=. \\
        .venv/bin/python scripts/diagnose_cross_sectional_holdout.py
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from scripts import evaluate_cross_sectional_holdout as xh
from scripts import evaluate_forward_holdout as fh
from scripts.walk_forward_backtest_compare import universe_average_gross
from src.backtest.buffered import _build_held_timeline, run_buffered_backtest
from src.backtest.daily_equity import daily_max_drawdown, max_drawdown
from src.eval.test_lock import TestSetLockedError, confirm_final_test_use
from src.ml.cross_section import daily_rank_ic, summarize_ic
from src.ml.strategy import make_model_score_fn, predictions_for_dataset

CALLER = "diagnose_cross_sectional_holdout.py"
DEFAULT_OUT = "reports/cross_sectional_holdout/diagnostics"
N_BUCKETS = 10
SCORE = xh.SCORE_COL
TARGET = "target_return_5d"


# ---------------------------------------------------------------- A
def add_buckets(part: pd.DataFrame, n: int = N_BUCKETS) -> pd.DataFrame:
    """Per-date score bucket 1 (lowest) .. n (highest) from the average-tie percentile rank."""
    out = part.copy()
    pct = out.groupby("trade_date")[SCORE].rank(method="average", pct=True)
    out["bucket"] = np.ceil(pct * n).clip(1, n).astype(int)
    out["ret_dm"] = out[TARGET] - out.groupby("trade_date")[TARGET].transform("mean")
    return out


def engine_top_n(part: pd.DataFrame, top_n: int = 10) -> pd.Series:
    """True for the engine's plain top-n pick per date (score desc, ties -> lower code first)."""
    ordered = part.sort_values(["trade_date", SCORE, "stock_code"], ascending=[True, False, True])
    first = ordered.groupby("trade_date").cumcount() < top_n
    return first.reindex(part.index)


def nw_t(daily: pd.Series, horizon: int = xh.HORIZON) -> float:
    return xh.t_stat(daily, horizon)


def bucket_table(part: pd.DataFrame) -> pd.DataFrame:
    b = add_buckets(part)
    per_day = b.groupby(["trade_date", "bucket"]).agg(ret=(TARGET, "mean"), ret_dm=("ret_dm", "mean"), n=(TARGET, "size"))
    rows = []
    for k, g in per_day.groupby(level="bucket"):
        rows.append({"group": f"D{k}", "days": len(g), "stocks_per_day": g["n"].mean(),
                     "ret_5d": g["ret"].mean(), "ret_5d_demeaned": g["ret_dm"].mean(), "t_demeaned": nw_t(g["ret_dm"])})

    def grp(name, mask):
        g = b[mask].groupby("trade_date").agg(ret=(TARGET, "mean"), ret_dm=("ret_dm", "mean"), n=(TARGET, "size"))
        rows.append({"group": name, "days": len(g), "stocks_per_day": g["n"].mean(), "ret_5d": g["ret"].mean(),
                     "ret_5d_demeaned": g["ret_dm"].mean(), "t_demeaned": nw_t(g["ret_dm"])})
        return g

    top10 = grp("top10%", b["bucket"] == 10)
    grp("top20%", b["bucket"] >= 9)
    bot10 = grp("bottom10%", b["bucket"] == 1)
    grp("engine_top10", engine_top_n(b))
    grp("all", b["bucket"] >= 1)
    ls = (top10["ret"] - bot10["ret"]).dropna()
    rows.append({"group": "long_short(top10%-bottom10%)", "days": len(ls), "ret_5d": ls.mean(), "t_demeaned": nw_t(ls)})
    return pd.DataFrame(rows)


def distinct_scores(part: pd.DataFrame) -> float:
    return float(part.groupby("trade_date")[SCORE].nunique().mean())


# ---------------------------------------------------------------- B
def holdings_table(part: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    data = fh._to_data_by_stock(part)
    scores = part[["trade_date", "stock_code", SCORE]].rename(columns={SCORE: "predicted_return"})
    _, _, held, carried, meta, _, _ = _build_held_timeline(data, fh.BUFFERED_CONFIG, make_model_score_fn(scores), fh.TOP_N)
    trades = pd.DataFrame([t.__dict__ for t in run_buffered_backtest(data, fh.BUFFERED_CONFIG, make_model_score_fn(scores), fh.TOP_N)])
    trades["decision_date"] = pd.to_datetime(trades["decision_date"])
    rows, prev, entry_score, age = [], set(), {}, {}
    lengths = []
    for j, m in enumerate(meta):
        if m is None:
            prev = set()
            continue
        h, c = held[j], carried[j]
        new, dropped = h - c, prev - h
        for s in dropped:
            lengths.append(age.pop(s))
        for s in new:
            entry_score[s], age[s] = m["scores"][s], 1
        for s in c:
            age[s] += 1
        tr = trades[trades["decision_date"] == pd.Timestamp(m["decision_date"])].set_index("stock_code")
        rows.append({
            "decision_date": m["decision_date"], "held": len(h), "kept": len(c), "new": len(new), "dropped": len(dropped),
            "rank_kept_mean": np.mean([m["rank_of"][s] for s in c]) if c else np.nan,
            "rank_new_mean": np.mean([m["rank_of"][s] for s in new]) if new else np.nan,
            "score_change_kept": np.mean([m["scores"][s] - entry_score[s] for s in c]) if c else np.nan,
            "net_kept": tr.loc[sorted(c), "net_return"].mean() if c else np.nan,
            "net_new": tr.loc[sorted(new), "net_return"].mean() if new else np.nan,
            "n_universe": len(m["rank_of"]),
        })
        prev = h
    lengths.extend(age.values())
    per = pd.DataFrame(rows)
    summary = pd.DataFrame([{
        "periods": len(per), "held": per["held"].mean(), "kept": per["kept"].mean(), "new": per["new"].mean(),
        "dropped": per["dropped"].mean(), "replacements_total": int(per["new"].sum()),
        "rank_kept_mean": per["rank_kept_mean"].mean(), "rank_new_mean": per["rank_new_mean"].mean(),
        "score_change_kept": per["score_change_kept"].mean(),
        "net_kept_mean": per["net_kept"].mean(), "net_new_mean": per["net_new"].mean(),
        "holding_periods_median": float(np.median(lengths)), "holding_periods_mean": float(np.mean(lengths)),
        "holding_1_period_share": float(np.mean(np.array(lengths) == 1)),
    }])
    return per, summary


# ---------------------------------------------------------------- C, D
def offset_trades(part: pd.DataFrame, offset: int) -> tuple[pd.DataFrame, dict, list, pd.Series]:
    sub = fh.phase_offset_part(part, offset)
    data = fh._to_data_by_stock(sub)
    scores = sub[["trade_date", "stock_code", SCORE]].rename(columns={SCORE: "predicted_return"})
    tl = run_buffered_backtest(data, fh.BUFFERED_CONFIG, make_model_score_fn(scores), fh.TOP_N)
    df = pd.DataFrame([t.__dict__ for t in tl])
    df["decision_date"] = pd.to_datetime(df["decision_date"])
    df["price_move"] = df["exit_price"] / df["entry_price"] - 1.0
    df["cost"] = df["price_move"] - df["net_return"]
    bench = universe_average_gross(data)
    bench.index = pd.to_datetime(bench.index)
    return df, data, tl, bench


def contribution_table(df: pd.DataFrame, names: dict[str, str]) -> tuple[pd.DataFrame, dict]:
    df = df.assign(c_net=df["weight"] * df["net_return"], c_move=df["weight"] * df["price_move"], c_cost=df["weight"] * df["cost"])
    per = df.groupby("stock_code").agg(periods=("net_return", "size"), contrib_net=("c_net", "sum"),
                                       contrib_move=("c_move", "sum"), contrib_cost=("c_cost", "sum"),
                                       mean_net=("net_return", "mean")).sort_values("contrib_net")
    per.insert(0, "name", [names.get(c, "") for c in per.index])
    total = float(per["contrib_net"].sum())
    neg = per.loc[per["contrib_net"] < 0, "contrib_net"]
    stats = {
        "stocks_held": int(len(per)), "sum_contrib_net": total, "sum_contrib_move": float(per["contrib_move"].sum()),
        "sum_contrib_cost": float(per["contrib_cost"].sum()),
        "stocks_negative": int((per["contrib_net"] < 0).sum()), "stocks_positive": int((per["contrib_net"] > 0).sum()),
        "worst5_contrib": float(per["contrib_net"].head(5).sum()), "best5_contrib": float(per["contrib_net"].tail(5).sum()),
        "worst5_share_of_losses": float(per["contrib_net"].head(5).sum() / neg.sum()) if len(neg) else np.nan,
        "sum_without_worst5": float(per["contrib_net"].iloc[5:].sum()),
        "positions_negative_share": float((df["net_return"] < 0).mean()),
    }
    return per, stats


def regime_label(dates: pd.Series) -> pd.Series:
    d = pd.to_datetime(dates)
    return pd.Series(np.where(d.dt.year == 2023, "2023H2", d.dt.year.astype(str)), index=dates.index)


def regime_rows(df: pd.DataFrame, data: dict, tl: list, bench: pd.Series, ic: pd.Series) -> pd.DataFrame:
    df = df.copy()
    df["regime"] = regime_label(df["decision_date"])
    period_ret = (df["weight"] * df["net_return"]).groupby([df["regime"], df["decision_date"]]).sum()
    bench_r = regime_label(bench.index.to_series()).to_numpy()
    ic_r = regime_label(ic.index.to_series()).to_numpy()
    tl_r = regime_label(pd.Series([pd.Timestamp(t.decision_date) for t in tl])).to_numpy()
    rows = []
    for r in sorted(df["regime"].unique()):
        eq = (1.0 + period_ret.loc[r]).cumprod()
        top10 = float(eq.iloc[-1] - 1.0)
        bench_cum = float((1.0 + bench[bench_r == r]).prod() - 1.0)
        rows.append({
            "regime": r, "ic": summarize_ic(ic[ic_r == r]).mean_ic, "periods": int(len(eq)),
            "top10_net": top10, "bench_ew_gross": bench_cum, "excess": top10 - bench_cum,
            "mdd_period": max_drawdown(eq),
            "mdd_daily": daily_max_drawdown([t for t, x in zip(tl, tl_r) if x == r], data),
        })
    return pd.DataFrame(rows)


def regime_turnover(part: pd.DataFrame, offset: int) -> pd.Series:
    sub = fh.phase_offset_part(part, offset)
    data = fh._to_data_by_stock(sub)
    scores = sub[["trade_date", "stock_code", SCORE]].rename(columns={SCORE: "predicted_return"})
    _, _, held, carried, meta, _, _ = _build_held_timeline(data, fh.BUFFERED_CONFIG, make_model_score_fn(scores), fh.TOP_N)
    rows = [(m["decision_date"], len(held[j] - carried[j])) for j, m in enumerate(meta) if m is not None]
    s = pd.Series([n for _, n in rows], index=pd.to_datetime([d for d, _ in rows]))
    return s.groupby(regime_label(s.index.to_series()).values).mean()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=DEFAULT_OUT)
    args = ap.parse_args(argv)
    out = Path(args.out)

    if set(xh.STOCK_CODES) != set(xh.get_universe("top50")):
        print("STOP: run with STOCKLENS_UNIVERSE=top50. Nothing was read.")
        return 2
    trained, _ = xh.train_frozen_model(xh._load_priced_dataset())
    if not fh.frozen_model_ok(trained.best_iteration, xh.frozen_model_fingerprint(trained)):
        print("STOP: not the pre-registered frozen model. The extra stocks were NOT read.")
        return 4
    try:
        confirm_final_test_use(CALLER)
    except TestSetLockedError as locked:
        print(f"STOP: {locked}\nThe extra stocks were NOT read.")
        return 5

    codes = xh.holdout_codes()
    names = {s.code: s.name for s in xh.load_universe_file(xh.KOSPI200_UNIVERSE_PATH)}
    dataset, _ = xh.load_holdout_dataset(codes)
    preds = predictions_for_dataset(trained, dataset).rename(columns={"predicted_return": SCORE})
    df = dataset.merge(preds, on=["trade_date", "stock_code"], how="left")
    name, start, end, _ = xh.PERIODS[0]
    part, _ = xh.eligible(xh.period_rows(df, start, end))
    ic = daily_rank_ic(part, SCORE, TARGET)

    a = bucket_table(part)
    b_per, b_sum = holdings_table(part)
    c_tables, c_stats, d_tables = [], [], []
    for k in fh.PHASE_OFFSETS:
        tdf, data, tl, bench = offset_trades(part, k)
        per, st = contribution_table(tdf, names)
        c_tables.append(per.assign(offset=k))
        c_stats.append({"offset": k, **st})
        d = regime_rows(tdf, data, tl, bench, ic)
        d["entries_per_period"] = d["regime"].map(regime_turnover(part, k))
        d_tables.append(d.assign(offset=k))
    c0 = c_tables[0].drop(columns="offset")
    c_stats = pd.DataFrame(c_stats)
    d_all = pd.concat(d_tables, ignore_index=True)
    d_mean = d_all.drop(columns="offset").groupby("regime").mean(numeric_only=True)

    out.mkdir(parents=True, exist_ok=True)
    a.to_csv(out / "A_score_buckets.csv", index=False, encoding="utf-8-sig")
    b_per.to_csv(out / "B_holdings_by_period.csv", index=False, encoding="utf-8-sig")
    b_sum.to_csv(out / "B_holdings_summary.csv", index=False, encoding="utf-8-sig")
    pd.concat(c_tables).to_csv(out / "C_contribution_by_stock.csv", encoding="utf-8-sig")
    c_stats.to_csv(out / "C_contribution_summary.csv", index=False, encoding="utf-8-sig")
    d_all.to_csv(out / "D_regime_by_offset.csv", index=False, encoding="utf-8-sig")

    f = lambda x: f"{x:+.4f}"  # noqa: E731
    print("=" * 100)
    print(f"POST-HOC DIAGNOSTICS (item 81) -- period P {part['trade_date'].min():%Y-%m-%d} ~ "
          f"{part['trade_date'].max():%Y-%m-%d}, {part['stock_code'].nunique()} stocks. Not evidence; see item 81.")
    print("=" * 100)
    print(f"\n[A] score vs 5-day forward return (no costs). distinct scores per date: {distinct_scores(part):.1f}")
    print(a.to_string(index=False, float_format=f))
    print("\n[B] buffer holdings, reported schedule (offset 0)")
    print(b_sum.T.to_string(header=False, float_format=f))
    print("\n[C] per-stock contribution, offset 0 -- worst 10 / best 5")
    print(c0.head(10).to_string(float_format=f))
    print(c0.tail(5).to_string(float_format=f))
    print("\n[C] concentration by offset")
    print(c_stats.to_string(index=False, float_format=f))
    print("\n[D] regime, mean over 5 start offsets")
    print(d_mean.to_string(float_format=f))
    print(f"\nsaved: {out}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
