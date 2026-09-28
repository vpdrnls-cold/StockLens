"""Intraday overlay on the frozen daily model -- dev segment only (item 46: I1-I4).

Everything below was fixed in CURRENT_STATUS item 46 BEFORE this script ran:

  I1  features (intraday-only, sign fixed from the 2026-09-24 diagnostic):
        vshare_auction (+), vshare_open30 (-), vshare_late (+), rv_intraday (-)
  I2  intraday score, no fitting: per date, z-score each feature across stocks,
      multiply by its sign, average (needs >= 3 of 4), z-score the average again.
  I3  overlay: score = z(daily ML) + w * z(intraday), w in {0, 0.25, 0.5}.
      A stock-day without an intraday score gets z(intraday) = 0 (neutral), so
      every w is evaluated on exactly the same rows.
  I4  decision (primary metric = daily rank IC vs the raw 5-day target,
      close(T+5)/open(T+1)-1): a w > 0 passes only if its IC beats w = 0 in ALL
      three dev blocks B1 (2025-09~12), B2 (2026-01~03), B3 (2026-04~06). Among
      passing w, adopt the one with the highest IC over the whole dev segment.
      If none passes, stop the intraday overlay (daily alone stays).
      Beta-neutral IC and the buffered backtest are reported for information
      only -- they do not enter the decision.

Timing (item 46, option A): features use day T's whole regular session (T is
final at 20:00 KST); entry at T+1's open. Labels come from the daily dataset
(adjusted prices), the same target the daily model and backtest use. Segments
come from src.data.intraday_split, which purges labels that cross a block end.
Only dev dates are read -- semi_holdout and forward stay locked.

Daily model: the frozen model of scripts/run_ml_backtest.py (train 2002-2019,
early stopping 2020-2023H1); 2025-09 onward is out-of-sample for it.

    # rebuild the intraday panel from data/raw/kiwoom/ka10080 (default)
    STOCKLENS_UNIVERSE=top50 PYTHONPATH=. python scripts/experiment_intraday_overlay_dev.py
    # or reuse the panel saved by scripts/intraday_ic_diagnostic.py
    STOCKLENS_UNIVERSE=top50 PYTHONPATH=. python scripts/experiment_intraday_overlay_dev.py \\
        --panel reports/intraday_ic/features_panel.csv
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from scripts.intraday_ic_diagnostic import build_panel
from scripts.run_ml_backtest import (
    BUFFERED_CONFIG,
    TOP_N,
    _load_priced_dataset,
    _to_data_by_stock,
    train_frozen_model,
)
from src.backtest.baseline import calculate_performance
from src.backtest.buffered import BufferedBaselineConfig, run_buffered_backtest_with_turnover
from src.data.intraday_split import DEV_BLOCKS, select_segment
from src.ml.cross_section import daily_rank_ic, summarize_ic
from src.ml.strategy import make_model_score_fn, predictions_for_dataset
from scripts.walk_forward_backtest_compare import universe_average_gross

# Same engine and buffer with every cost set to zero -> gross return (information only).
GROSS_BUFFERED_CONFIG = BufferedBaselineConfig(
    **{f: getattr(BUFFERED_CONFIG, f) for f in BUFFERED_CONFIG.__dataclass_fields__
       if f not in ("buy_fee", "sell_fee", "sell_tax", "buy_slippage", "sell_slippage")},
    buy_fee=0.0, sell_fee=0.0, sell_tax=0.0, buy_slippage=0.0, sell_slippage=0.0,
)

FEATURE_SIGNS = {
    "vshare_auction": +1.0,
    "vshare_open30": -1.0,
    "vshare_late": +1.0,
    "rv_intraday": -1.0,
}
MIN_FEATURES = 3
WEIGHTS = (0.0, 0.25, 0.5)
SEGMENTS = ["dev"] + [b.name for b in DEV_BLOCKS]
BETA_WINDOW = 60
CALLER = "experiment_intraday_overlay_dev.py"


def zscore_by_date(df: pd.DataFrame, col: str) -> pd.Series:
    g = df.groupby("trade_date")[col]
    std = g.transform("std")
    z = (df[col] - g.transform("mean")) / std
    return z.where(std > 0)


def load_intraday_panel(panel_path: str | None, minute_dir: str) -> pd.DataFrame:
    if panel_path:
        panel = pd.read_csv(panel_path, dtype={"code": str}, encoding="utf-8-sig")
        if "_valid" in panel.columns:
            panel = panel[panel["_valid"].astype(bool)]
    else:
        panel = build_panel(Path(minute_dir))
        panel = panel[panel["_valid"]]
    panel = panel.rename(columns={"code": "stock_code", "date": "trade_date"})
    panel["stock_code"] = panel["stock_code"].str.zfill(6)
    panel["trade_date"] = pd.to_datetime(panel["trade_date"])
    return panel[["stock_code", "trade_date", *FEATURE_SIGNS]]


def add_beta(dataset: pd.DataFrame) -> pd.DataFrame:
    """Rolling 60-day beta to the equal-weight universe, using returns up to T only."""
    close = dataset.pivot(index="trade_date", columns="stock_code", values="close_price").sort_index()
    ret = close.pct_change(fill_method=None)
    mkt = ret.mean(axis=1)
    mp = BETA_WINDOW * 2 // 3
    beta = ret.rolling(BETA_WINDOW, min_periods=mp).cov(mkt).div(
        mkt.rolling(BETA_WINDOW, min_periods=mp).var(), axis=0
    )
    b = beta.stack(future_stack=True).rename("beta").reset_index()
    return dataset.merge(b, on=["trade_date", "stock_code"], how="left")


def beta_neutral_target(df: pd.DataFrame) -> pd.Series:
    """Per-date OLS residual of target_return_5d on [1, beta] (secondary metric only)."""
    out = pd.Series(np.nan, index=df.index)
    for _, g in df.groupby("trade_date"):
        g = g.dropna(subset=["target_return_5d", "beta"])
        if len(g) < 10:
            continue
        X = np.column_stack([np.ones(len(g)), g["beta"].to_numpy()])
        y = g["target_return_5d"].to_numpy()
        coef, *_ = np.linalg.lstsq(X, y, rcond=None)
        out.loc[g.index] = y - X @ coef
    return out


def build_scores(dataset: pd.DataFrame, panel: pd.DataFrame, trained) -> pd.DataFrame:
    # I1/I2: intraday score (no fitting)
    p = panel.copy()
    zs = []
    for f, sign in FEATURE_SIGNS.items():
        p[f"_z_{f}"] = sign * zscore_by_date(p, f)
        zs.append(f"_z_{f}")
    enough = p[zs].notna().sum(axis=1) >= MIN_FEATURES
    p["_intraday_raw"] = p[zs].mean(axis=1).where(enough)
    p["z_intraday"] = zscore_by_date(p, "_intraday_raw")

    # frozen daily model score
    preds = predictions_for_dataset(trained, dataset)
    df = dataset.merge(preds, on=["trade_date", "stock_code"], how="left")
    df["z_daily"] = zscore_by_date(df, "predicted_return").fillna(0.0)
    df = df.merge(p[["trade_date", "stock_code", "z_intraday"]], on=["trade_date", "stock_code"], how="left")
    df["has_intraday"] = df["z_intraday"].notna()
    df["z_intraday"] = df["z_intraday"].fillna(0.0)

    # I3: overlay scores
    for w in WEIGHTS:
        df[f"score_w{w}"] = df["z_daily"] + w * df["z_intraday"]
    return df


def evaluate(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for seg in SEGMENTS:
        part = select_segment(df, seg, caller=CALLER, horizon=5)
        part = part.dropna(subset=["target_return_5d"]).copy()
        part["target_bn"] = beta_neutral_target(part)
        data_by_stock = _to_data_by_stock(part)
        # equal-weight universe, same decision grid, no costs: the long-only bar to beat
        univ_cum = float((1.0 + universe_average_gross(data_by_stock)).prod() - 1.0)
        for w in WEIGHTS:
            col = f"score_w{w}"
            ic = summarize_ic(daily_rank_ic(part, col, "target_return_5d"))
            ic_bn = summarize_ic(daily_rank_ic(part.dropna(subset=["target_bn"]), col, "target_bn"))
            scores = part[["trade_date", "stock_code", col]].rename(columns={col: "predicted_return"})
            score_fn = make_model_score_fn(scores)
            net_trades, turnover = run_buffered_backtest_with_turnover(
                data_by_stock, BUFFERED_CONFIG, score_fn=score_fn, top_n=TOP_N
            )
            gross_trades, _ = run_buffered_backtest_with_turnover(
                data_by_stock, GROSS_BUFFERED_CONFIG, score_fn=score_fn, top_n=TOP_N
            )
            perf = calculate_performance(net_trades)
            gross_cum = calculate_performance(gross_trades)["total_return"]
            rows.append({
                "segment": seg, "w": w,
                "start": part["trade_date"].min(), "end": part["trade_date"].max(),
                "days": ic.n_days, "intraday_cov": part["has_intraday"].mean(),
                "ic": ic.mean_ic, "ic_pos": ic.pct_pos, "ic_bn": ic_bn.mean_ic,
                "buf_gross_cum": gross_cum, "univ_ew_cum": univ_cum,
                "entries": turnover["entries_per_period"],
                "buf_net_cum": perf["total_return"], "buf_mdd": perf["max_drawdown"],
                "periods": int(perf["period_count"]),
            })
    return pd.DataFrame(rows)


def decide(res: pd.DataFrame) -> tuple[float | None, pd.DataFrame]:
    wide = res.pivot(index="segment", columns="w", values="ic")
    blocks = [b.name for b in DEV_BLOCKS]
    passing = [w for w in WEIGHTS if w > 0 and all(wide.loc[b, w] > wide.loc[b, 0.0] for b in blocks)]
    chosen = max(passing, key=lambda w: wide.loc["dev", w]) if passing else None
    return chosen, wide


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--panel", default=None, help="saved features_panel.csv (default: rebuild from raw)")
    ap.add_argument("--minute-dir", default="data/raw/kiwoom/ka10080")
    ap.add_argument("--out", default="reports/intraday_overlay")
    args = ap.parse_args()

    dataset = add_beta(_load_priced_dataset())
    print("=== frozen daily model ===")
    trained, _ = train_frozen_model(dataset)
    print(f"best_iteration={trained.best_iteration}")

    print("=== intraday panel ===")
    panel = load_intraday_panel(args.panel, args.minute_dir)
    print(f"{panel['stock_code'].nunique()} stocks, {panel['trade_date'].nunique()} days, "
          f"{panel['trade_date'].min():%Y-%m-%d} ~ {panel['trade_date'].max():%Y-%m-%d}")

    df = build_scores(dataset, panel, trained)
    res = evaluate(df)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    res.to_csv(out / "dev_results.csv", index=False, encoding="utf-8-sig")

    print("\n" + "=" * 110)
    print(f"DEV SEGMENT RESULTS   (score = z(daily) + w*z(intraday); top_n={TOP_N}, buffer=3.0, real costs)")
    print("=" * 110)
    print(f"{'segment':<8}{'w':>6}{'period':>25}{'days':>6}{'cov':>7}{'IC':>9}{'IC>0':>7}"
          f"{'IC_bn':>9}{'gross':>9}{'net':>9}{'mdd':>8}{'univEW':>8}{'entries':>8}")
    for r in res.itertuples():
        print(f"{r.segment:<8}{r.w:>6.2f}{f'{r.start:%Y-%m-%d}~{r.end:%Y-%m-%d}':>25}{r.days:>6}"
              f"{r.intraday_cov:>7.1%}{r.ic:>+9.4f}{r.ic_pos:>7.1%}{r.ic_bn:>+9.4f}"
              f"{r.buf_gross_cum:>9.1%}{r.buf_net_cum:>9.1%}{r.buf_mdd:>8.1%}{r.univ_ew_cum:>8.1%}{r.entries:>8.2f}")
    print("gross/net/mdd: buffered top-10 backtest (info only). univEW: equal-weight universe, no costs.")

    chosen, wide = decide(res)
    print("\n" + "=" * 110)
    print("PRE-REGISTERED DECISION (I4): w > 0 must beat w = 0 on IC in B1, B2 and B3")
    print("=" * 110)
    for w in WEIGHTS[1:]:
        diffs = "  ".join(f"{b.name} {wide.loc[b.name, w] - wide.loc[b.name, 0.0]:+.4f}" for b in DEV_BLOCKS)
        ok = all(wide.loc[b.name, w] > wide.loc[b.name, 0.0] for b in DEV_BLOCKS)
        print(f"w={w:<5} IC diff vs w=0:  {diffs}   dev {wide.loc['dev', w] - wide.loc['dev', 0.0]:+.4f}"
              f"   -> {'PASS' if ok else 'fail'}")
    if chosen is None:
        print("=> STOP: no w passes. Keep the daily model alone; skip I5.")
    else:
        print(f"=> CANDIDATE w={chosen}. Next: I5 (semi_holdout sign check, once).")
    print(f"\nsaved: {out / 'dev_results.csv'}")


if __name__ == "__main__":
    main()
