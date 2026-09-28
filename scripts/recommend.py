"""Daily recommendation CLI: today's top picks with the reason for each (item 51).

What it does
  1. Rebuilds features from every stock's daily bars, INCLUDING the most recent
     bars (the training dataset drops the last 5 days because their 5-day
     target is unknown -- a live recommendation needs exactly those days).
  2. Scores the latest common trade date T with the frozen daily model of
     scripts/run_ml_backtest.py (train 2002-2019, early stopping 2020-2023H1,
     rank target, IC early stopping, deterministic).
  3. Prints the top N (default 10) with each pick's top 3 TreeSHAP drivers --
     the exact per-feature terms of that pick's score (src/explanation/
     model_attribution.py), with the feature's actual value.
  4. Saves reports/daily_picks/<T>.csv -- a paper-trading log. It is NOT the
     forward holdout evaluation (scripts/evaluate_forward_holdout.py) and must
     not be used to change the model or the strategy before that runs.

Timing (item 46, option A): scores use day T's close; the trade would be
entered at T+1's open and held 5 trading days. The buffered strategy keeps a
held stock while it stays within the top 30 (buffer 3.0 x top 10), so the
file also stores every stock's rank, not only the top 10.

Not included on purpose
  - The intraday overlay (w=0.5) is still a candidate until the forward check
    (items 49/50) -- daily score only.
  - The risk-profile re-ranking (src/recommendation/scoring.py) was designed
    for a model that predicted raw returns; the current model outputs rank-
    scale scores, so its fixed weights would mix incompatible scales. It needs
    recalibration before it is shown (item 51, follow-up).

    STOCKLENS_UNIVERSE=top50 PYTHONPATH=. python scripts/recommend.py
    STOCKLENS_UNIVERSE=top50 PYTHONPATH=. python scripts/recommend.py --top-n 5 --no-save
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from scripts.run_ml_backtest import STOCK_CODES, _load_priced_dataset, train_frozen_model
from src.data.storage import HistoricalStorage
from src.data.universe import TOP50_UNIVERSE_PATH, load_universe_file
from src.explanation.model_attribution import explain_pick, shap_contributions
from src.features.engineering import FEATURE_COLUMNS, build_features

KST = timezone(timedelta(hours=9))
MIN_COVERAGE = 0.9  # latest date must have bars for >= 90% of the universe
EXPECTED_BEST_ITERATION = 9


def stock_names() -> dict[str, str]:
    try:
        return {s.code: s.name for s in load_universe_file(TOP50_UNIVERSE_PATH)}
    except (OSError, ValueError, KeyError):
        return {}


def live_features() -> pd.DataFrame:
    """Features for every bar of every stock, last days included."""
    storage = HistoricalStorage("data")
    frames = []
    for code in STOCK_CODES:
        bars = storage.load_daily_bars(code)
        if not bars:
            continue
        f = build_features(bars)
        f["stock_code"] = code
        frames.append(f)
    df = pd.concat(frames, ignore_index=True)
    df["trade_date"] = pd.to_datetime(df["trade_date"])
    df[list(FEATURE_COLUMNS)] = df[list(FEATURE_COLUMNS)].replace([np.inf, -np.inf], np.nan)
    return df


def latest_decision_date(df: pd.DataFrame, requested: str | None) -> pd.Timestamp:
    counts = df.groupby("trade_date")["stock_code"].nunique()
    if requested:
        date = pd.Timestamp(requested)
        if date not in counts.index:
            raise SystemExit(f"{requested}: 이 날짜의 봉이 없습니다.")
        return date
    ok = counts[counts >= MIN_COVERAGE * len(STOCK_CODES)]
    return ok.index.max()


def rank_like_engine(scores: pd.Series) -> pd.Series:
    """1 = best. Ties go to the lower stock code, as in src/backtest (stable sort
    over codes in ascending order)."""
    order = sorted(scores.index, key=lambda c: (-round(float(scores[c]), 9), str(c)))
    return pd.Series(range(1, len(order) + 1), index=order).reindex(scores.index)


def staleness_warning(date: pd.Timestamp) -> str | None:
    """Warn when the newest bar is older than the last finished weekday session."""
    now = datetime.now(KST)
    last_session = now.date() if now.hour >= 16 else (now - timedelta(days=1)).date()
    while last_session.weekday() >= 5:
        last_session -= timedelta(days=1)
    if date.date() < last_session:
        return (
            f"주의: 가장 최근 일봉이 {date.date()} 입니다(마지막 장 마감일 {last_session}). "
            "휴장일이 아니라면 일봉을 먼저 갱신하세요:\n"
            "  STOCKLENS_UNIVERSE=top50 PYTHONPATH=. python scripts/ingest_kiwoom_daily_chart_batch.py"
        )
    return None


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--top-n", type=int, default=10)
    ap.add_argument("--date", default=None, help="YYYY-MM-DD (default: latest date with enough bars)")
    ap.add_argument("--out", default="reports/daily_picks")
    ap.add_argument("--no-save", action="store_true")
    args = ap.parse_args()

    trained, _ = train_frozen_model(_load_priced_dataset())
    if trained.best_iteration != EXPECTED_BEST_ITERATION:
        print(f"주의: 고정 모델 best_iteration={trained.best_iteration} (기대값 {EXPECTED_BEST_ITERATION}). "
              "학습 데이터나 코드가 바뀌었는지 확인하세요.")

    feats = live_features()
    date = latest_decision_date(feats, args.date)
    day = feats[feats["trade_date"] == date].set_index("stock_code")
    cols = list(trained.feature_columns)
    day = day[day[cols].notna().sum(axis=1) >= len(cols) - 2]  # skip stocks without enough history

    day["score"] = trained.model.predict(day[cols])
    # Same order the backtest engines use: sorted(scores, key=score, reverse=True)
    # over stocks in ascending code order, i.e. ties go to the lower stock code.
    # The depth-2, 9-round model yields only ~8 distinct scores a day, so ties
    # are common (item 51) -- the rule must match what was backtested.
    day["rank"] = rank_like_engine(day["score"])
    day["tie_size"] = day.groupby(day["score"].round(9))["score"].transform("size").astype(int)
    day["percentile"] = day["score"].rank(pct=True)
    contribs = shap_contributions(trained, day)
    gap = float((contribs.sum(axis=1) - day["score"]).abs().max())
    if gap > 1e-4:
        raise SystemExit(f"TreeSHAP 합이 점수와 {gap:.2e} 차이납니다 -- 설명을 신뢰할 수 없어 중단합니다.")

    names = stock_names()
    n = len(day)
    picks = day.sort_values("rank").head(args.top_n)

    warn = staleness_warning(date)
    print("=" * 78)
    print(f"StockLens 추천 — 판단일 {date.date()} 종가 기준, 다음 거래일 시가 진입 · 5거래일 보유")
    print(f"고정 daily 모델(best_iteration={trained.best_iteration}), {n}종목 중 상위 {len(picks)}")
    print("=" * 78)
    if warn:
        print(warn + "\n")

    rows = []
    for code, r in picks.iterrows():
        exp = explain_pick(
            stock_code=code, name=names.get(code, code), rank=int(r["rank"]), score=float(r["score"]),
            percentile=float(r["percentile"]), n_stocks=n, features=r[cols], contributions=contribs.loc[code],
        )
        text = exp.text
        if int(r["tie_size"]) > 1:
            text += (f"\n  · 같은 점수 {int(r['tie_size'])}종목 — 백테스트와 같은 규칙"
                     "(종목코드 오름차순)으로 순위를 정함")
        print(text + "\n")
    for code, r in day.sort_values("rank").iterrows():
        top3 = contribs.loc[code].drop("bias").abs().sort_values(ascending=False).index[:3]
        rows.append({
            "trade_date": date.date(), "rank": int(r["rank"]), "stock_code": code,
            "name": names.get(code, code), "score": float(r["score"]), "tie_size": int(r["tie_size"]),
            "top_drivers": ";".join(f"{f}:{contribs.loc[code, f]:+.4f}" for f in top3),
        })

    print("읽는 법: 랭킹 점수는 '5일 뒤 수익률 순위'에 대한 모델의 상대 점수입니다(예상 수익률 % 아님).")
    print("각 줄은 그 종목 점수를 가장 크게 움직인 feature와 실제 값, 기여 크기(TreeSHAP)입니다.")
    n_tied = int((day["score"].round(9) >= round(float(picks["score"].min()), 9)).sum())
    if n_tied > len(picks):
        print(f"동점 주의: {len(picks)}위 점수 이상인 종목이 {n_tied}개입니다. 모델 점수 종류가 적어서 "
              "상위권 일부는 동점 처리 규칙으로 정해집니다.")
    print("검증 상태: 이 모델의 표본 밖 성과 확인은 2027년 1월 forward 평가 전까지 미완료입니다. 투자 권유가 아닙니다.")

    if not args.no_save:
        out = Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        path = out / f"{date:%Y%m%d}.csv"
        pd.DataFrame(rows).to_csv(path, index=False, encoding="utf-8-sig")
        print(f"\n저장: {path} (전 종목 순위 포함)")


if __name__ == "__main__":
    main()
