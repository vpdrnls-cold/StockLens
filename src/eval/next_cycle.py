"""Next-cycle candidate grid -- the fixed rules of CURRENT_STATUS item 84 (confirmed 2026-10-08).

Single source for the candidates, the dev/training boundaries, the selection rule
and the forward2 length rule. Everything here was fixed before any dev-period
result was seen; changing a value here after the run is a new pre-registration,
not a fix. ``scripts/run_next_cycle_grid.py`` is the only runner.

Pure functions only: no file or network access, so every rule is unit-tested on
synthetic data.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import erf, sqrt

import numpy as np
import pandas as pd

from src.data.dataset import TRAIN_START_DATE
from src.data.intraday_split import FORWARD_START, INTRADAY_DATA_START

# --- B. periods -------------------------------------------------------------
DEV_START = INTRADAY_DATA_START          # selection dev starts here (2025-09-01)
INTERNAL_VALIDATION_YEARS = 1            # M1 early stopping: last year of its training range
PURGE_DAYS = 5                           # 5-day label overlap (split_by_time purge, item 65)
MIN_STOCKS = 50                          # dates with fewer scored + labeled stocks are dropped (as item 79)

# --- C. candidates ----------------------------------------------------------
MIN_TREES = 100                          # M1: no early stop before 100 trees


@dataclass(frozen=True)
class Portfolio:
    top_n: int
    holding_days: int
    buffer_multiplier: float = 3.0


PORTFOLIOS: dict[str, Portfolio] = {
    "P0": Portfolio(top_n=10, holding_days=5),   # current production path
    "P1": Portfolio(top_n=20, holding_days=10),
    "P2": Portfolio(top_n=30, holding_days=20),
}
MODELS = ("M0", "M1")  # M0 = frozen model (no retrain), M1 = min-trees retrain
BASELINE = "M0P0"
# Fixed order: also the tie-break when two passing candidates have the same mean excess.
CANDIDATES = ("M0P0", "M0P1", "M0P2", "M1P0", "M1P1", "M1P2")
PHASE_OFFSETS = (0, 1, 2, 3, 4)

# --- A-3. selection rule ----------------------------------------------------
MIN_WINS = 4  # of the 5 start offsets, the candidate must beat the baseline's excess

# --- A-5. forward2 length rule ----------------------------------------------
ASSUMED_TRUE_IC = 0.03
T_THRESHOLD = 1.65
TARGET_POWER = 0.60
LENGTH_STEP = 125   # trading days (~6 months)
LENGTH_CAP = 500    # trading days (~2 years)
LABEL_HORIZON = 5


def split_candidate(candidate: str) -> tuple[str, Portfolio]:
    """'M1P2' -> ('M1', PORTFOLIOS['P2'])."""
    if candidate not in CANDIDATES:
        raise ValueError(f"unknown candidate {candidate!r}")
    return candidate[:2], PORTFOLIOS[candidate[2:]]


def _normal_cdf(x: float) -> float:
    return 0.5 * (1.0 + erf(x / sqrt(2.0)))


def forward2_power(n_days: int, ic_sd: float, true_ic: float = ASSUMED_TRUE_IC,
                   threshold: float = T_THRESHOLD, horizon: int = LABEL_HORIZON) -> float:
    """P(t > threshold) after ``n_days`` decision dates, t = mean IC / (sd / sqrt(n / horizon)).

    Normal approximation, the same t as item 79. Item 79's numbers: sd 0.155 ->
    250 days ~39%, 500 days ~61%.
    """
    if n_days <= 0 or not np.isfinite(ic_sd) or ic_sd <= 0:
        raise ValueError("n_days must be > 0 and ic_sd a positive finite number.")
    shift = true_ic * sqrt(n_days / horizon) / ic_sd
    return 1.0 - _normal_cdf(threshold - shift)


def forward2_length(ic_sd: float) -> int | None:
    """Shortest length (multiple of 125 trading days, <= 500) with power >= 60%.

    ``None`` = even 500 days is not enough: forward2 then only checks for harm and
    records the direction, without a pass verdict (item 84 A-5).
    """
    for n in range(LENGTH_STEP, LENGTH_CAP + 1, LENGTH_STEP):
        if forward2_power(n, ic_sd) >= TARGET_POWER:
            return n
    return None


def decide(phases: pd.DataFrame) -> tuple[str, pd.DataFrame]:
    """Item 84 A-3 on a table with columns candidate, offset, excess_vs_univ.

    A candidate passes when, on at least ``MIN_WINS`` of the start offsets, its
    excess return over the equal-weight universe is higher than the baseline's at
    the same offset, and its mean excess is > 0. The passing candidate with the
    highest mean excess is chosen (ties: ``CANDIDATES`` order); none -> baseline.
    """
    needed = {"candidate", "offset", "excess_vs_univ"}
    if not needed <= set(phases.columns):
        raise ValueError(f"phases needs columns {sorted(needed)}")
    wide = phases.pivot(index="offset", columns="candidate", values="excess_vs_univ")
    missing = [c for c in CANDIDATES if c not in wide.columns]
    if missing or sorted(wide.index) != list(PHASE_OFFSETS):
        raise ValueError(f"phases must hold every candidate at every offset; missing {missing}")
    base = wide[BASELINE]
    rows = []
    for c in CANDIDATES:
        wins = int((wide[c] > base).sum()) if c != BASELINE else 0
        mean = float(wide[c].mean())
        passed = c != BASELINE and wins >= MIN_WINS and mean > 0
        rows.append({"candidate": c, "wins_vs_baseline": wins, "mean_excess": mean,
                     "min_excess": float(wide[c].min()), "max_excess": float(wide[c].max()), "passes": passed})
    table = pd.DataFrame(rows)
    passing = table[table["passes"]]
    if passing.empty:
        return BASELINE, table
    best = passing["mean_excess"].max()
    return str(passing[passing["mean_excess"] == best]["candidate"].iloc[0]), table


def drop_last_dates(frame: pd.DataFrame, n: int) -> pd.DataFrame:
    """``frame`` without the rows of its last ``n`` trade dates (label purge)."""
    if n <= 0 or frame.empty:
        return frame
    dates = sorted(pd.to_datetime(frame["trade_date"]).unique())
    if n >= len(dates):
        return frame.iloc[0:0]
    return frame[pd.to_datetime(frame["trade_date"]) < dates[-n]]


def m1_training_frames(dataset: pd.DataFrame, end_date: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(fit, internal validation) for M1, using only rows dated TRAIN_START_DATE..``end_date``.

    Internal validation = the last ``INTERNAL_VALIDATION_YEARS`` of that range.
    Both parts lose their last ``PURGE_DAYS`` trade dates so no label reaches the
    next part (fit -> validation, validation -> after ``end_date``).
    Selection run: ``end_date`` = the day before ``DEV_START``. Final run: dev end.
    """
    end = pd.Timestamp(end_date)
    val_start = end - pd.DateOffset(years=INTERNAL_VALIDATION_YEARS) + pd.Timedelta(days=1)
    d = pd.to_datetime(dataset["trade_date"])
    in_range = dataset[(d >= pd.Timestamp(TRAIN_START_DATE)) & (d <= end)]
    dr = pd.to_datetime(in_range["trade_date"])
    fit = drop_last_dates(in_range[dr < val_start], PURGE_DAYS)
    val = drop_last_dates(in_range[dr >= val_start], PURGE_DAYS)
    if fit.empty or val.empty:
        raise ValueError("M1 training range too short for a fit and an internal validation part.")
    return fit, val


def selection_train_end() -> str:
    """Last date M1 may train on during selection: the day before DEV_START."""
    return (pd.Timestamp(DEV_START) - pd.Timedelta(days=1)).date().isoformat()


def dev_needs_forward_evaluation(dev_end: str) -> bool:
    """True when the dev range reaches the forward period (readable only after the one forward look)."""
    return pd.Timestamp(dev_end) >= pd.Timestamp(FORWARD_START)


def decile_spread(part: pd.DataFrame, score_col: str, label_col: str = "target_return_5d") -> float:
    """Mean over dates of (top-decile mean label - bottom-decile mean label). Diagnostic only."""
    spreads = []
    for _, g in part.dropna(subset=[score_col, label_col]).groupby("trade_date"):
        if len(g) < 10:
            continue
        decile = np.ceil(g[score_col].rank(pct=True, method="average") * 10).clip(1, 10)
        top, bottom = g.loc[decile == 10, label_col], g.loc[decile == 1, label_col]
        if len(top) and len(bottom):
            spreads.append(float(top.mean() - bottom.mean()))
    return float(np.mean(spreads)) if spreads else float("nan")


def bottom_avoid_excess(part: pd.DataFrame, score_col: str, frac: float = 0.2,
                        label_col: str = "target_return_5d") -> float:
    """Mean over dates of (mean label without the bottom ``frac`` by score - mean label of all).

    Gross, overlapping 5-day labels, no costs: a diagnostic of item 84 A-1, never a verdict.
    """
    diffs = []
    for _, g in part.dropna(subset=[score_col, label_col]).groupby("trade_date"):
        pct = g[score_col].rank(pct=True, method="average")
        kept = g.loc[pct > frac, label_col]
        if len(kept):
            diffs.append(float(kept.mean() - g[label_col].mean()))
    return float(np.mean(diffs)) if diffs else float("nan")
