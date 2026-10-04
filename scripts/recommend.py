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

Buffered holdings (item 66)
  The backtested / forward-evaluated strategy keeps a held stock while it stays in
  the top 30 (buffer 3.0 x top 10), so its holdings differ from the plain top-N.
  A neutral run therefore also prints the strategy's holdings for T, recomputed by
  replaying the earlier neutral logs' rankings with the engine's own rule
  (src/portfolio/paper_holdings.py), and stores them as ``held_buffered``.

Risk profiles (item 56)
  --profile conservative | aggressive re-ranks with src/recommendation/scoring.py:
  z(model) + lambda * profile tilt, lambda calibrated on the frozen model's
  TRAIN period (mean rank corr with the model ranking = 0.8; no returns used).
  Both passed the item 56 validation check (direction + signal kept). The
  default stays neutral (= the model ranking), and ONLY the neutral run writes
  the paper-trading log reports/daily_picks/<T>.csv -- that log is the record
  of the pre-registered strategy. Profile runs save to
  reports/daily_picks_<profile>/ instead.

    STOCKLENS_UNIVERSE=top50 PYTHONPATH=. python scripts/recommend.py
    STOCKLENS_UNIVERSE=top50 PYTHONPATH=. python scripts/recommend.py --top-n 5 --no-save
    STOCKLENS_UNIVERSE=top50 PYTHONPATH=. python scripts/recommend.py --profile conservative
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from scripts.run_ml_backtest import (
    BUFFER_MULTIPLIER,
    STOCK_CODES,
    TOP_N,
    _load_priced_dataset,
    frozen_model_matches,
    train_frozen_model,
)
from src.data.session import intraday_bar_error
from src.data.storage import HistoricalStorage
from src.data.universe import TOP50_UNIVERSE_PATH, load_universe_file
from src.explanation.model_attribution import explain_pick, shap_contributions
from src.portfolio.paper_holdings import HoldingStep, load_logged_rankings, replay_holdings, schedule_gaps
from src.features.engineering import FEATURE_COLUMNS, build_features
from src.ml.strategy import predictions_for_dataset
from src.recommendation import survey
from src.recommendation.scoring import PROFILES, calibrate_lambda, personalize_scores

KST = timezone(timedelta(hours=9))
MIN_COVERAGE = 0.9  # latest date must have bars for >= 90% of the universe
EXPECTED_BEST_ITERATION = 9
PROFILE_SIGNAL_COLUMNS = ["trade_date", "stock_code", "volatility_20", "price_to_sma_5", "volume_ratio_20"]
PROFILE_LABELS = {"conservative": "안정형", "neutral": "중립형", "aggressive": "공격형"}


def profile_lambda(trained, splits, profile: str) -> float:
    """Tilt strength from the frozen model's TRAIN rows only (item 56)."""
    if profile == "neutral":
        return 0.0
    train = splits.train[PROFILE_SIGNAL_COLUMNS].copy()
    train["trade_date"] = pd.to_datetime(train["trade_date"])
    train = train.merge(predictions_for_dataset(trained, splits.train), on=["trade_date", "stock_code"])
    return calibrate_lambda(train, profile)


def apply_profile(day: pd.DataFrame, profile: str, lam: float) -> pd.DataFrame:
    """Add personalized_score + contribution columns for one decision date (index = stock_code)."""
    sig = day.reset_index()[PROFILE_SIGNAL_COLUMNS].assign(predicted_return=day["score"].to_numpy())
    scored = personalize_scores(sig, profile, lam=lam if profile != "neutral" else None).set_index("stock_code")
    cols = ["personalized_score", "contribution_model", "contribution_risk", "contribution_volume"]
    return day.join(scored[cols])


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


def buffered_holdings(day_ranked: list[str], date: pd.Timestamp, log_dir: Path):
    """Strategy holdings for ``date`` (item 66): replay earlier neutral logs, then today.

    Returns (today's step, previous step or None, number of earlier logs, schedule gaps).
    """
    history = load_logged_rankings(log_dir, before=date)
    steps = replay_holdings(history + [(date, day_ranked)], top_n=TOP_N, buffer_multiplier=BUFFER_MULTIPLIER)
    prev: HoldingStep | None = steps[-2] if len(steps) > 1 else None
    return steps[-1], prev, len(history), schedule_gaps([d for d, _ in history] + [date])


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
    ap.add_argument("--profile", choices=sorted(PROFILES) + ["saved"], default="neutral",
                    help="투자성향 재랭킹 (기본 neutral = 모델 순위 그대로, 항목 56). "
                         "saved = scripts/survey.py 로 저장한 진단 결과 사용 (항목 57)")
    args = ap.parse_args()
    if args.profile == "saved":
        try:
            saved = survey.load()
        except FileNotFoundError:
            raise SystemExit("저장된 투자성향이 없습니다. 먼저 실행하세요: PYTHONPATH=. python scripts/survey.py")
        except ValueError as e:
            raise SystemExit(str(e))
        if not saved.eligible:
            raise SystemExit(survey.explain(saved))
        print(f"저장된 투자성향 사용: {survey.PROFILE_LABELS[saved.profile]}({saved.profile}), 진단일 {saved.created_at[:10]}")
        args.profile = saved.profile

    trained, splits = train_frozen_model(_load_priced_dataset())
    if trained.best_iteration != EXPECTED_BEST_ITERATION or not frozen_model_matches(trained):
        print(f"주의: 고정 모델이 기록된 모델과 다릅니다(best_iteration={trained.best_iteration}, "
              f"기대값 {EXPECTED_BEST_ITERATION}, 트리 지문은 config/frozen_daily_model.json). "
              "학습 데이터나 코드·라이브러리가 바뀌었는지 확인하세요. forward 평가는 이 상태로 실행되지 않습니다.")

    feats = live_features()
    date = latest_decision_date(feats, args.date)
    guard = intraday_bar_error(date.date(), datetime.now(KST))  # item 63
    if guard:
        raise SystemExit(guard)
    day = feats[feats["trade_date"] == date].set_index("stock_code")
    cols = list(trained.feature_columns)
    day = day[day[cols].notna().sum(axis=1) >= len(cols) - 2]  # skip stocks without enough history

    day["score"] = trained.model.predict(day[cols])
    # Same order the backtest engines use: sorted(scores, key=score, reverse=True)
    # over stocks in ascending code order, i.e. ties go to the lower stock code.
    # The depth-2, 9-round model yields only ~8 distinct scores a day, so ties
    # are common (item 51) -- the rule must match what was backtested.
    lam = profile_lambda(trained, splits, args.profile)
    day = apply_profile(day, args.profile, lam)
    rank_col = "score" if args.profile == "neutral" else "personalized_score"
    day["rank"] = rank_like_engine(day[rank_col])
    day["tie_size"] = day.groupby(day[rank_col].round(9))[rank_col].transform("size").astype(int)
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
    print(f"투자성향: {PROFILE_LABELS[args.profile]}({args.profile})"
          + ("" if args.profile == "neutral" else f", 성향 반영 강도 λ={lam:.3f} (모델 순위와의 상관 0.8 유지)"))
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
        if args.profile != "neutral":
            text += (f"\n  · 성향 반영: 모델 순위 점수 {r['contribution_model']:+.2f}, "
                     f"변동성 조정 {r['contribution_risk']:+.2f}, 거래량 {r['contribution_volume']:+.2f} "
                     f"→ 최종 {r['personalized_score']:+.2f} (그날 종목 간 표준화 값)")
        if int(r["tie_size"]) > 1:
            text += (f"\n  · 같은 점수 {int(r['tie_size'])}종목 — 백테스트와 같은 규칙"
                     "(종목코드 오름차순)으로 순위를 정함")
        print(text + "\n")

    if args.profile != "neutral":
        print("성향 반영 순위는 모델 점수에 투자성향(변동성·거래량) 기울기를 더한 것입니다. 항목 56 validation에서 "
              "의도한 방향으로 작동하고 모델 신호를 유지하는 것만 확인했고, 수익 개선을 뜻하지 않습니다.")
    print("읽는 법: 랭킹 점수는 '5일 뒤 수익률 순위'에 대한 모델의 상대 점수입니다(예상 수익률 % 아님).")
    print("각 줄은 그 종목 점수를 가장 크게 움직인 feature와 실제 값, 기여 크기(TreeSHAP)입니다.")
    n_tied = int((day[rank_col].round(9) >= round(float(picks[rank_col].min()), 9)).sum())
    if n_tied > len(picks):
        print(f"동점 주의: {len(picks)}위 점수 이상인 종목이 {n_tied}개입니다. 모델 점수 종류가 적어서 "
              "상위권 일부는 동점 처리 규칙으로 정해집니다.")
    held = None
    if args.profile == "neutral":
        step, prev, n_logs, gaps = buffered_holdings(
            [str(c) for c in day.sort_values("rank").index], date, Path(args.out)
        )
        held = step.held
        print("\n" + "-" * 78)
        print(f"평가 대상 전략(top-{TOP_N}, buffer {BUFFER_MULTIPLIER})의 보유 종목 — 이전 기록 {n_logs}개를 같은 규칙으로 재생")
        print("-" * 78)
        for code in day.sort_values("rank").index:
            if code in held:
                tag = "유지" if code in step.carried else "신규"
                print(f"  [{tag}] {names.get(code, code)}({code}) — 오늘 {int(day.loc[code, 'rank'])}위")
        if prev is not None:
            sold = sorted(prev.held - held)
            print("  매도: " + (", ".join(f"{names.get(c, c)}({c})" for c in sold) if sold else "없음"))
        else:
            print("  (첫 기록 — 보유가 없던 상태에서 시작해 상위 10개와 같음)")
        print("위 상위 목록은 그날 순위 그대로이고, 전략은 이미 보유한 종목을 30위 안이면 유지합니다. "
              "실제 전략과 비교할 것은 이 보유 목록입니다.")
        if gaps:
            print("주의: 기록 간격이 벌어진 구간이 있어(" + ", ".join(f"{a:%m-%d}→{b:%m-%d}" for a, b in gaps)
                  + ") 엔진의 5거래일 리밸런싱 일정과 다릅니다.")
    else:
        print("전략과의 차이: 이 목록은 성향을 반영한 그날 순위입니다. 평가 대상 전략(중립, buffer 3.0)의 보유 종목은 "
              "중립 실행에서 확인하세요(항목 66).")
    print("검증 상태: 이 모델의 표본 밖 성과 확인은 2027년 1월 forward 평가 전까지 미완료입니다. 투자 권유가 아닙니다.")

    for code, r in day.sort_values("rank").iterrows():
        top3 = contribs.loc[code].drop("bias").abs().sort_values(ascending=False).index[:3]
        rows.append({
            "trade_date": date.date(), "rank": int(r["rank"]), "stock_code": code,
            "name": names.get(code, code), "score": float(r["score"]), "tie_size": int(r["tie_size"]),
            "top_drivers": ";".join(f"{f}:{contribs.loc[code, f]:+.4f}" for f in top3),
            "profile": args.profile, "personalized_score": float(r["personalized_score"]),
            "held_buffered": (code in held) if held is not None else None,
        })

    if not args.no_save:
        out = Path(args.out if args.profile == "neutral" else f"{args.out}_{args.profile}")
        out.mkdir(parents=True, exist_ok=True)
        path = out / f"{date:%Y%m%d}.csv"
        pd.DataFrame(rows).to_csv(path, index=False, encoding="utf-8-sig")
        print(f"\n저장: {path} (전 종목 순위 포함)")


if __name__ == "__main__":
    main()
