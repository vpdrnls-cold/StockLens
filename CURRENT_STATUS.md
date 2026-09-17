StockLens Current Project Status

  This file is a mutable project-state record. Update it whenever a
  meaningful implementation task is completed. Do NOT use this file as
  the permanent project rulebook. Permanent development rules belong in
  AGENTS.md.

------------------------------------------------------------------------

1. Current Project Goal

StockLens is being developed as a personalized stock analysis and
recommendation system.

The eventual product goal is:

User investment-profile questionnaire → analyze stocks using available
market information → produce stock-level signals/predictions →
personalize ranking according to the user’s investment style → return a
Top 5 recommendation with explanations.

The final vision may later include intraday data, news, macroeconomic
data, and user-behavior feedback.

However, these are NOT part of the current MVP implementation scope.

------------------------------------------------------------------------

2. Current MVP Scope

The current MVP is intentionally limited.

MVP target

Build and evaluate a daily OHLCV-based stock analysis / prediction
pipeline that can answer:

  Can technically engineered features from historical daily stock data
  produce a useful out-of-sample predictive signal, and can an ML model
  perform meaningfully compared with a simple rule-based baseline?

The MVP ends at:

-   reliable historical daily data
-   deterministic technical feature engineering
-   clearly defined prediction target
-   leakage-safe temporal dataset construction
-   rule-based baseline
-   feature selection
-   ML model
-   out-of-sample evaluation / comparison against the baseline

Do NOT expand into intraday, news, macro, personalization, or real-time
architecture before the MVP has been properly evaluated, unless the
project scope is explicitly changed.

------------------------------------------------------------------------

3. Completed Work

3.1 Kiwoom REST API Integration

Status: COMPLETE

Implemented and verified:

-   Kiwoom authentication
-   production REST API communication
-   current stock quote retrieval
-   daily chart retrieval (ka10081)
-   API response handling / normalization
-   API error handling
-   diagnostic handling
-   tests using mocked responses

Real API communication has been successfully verified.

------------------------------------------------------------------------

3.2 Daily Historical Data Collection

Status: COMPLETE, subject to data-quality verification/recollection

Five stocks have been collected:

-   000660
-   005380
-   005930
-   035420
-   035720

Most recent observed dataset size:

-   approximately 601 daily bars per stock
-   approximately 2024-03-13 through 2026-09-01

The exact range/row count may change after historical-data cleanup.

------------------------------------------------------------------------

3.3 Important Data-Quality Discovery

Status: DISCOVERED / NEEDS TO BE ACCOUNTED FOR

A ka10081 daily-chart request made during market hours can contain the
current day’s incomplete candle.

Example:

An API response observed during 2026-08-31 contained a still-forming
daily candle whose OHLCV differed from the final completed 2026-08-31
candle.

This is expected behavior for a real-time/current-date request and is
NOT evidence that the Kiwoom API is necessarily incorrect.

Required distinction:

Historical training/backtesting

Use completed daily candles unless the model explicitly simulates an
intraday decision timestamp.

Real-time inference

A future version of StockLens may use the current in-progress candle
when the prediction is explicitly defined at that current timestamp.

Therefore, do NOT impose a blanket rule that the live system must always
use yesterday’s data.

------------------------------------------------------------------------

4. Current Feature Engineering

Status: COMPLETE

Current daily technical feature pipeline produces approximately 25
features.

Returns

-   return_1d
-   return_5d
-   return_10d
-   return_20d

Price / Candle

-   intraday_return
-   high_low_range
-   gap

Trend

-   sma_5
-   sma_20
-   sma_60
-   price_to_sma_5
-   price_to_sma_20
-   price_to_sma_60

Momentum

-   rsi_14
-   roc_10
-   roc_20
-   macd
-   macd_signal
-   macd_hist

Volatility

-   volatility_5
-   volatility_20
-   atr_14

Volume

-   volume_change_1d
-   volume_sma_20
-   volume_ratio_20

Tests exist for important feature calculations, date ordering, returns,
moving averages, and warm-up NaNs.

------------------------------------------------------------------------

5. Current Dataset / ML Status

Status: NOT YET READY FOR FINAL FEATURE SELECTION

The technical features exist, but the ML problem must be finalized
before blindly applying Feature Selection.

Still to define/verify:

1.  Prediction target
2.  Prediction horizon
3.  Exact decision timestamp
4.  Label construction
5.  Historical information availability
6.  Temporal train/validation/test split
7.  Leakage-safe preprocessing
8.  Rule-based baseline definition
9.  Evaluation metrics
10. Backtesting assumptions

Do NOT select features using the entire dataset before these decisions
are established.

------------------------------------------------------------------------

6. Immediate Next Work

The next work should be performed in this order.

Step 1. Verify historical data quality

Check that the historical dataset contains only appropriate completed
bars for the intended daily decision model.

Check:

-   duplicate dates
-   missing dates
-   malformed values
-   impossible OHLC relationships
-   incomplete current-day bars
-   data consistency across the five stocks

If necessary, recollect the historical dataset.

------------------------------------------------------------------------

Step 2. Define the prediction problem

Explicitly decide:

Decision timestamp

Example:

“After the daily market close.”

or another explicitly defined time.

Target

Possible examples:

-   next-day return
-   future N-day return
-   probability of positive future return
-   threshold-exceedance probability

Horizon

Possible examples:

-   next trading day
-   next 5 trading days
-   next 20 trading days

Do not choose arbitrarily.

The target/horizon must make sense for the intended MVP.

------------------------------------------------------------------------

Step 3. Build the leakage-safe dataset

Construct:

Features at time t → target representing future outcome after t

Ensure:

-   no future price information in features
-   no future volume
-   no future labels
-   no future-derived normalization
-   no random time-series shuffling
-   preprocessing fitted only using appropriate training data

------------------------------------------------------------------------

Step 4. Establish Rule-Based Baseline

Create a simple explainable baseline before complex ML.

The baseline should rank stocks using a transparent set of technical
signals.

Exact weights/rules should be treated as experimental parameters and
evaluated rather than assumed to be optimal.

------------------------------------------------------------------------

Step 5. Temporal Split

Use chronological train/validation/test separation.

Do not randomly shuffle ordinary time-series observations.

Keep the final test period as an out-of-sample evaluation set.

------------------------------------------------------------------------

Step 6. Feature Selection

Only after Steps 1-5 are sufficiently defined.

Initial Filter Method candidates:

-   missingness / constant checks
-   feature-target correlation
-   mutual information
-   feature-feature correlation
-   redundancy removal
-   temporal stability

Feature Selection must be fitted/decided using training information
only.

Do NOT use the final test set to choose features.

------------------------------------------------------------------------

Step 7. ML Model

Train a reproducible ML model using the selected features.

Evaluate:

-   validation performance
-   untouched test performance
-   recommendation usefulness where applicable
-   comparison with the rule-based baseline

Do not claim success from training accuracy.

------------------------------------------------------------------------

Step 8. MVP Evaluation

The MVP is complete only when we can answer:

-   Does the model generalize out of sample?
-   Does it beat or meaningfully complement the rule-based baseline?
-   Is the improvement stable?
-   Does it produce useful ranking/recommendation behavior?
-   Are the results robust to reasonable evaluation assumptions?
-   Is there any remaining leakage or data-quality issue?

If the answer is no, diagnose and improve the MVP before expanding
scope.

------------------------------------------------------------------------

7. Future Work, NOT CURRENT SCOPE

These are possible post-MVP extensions.

They should not be treated as currently implemented.

Intraday

Kiwoom provides separate minute-chart data.

Potential future data:

-   1-minute
-   3-minute
-   5-minute
-   10-minute
-   15-minute
-   30-minute
-   45-minute
-   60-minute

Daily bars cannot be reconstructed into exact minute bars.

Intraday data would support:

-   current momentum
-   short-term volatility
-   unusual volume
-   short-horizon prediction

------------------------------------------------------------------------

News

Potential future signals:

-   news volume
-   sentiment
-   event type
-   event severity
-   relevance
-   recency

Historical news must be aligned to the actual time it was available.

------------------------------------------------------------------------

Macro / Market Data

Potential future inputs:

-   interest rates
-   USD/KRW
-   oil
-   gold
-   KOSPI/KOSDAQ
-   global indices
-   other useful macro variables

Historical availability/timestamps must be respected.

------------------------------------------------------------------------

Integrated Model

Future architecture may combine:

Daily features + Intraday features + News signals + Macro signals →
integrated prediction/scoring → recommendation ranking.

The current daily model is not wasted if this happens.

It can become:

-   a baseline
-   a daily/medium-term signal
-   a component of the final model
-   a source of features/signals

The final integrated model may require retraining after new data sources
are added.

------------------------------------------------------------------------

Personalization

Future system:

Questionnaire → initial user profile → personalized ranking.

Later, if sufficient data is collected:

User actions / preferences / outcomes → observed behavioral profile →
refined personalization.

The system should not force every user to receive different stocks.

The objective is to rank stocks appropriately for each user, even if
some users receive overlapping recommendations.

------------------------------------------------------------------------

Real-Time Recommendation

Future target behavior:

User runs StockLens at a specific current time → current market snapshot
→ latest available external information → feature update →
prediction/scoring → personalization → Top 5 → explanation.

Real-time inference may use an in-progress candle if the prediction
problem is explicitly defined at that timestamp.

Historical training must still respect the information set that would
have existed at each historical timestamp.

------------------------------------------------------------------------

User Feedback / Outcome Learning

Potential future feedback loop:

Recommendation → user views/chooses → optional purchase/position
information → holding period → exit → return / drawdown / outcome →
observed preference → personalization update.

Do NOT immediately change the market prediction model after one
successful or failed trade.

User behavior is noisy.

Market prediction and user-preference learning should remain
conceptually separate.

------------------------------------------------------------------------

8. Current Project Position

Current state:

Kiwoom API → COMPLETE

Historical daily data → COLLECTED / DATA QUALITY VERIFICATION NEEDED

Daily feature engineering → COMPLETE

Prediction problem → CURRENT NEXT DESIGN TASK

Rule-based baseline → NOT YET COMPLETE

Feature Selection → NOT YET STARTED

ML model → NOT YET STARTED

Out-of-sample evaluation → NOT YET STARTED

MVP completion → NOT YET REACHED

Post-MVP intraday/news/macro/personalization/real-time → FUTURE ONLY

------------------------------------------------------------------------

9. Current Priority

The immediate priority is NOT:

-   minute data collection
-   news APIs
-   macro APIs
-   real-time architecture
-   user behavior learning
-   sophisticated personalization
-   complex model ensembles

The immediate priority is:

Historical data validation → prediction target → decision timestamp →
leakage-safe dataset → rule-based baseline → temporal evaluation design
→ Feature Selection → ML → out-of-sample comparison.

Do not expand scope merely because the final product vision contains
those capabilities.

------------------------------------------------------------------------

10. Update Policy

Whenever a meaningful project task is completed:

1.  Update this file.
2.  Move the relevant item from “next” to “completed.”
3.  Record important discoveries or unresolved issues.
4.  Keep future ideas clearly separated from implemented functionality.
5.  Do not rewrite AGENTS.md just to update progress.

This file should remain a concise, machine-readable snapshot of the
current implementation state.

11. **평가지표(Metrics) 구현 및 테스트 완료**
- ML 모델의 예측 성능을 평가하기 위한 기본 회귀 평가지표를 구현함.
- `RMSE(Root Mean Squared Error)`를 포함한 평가 함수를 작성하고 단위 테스트를 수행함.
- RMSE 계산 과정에서 테스트 기대값과 실제 수학적 계산값의 불일치를 확인하고 수정함.
- 최종적으로 전체 metrics 테스트가 `5 passed`로 통과하여 구현된 평가지표의 기본 동작을 검증함.
- 향후 모델 학습 및 검증 단계에서는 단일 지표만으로 판단하지 않고, 문제의 목적에 맞는 여러 평가 지표를 함께 사용해야 함.
12. **ML 데이터셋 구축 준비 및 Feature Selection 단계 진입**
- 기존의 일별 OHLCV 데이터와 약 25개의 기술적 feature를 기반으로 ML 학습용 데이터셋을 구성하는 작업을 진행함.
- 현재 feature들은 최종 feature set이 아니라, Feature Selection을 통해 유용성·중복성·안정성을 검토해야 하는 후보 feature 집합으로 정의함.
- Feature Selection은 전체 데이터를 한꺼번에 사용하면 미래 정보가 학습 과정에 유입될 수 있으므로, 이후 정의할 시간 순서 기반 Train/Validation/Test 구조 안에서 수행하도록 설계함.
13. **현재 단계에서의 핵심 과제 정리**
- 현재까지 **Kiwoom API 연동 → 과거 일별 데이터 수집 → 데이터 품질 이슈 확인 → 기술적 Feature Engineering → 관련 테스트 → Metrics 테스트**까지 진행함.
- 다음 단계는 단순히 모델을 바로 학습시키는 것이 아니라, 먼저 **예측 대상(Target), 예측 기간(Horizon), 의사결정 시점(Decision Timestamp)**을 명확하게 정의하는 것임.
- 이후 해당 정의에 맞춰 **미래 정보가 포함되지 않는 Leakage-safe ML Dataset**을 구축하고, 시간 순서를 유지한 Train/Validation/Test 분할을 적용해야 함.
- 그 다음 **Rule-based Baseline → Feature Selection → ML Model → Out-of-Sample Evaluation** 순서로 진행하여 ML 모델이 단순한 기준 전략보다 실제로 유용한지를 검증할 예정임.

14. **ML 백테스트 손실 원인 진단 (IC 분석) 및 SELECTED_FEATURES 임시 확장**

- 문제 상황: `scripts/run_ml_backtest.py`로 5개 selected feature(`price_to_sma_5, price_to_sma_60, macd_hist_pct, volatility_20, atr_pct`) 기반 XGBoost 전략을 테스트 기간(2023-07~2026-09)에 돌린 결과, 누적수익률 -28.55%로 룰베이스 모멘텀 baseline(+24.08%)에 크게 뒤짐.
- 원인 진단(IC): 예측값과 실제 `target_return_5d`의 cross-sectional rank IC를 계산한 결과 평균 -0.0280, IC>0인 날 비율 43.62%(동전던지기 이하)로 랭킹 신호가 사실상 없음을 확인. 000660 제외 4종목 재실행 시에도 -0.0136 / 46.76%로 크게 개선되지 않아, **손실 원인이 특정 종목(000660) 쏠림이 아님**을 확인함.
- 근본 원인: 현재 5개 feature는 애초에 Filter/Wrapper/Embedded로 정식 검증된 적이 없음 — 원래 Wrapper 승자(sma_5, sma_60, macd_hist, atr_14 등 raw-price-scale 피처)가 종목 간 가격 스케일 차이를 랭킹 신호로 오인하는 버그가 있었고, 그 수정(scale-free 버전으로 교체)은 재검증 없이 적용됐으며, 이후 학습 데이터 범위가 601개 bar(2024-03~2026-09)에서 전체 이력(2002-10~2026-09)로 확장되면서 그마저도 다른 데이터 체제에서 그대로 재사용되고 있었음.
- 검증: raw-scale 8개(`sma_5, sma_20, sma_60, macd, macd_signal, macd_hist, atr_14, volume_sma_20`)를 제외한 scale-free 19개 후보 전체로 넓혀 validation 구간에서 하이퍼파라미터·feature subset을 스캔(교차검증은 validation만 사용, test는 최종 확인 1회만 — AGENTS.md 13절 원칙 준수). Default 하이퍼파라미터가 최적이었고, feature set을 19개로 넓힌 것이 유일하게 유의미한 개선(validation cross-sectional IC +0.0179 → +0.0289).
- 조치: `src/features/engineering.py`의 `SELECTED_FEATURES`를 scale-free 19개 후보 전체로 임시 확장(브루트포스 — 정식 Feature Selection 재실행 아님). Test 기간 1회 확인 결과 ML 전략 누적수익률 -28.55% → **+3.42%**, Hit Rate 51.95% → 52.60%, MDD -43.32% → -38.21%로 개선됐으나, 여전히 룰베이스 baseline(+24.08%)에는 못 미침.
- 다음 단계(미완료): (1) 지금의 19개 전체 사용은 정식 선택이 아니므로, raw-scale 8개를 제외한 후보로 Filter/Wrapper/Embedded를 cross-sectional IC 기준으로 재실행할 것. (2) 그래도 baseline을 못 넘으면 가격/변동성 기반 feature의 한계로 보고 Phase H~J(뉴스·매크로·거래량 심화)로 진행할 것.

15. **Feature Selection 재실행(Filter/Wrapper/Embedded, cross-sectional IC 기준) — 안정적 개선 없음 확인, MVP 결론 및 scope 확장 결정**

- `scripts/feature_selection_ic_rerun.py` 작성: scale-free 19개 후보에 대해 Filter(개별 feature 표준 IC 랭킹), Wrapper(cross-sectional IC 기준 순방향 탐색), Embedded(XGBoost gain importance) 세 방식을 재실행. 항상 validation으로만 비교하고 test는 최종 확인 1회만 사용(AGENTS.md 13절 원칙 준수).
- 단일 validation 구간(2020-2023) 결과: Filter/Embedded는 결국 19개 전체가 최선이었고, Wrapper만 `atr_pct + gap` 2개 조합으로 validation IC +0.0464(19개 전체 대비 +0.0289보다 높음)를 찾음. Test 1회 확인 시 IC +0.0439, IC>0 비율 51.80%로 처음으로 50%를 확실히 넘김. 다만 실제 백테스트에서는 누적수익률 +15.47%(19개 전체 +3.42%보다 높음)이나 Hit Rate 47.40%(19개 전체 52.60%보다 낮음), MDD -56.17%(19개 전체 -38.21%보다 나쁨, baseline -55.11%과 비슷한 수준)로 트레이드오프 존재.
- **재현성 문제 발견**: 동일 코드·동일 데이터를 다른 기기에서 실행하니 Wrapper 승자가 다르게 나옴(`atr_pct+gap` vs `return_20d`). XGBoost 히스토그램 트리 학습이 `n_jobs=-1`일 때 스레드별 부분합 순서가 기기(코어 수)에 따라 달라져 `random_state` 고정에도 결과가 갈릴 수 있음을 확인. `DETERMINISTIC_PARAMS={"n_jobs":1}`로 고정했으나 **그래도 기기 간 차이가 해소되지 않음** — 즉 원인이 스레딩이 아니었음.
- **`scripts/walk_forward_wrapper.py`로 근본 원인 확인**: 같은 기기 하나에서 train/validation 경계만 다르게 3개 구간(2012-2015, 2016-2019, 2020-2023.06)으로 잘라 같은 Wrapper 탐색을 반복한 결과, 매번 다른 승자가 나옴 — `return_5d`(IC +0.0885) → `price_to_sma_5, atr_pct`(IC +0.0528) → `atr_pct, gap`(IC +0.0464). `atr_pct`만 2/3 구간에서 재등장했을 뿐 안정적인 단일 승자는 없었고, IC 크기 자체도 구간이 최근으로 올수록 계속 감소함(시장 효율화/알파 감쇠 가능성 — 추가 검증 없이는 가설 수준).
- **결론**: 기기 간 재현성 문제와 시간 구간 간 불안정성 문제가 동시에 존재하며, 후자가 근본 원인 — 즉 Wrapper가 찾아내는 "승자"는 그 구간에 특화된 노이즈이지 안정적인 신호가 아님. Filter/Embedded도 결국 19개 전체가 최선이라고 판단한 것과 일관됨.
- **MVP 평가(본 문서 8절 기준) 결론**: "daily OHLCV 기반 feature만으로 baseline 대비 안정적으로 우월한 랭킹 신호를 만들 수 있는가?"에 대한 답은 현재로선 **아니오**. 5→19개 확장은 실질적 개선이었으나, 그 이상으로 더 쪼개거나 선택을 정교화하는 시도는 세 시간구간·두 기기에서 반복 검증한 결과 효과가 없음이 확인됨.
- **조치**: `SELECTED_FEATURES`는 19개 scale-free 전체로 유지(변경하지 않음, 이미 이 상태로 커밋됨). Wrapper/Filter/Embedded로 더 쪼개려는 시도는 여기서 종료. 본 문서 9절("만약 답이 아니오면, scope를 넓히기 전에 MVP를 진단하고 개선하라")에 따라, daily 기술적 feature만으로는 진단·개선을 충분히 시도했다고 보고 **Phase H(인트라데이) 이후로 scope 확장을 진행**하기로 결정.
- **결정 재검토 (항목 16 참고)**: 위에서 Phase H로 바로 넘어가기로 했던 결정은, 최종 산출물의 형태(개인화 재랭킹, 보유 종목 HOLD/SELL 판단)가 아직 전혀 구현되지 않은 상태에서 내려진 것이었음을 재훈이 다시 짚었고, 재검토 끝에 이 두 레이어를 먼저 구현하는 것으로 순서를 바꿈. 자세한 내용은 항목 16 참고.

16. **개인화 재랭킹 레이어 + 보유 종목 HOLD/SELL 판단 레이어 최초 구현**

- **배경**: 재훈이 최종 산출물의 형태에 대한 방향성을 다시 점검하면서, (a) 공격형/안정형 등 투자성향별 추천 차별화, (b) 사용자가 매수가를 입력하면 그에 맞춰 보유 종목을 HOLD/SELL 판단해주는 기능, 이 두 가지가 원래 비전에 있었지만 아직 구현되지 않았음을 확인함. AGENTS.md 5절(로드맵)에는 개인화(Phase L)가 인트라데이/뉴스/매크로(Phase H~K)보다 뒤에 있지만, 개인화/HOLD-SELL "레이어의 배관"은 어떤 신호가 들어오든 그 위에 얹는 별도 구조(AGENTS.md 9·10절)이므로, 데이터 소스 확장을 건너뛰는 것이 아니라 소비자 레이어를 먼저 만들어두는 것으로 판단하여 순서를 조정함.
- **개인화 재랭킹 레이어** (`src/recommendation/scoring.py`): AGENTS.md 9절의 conservative/neutral/aggressive 예시를 그대로 따라 `RiskProfile` 및 `PROFILES` 정의. `personalized_score = predicted_return + momentum_weight*price_to_sma_5 + volume_weight*(volume_ratio_20-1) - risk_weight*volatility_20`. neutral은 가중치 전부 0 → 기존 모델 예측값과 완전히 동일. 모델 재학습이나 새 feature 계산 없이, 이미 존재하는 scale-free feature만 재조합함(AGENTS.md 9절 "personalization은 객관적 시장 신호 자체를 왜곡하면 안 된다" 준수). `personalize_scores()`, `top_n_recommendations()`, `make_profile_score_fn()`(기존 `src/ml/strategy.make_model_score_fn`과 동일한 인터페이스로 백테스트 엔진 재사용) 구현.
- **가중치 검증**: AGENTS.md 9절 "이 가중치를 임의로 하드코딩하고 과학적으로 타당하다고 하지 마라 — 백테스트로 실제 효과를 확인하라"는 원칙에 따라, `scripts/evaluate_personalization.py`로 validation 구간에서 3개 프로필을 실제 백테스트 엔진에 태워 비교. 결과: neutral 대비 conservative는 기간별 수익률 표준편차 3.96%→3.52%(하락, 의도대로 안정적), aggressive는 3.96%→4.33%(상승, 의도대로 변동성 높음) — 의도한 방향으로 실제 차별화가 확인됨(수익률 자체를 개선하려는 목적이 아니라, 프로필이 실제로 다른 리스크 프로파일을 만드는지 확인하는 것이 목적).
- **보유 종목 HOLD/SELL 판단 레이어** (`src/portfolio/optimizer.py`): 원래 로드맵의 "Phase 4: 동적 투자 판단(상승확률·목표가·위험가 기반 HOLD/SELL/BUY 로직)"을 CURRENT_STATUS.md 자체의 "User Feedback / Outcome Learning" 원칙("한 번의 거래로 시장 예측 모델을 즉시 바꾸지 마라")에 맞게 구현. 모델 재학습 없이, 이미 계산된 예측치(`predicted_return`)와 `atr_pct`만으로 두 가지 규칙 적용: ① 손절(stop-loss) — 보유 수익률이 그 종목 자체의 ATR% 기반 임계값(기본 3×ATR%) 밑으로 떨어지면 모델 예측과 무관하게 SELL, ② 신호 반전 — 손절선 이내라도 모델이 더 이상 양의 수익률을 예측하지 않으면 SELL, ③ 그 외 HOLD. 모든 판단에 근거 수치(`unrealized_return`, `stop_loss_threshold`, `predicted_return`)를 함께 반환하여 설명 가능(AGENTS.md 24절)하게 구성.
- **테스트**: `tests/test_recommendation_scoring.py`(11개), `tests/test_portfolio_optimizer.py`(7개) 신규 작성. 전체 테스트 스위트 94→113개 전부 통과.
- **AGENTS.md 보강**: 이번 프로젝트에서 실제로 겪은 문제 중 앞으로도 재발 가능한 일반 원칙 3가지를 12절(cross-sectional 모델에 raw-scale/scale-free 피처를 섞지 말 것 + 단일 validation split만으로 feature subset을 채택하지 말고 walk-forward로 확인할 것), 22절(cross-sectional rank IC를 기본 평가지표로 사용할 것 + 최소 유효 일수 기준), 25절(XGBoost 등 히스토그램 기반 모델의 멀티스레드 비결정성 및 n_jobs=1 고정 권고)에 추가.
- **다음 단계(미완료)**: (1) 실제 추천 결과를 사용자에게 보여주는 explanation/UI 레이어는 아직 없음 — `top_n_recommendations()`와 `evaluate_position()`의 출력을 사람이 읽는 설명으로 변환하는 작업이 남음. (2) HOLD/SELL 규칙의 파라미터(3×ATR% 손절 등)도 개인화 가중치와 마찬가지로 임의 초기값이며 아직 백테스트로 검증되지 않음. (3) Phase H(인트라데이) 착수 여부는 이 레이어들이 실사용 가능한 수준으로 다듬어진 뒤 다시 논의하기로 함.
