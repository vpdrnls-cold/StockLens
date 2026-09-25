"""Entry timing IC comparison: close vs next-open (T-1 framing, Phase H).

기존 ml_dataset.csv 로 feature 별 cross-sectional rank IC 를 두 가지 target 에서 비교한다.
  close     : close(t+5) / close(t)   - 1   (기존 target_return_5d)
  next_open : close(t+5) / open(t+1)  - 1   (T-1 프레이밍, 실제로 체결 가능한 진입)

next_open target 은 ml_dataset.csv 만으로 계산된다:
  open(t+1) = close(t) × (1 + gap(t+1))  이므로
  next_open = (1 + target_close) / (1 + gap(t+1)) - 1

평가는 train / validation 만 사용한다 (test 는 보지 않음).
IC 는 raw 와 베타 중립(매일 label 을 rolling 베타로 회귀한 잔차) 둘 다 계산한다.
일봉 분해 feature 의 5일 집계(gap_sum_5, intraday_sum_5, range_mean_5)도 후보로 함께 본다.

사용 (저장소 루트에서):
    python scripts/entry_timing_ic.py
    python scripts/entry_timing_ic.py --dataset data/processed/ml_dataset.csv --min-stocks 5
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.data.dataset import (  # noqa: E402
    TARGET_COLUMN,
    TRAIN_END_DATE,
    TRAIN_START_DATE,
    VALIDATION_END_DATE,
    VALIDATION_START_DATE,
)
from src.features.engineering import SELECTED_FEATURES  # noqa: E402

DERIVED = ["gap_sum_5", "intraday_sum_5", "range_mean_5"]


def newey_west_t(x: np.ndarray, lag: int) -> float:
    x = x[~np.isnan(x)]
    n = len(x)
    if n < 10:
        return np.nan
    e = x - x.mean()
    v = (e @ e) / n
    for k in range(1, lag + 1):
        v += 2 * (1 - k / (lag + 1)) * (e[k:] @ e[:-k]) / n
    return float(x.mean() / np.sqrt(v / n)) if v > 0 else np.nan


def prepare(df: pd.DataFrame, beta_window: int) -> pd.DataFrame:
    df = df.sort_values(["stock_code", "trade_date"]).copy()
    g = df.groupby("stock_code", group_keys=False)

    # next-open target: 다음 행이 바로 다음 거래일이어야 함 (warm-up/끝 행만 빠지므로 성립)
    next_gap = g["gap"].shift(-1)
    df["target_close"] = df[TARGET_COLUMN]
    df["target_next_open"] = (1 + df[TARGET_COLUMN]) / (1 + next_gap) - 1

    # 일봉 분해 feature 의 5일 집계
    df["gap_sum_5"] = g["gap"].transform(lambda s: s.rolling(5).sum())
    df["intraday_sum_5"] = g["intraday_return"].transform(lambda s: s.rolling(5).sum())
    df["range_mean_5"] = g["high_low_range"].transform(lambda s: s.rolling(5).mean())

    # rolling 베타 (t 까지의 return_1d 만 사용)
    ret = df.pivot(index="trade_date", columns="stock_code", values="return_1d").sort_index()
    mkt = ret.mean(axis=1)
    mp = beta_window * 2 // 3
    beta = ret.rolling(beta_window, min_periods=mp).cov(mkt).div(
        mkt.rolling(beta_window, min_periods=mp).var(), axis=0)
    b = beta.stack(future_stack=True).rename("beta").reset_index()
    return df.merge(b, on=["trade_date", "stock_code"], how="left")


def daily_ic(df: pd.DataFrame, feats: list[str], label: str, min_stocks: int, neutral: bool) -> pd.DataFrame:
    rows = []
    for d, g in df.groupby("trade_date"):
        g = g[g[label].notna()]
        if neutral:
            g = g[g["beta"].notna()]
        if len(g) < min_stocks:
            continue
        y = g[label].values
        if neutral:
            X = np.column_stack([np.ones(len(g)), g["beta"].values])
            coef, *_ = np.linalg.lstsq(X, y, rcond=None)
            y = y - X @ coef
        yr = pd.Series(y, index=g.index).rank()
        rec = {"trade_date": d}
        for f in feats:
            x = g[f]
            m = x.notna()
            rec[f] = x[m].rank().corr(yr[m]) if m.sum() >= min_stocks else np.nan
        rows.append(rec)
    return pd.DataFrame(rows).set_index("trade_date")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dataset", default="data/processed/ml_dataset.csv")
    ap.add_argument("--out", default="reports/entry_timing_ic")
    ap.add_argument("--min-stocks", type=int, default=5)
    ap.add_argument("--beta-window", type=int, default=60)
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    df = pd.read_csv(args.dataset, dtype={"stock_code": str}, parse_dates=["trade_date"])
    print(f"데이터: {df['stock_code'].nunique()}종목, {df['trade_date'].min().date()} ~ {df['trade_date'].max().date()}")
    df = prepare(df, args.beta_window)

    feats = [f for f in SELECTED_FEATURES if f in df.columns] + DERIVED
    splits = {
        "train": (TRAIN_START_DATE, TRAIN_END_DATE),
        "validation": (VALIDATION_START_DATE, VALIDATION_END_DATE),
    }
    lag = 6  # 5일 target 겹침 보정

    tables = []
    for split, (s, e) in splits.items():
        part = df[(df["trade_date"] >= s) & (df["trade_date"] <= e)]
        cols = {}
        for label in ("target_close", "target_next_open"):
            short = "close" if label == "target_close" else "open"
            for neutral in (False, True):
                ic = daily_ic(part, feats, label, args.min_stocks, neutral)
                tag = f"{short}_{'bn' if neutral else 'raw'}"
                cols[f"ic_{tag}"] = ic.mean()
                cols[f"t_{tag}"] = pd.Series({f: newey_west_t(ic[f].values, lag) for f in feats})
        tbl = pd.DataFrame(cols).loc[feats]
        tbl.insert(0, "split", split)
        tables.append(tbl.reset_index(names="feature"))

        view = tbl[["ic_close_bn", "t_close_bn", "ic_open_bn", "t_open_bn", "ic_open_raw", "t_open_raw"]]
        view = view.reindex(view["t_open_bn"].abs().sort_values(ascending=False).index)
        pd.set_option("display.width", 200)
        print(f"\n=== {split} ({s} ~ {e}) | 베타 중립(bn) 기준, next-open |t| 순 ===")
        print(view.round(4).to_string())

    res = pd.concat(tables, ignore_index=True)
    res.to_csv(out / "entry_timing_ic.csv", index=False, encoding="utf-8-sig")

    # 요약: 진입 시점을 바꾸면 feature 순위가 얼마나 바뀌는가
    print("\n=== 요약: close vs next-open (베타 중립 IC) ===")
    for split in splits:
        r = res[res["split"] == split].dropna(subset=["ic_close_bn", "ic_open_bn"])
        rho = r["ic_close_bn"].rank().corr(r["ic_open_bn"].rank())
        flips = r[np.sign(r["ic_close_bn"]) != np.sign(r["ic_open_bn"])]["feature"].tolist()
        print(f"  {split}: feature IC 순위상관 {rho:.3f}, 부호가 바뀐 feature {flips}")
    print(f"\n결과 CSV: {out.resolve()}")


if __name__ == "__main__":
    main()
