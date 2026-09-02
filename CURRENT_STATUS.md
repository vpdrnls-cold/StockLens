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
