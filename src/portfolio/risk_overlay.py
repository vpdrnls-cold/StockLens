"""Portfolio-level risk overlay: scale total exposure, keep stock selection (CURRENT_STATUS item 55).

The strategy engine (``src.backtest.buffered``) always holds ``top_n`` names
fully invested. This module does NOT touch it. It takes the engine's
per-period net returns and scales each period by an exposure ``e_T`` in
[0, 1] decided at the decision date ``T`` (after T's close, decision time A,
item 46); the rest of the capital sits in cash at 0%. No leverage.

Pre-registered candidates (item 55 -- no other rule, no parameter grid)
    R0  e = 1                                          (reference)
    R1  e = min(1, sigma_star / sigma_hat_T)            volatility targeting
    R2  e = 1 if index_T > MA200_T else 0.5             trend filter
    R3  e = e_R1 * e_R2                                 combined

``sigma_hat_T``  20-trading-day stdev of the market proxy's daily returns x sqrt(252)
``sigma_star``   median of sigma_hat over the window's TRAIN dates only
market proxy     equal-weight index of the universe (``universe_ew_index``);
                 survivorship-biased (AGENTS.md 23) -> relative comparison only

Where history is too short for sigma_hat / MA200 the exposure is 1 (no
opinion = stay invested, identical to R0).

Exposure changes cost ``|e_T - e_{T-1}| * EXPOSURE_CHANGE_COST`` (the larger,
sell-side one-way cost: fee 0.015% + tax 0.20% + slippage 0.10%). The first
period has no change cost: the engine's own entry cost is already in its
return and is scaled by ``e`` like every other cost.

Every exposure at T uses only index values at dates <= T
(tests/test_risk_overlay.py checks that changing later prices leaves it unchanged).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd

from src.backtest.baseline import Trade, trades_to_dataframe

# ---- pre-registered constants (item 55). Changing any of these is a new experiment.
VOL_WINDOW = 20
TREND_WINDOW = 200
TREND_LOW_EXPOSURE = 0.5  # decided 2026-09-30 before any result (design reason, not data)
EXPOSURE_CHANGE_COST = 0.00015 + 0.0020 + 0.0010  # 0.315%
TRADING_DAYS_PER_YEAR = 252
HOLDING_DAYS = 5
PERIODS_PER_YEAR = TRADING_DAYS_PER_YEAR / HOLDING_DAYS

CANDIDATES = ("R0", "R1", "R2", "R3")
SIMPLICITY_ORDER = ("R2", "R1", "R3")  # tie-break among passing candidates
MDD_MARGIN = 0.05  # candidate MDD must be >= 5%p better than R0 in every window
CALMAR_TIE = 0.05  # mean-Calmar gap below this -> prefer the simpler candidate


# ---------------------------------------------------------------------------
# market proxy and exposures
# ---------------------------------------------------------------------------
def universe_ew_index(prices: pd.DataFrame) -> pd.Series:
    """Equal-weight daily index from a tidy ``trade_date, stock_code, close_price`` frame.

    Each stock's daily return is close / its own previous close - 1; the index
    return on a date is the mean over stocks that have a return that date.
    The index starts at 1.0 on the first date.
    """
    df = prices[["trade_date", "stock_code", "close_price"]].copy()
    df["trade_date"] = pd.to_datetime(df["trade_date"])
    df = df[np.isfinite(df["close_price"]) & (df["close_price"] > 0)]
    df = df.sort_values(["stock_code", "trade_date"])
    df["ret"] = df.groupby("stock_code", sort=False)["close_price"].pct_change()
    daily = df.groupby("trade_date")["ret"].mean().sort_index().fillna(0.0)
    return (1.0 + daily).cumprod().rename("universe_ew_index")


def realized_vol(index: pd.Series, window: int = VOL_WINDOW) -> pd.Series:
    """Annualized stdev of the last ``window`` daily returns, known at each date's close."""
    rets = index.sort_index().pct_change()
    return rets.rolling(window, min_periods=window).std() * math.sqrt(TRADING_DAYS_PER_YEAR)


def sigma_star_from_train(vol: pd.Series, train_start: str, train_end: str) -> float:
    """Median of sigma_hat over the TRAIN dates only (validation never used)."""
    v = vol.loc[pd.Timestamp(train_start):pd.Timestamp(train_end)].dropna()
    if v.empty:
        raise ValueError("no realized-vol values inside the train period")
    return float(v.median())


def _asof(series: pd.Series, dates) -> pd.Series:
    """Value of ``series`` at the last date <= each decision date (no look-ahead)."""
    s = series.sort_index()
    idx = pd.DatetimeIndex(pd.to_datetime(dates))
    pos = s.index.searchsorted(idx, side="right") - 1
    values = np.where(pos >= 0, s.to_numpy()[np.clip(pos, 0, None)], np.nan)
    return pd.Series(values, index=idx)


def exposure_vol_target(index: pd.Series, dates, sigma_star: float, window: int = VOL_WINDOW) -> pd.Series:
    vol = _asof(realized_vol(index, window), dates)
    e = (sigma_star / vol).clip(upper=1.0, lower=0.0)
    return e.fillna(1.0).rename("R1")


def exposure_trend(
    index: pd.Series, dates, window: int = TREND_WINDOW, low: float = TREND_LOW_EXPOSURE
) -> pd.Series:
    s = index.sort_index()
    ma = s.rolling(window, min_periods=window).mean()
    level, avg = _asof(s, dates), _asof(ma, dates)
    e = pd.Series(np.where(level > avg, 1.0, low), index=level.index)
    return e.where(avg.notna(), 1.0).rename("R2")


def candidate_exposures(index: pd.Series, dates, sigma_star: float) -> dict[str, pd.Series]:
    idx = pd.DatetimeIndex(pd.to_datetime(dates))
    r1 = exposure_vol_target(index, idx, sigma_star)
    r2 = exposure_trend(index, idx)
    return {
        "R0": pd.Series(1.0, index=idx, name="R0"),
        "R1": r1,
        "R2": r2,
        "R3": (r1 * r2).rename("R3"),
    }


# ---------------------------------------------------------------------------
# returns and metrics
# ---------------------------------------------------------------------------
def period_returns(trades: list[Trade]) -> pd.Series:
    """Per-decision-date portfolio net return -- same grouping as ``calculate_performance``."""
    df = trades_to_dataframe(trades)
    if df.empty:
        return pd.Series(dtype="float64")
    df["decision_date"] = pd.to_datetime(df["decision_date"])
    df["wr"] = df["weight"] * df["net_return"]
    return df.groupby("decision_date")["wr"].sum().sort_index().rename("period_return")


@dataclass(frozen=True)
class OverlayResult:
    returns: pd.Series  # net of exposure-change cost
    exposure: pd.Series
    change_cost: pd.Series


def apply_exposure(
    returns: pd.Series, exposure: pd.Series, cost: float = EXPOSURE_CHANGE_COST
) -> OverlayResult:
    r = returns.sort_index()
    e = exposure.reindex(r.index)
    if e.isna().any():
        raise ValueError("exposure missing for some decision dates")
    if ((e < 0) | (e > 1)).any():
        raise ValueError("exposure must be within [0, 1]")
    prev = e.shift(1)
    prev.iloc[0] = e.iloc[0]  # first period: no change cost (entry cost already in r)
    change_cost = (e - prev).abs() * cost
    return OverlayResult(returns=e * r - change_cost, exposure=e, change_cost=change_cost)


def risk_metrics(result: OverlayResult, periods_per_year: float = PERIODS_PER_YEAR) -> dict[str, float]:
    r = result.returns
    n = len(r)
    if n == 0:
        raise ValueError("no periods")
    equity = (1.0 + r).cumprod()
    net_cum = float(equity.iloc[-1] - 1.0)
    ann_return = float((1.0 + net_cum) ** (periods_per_year / n) - 1.0) if net_cum > -1 else -1.0
    std = float(r.std(ddof=1)) if n > 1 else 0.0
    mdd = float((equity / equity.cummax() - 1.0).min())
    mdd = min(mdd, 0.0)
    return {
        "periods": float(n),
        "net_cum": net_cum,
        "ann_return": ann_return,
        "ann_vol": std * math.sqrt(periods_per_year),
        "sharpe": float(r.mean() / std * math.sqrt(periods_per_year)) if std > 0 else float("nan"),
        "mdd": mdd,
        "calmar": ann_return / abs(mdd) if mdd < 0 else float("nan"),
        "hit_rate": float((r > 0).mean()),
        "avg_exposure": float(result.exposure.mean()),
        "reduced_share": float((result.exposure < 1.0).mean()),
        "change_cost_total": float(result.change_cost.sum()),
    }


# ---------------------------------------------------------------------------
# pre-registered decision (item 55)
# ---------------------------------------------------------------------------
def decide(results: pd.DataFrame) -> dict:
    """``results`` has one row per (window, candidate) with ``mdd`` and ``calmar``.

    Rk passes iff in EVERY window: mdd_k - mdd_R0 >= MDD_MARGIN and calmar_k >= calmar_R0.
    Among passing: highest mean Calmar; if another passing candidate is within
    CALMAR_TIE of the best, take the simplest (R2 -> R1 -> R3). None passing -> R0.
    """
    wide_mdd = results.pivot(index="window", columns="candidate", values="mdd")
    wide_cal = results.pivot(index="window", columns="candidate", values="calmar")
    passed = {}
    for k in SIMPLICITY_ORDER:
        mdd_ok = bool(((wide_mdd[k] - wide_mdd["R0"]) >= MDD_MARGIN - 1e-12).all())
        cal_ok = bool((wide_cal[k] >= wide_cal["R0"]).all())
        passed[k] = mdd_ok and cal_ok
    winners = [k for k in SIMPLICITY_ORDER if passed[k]]
    if not winners:
        return {"passed": passed, "adopt": "R0", "mean_calmar": wide_cal.mean().to_dict()}
    mean_cal = wide_cal.mean()
    best = max(mean_cal[k] for k in winners)
    contenders = [k for k in winners if mean_cal[k] > best - CALMAR_TIE]
    return {"passed": passed, "adopt": contenders[0], "mean_calmar": mean_cal.to_dict()}
