"""Cross-sectional (per-date) helpers shared by the IC experiments.

The model's job is to rank stocks *within a date*, so evaluation (rank IC)
and, optionally, the training target should be defined per date too.

Why the target matters: ``target_return_5d`` contains a market-wide
component -- on any given date most stocks move together. That common
component dominates the variance of the raw target but carries no
information about which stock will beat the others, and it is hard to
predict. A regression fit with RMSE spends its capacity (and its early
stopping) on it, so with weak cross-sectional signal the boosted model
stops after very few trees and outputs (near-)identical predictions for
every stock on many days (coverage < 100% in the IC reports). Removing the
per-date mean, or using the per-date rank, leaves only the cross-sectional
part the model is supposed to learn.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class ICSummary:
    mean_ic: float      # undefined days count as 0
    pct_pos: float      # share of ALL eligible days with IC > 0
    n_days: int         # eligible days (>= min_stocks stocks)
    coverage: float     # share of eligible days with a defined IC


def daily_rank_ic(
    df: pd.DataFrame,
    score_col: str,
    target_col: str = "target_return_5d",
    *,
    min_stocks: int = 3,
) -> pd.Series:
    """Spearman rank IC per ``trade_date``.

    Dates with fewer than ``min_stocks`` stocks are omitted. Dates where the
    score (or the target) is identical for every stock are kept as NaN
    (IC undefined).
    """
    values: dict[pd.Timestamp, float] = {}
    for date, group in df.groupby("trade_date"):
        if len(group) < min_stocks:
            continue
        score_rank = group[score_col].rank()
        target_rank = group[target_col].rank()
        if score_rank.nunique() < 2 or target_rank.nunique() < 2:
            values[date] = np.nan
        else:
            values[date] = float(score_rank.corr(target_rank))
    return pd.Series(values, dtype="float64", name="ic")


def summarize_ic(ics: pd.Series) -> ICSummary:
    if ics.empty:
        return ICSummary(float("nan"), float("nan"), 0, 0.0)
    filled = ics.fillna(0.0)
    return ICSummary(
        mean_ic=float(filled.mean()),
        pct_pos=float((filled > 0).mean()),
        n_days=int(len(ics)),
        coverage=float(ics.notna().mean()),
    )


def demean_by_date(df: pd.DataFrame, col: str) -> pd.Series:
    """Subtract the per-date mean (removes the market-wide component)."""
    return df[col] - df.groupby("trade_date")[col].transform("mean")


def rank_by_date(df: pd.DataFrame, col: str) -> pd.Series:
    """Per-date percentile rank, centered to (-0.5, 0.5)."""
    grouped = df.groupby("trade_date")[col]
    return grouped.rank(method="average") / grouped.transform("count") - 0.5 - 0.5 / grouped.transform("count")
