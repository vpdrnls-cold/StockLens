"""Intraday IC robustness checks (Phase H).

scripts/intraday_ic_diagnostic.py 가 만든 reports/intraday_ic/features_panel.csv 를 읽어
1차 결과(1일 뒤 반전·변동성·종가 단일가 비중 신호)가 진짜인지 네 가지로 점검한다.

  A. 시장 상승일/하락일 분리 IC  : 변동성 신호가 베타(시장 방향) 때문인지
  B. 베타 중립 IC               : 매일 label 에서 베타 노출을 회귀로 제거한 뒤 IC
  C. 부분 IC                    : 변동성(rv_intraday)·전일 수익률(bm_ret_1d)을 통제한 뒤 남는 IC
  D. 1일 보유 long-only 성과     : 상위 10종목 − 동일가중 시장, 하루 평균 초과수익(bp)과
                                   손익분기 거래비용 → 실제 매매 가능성

사용 (저장소 루트에서, intraday_ic_diagnostic.py 실행 후):
    python scripts/intraday_ic_robustness.py
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

KEY = ["bm_ret_1d", "rv_intraday", "range_pct", "vshare_auction", "bm_gap",
       "ret_intraday", "close_loc", "vol_ret_corr", "vshare_open30", "vshare_late", "ret_late"]
CONTROLS = ["rv_intraday", "bm_ret_1d"]


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


def rank_ic(a: pd.Series, b: pd.Series) -> float:
    m = a.notna() & b.notna()
    return a[m].rank().corr(b[m].rank()) if m.sum() >= 20 else np.nan


def residualize(y: np.ndarray, X: np.ndarray) -> np.ndarray:
    X1 = np.column_stack([np.ones(len(y)), X])
    beta, *_ = np.linalg.lstsq(X1, y, rcond=None)
    return y - X1 @ beta


def add_beta(panel: pd.DataFrame, window: int) -> pd.DataFrame:
    """d일까지의 일간 수익률로 추정한 rolling 베타 (d+1 시가 전에 알 수 있는 정보만 사용)."""
    close = panel.pivot(index="date", columns="code", values="_close").sort_index()
    ret = close.pct_change(fill_method=None)
    mkt = ret.mean(axis=1)
    cov = ret.rolling(window, min_periods=window * 2 // 3).cov(mkt)
    var = mkt.rolling(window, min_periods=window * 2 // 3).var()
    beta = cov.div(var, axis=0)
    s = beta.stack(future_stack=True).rename("beta").reset_index()
    return panel.merge(s, on=["date", "code"], how="left")


def summarize(ic: pd.DataFrame, lag: int) -> pd.DataFrame:
    return pd.DataFrame({
        "ic_mean": ic.mean(),
        "t_nw": {c: newey_west_t(ic[c].values, lag) for c in ic.columns},
        "n": ic.notna().sum(),
    })


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--panel", default="reports/intraday_ic/features_panel.csv")
    ap.add_argument("--out", default="reports/intraday_ic")
    ap.add_argument("--horizons", type=int, nargs="+", default=[1, 5])
    ap.add_argument("--beta-window", type=int, default=60)
    ap.add_argument("--top-n", type=int, default=10)
    args = ap.parse_args()

    out = Path(args.out)
    panel = pd.read_csv(args.panel, dtype={"code": str}, parse_dates=["date"])
    panel = add_beta(panel, args.beta_window)
    feats = [f for f in KEY if f in panel.columns]
    pd.set_option("display.width", 220)

    all_rows = []
    for h in args.horizons:
        lab = f"fwd_ret_{h}"
        lag = h + 1
        recA, recB, recC = [], [], []
        for d, g in panel.groupby("date"):
            g = g[g[lab].notna()]
            if len(g) < 20:
                continue
            mkt = g[lab].mean()
            # A. 상승일/하락일 분리
            rA = {"date": d, "up": mkt > 0}
            for f in feats:
                rA[f] = rank_ic(g[f], g[lab])
            recA.append(rA)
            # B. 베타 중립 label
            gb = g[g["beta"].notna()]
            if len(gb) >= 20:
                y = residualize(gb[lab].values, gb[["beta"]].values)
                yb = pd.Series(y, index=gb.index)
                rB = {"date": d}
                for f in feats:
                    rB[f] = rank_ic(gb[f], yb)
                recB.append(rB)
            # C. 부분 IC: rank(feature) 를 rank(controls) 로 회귀한 잔차
            gc = g.dropna(subset=CONTROLS)
            if len(gc) >= 20:
                Xc = gc[CONTROLS].rank().values
                rC = {"date": d}
                for f in feats:
                    if f in CONTROLS:
                        rC[f] = np.nan
                        continue
                    sub = gc[gc[f].notna()]
                    if len(sub) < 20:
                        rC[f] = np.nan
                        continue
                    res = residualize(sub[f].rank().values, sub[CONTROLS].rank().values)
                    rC[f] = pd.Series(res).corr(sub[lab].rank().reset_index(drop=True))
                recC.append(rC)

        A = pd.DataFrame(recA).set_index("date")
        up, dn = A[A["up"]].drop(columns="up"), A[~A["up"]].drop(columns="up")
        B = pd.DataFrame(recB).set_index("date")
        C = pd.DataFrame(recC).set_index("date")
        base = summarize(A.drop(columns="up"), lag)

        tbl = pd.DataFrame({
            "ic_all": base["ic_mean"], "t_all": base["t_nw"],
            "ic_up_days": up.mean(), "ic_down_days": dn.mean(),
            "ic_beta_neutral": B.mean(), "t_beta_neutral": summarize(B, lag)["t_nw"],
            "ic_partial": C.mean(), "t_partial": summarize(C, lag)["t_nw"],
        })
        tbl.insert(0, "horizon", h)
        all_rows.append(tbl.reset_index(names="feature"))
        print(f"\n=== horizon {h}일 | 상승일 {len(up)}일 / 하락일 {len(dn)}일 ===")
        print("  ic_partial = rv_intraday·bm_ret_1d 통제 후 (통제변수 자신은 NaN)")
        print(tbl.drop(columns="horizon").round(4).to_string())

    res = pd.concat(all_rows, ignore_index=True)
    res.to_csv(out / "ic_robustness.csv", index=False, encoding="utf-8-sig")

    # D. 1일 보유 long-only 성과 (d+1 시가 매수 → d+1 종가 매도)
    print(f"\n=== D. 1일 보유 long-only: 상위 {args.top_n}종목 − 동일가중 시장 ===")
    lab = "fwd_ret_1"
    signals = {  # 부호: IC 방향대로 '좋은 쪽'이 상위가 되도록
        "bm_ret_1d (반전)": ("bm_ret_1d", -1),
        "rv_intraday (저변동)": ("rv_intraday", -1),
        "vshare_auction": ("vshare_auction", +1),
        "combo (3개 순위 평균)": (None, None),
    }
    rows = []
    for name, (col, sign) in signals.items():
        daily = []
        for d, g in panel.groupby("date"):
            g = g.dropna(subset=[lab, "bm_ret_1d", "rv_intraday", "vshare_auction"])
            if len(g) < 20:
                continue
            if col is None:
                score = (-g["bm_ret_1d"]).rank() + (-g["rv_intraday"]).rank() + g["vshare_auction"].rank()
            else:
                score = sign * g[col]
            top = g.loc[score.nlargest(args.top_n).index]
            daily.append(top[lab].mean() - g[lab].mean())  # 매일 시가 매수·종가 매도 → 매일 전량 회전
        x = np.array(daily)
        rows.append({
            "signal": name, "days": len(x),
            "excess_bp_per_day": x.mean() * 1e4,
            "t": newey_west_t(x, 2),
            "hit_rate": (x > 0).mean(),
            "breakeven_cost_bp_roundtrip": x.mean() * 1e4,  # 하루 1회 왕복이므로 초과수익 = 손익분기 왕복비용
        })
    D = pd.DataFrame(rows)
    D.to_csv(out / "longonly_1d.csv", index=False, encoding="utf-8-sig")
    print(D.round(2).to_string(index=False))
    print("\n참고: 국내 주식 왕복비용(증권거래세+수수료+슬리피지) 대략 20~30bp. "
          "손익분기 비용이 이보다 작으면 1일 보유로는 실매매 불가.")
    print(f"결과 CSV: {out.resolve()}")


if __name__ == "__main__":
    main()
