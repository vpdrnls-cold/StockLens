"""분봉 raw 데이터 sanity check (Intraday raw data sanity checks).

세 가지를 점검하고 결과를 CSV로 남긴다.
  1. coverage   : 종목별 분봉 커버 기간, 일봉 캘린더 대비 누락일, train/val/test 구간별 일수
  2. reconcile  : 분봉을 일봉으로 집계해 기존 일봉과 비교 (수정주가 미적용·거래량 차이 탐지)
  3. timestamp  : 시각별 봉 존재율·거래량 비중, 하루 봉 개수 분포, 비정상 거래일

입력: 키움 raw 응답 JSON 폴더
  data/raw/kiwoom/ka10080/{종목코드}/*.json   (분봉)
  data/raw/kiwoom/ka10081/{종목코드}/*.json   (일봉)
한 종목에 스냅샷 파일이 여러 개면 모두 합치고, 같은 시각은 가장 최근 파일 값을 쓴다.

사용 예 (저장소 루트에서):
  python scripts/check_intraday_raw.py
"""
from __future__ import annotations

import argparse
import glob
import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# 설정
# ---------------------------------------------------------------------------
ALIASES = {
    "ts": ["cntr_tm", "datetime", "timestamp", "time", "date_time", "dt_tm", "체결시간"],
    "date": ["dt", "date", "base_dt", "trade_date", "일자"],
    "open": ["open_pric", "open", "시가"],
    "high": ["high_pric", "high", "고가"],
    "low": ["low_pric", "low", "저가"],
    "close": ["cur_prc", "close", "close_pric", "현재가", "종가"],
    "volume": ["trde_qty", "volume", "vol", "거래량"],
}

# src/data/dataset.py 를 import 하지 못할 때 쓰는 기본값 (overview 기준)
DEFAULT_SPLITS = {
    "train": ("2002-10-29", "2019-12-31"),
    "val": ("2020-01-01", "2023-06-30"),
    "test": ("2023-07-01", "2026-09-16"),
}

KEY_TIMES = ["09:00", "09:15", "09:30", "15:00", "15:15", "15:20", "15:30", "15:45"]


def load_splits() -> dict[str, tuple[str, str]]:
    """가능하면 src/data/dataset.py 의 split 상수를 그대로 쓴다."""
    try:
        sys.path.insert(0, str(Path.cwd()))
        from src.data import dataset as ds  # type: ignore

        cand = {}
        for name in ("TRAIN", "VAL", "TEST"):
            s = getattr(ds, f"{name}_START", None)
            e = getattr(ds, f"{name}_END", None)
            if s is not None and e is not None:
                cand[name.lower()] = (str(s), str(e))
        if len(cand) == 3:
            return cand
    except Exception:
        pass
    return DEFAULT_SPLITS


# ---------------------------------------------------------------------------
# 로딩
# ---------------------------------------------------------------------------
def code_from_path(p: str) -> str:
    m = re.search(r"(\d{6})", Path(p).stem)
    return m.group(1) if m else Path(p).stem


def pick(cols: list[str], key: str, override: dict[str, str]) -> str | None:
    if key in override:
        return override[key]
    lower = {c.lower(): c for c in cols}
    for a in ALIASES[key]:
        if a.lower() in lower:
            return lower[a.lower()]
    return None


def to_num(s: pd.Series) -> pd.Series:
    """키움 가격은 '+70000' / '-69800' 처럼 전일 대비 부호가 붙어 온다 → 절댓값."""
    s = s.astype(str).str.replace(",", "", regex=False).str.strip()
    return pd.to_numeric(s, errors="coerce").abs()


def parse_ts(s: pd.Series) -> pd.Series:
    raw = s.astype(str).str.strip()
    digits = raw.str.replace(r"\D", "", regex=True)
    if digits.str.len().eq(14).all():
        return pd.to_datetime(digits, format="%Y%m%d%H%M%S", errors="coerce")
    if digits.str.len().eq(12).all():
        return pd.to_datetime(digits, format="%Y%m%d%H%M", errors="coerce")
    return pd.to_datetime(raw, errors="coerce")


def parse_date(s: pd.Series) -> pd.Series:
    raw = s.astype(str).str.strip()
    digits = raw.str.replace(r"\D", "", regex=True)
    if digits.str.len().eq(8).all():
        return pd.to_datetime(digits, format="%Y%m%d", errors="coerce")
    return pd.to_datetime(raw, errors="coerce").dt.normalize()


def parse_override(text: str | None) -> dict[str, str]:
    """'ts=cntr_tm,close=cur_prc' → dict"""
    if not text:
        return {}
    return dict(kv.split("=", 1) for kv in text.split(","))


def _records_from_json(obj) -> list[dict]:
    """응답 JSON에서 가장 긴 list[dict] 값을 찾아 반환 (stk_min_pole_chart_qry 등)."""
    if isinstance(obj, list):
        return [r for r in obj if isinstance(r, dict)]
    best: list[dict] = []
    if isinstance(obj, dict):
        for v in obj.values():
            if isinstance(v, list) and v and isinstance(v[0], dict) and len(v) > len(best):
                best = v
            elif isinstance(v, (dict, list)):
                sub = _records_from_json(v)
                if len(sub) > len(best):
                    best = sub
    return best


def read_code_dir(code_dir: str) -> pd.DataFrame:
    """종목 폴더의 모든 스냅샷 JSON을 합친다. 파일명(UTC 타임스탬프) 순서 → 뒤 파일이 우선."""
    frames = []
    for i, f in enumerate(sorted(glob.glob(str(Path(code_dir) / "*.json")))):
        with open(f, encoding="utf-8") as fh:
            recs = _records_from_json(json.load(fh))
        if recs:
            df = pd.DataFrame(recs).astype(str)
            df["_file_order"] = i
            frames.append(df)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def load_minute(path: str, override: dict[str, str]) -> pd.DataFrame:
    df = read_code_dir(path)
    if df.empty:
        raise ValueError(f"{path}: JSON 레코드 없음")
    cols = list(df.columns)
    m = {k: pick(cols, k, override) for k in ("ts", "open", "high", "low", "close", "volume")}
    missing = [k for k, v in m.items() if v is None]
    if missing:
        raise ValueError(f"{path}: 컬럼 인식 실패 {missing} (현재 컬럼: {cols}) → --minute-cols 로 지정")
    df = df.sort_values("_file_order", kind="stable")
    out = pd.DataFrame({"ts": parse_ts(df[m["ts"]])})
    for k in ("open", "high", "low", "close", "volume"):
        out[k] = to_num(df[m[k]])
    n_raw = len(out)
    out = out.dropna(subset=["ts"])
    out.attrs["n_bad_ts"] = n_raw - len(out)
    out.attrs["n_dup"] = int(out.duplicated("ts").sum())
    out.attrs["was_sorted_asc"] = bool(out["ts"].is_monotonic_increasing)
    out = out.drop_duplicates("ts", keep="last").sort_values("ts").reset_index(drop=True)
    out["date"] = out["ts"].dt.normalize()
    out["hhmm"] = out["ts"].dt.strftime("%H:%M")
    return out


def load_daily(path: str, override: dict[str, str]) -> pd.DataFrame:
    df = read_code_dir(path)
    if df.empty:
        raise ValueError(f"{path}: JSON 레코드 없음")
    df = df.sort_values("_file_order")
    cols = list(df.columns)
    m = {k: pick(cols, k, override) for k in ("date", "open", "high", "low", "close", "volume")}
    missing = [k for k, v in m.items() if v is None]
    if missing:
        raise ValueError(f"{path}: 컬럼 인식 실패 {missing} (현재 컬럼: {cols}) → --daily-cols 로 지정")
    out = pd.DataFrame({"date": parse_date(df[m["date"]])})
    for k in ("open", "high", "low", "close", "volume"):
        out[k] = to_num(df[m[k]])
    return (out.dropna(subset=["date"]).drop_duplicates("date", keep="last")
            .sort_values("date").reset_index(drop=True))


# ---------------------------------------------------------------------------
# 1. coverage
# ---------------------------------------------------------------------------
def check_coverage(code, mdf, ddf, splits):
    m_days = pd.DatetimeIndex(mdf["date"].unique())
    first, last = m_days.min(), m_days.max()
    cal = pd.DatetimeIndex(ddf["date"])
    cal_in = cal[(cal >= first) & (cal <= last)]
    missing = cal_in.difference(m_days)
    extra = m_days.difference(cal)  # 분봉엔 있는데 일봉엔 없는 날

    row = {
        "code": code,
        "minute_first": first.date(),
        "minute_last": last.date(),
        "minute_days": len(m_days),
        "daily_days_in_range": len(cal_in),
        "missing_days": len(missing),
        "missing_pct": round(100 * len(missing) / max(len(cal_in), 1), 2),
        "extra_days_not_in_daily": len(extra),
        "daily_first": cal.min().date() if len(cal) else None,
        "n_bad_ts": mdf.attrs.get("n_bad_ts", 0),
        "n_dup_ts": mdf.attrs.get("n_dup", 0),
        "raw_sorted_asc": mdf.attrs.get("was_sorted_asc"),
    }
    for name, (s, e) in splits.items():
        s, e = pd.Timestamp(s), pd.Timestamp(e)
        row[f"{name}_minute_days"] = int(((m_days >= s) & (m_days <= e)).sum())
        row[f"{name}_daily_days"] = int(((cal >= s) & (cal <= e)).sum())
    miss_rows = [{"code": code, "date": d.date(), "kind": "missing_in_minute"} for d in missing]
    miss_rows += [{"code": code, "date": d.date(), "kind": "not_in_daily"} for d in extra]
    return row, miss_rows


# ---------------------------------------------------------------------------
# 2. reconcile
# ---------------------------------------------------------------------------
def check_reconcile(code, mdf, ddf, tol_pct, break_pct):
    agg = (
        mdf.groupby("date")
        .agg(m_open=("open", "first"), m_high=("high", "max"), m_low=("low", "min"),
             m_close=("close", "last"), m_volume=("volume", "sum"))
        .reset_index()
    )
    j = agg.merge(ddf.rename(columns={c: f"d_{c}" for c in ("open", "high", "low", "close", "volume")}),
                  on="date", how="inner")
    if j.empty:
        return None, pd.DataFrame(), pd.DataFrame()

    for k in ("open", "high", "low", "close", "volume"):
        j[f"r_{k}"] = j[f"m_{k}"] / j[f"d_{k}"].replace(0, np.nan)
    j.insert(0, "code", code)

    # 수정주가 불일치 탐지: close 비율이 연속된 두 날 사이에 break_pct 이상 점프
    r = j["r_close"]
    jump = (r / r.shift(1) - 1).abs() * 100
    breaks = j.loc[jump > break_pct, ["code", "date", "r_close"]].copy()
    breaks["prev_r_close"] = r.shift(1)[jump > break_pct].values
    breaks["jump_pct"] = jump[jump > break_pct].round(2).values

    tol = tol_pct / 100
    summ = {"code": code, "overlap_days": len(j)}
    for k in ("open", "high", "low", "close"):
        dev = (j[f"r_{k}"] - 1).abs()
        summ[f"{k}_ratio_median"] = round(j[f"r_{k}"].median(), 5)
        summ[f"{k}_mismatch_pct"] = round(100 * (dev > tol).mean(), 2)
    summ["volume_ratio_median"] = round(j["r_volume"].median(), 4)
    summ["volume_ratio_p05"] = round(j["r_volume"].quantile(0.05), 4)
    summ["volume_ratio_p95"] = round(j["r_volume"].quantile(0.95), 4)
    summ["adj_breaks"] = len(breaks)
    # 비율이 1 근처가 아닌 구간이 길게 이어지면 수정주가 미적용 가능성
    summ["close_ratio_far_from_1_pct"] = round(100 * ((j["r_close"] - 1).abs() > 0.05).mean(), 2)

    detail = j[j[[f"r_{k}" for k in ("open", "high", "low", "close")]].sub(1).abs().gt(tol).any(axis=1)
               | (j["r_volume"].sub(1).abs() > 0.02)]
    return summ, detail, breaks


# ---------------------------------------------------------------------------
# 3. timestamp / 봉 구조
# ---------------------------------------------------------------------------
def check_timestamp(code, mdf):
    diffs = mdf.groupby("date")["ts"].diff().dt.total_seconds().div(60).dropna()
    interval = diffs.mode().iloc[0] if len(diffs) else np.nan

    per_day = mdf.groupby("date").agg(
        n_bars=("ts", "size"),
        first_bar=("hhmm", "first"),
        last_bar=("hhmm", "last"),
        day_vol=("volume", "sum"),
        zero_vol_bars=("volume", lambda v: int((v == 0).sum())),
    )
    med_bars = per_day["n_bars"].median()
    mode_first = per_day["first_bar"].mode().iloc[0]
    mode_last = per_day["last_bar"].mode().iloc[0]

    row = {
        "code": code,
        "bar_interval_min": interval,
        "bars_per_day_median": med_bars,
        "bars_per_day_min": per_day["n_bars"].min(),
        "bars_per_day_max": per_day["n_bars"].max(),
        "first_bar_mode": mode_first,
        "first_bar_mode_share": round((per_day["first_bar"] == mode_first).mean(), 4),
        "last_bar_mode": mode_last,
        "last_bar_mode_share": round((per_day["last_bar"] == mode_last).mean(), 4),
        "zero_vol_bar_pct": round(100 * (mdf["volume"] == 0).mean(), 3),
        "ohlc_violation_bars": int(((mdf["high"] < mdf[["open", "close"]].max(axis=1))
                                    | (mdf["low"] > mdf[["open", "close"]].min(axis=1))).sum()),
    }

    # 시각별 존재율 / 거래량 비중
    m2 = mdf.merge(per_day["day_vol"], left_on="date", right_index=True)
    m2["vol_share"] = m2["volume"] / m2["day_vol"].replace(0, np.nan)
    n_days = len(per_day)
    tod = m2.groupby("hhmm").agg(days_present=("date", "nunique"), vol_share_mean=("vol_share", "mean"))
    tod["presence_rate"] = tod["days_present"] / n_days
    tod = tod.reset_index()
    tod.insert(0, "code", code)
    for t in KEY_TIMES:
        hit = tod.loc[tod["hhmm"] == t]
        row[f"presence_{t}"] = round(float(hit["presence_rate"].iloc[0]), 4) if len(hit) else 0.0
        row[f"volshare_{t}"] = round(float(hit["vol_share_mean"].iloc[0]), 4) if len(hit) else 0.0

    # 비정상 거래일: 시작/종료 시각이 최빈값과 다르거나 봉 수가 중앙값의 80% 미만
    ab = per_day[(per_day["first_bar"] != mode_first) | (per_day["last_bar"] != mode_last)
                 | (per_day["n_bars"] < 0.8 * med_bars)].reset_index()
    ab.insert(0, "code", code)
    return row, tod, ab


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--minute-dir", default="data/raw/kiwoom/ka10080")
    ap.add_argument("--daily-dir", default="data/raw/kiwoom/ka10081")
    ap.add_argument("--out", default="reports/intraday_sanity")
    ap.add_argument("--minute-cols", help="예: ts=cntr_tm,close=cur_prc,volume=trde_qty")
    ap.add_argument("--daily-cols", help="예: date=dt,close=cur_prc")
    ap.add_argument("--tol-pct", type=float, default=0.5, help="OHLC 불일치 허용 오차(%%)")
    ap.add_argument("--break-pct", type=float, default=5.0, help="수정주가 점프 판정 기준(%%)")
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    m_ov, d_ov = parse_override(args.minute_cols), parse_override(args.daily_cols)
    splits = load_splits()

    def code_dirs(root):
        return {p.name: str(p) for p in sorted(Path(root).iterdir())
                if p.is_dir() and re.fullmatch(r"\d{6}", p.name)} if Path(root).is_dir() else {}

    minute_files = code_dirs(args.minute_dir)
    daily_files = code_dirs(args.daily_dir)
    codes = sorted(set(minute_files) & set(daily_files))
    only_m = sorted(set(minute_files) - set(daily_files))
    if not codes:
        sys.exit(f"매칭되는 종목 없음. 분봉 폴더 {len(minute_files)}개, 일봉 폴더 {len(daily_files)}개 발견 "
                 f"({args.minute_dir}, {args.daily_dir})")
    if only_m:
        print(f"[경고] 일봉 폴더가 없는 분봉 종목: {only_m}")

    cov, miss, rec, rec_detail, breaks, ts_rows, tods, abn = [], [], [], [], [], [], [], []
    for code in codes:
        try:
            mdf = load_minute(minute_files[code], m_ov)
            ddf = load_daily(daily_files[code], d_ov)
        except ValueError as e:
            print(f"[스킵] {e}")
            continue
        if mdf.empty:
            print(f"[스킵] {code}: 분봉 비어 있음")
            continue

        c_row, c_miss = check_coverage(code, mdf, ddf, splits)
        cov.append(c_row)
        miss += c_miss

        r_sum, r_det, r_brk = check_reconcile(code, mdf, ddf, args.tol_pct, args.break_pct)
        if r_sum:
            rec.append(r_sum)
            rec_detail.append(r_det)
            breaks.append(r_brk)

        t_row, t_tod, t_ab = check_timestamp(code, mdf)
        ts_rows.append(t_row)
        tods.append(t_tod)
        abn.append(t_ab)
        print(f"  {code}: {c_row['minute_first']} ~ {c_row['minute_last']}, "
              f"{c_row['minute_days']}일, 누락 {c_row['missing_days']}일")

    def save(obj, name):
        df = pd.concat(obj, ignore_index=True) if isinstance(obj, list) and obj and isinstance(obj[0], pd.DataFrame) \
            else pd.DataFrame(obj)
        df.to_csv(out / name, index=False, encoding="utf-8-sig")
        return df

    cov_df = save(cov, "1_coverage.csv")
    save(miss, "1_missing_days.csv")
    rec_df = save(rec, "2_reconcile_summary.csv")
    save(rec_detail, "2_reconcile_mismatch_days.csv")
    brk_df = save(breaks, "2_adjustment_breaks.csv")
    ts_df = save(ts_rows, "3_timestamp_summary.csv")
    tod_df = save(tods, "3_time_of_day_profile.csv")
    save(abn, "3_abnormal_days.csv")

    # 전체 종목 합친 시각별 프로파일 (timestamp 규칙 판단용)
    if not tod_df.empty:
        pooled = tod_df.groupby("hhmm").agg(presence_rate=("presence_rate", "mean"),
                                            vol_share_mean=("vol_share_mean", "mean")).reset_index()
        pooled.to_csv(out / "3_time_of_day_pooled.csv", index=False, encoding="utf-8-sig")

    # ---------------- 콘솔 요약 ----------------
    pd.set_option("display.width", 200)
    pd.set_option("display.max_columns", 30)
    print("\n=== 1. 커버리지 ===")
    cols = ["code", "minute_first", "minute_last", "minute_days", "missing_pct"] + \
           [f"{s}_minute_days" for s in splits]
    print(cov_df[cols].to_string(index=False))
    print(f"\n  split 기준: {splits}")
    if not cov_df.empty:
        tr = cov_df["train_minute_days"].sum() if "train_minute_days" in cov_df else 0
        print(f"  → train 구간 분봉 일수 합계: {tr} "
              f"({'train에 intraday feature 사용 불가 수준' if tr < 250 else '사용 가능'})")

    print("\n=== 2. 일봉 대조 ===")
    if not rec_df.empty:
        print(rec_df[["code", "overlap_days", "close_ratio_median", "close_mismatch_pct",
                      "volume_ratio_median", "adj_breaks", "close_ratio_far_from_1_pct"]].to_string(index=False))
        if not brk_df.empty:
            print("\n  수정주가 불일치 의심 지점:")
            print(brk_df.to_string(index=False))

    print("\n=== 3. timestamp / 봉 구조 ===")
    if not ts_df.empty:
        print(ts_df[["code", "bar_interval_min", "bars_per_day_median", "first_bar_mode",
                     "last_bar_mode", "zero_vol_bar_pct", "ohlc_violation_bars"]].to_string(index=False))
        key = [c for c in ts_df.columns if c.startswith("presence_") or c.startswith("volshare_")]
        print("\n  주요 시각 존재율/거래량 비중 (종목 평균):")
        print(ts_df[key].mean().round(4).to_string())

    print(f"\n결과 CSV: {out.resolve()}")


if __name__ == "__main__":
    main()
