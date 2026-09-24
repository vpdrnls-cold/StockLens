"""Intraday summary feature IC diagnostic (Phase H).

ka10080 15분봉(약 1년 × 유니버스)으로 종목-일 단위 intraday 요약 feature를 만들고,
미래 수익률과의 cross-sectional rank IC를 측정한다. 모델 학습은 하지 않는다 — 신호 유무 진단용.

타이밍 (T-1 프레이밍)
  - feature: d일 정규장(09:00–15:30) 봉으로 계산 → d일 20:00 이후 확정, d+1 시가 전에 사용 가능
  - label  : fwd_ret_h = close(d+h) / open(d+1) - 1   (d+1 시가 진입, h 거래일 보유)
  - 가격(open/close)도 분봉에서 직접 집계 → 장중 일봉 스냅샷 문제(9/16, 9/21)와 무관

데이터 규칙 (Intraday raw data sanity checks 결과 반영)
  - 정규장 봉만 사용: 09:00, 09:15, …, 15:15 (26개) + 15:30 종가 단일가 (1개) = 27개
    애프터마켓(16:00–20:00, 2026-09-14~)은 제외
  - 27개가 정확히 있는 날만 feature 계산 → 늦은 개장일(수능·새해 첫날), 마감 지연일, 미완성 당일 자동 제외
  - 거래정지일은 데이터가 없으므로 결측. label 구간(d+1..d+h)에 결측이 있으면 label도 결측
  - 분할 전 분봉 거래량 미조정 문제 → 거래량 feature는 '하루 안 비중' 형태만 사용

사용 (저장소 루트에서):
    python scripts/intraday_ic_diagnostic.py
    python scripts/intraday_ic_diagnostic.py --horizons 1 5 10 --min-stocks 30
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

REG_TIMES = [f"{h:02d}:{m:02d}" for h in range(9, 16) for m in (0, 15, 30, 45)
             if (h, m) <= (15, 15)] + ["15:30"]  # 27개
AUCTION = "15:30"
LAST_CONT = "15:15"   # 15:15–15:20 접속매매 마지막 봉
LATE_START = "14:15"  # 마감 전 1시간 기준점 (14:30 이후 ~ 15:20)


# ---------------------------------------------------------------------------
# 로딩
# ---------------------------------------------------------------------------
def _records(obj) -> list[dict]:
    if isinstance(obj, list):
        return [r for r in obj if isinstance(r, dict)]
    best: list[dict] = []
    if isinstance(obj, dict):
        for v in obj.values():
            if isinstance(v, list) and v and isinstance(v[0], dict) and len(v) > len(best):
                best = v
    return best


def _num(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s.astype(str).str.replace(",", "", regex=False), errors="coerce").abs()


def load_minute(code_dir: Path) -> pd.DataFrame:
    frames = []
    for i, f in enumerate(sorted(code_dir.glob("*.json"))):
        with open(f, encoding="utf-8") as fh:
            recs = _records(json.load(fh))
        if recs:
            df = pd.DataFrame(recs)
            df["_ord"] = i
            frames.append(df)
    if not frames:
        return pd.DataFrame()
    df = pd.concat(frames, ignore_index=True).sort_values("_ord", kind="stable")
    out = pd.DataFrame({
        "ts": pd.to_datetime(df["cntr_tm"].astype(str), format="%Y%m%d%H%M%S", errors="coerce"),
        "open": _num(df["open_pric"]), "high": _num(df["high_pric"]),
        "low": _num(df["low_pric"]), "close": _num(df["cur_prc"]),
        "volume": _num(df["trde_qty"]),
    }).dropna(subset=["ts"])
    out = out.drop_duplicates("ts", keep="last").sort_values("ts").reset_index(drop=True)
    out["date"] = out["ts"].dt.normalize()
    out["hhmm"] = out["ts"].dt.strftime("%H:%M")
    return out


# ---------------------------------------------------------------------------
# feature
# ---------------------------------------------------------------------------
def day_features(g: pd.DataFrame) -> dict | None:
    """정규장 27봉이 정확히 있는 날만 feature 반환."""
    reg = g[g["hhmm"] <= "15:59"]
    if list(reg["hhmm"]) != REG_TIMES:
        return None
    b = reg.set_index("hhmm")
    o, c = b.loc["09:00", "open"], b.loc[AUCTION, "close"]
    hi, lo = reg["high"].max(), reg["low"].min()
    vol = reg["volume"]
    vtot = vol.sum()
    if o <= 0 or c <= 0 or vtot <= 0:
        return None

    cont = reg[reg["hhmm"] <= LAST_CONT]  # 접속매매 구간
    lr = np.log(cont["close"]).diff().dropna()
    typical = (reg["high"] + reg["low"] + reg["close"]) / 3
    vwap = (typical * vol).sum() / vtot

    late_hours = [t for t in REG_TIMES if "14:15" <= t <= LAST_CONT]
    return {
        # 가격
        "ret_open30": b.loc["09:15", "close"] / o - 1,
        "ret_mid": b.loc[LATE_START, "close"] / b.loc["09:15", "close"] - 1,
        "ret_late": b.loc[LAST_CONT, "close"] / b.loc[LATE_START, "close"] - 1,
        "ret_auction": c / b.loc[LAST_CONT, "close"] - 1,
        "ret_intraday": c / o - 1,
        "rv_intraday": float(np.sqrt((lr ** 2).sum())),
        "range_pct": (hi - lo) / c,
        "close_loc": (c - lo) / (hi - lo) if hi > lo else np.nan,
        "vwap_dev": c / vwap - 1,
        "up_bar_ratio": float((cont["close"] > cont["open"]).mean()),
        # 거래량 (하루 안 비중 → 분할 미조정과 무관)
        "vshare_open30": vol[b.index.isin(["09:00", "09:15"])].sum() / vtot,
        "vshare_late": vol[b.index.isin(late_hours)].sum() / vtot,
        "vshare_auction": b.loc[AUCTION, "volume"] / vtot,
        "vol_ret_corr": float(np.corrcoef(cont["volume"].iloc[1:], lr.abs())[0, 1])
        if lr.std() > 0 else np.nan,
        # label / 비교용 원재료
        "_open": o, "_close": c,
    }


def build_panel(minute_root: Path) -> pd.DataFrame:
    rows = []
    for code_dir in sorted(p for p in minute_root.iterdir() if p.is_dir() and re.fullmatch(r"\d{6}", p.name)):
        m = load_minute(code_dir)
        if m.empty:
            continue
        n_ok = 0
        for d, g in m.groupby("date", sort=True):
            f = day_features(g)
            if f is None:
                # feature는 없어도 label용 시가/종가는 남긴다 (정규장 시가·종가가 있는 경우)
                reg = g[g["hhmm"] <= "15:59"].set_index("hhmm")
                if "09:00" in reg.index or AUCTION in reg.index:
                    rows.append({"code": code_dir.name, "date": d, "_valid": False,
                                 "_open": reg["open"].iloc[0], "_close": reg["close"].get(AUCTION, np.nan)})
                continue
            f.update(code=code_dir.name, date=d, _valid=True)
            rows.append(f)
            n_ok += 1
        print(f"  {code_dir.name}: 유효 {n_ok}일 / 전체 {m['date'].nunique()}일")
    return pd.DataFrame(rows)


def add_labels_and_benchmarks(panel: pd.DataFrame, horizons: list[int]) -> pd.DataFrame:
    cal = pd.DatetimeIndex(sorted(panel["date"].unique()))
    idx = {d: i for i, d in enumerate(cal)}
    panel = panel.copy()
    panel["_i"] = panel["date"].map(idx)
    opn = panel.pivot(index="_i", columns="code", values="_open").reindex(range(len(cal)))
    cls = panel.pivot(index="_i", columns="code", values="_close").reindex(range(len(cal)))

    out = {}
    for h in horizons:
        # close(d+h)/open(d+1)-1, d+1..d+h 중 하나라도 결측이면 NaN
        fwd = cls.shift(-h) / opn.shift(-1) - 1
        complete = opn.shift(-1).notna()
        for k in range(1, h + 1):
            complete &= cls.shift(-k).notna()
        out[f"fwd_ret_{h}"] = fwd.where(complete)
    # 비교용 일봉 feature (분봉에서 만든 종가 기준)
    out["bm_ret_1d"] = cls / cls.shift(1) - 1
    out["bm_ret_20d"] = cls / cls.shift(20) - 1
    out["bm_gap"] = opn / cls.shift(1) - 1  # 전일 종가 → 당일 시가

    for name, wide in out.items():
        s = wide.stack(future_stack=True).rename(name).reset_index()
        panel = panel.merge(s, on=["_i", "code"], how="left")
    return panel.drop(columns=["_i"])


# ---------------------------------------------------------------------------
# IC
# ---------------------------------------------------------------------------
def newey_west_t(x: np.ndarray, lag: int) -> float:
    x = x[~np.isnan(x)]
    n = len(x)
    if n < 10:
        return np.nan
    e = x - x.mean()
    v = (e @ e) / n
    for k in range(1, lag + 1):
        w = 1 - k / (lag + 1)
        v += 2 * w * (e[k:] @ e[:-k]) / n
    return float(x.mean() / np.sqrt(v / n)) if v > 0 else np.nan


def daily_ic(panel: pd.DataFrame, feats: list[str], label: str, min_stocks: int) -> pd.DataFrame:
    rows = []
    for d, g in panel.groupby("date"):
        rec = {"date": d}
        for f in feats:
            if f == label:
                rec[f] = 1.0
                continue
            sub = g[[f, label]].dropna()
            rec[f] = sub[f].rank().corr(sub[label].rank()) if len(sub) >= min_stocks else np.nan
        rows.append(rec)
    return pd.DataFrame(rows).set_index("date")


def summarize(ic: pd.DataFrame, h: int, redundancy: pd.Series) -> pd.DataFrame:
    rows = []
    half = ic.index[len(ic) // 2] if len(ic) else None
    for f in ic.columns:
        x = ic[f].dropna()
        if x.empty:
            continue
        rows.append({
            "feature": f, "horizon": h, "n_dates": len(x),
            "ic_mean": x.mean(), "ic_std": x.std(),
            "icir": x.mean() / x.std() if x.std() > 0 else np.nan,
            "t_nw": newey_west_t(x.values, lag=max(h - 1, 0) + 2),
            "hit_rate": (x > 0).mean(),
            "ic_1st_half": x[x.index < half].mean(),
            "ic_2nd_half": x[x.index >= half].mean(),
            "rank_corr_w_ret1d": redundancy.get(f, np.nan),
        })
    return pd.DataFrame(rows)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--minute-dir", default="data/raw/kiwoom/ka10080")
    ap.add_argument("--out", default="reports/intraday_ic")
    ap.add_argument("--horizons", type=int, nargs="+", default=[1, 5])
    ap.add_argument("--min-stocks", type=int, default=20, help="하루 IC 계산에 필요한 최소 종목 수")
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    print("feature 계산 중...")
    panel = build_panel(Path(args.minute_dir))
    if panel.empty:
        raise SystemExit(f"분봉 데이터 없음: {args.minute_dir}")
    panel = add_labels_and_benchmarks(panel, args.horizons)
    panel = panel[panel["_valid"]].drop(columns=["_valid"])

    intraday = [c for c in panel.columns
                if not c.startswith(("_", "fwd_", "bm_")) and c not in ("code", "date")]
    bench = ["bm_ret_1d", "bm_ret_20d", "bm_gap"]
    feats = intraday + bench
    panel.to_csv(out / "features_panel.csv", index=False, encoding="utf-8-sig")

    # 중복도: 각 feature와 전일 대비 수익률(bm_ret_1d)의 일별 순위상관 평균
    red = daily_ic(panel, feats, "bm_ret_1d", args.min_stocks).mean()

    summaries = []
    for h in args.horizons:
        ic = daily_ic(panel, feats, f"fwd_ret_{h}", args.min_stocks)
        ic.to_csv(out / f"ic_daily_h{h}.csv", encoding="utf-8-sig")
        summaries.append(summarize(ic, h, red))
    summ = pd.concat(summaries, ignore_index=True)
    summ.to_csv(out / "ic_summary.csv", index=False, encoding="utf-8-sig")

    # ---------------- 콘솔 요약 ----------------
    pd.set_option("display.width", 200)
    n_dates, n_codes = panel["date"].nunique(), panel["code"].nunique()
    print(f"\n패널: {n_codes}종목 × {n_dates}일 (유효 stock-day {len(panel)}), "
          f"{panel['date'].min().date()} ~ {panel['date'].max().date()}")
    for h in args.horizons:
        s = summ[summ["horizon"] == h].copy()
        s["abs_t"] = s["t_nw"].abs()
        s = s.sort_values("abs_t", ascending=False).drop(columns=["abs_t", "horizon"])
        print(f"\n=== horizon {h}일 (label = close(d+{h}) / open(d+1) - 1) ===")
        print(s.round(4).to_string(index=False))
    n_tests = len(feats) * len(args.horizons)
    print(f"\n참고: 검정 {n_tests}개 → |t|>2 가 우연히 {n_tests * 0.046:.1f}개 정도 나올 수 있음. "
          "bm_* 는 비교용 일봉 feature.")
    print(f"결과 CSV: {out.resolve()}")


if __name__ == "__main__":
    main()
