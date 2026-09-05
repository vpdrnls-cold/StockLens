StockLens AGENTS.md

0. Highest-Priority Project Context

StockLens is a personalized, data-driven stock analysis and
recommendation system.

The final product goal is:

  A user answers questions about their investment preferences/risk
  tolerance, StockLens analyzes the current market using historical and
  current market data plus eventually news and macroeconomic
  information, and returns a personalized Top-N stock recommendation
  with reasons.

StockLens is an investment decision-support system, NOT an automatic
trading system.

Never implement real buy/sell order execution unless the project scope
is explicitly changed by the user.

IMPORTANT: Current intended product behavior

The eventual user flow is approximately:

User → investment profile/questionnaire → current market snapshot →
stock-level analysis → daily/longer-term signals → intraday/short-term
signals → news/event signals → macro/market signals → prediction/scoring
→ personalization/re-ranking → Top 5 → explanation of why each stock was
recommended and what risks/signals matter.

Example: If the user is conservative, longer-horizon and
lower-volatility signals should have more influence. If the user is
aggressive and accepts concentrated/high-risk positions, short-term
momentum, unusual volume, event/news-driven opportunities, and
high-upside/high-risk signals may matter more.

This does NOT mean arbitrary hard-coded weights. User-profile effects
and scoring weights must ultimately be evaluated with
experiments/backtesting.

The final system should not be understood as “one ML model predicts the
best stock for everyone.”

The architecture should instead distinguish:

1.  Market/stock signal generation
2.  Prediction or scoring
3.  User-specific personalization/ranking
4.  Explanation

------------------------------------------------------------------------

1. CRITICAL MEMORY / NON-NEGOTIABLE CONTEXT

These rules exist because the project has previously accumulated
confusion around what has already been done and what the final goal is.

1.1 Do NOT forget the actual final goal

The final goal is personalized Top-5 stock recommendation, not merely
stock-price prediction.

The system should eventually use:

-   historical OHLCV
-   technical indicators
-   intraday data
-   news/events
-   interest rates
-   exchange rates
-   oil
-   gold
-   market indices
-   other useful macro/market signals
-   user investment profile

when justified by data availability and backtesting.

1.2 Do NOT tell the user to use Codex

Codex is not available/usable for this user in the current workflow.

Do NOT repeatedly instruct the user to “run this in Codex”, “ask Codex”,
“use Codex”, or otherwise assume Codex availability.

When implementation help is requested, provide instructions/code/patches
that the user can execute in their normal project environment, or use
the tools actually available in the current conversation.

1.3 Do not confuse project conversation with current implementation

Previous discussions may contain plans that were later changed.

Always distinguish:

-   CURRENT IMPLEMENTATION
-   CURRENTLY AGREED DESIGN
-   FUTURE/PLANNED FEATURES
-   OPEN DESIGN QUESTIONS

Do not silently treat a future idea as already implemented.

1.4 Do not prematurely push the project into ML

The project should not jump from technical features directly into a
complex model without first defining:

-   prediction target
-   prediction horizon
-   decision timestamp
-   information available at that timestamp
-   temporal split
-   baseline
-   evaluation/backtesting methodology

Feature Selection must not be treated as an isolated mechanical step.

------------------------------------------------------------------------

2. CURRENT PROJECT STATUS

At the current point in development, the following has been completed or
substantially implemented:

2.1 Kiwoom API

-   Kiwoom REST API authentication works.
-   Real production API communication has been verified.
-   Current quote endpoint integration exists.
-   Daily chart (ka10081) integration exists.
-   Raw Kiwoom responses have been inspected.
-   Tests exist for API request structure, authentication reuse, error
    handling, and daily chart request fields.

The supplied local Kiwoom REST API specification is the authoritative
source for endpoint names, request fields, headers, and response
structures.

2.2 Historical Daily Data

Historical daily data has been collected for five stocks:

-   000660
-   005380
-   005930
-   035420
-   035720

The current historical dataset was approximately:

-   601 daily bars per stock
-   2024-03-13 through 2026-09-01 in the most recent collection

Important: the date range and exact row counts may change after
data-quality fixes/recollection.

2.3 Important historical-data issue discovered

A Kiwoom daily-chart request made during market hours can contain the
current day’s still-forming candle.

Example discovered:

The API response for 2026-08-31 contained approximately:

-   open 249,000
-   high 253,000
-   low 246,000
-   current/close-like value 251,000
-   volume about 6.8M

while the later completed daily candle shown after market close had
different final values.

This was NOT a reason to conclude the Kiwoom API was wrong.

The actual issue was that an in-progress daily candle had been
observed/stored before the trading day was complete.

Therefore:

Historical/training data rule

Historical daily training/backtesting datasets must use completed
candles unless the model is explicitly designed to operate on
in-progress candles at a specific historical timestamp.

Real-time inference rule

Real-time recommendation MAY use the current in-progress candle, because
the user is asking what the system would recommend NOW.

Do NOT “solve” historical data quality by forcing the eventual real-time
system to always use yesterday’s data.

Historical training and real-time inference have different information
states.

------------------------------------------------------------------------

3. CURRENT FEATURE ENGINEERING STATUS

Current daily feature engineering produces approximately 25 technical
features.

Known current feature groups include:

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

Feature-engineering tests exist for deterministic calculations, date
ordering, returns, moving averages, and warm-up NaNs.

These features are NOT automatically “the final feature set.”

Feature Selection must determine which are useful, redundant, unstable,
or unnecessary for the defined target.

------------------------------------------------------------------------

4. CURRENT ARCHITECTURE

Intended responsibility separation:

StockLens ├── application/UI ├── configuration ├── data ├── external
APIs ├── feature engineering ├── recommendation/scoring ├── models ├──
news ├── macro ├── portfolio/personalization └── tests

Expected conceptual source structure:

src/ ├── api/ │ └── kiwoom_client.py ├── data/ │ └── ingestion /
validation / dataset logic ├── features/ │ └── engineering.py ├──
models/ │ └── prediction/model logic ├── recommendation/ │ └──
scoring.py ├── news/ │ └── news collection / signals ├── macro/ │ └──
macro signals ├── portfolio/ │ └── personalization / portfolio analysis
└── utils/ └── configuration and shared utilities

The exact current filesystem must always be inspected before making
assumptions.

Do not create duplicate modules merely because an intended architecture
lists a file that may not yet exist.

------------------------------------------------------------------------

5. OVERALL DEVELOPMENT ROADMAP

The project should evolve approximately as follows:

PHASE A Kiwoom API → raw data retrieval → normalization → validation

PHASE B Historical daily dataset → clean completed daily bars →
deterministic storage → reproducible loading

PHASE C Daily technical feature engineering → current 25-feature
pipeline → validation

PHASE D Define prediction problem → decision timestamp → target →
horizon → label construction → leakage rules

PHASE E Rule-based baseline → explainable signal scores → stock ranking
→ baseline backtest

E-1 Rule/Strategy Research
기존의 공개된 투자 전략 및 논문을 조사하고, 적용 가능한 전략의 수학적 가정과 신호 생성 방식을 이해한다.

E-2 Strategy Hypothesis
사용할 지표, 조건, threshold, weighting 등을 가설로 정의한다.

E-3 Baseline Implementation
전략을 재현 가능하고 설명 가능한 코드로 구현한다.

E-4 Parameter Experimentation
threshold, weighting, holding period 등의 민감도를 검증한다.

E-5 Baseline Backtest
거래비용, 슬리피지 등을 포함해 시간순 백테스트를 수행한다.

E-6 Baseline Selection
최종 test period를 건드리지 않고 validation 결과를 바탕으로 baseline을 확정한다.

PHASE F Feature Selection → performed only within training context →
relevance → redundancy → stability → no future leakage

PHASE G Daily ML model → train → validation → out-of-sample test →
compare against baseline

PHASE H Intraday data → Kiwoom minute data → intraday features →
short-horizon model/signals → appropriate historical timestamp
simulation

PHASE I News → timestamped collection → event/sentiment/relevance
features → historical availability alignment

PHASE J Macro → rates → FX → oil → gold → indices → timestamp alignment

PHASE K Integrated stock scoring → daily → intraday → news → macro →
prediction/risk signals

PHASE L Personalization → questionnaire → investor profile →
profile-aware ranking

PHASE M Real-time recommendation → current snapshot →
cached/pre-collected external information → fast feature update →
inference → ranking → Top 5 → explanation

The phases may overlap, but do not skip foundational validation merely
because a later feature sounds more exciting.

------------------------------------------------------------------------

6. PREDICTION PROBLEM MUST BE DEFINED BEFORE ML

Before building or selecting an ML model, explicitly define:

6.1 Decision timestamp

Example:

“At 2026-09-03 14:00, what information is allowed?”

Possible information:

-   price through 14:00
-   volume through 14:00
-   completed previous daily bars
-   current in-progress daily bar up to 14:00
-   news published before 14:00
-   macro values known before 14:00

Forbidden:

-   prices after 14:00
-   final closing price if it was not known at 14:00
-   news published after 14:00
-   revised/finalized macro information unavailable at 14:00

6.2 Target

Possible targets include:

-   future return
-   future excess return
-   probability of positive return
-   probability of exceeding a threshold
-   risk-adjusted future performance
-   future volatility/drawdown

Do NOT select a target arbitrarily.

6.3 Horizon

Potential horizons:

-   next 1 hour
-   next trading session/day
-   next 5 trading days
-   next 20 trading days

Different horizons may be useful for different investor profiles.

The final system may use multiple prediction horizons instead of forcing
one model to represent all investment styles.

------------------------------------------------------------------------

7. DAILY VS INTRADAY: CRITICAL DESIGN DISTINCTION

Kiwoom provides separate chart endpoints.

The daily chart endpoint (ka10081) is not a compressed version of minute
data.

Minute data must be obtained from the appropriate minute-chart endpoint
(ka10080) when required.

Do NOT take an OHLC daily bar and pretend it can be split back into
exact minute bars.

Daily and intraday data should coexist.

Conceptually:

Daily data → long/medium-term trend, volatility, momentum, regime

Intraday data → current momentum, short-term volatility, unusual volume,
rapid movement

For example:

Daily: - return_20d - RSI - MACD - volatility_20

Intraday: - return_15m - return_1h - intraday volatility - recent volume
ratio - short-term momentum - range expansion

Do not assume that “more rows” automatically means more independent
training information.

Minute observations within a single trading day are highly correlated.

------------------------------------------------------------------------

8. REAL-TIME PRODUCT DESIGN

The eventual real-time workflow is:

User launches StockLens at time T → obtain current market snapshot →
obtain/update current stock data → use current in-progress
intraday/daily information where appropriate → combine with previously
collected historical data → update only necessary features → obtain
latest available news/events → obtain latest available macro signals →
run prediction/scoring → personalize ranking → return Top 5 → generate
explanation from actual signals.

Important:

The real-time system does NOT need to re-download all historical data
every time.

Use:

-   persistent historical data
-   cached data
-   incremental updates
-   pre-collected external information
-   current market snapshot

where appropriate.

Avoid a critical path like:

User clicks → API call 1 → wait → API call 2 → wait → API call 3 → wait
→ API call 4 → calculate everything from scratch.

External data should generally be collected/normalized/cached ahead of
the final recommendation request.

------------------------------------------------------------------------

9. USER PERSONALIZATION

The user profile should influence recommendation ranking, not corrupt
the underlying factual market signals.

A useful conceptual separation:

Market analysis → objective/market-relative signals

Prediction → expected future performance / risk / event likelihood

Personalization → interpret those signals according to the user’s
preferences

Recommendation → final ranking

Example:

Conservative: - favor lower risk - favor stability - favor longer
horizons - penalize extreme volatility - potentially value downside
protection

Neutral/balanced: - balance expected return and risk

Aggressive: - tolerate higher volatility - give more weight to
short-term momentum - consider unusual volume - consider
event/news-driven opportunities - accept greater downside risk

Do not hard-code these as arbitrary weights and call them scientifically
valid.

Use backtesting and experiments to determine whether profile-specific
ranking improves useful outcomes.

------------------------------------------------------------------------

10. RECOMMENDATION IS NOT THE SAME AS PREDICTION

A model may predict:

Stock A: +12% Stock B: +8% Stock C: +5%

but that does not automatically mean A should be recommended to every
user.

Recommendation may consider:

-   expected return
-   risk
-   volatility
-   drawdown
-   liquidity
-   momentum
-   trend
-   news/events
-   macro regime
-   user profile
-   holding horizon

Therefore:

Prediction/Signal Layer → estimates relevant quantities

Recommendation Layer → turns those estimates into personalized rankings

Explanation Layer → reports the actual contributors

Keep these responsibilities separate.

------------------------------------------------------------------------

11. RULE-BASED BASELINE

Before complex ML, establish an explainable baseline.

Conceptually:

Market / Company Data + Technical Features + News Signals + Macro
Signals ↓ Individual signal scores ↓ Weighted score ↓ Rank stocks ↓
Explain score

The exact weights must be treated as experimental parameters.

Do not invent arbitrary weights and present them as objectively correct.

A baseline is valuable because ML must later demonstrate improvement
over something.

------------------------------------------------------------------------

12. FEATURE SELECTION RULES

Feature Selection is NOT “run correlation and pick the biggest numbers.”

Before Feature Selection:

1.  Define target.
2.  Define decision timestamp.
3.  Define train/validation/test split.
4.  Ensure no future information enters features.
5.  Fit selection procedures only on training data.

Potential Filter Method components:

-   missingness check
-   constant/near-constant feature check
-   feature-target correlation
-   mutual information
-   feature-feature correlation
-   redundancy removal
-   stability across temporal folds

Important:

A feature can have low univariate correlation and still be useful
jointly.

A feature can have high correlation with the target and still be
redundant.

Do not blindly select “top 10 correlation features.”

The final selected set should be justified by:

-   relevance
-   redundancy
-   stability
-   predictive usefulness
-   backtest behavior

------------------------------------------------------------------------

13. TIME SERIES SPLITTING

Do NOT randomly shuffle time-series data for ordinary train/test
evaluation.

Use chronological splits.

Conceptual example:

Historical data → older period: training → later period: validation →
latest untouched period: test

For more robust evaluation, consider walk-forward/rolling evaluation.

Never use the final test period to repeatedly make design decisions.

The test set should remain as close as possible to a final out-of-sample
evaluation.

------------------------------------------------------------------------

14. DATA LEAKAGE: HIGHEST PRIORITY

At decision time t, every feature must be constructible from information
available at or before t.

Examples of forbidden leakage:

-   tomorrow’s price in today’s feature
-   final daily close when decision is at 14:00
-   future volume
-   future news
-   future macro value
-   future corporate information
-   using the full dataset to scale data before temporal split
-   selecting features using validation/test labels
-   calculating normalization statistics using future periods
-   random split that allows future observations into training
-   using a revised data value that was unavailable historically

Particular caution:

Historical news must be timestamped.

Historical macro data must be timestamped.

“Published date” and “known/available date” may differ.

When uncertain, choose the more conservative availability assumption or
explicitly document the limitation.

------------------------------------------------------------------------

15. HISTORICAL DATA MUST RECREATE THE INFORMATION SET

Backtesting should answer:

“If StockLens had existed at historical time t, using only information
available at t, what would it have recommended?”

Not:

“Using today’s cleaned historical database, what would have looked
best?”

These are different questions.

For historical daily models:

-   use completed bars when decision is after close
-   use only information available at the simulated decision time

For intraday models:

-   reconstruct the market state at the simulated intraday timestamp
-   do not accidentally use the final daily bar

For news:

-   only news available by the simulated timestamp

For macro:

-   only values available by the simulated timestamp

------------------------------------------------------------------------

16. NEWS DATA

Eventually collect news/events relevant to stocks and sectors.

Potential features:

-   news count in recent window
-   sentiment
-   positive/negative ratio
-   event type
-   event severity
-   company relevance
-   sector relevance
-   recency
-   unusual news volume

Do not treat every positive headline as a positive trading signal.

News must be evaluated empirically.

Avoid look-ahead bias.

If an article was published after the historical decision time, it
cannot affect that historical prediction.

------------------------------------------------------------------------

17. MACRO DATA

Potential macro/market inputs:

-   interest rates
-   USD/KRW
-   oil
-   gold
-   KOSPI/KOSDAQ
-   major global indices
-   volatility indices where useful
-   sector indices
-   other economically meaningful signals

Macro variables should be timestamped and aligned correctly.

Do not blindly add variables simply because they are available.

Every added data source increases:

-   data complexity
-   failure modes
-   alignment risk
-   leakage risk
-   maintenance burden

Add variables when there is a defensible reason and evaluate whether
they improve out-of-sample usefulness.

------------------------------------------------------------------------

18. DATA ENGINEERING

Provider-specific formats must be converted into internal StockLens
representations.

Kiwoom-specific field names should not leak throughout the application.

Pipeline:

External API → raw response → validation → normalization → internal
representation → storage → feature engineering → scoring/model

Raw data should be preserved where practical for
reproducibility/debugging, but large generated datasets should not be
casually committed to Git.

Validate:

-   dates
-   numeric values
-   duplicate records
-   missing records
-   impossible OHLC relationships
-   volume types
-   stale values
-   API errors
-   pagination/continuation

Never silently turn invalid data into plausible-looking numbers.

------------------------------------------------------------------------

19. KIWOOM API RULES

config/kiwoom-rest-api-spec.json is the authoritative local
specification for the supplied Kiwoom REST API.

Before implementing any endpoint:

1.  Find endpoint in specification.
2.  Verify endpoint identifier.
3.  Verify HTTP method.
4.  Verify request fields.
5.  Verify required headers.
6.  Verify response fields.
7.  Verify pagination/continuation behavior.
8.  Verify any date/interval semantics.

Never guess field names.

Never invent endpoint IDs.

Do not modify the supplied API specification unless the user
intentionally provides an updated specification.

Keep Kiwoom implementation details inside src/api/.

------------------------------------------------------------------------

20. AUTHENTICATION / SECURITY

Never hard-code:

-   API key
-   API secret
-   access token
-   account number
-   credentials

Use environment variables / .env.

.env must not be committed.

.env.example may document required variables but must contain no real
secrets.

Never print full credentials or authentication responses to logs.

Tests must use fake credentials and mocked responses.

------------------------------------------------------------------------

21. TESTING

Use pytest.

Tests should cover:

-   API request construction
-   response normalization
-   malformed responses
-   missing values
-   duplicate records
-   feature calculations
-   target calculations
-   temporal alignment
-   leakage-sensitive transformations
-   scoring
-   model behavior
-   edge cases

Network requests must be mocked in tests.

Tests must not require:

-   real Kiwoom credentials
-   live market data
-   real trading accounts
-   unstable external services

Run focused tests after relevant changes, then broader tests as
appropriate.

A passing test suite does not prove financial validity.

------------------------------------------------------------------------

22. BACKTESTING

Backtesting is mandatory for claims about recommendation usefulness.

Document assumptions:

-   entry time
-   exit time
-   holding period
-   transaction costs
-   slippage
-   liquidity assumptions
-   rebalancing frequency
-   missing data
-   delisted/unavailable securities where relevant
-   universe definition

Do not silently omit bad periods.

Do not tune the system repeatedly against the final test period.

Predictive accuracy alone is insufficient.

Evaluate recommendation-level outcomes where appropriate:

-   cumulative return
-   risk-adjusted return
-   drawdown
-   hit rate
-   turnover
-   concentration
-   stability
-   performance relative to baseline

Exact metrics depend on the final prediction/recommendation definition.

------------------------------------------------------------------------

23. SURVIVORSHIP / UNIVERSE BIAS

Be careful about evaluating only today’s well-known stocks.

If the eventual system recommends from a defined universe, historical
backtests should consider whether the universe itself was historically
knowable.

Avoid:

“Take today’s top stocks and backtest them over ten years”

if the objective is to simulate what would actually have been available
at the time.

Document universe assumptions.

------------------------------------------------------------------------

24. EXPLAINABILITY

Every recommendation should eventually be explainable from actual
calculations.

Concept:

Recommendation → overall score → contributors

Example:

Top recommendation - positive 20-day trend contribution - moderate
volatility contribution - strong recent volume contribution - positive
news contribution - macro environment contribution

Do NOT fabricate explanations after the fact.

The explanation must be generated from the same signals/features/scores
that affected ranking.

------------------------------------------------------------------------

25. REAL-TIME LATENCY

Long-term target: approximately 1 second or less for the final
recommendation path.

This is a target, NOT a reason for premature optimization.

Prioritize:

1.  correctness
2.  reproducibility
3.  profiling
4.  optimization

When measuring latency, separate:

-   market-data ingestion
-   cached/external-data refresh
-   feature update
-   model inference
-   ranking
-   explanation
-   UI/rendering

Do not claim the target is achieved without measurement.

------------------------------------------------------------------------

26. ERROR HANDLING

Financial APIs may fail or return incomplete data.

Handle explicitly:

-   authentication failure
-   HTTP failure
-   API return codes
-   rate limits
-   timeout
-   malformed JSON
-   missing fields
-   stale data
-   duplicate data
-   missing timestamps
-   empty datasets
-   partial external data

A missing signal must NOT silently become a positive signal.

If data is unavailable, the system should either:

-   degrade explicitly
-   mark the signal unavailable
-   use a documented fallback
-   refuse to produce a misleading recommendation

------------------------------------------------------------------------

27. PERFORMANCE / ARCHITECTURE

Do not prematurely introduce:

-   databases
-   queues
-   microservices
-   distributed systems
-   unnecessary caching layers
-   complex model ensembles

unless actual requirements justify them.

The architecture should be able to evolve from:

historical daily analysis → daily ML → intraday → news → macro →
personalization → real-time recommendation

without a complete rewrite.

------------------------------------------------------------------------

28. FILE / CODE SAFETY

Before modifying code:

1.  Inspect current repository structure.
2.  Inspect relevant files.
3.  Understand upstream/downstream dependencies.
4.  Make the smallest coherent change.
5.  Avoid unrelated refactoring.
6.  Update tests.
7.  Run tests.
8.  Review for leakage/security/regressions.

Do not delete working functionality without a clear reason.

Do not create duplicate implementations without understanding why
existing code is insufficient.

------------------------------------------------------------------------

29. GIT SAFETY

Never commit:

-   .env
-   secrets
-   access tokens
-   account information
-   private credentials
-   large generated datasets
-   private raw API dumps when inappropriate

Use .gitignore.

Do not modify unrelated files.

------------------------------------------------------------------------

30. DOCUMENTATION ROLES

AGENTS.md → machine/developer instructions and non-negotiable project
rules.

README.md → human-readable project overview and setup.

CODEX_CONTEXT.md → broader project context if it exists; however, do NOT
assume Codex is available to the user.

If a major architecture decision changes, update the appropriate
documentation.

If CODEX_CONTEXT.md does not exist, do not block work merely because it
is mentioned in older instructions.

------------------------------------------------------------------------

31. CURRENT DESIGN DIRECTION: DAILY MODEL AS A BUILDING BLOCK

The current daily dataset and daily technical feature pipeline should
NOT be thrown away simply because the final system will use
intraday/news/macro data.

The intended evolution is:

CURRENT:

Daily OHLCV → Daily features → Daily prediction/scoring →
baseline/backtest

FUTURE:

Daily features + Intraday features + News features + Macro features +
possibly company/fundamental features → integrated prediction/scoring →
personalization → Top 5

The daily model may become:

-   a medium/long-term signal
-   one component of an ensemble
-   a feature provider
-   a baseline
-   a component of the final ranking engine

The final integrated model may need retraining once additional features
are introduced.

That is normal.

Do NOT describe this as “throwing away the old model.”

------------------------------------------------------------------------

32. MULTI-HORIZON POSSIBILITY

The final system may benefit from multiple horizons.

Conceptually:

Current snapshot ├── short horizon prediction ├── next-session/day
prediction └── medium/long horizon prediction

Then:

predictions/signals → risk/return assessment → user-profile-aware
ranking

This is particularly relevant because conservative and aggressive users
may care about different time horizons.

Do not implement multiple models merely because the idea sounds
sophisticated. Validate whether they improve the recommendation system.

------------------------------------------------------------------------

33. USER PROFILE SHOULD NOT CAUSE LEAKAGE

User preferences are available at recommendation time and may therefore
be used in personalization.

However, historical backtests that claim to simulate personalized
recommendations must define how the historical user profile is known.

Do not use information that would not have existed at the simulated
time.

------------------------------------------------------------------------

34. IMPORTANT DISTINCTION: HISTORICAL VS REAL-TIME DATA

Historical model training:

Use information that was actually available at the historical decision
timestamp.

Real-time inference:

Use information currently available at the current timestamp, including
an in-progress candle when the model is explicitly designed for that
state.

Therefore:

DO NOT implement a blanket rule:

“Always use yesterday’s data.”

Correct rule:

“Never use information from after the decision timestamp.”

For an after-close daily model, the latest completed daily candle may be
yesterday’s candle.

For a 14:00 intraday model, the current 14:00 market state may be used.

------------------------------------------------------------------------

35. DO NOT CONFUSE MORE DATA WITH BETTER DATA

Adding minute bars creates more observations but not necessarily more
independent information.

Minute data is strongly autocorrelated.

When moving from daily to intraday:

-   consider temporal dependence
-   define the unit of prediction
-   avoid leakage across overlapping windows
-   consider walk-forward evaluation
-   consider whether overlapping labels inflate apparent sample size
-   monitor computational/storage cost

------------------------------------------------------------------------

36. DECISION CHECKLIST BEFORE ANY MAJOR ML CHANGE

Before implementing an ML-related feature, answer:

1.  What exactly is being predicted?
2.  At what timestamp is the prediction made?
3.  What information is available at that timestamp?
4.  What is the target horizon?
5.  How is the target constructed?
6.  Can any future information leak into features?
7.  What is the temporal train/validation/test split?
8.  What baseline are we comparing against?
9.  What metrics matter?
10. How will this affect the final personalized recommendation system?

If these questions cannot be answered, pause and clarify the design
before coding.

------------------------------------------------------------------------

37. WHEN THE USER SAYS “ARE WE READY FOR FEATURE SELECTION?”

Do not answer based only on whether features exist.

Check:

-   target defined
-   target horizon defined
-   decision timestamp defined
-   historical data quality verified
-   incomplete current candles handled appropriately
-   temporal split defined
-   leakage rules satisfied
-   feature matrix generated deterministically

Only then proceed.

If the user wants a Filter Method specifically, start with:

1.  training-only missing/constant checks
2.  target relevance
3.  mutual information where appropriate
4.  feature redundancy
5.  temporal stability
6.  candidate subset
7.  later validation/model comparison

------------------------------------------------------------------------

38. PROJECT COMMUNICATION RULES

When explaining project state to the user:

-   Clearly distinguish completed work from planned work.
-   Do not claim an API/model/data source is implemented unless
    verified.
-   If the design changed, explicitly say so.
-   If a previous answer was incorrect, correct it clearly.
-   Do not blindly agree with the user.
-   Prefer technically accurate disagreement over reassurance.
-   Avoid telling the user they are “almost done” with a phase unless
    that is actually true.
-   When the user appears confused about project direction, reconstruct
    the full pipeline before recommending the next coding step.

------------------------------------------------------------------------

39. DEFAULT ANSWER BEHAVIOR FOR STOCKLENS QUESTIONS

Before answering a non-trivial StockLens question:

1.  Recall the final product goal.
2.  Identify the current project phase.
3.  Check whether the question changes architecture, target, data, or
    evaluation.
4.  Consider previous decisions and discovered issues.
5.  Avoid answering from the latest message alone if earlier project
    context materially changes the answer.
6.  If actual files are available, inspect relevant files rather than
    guessing.
7.  Prefer the smallest correct next step.

For implementation tasks:

-   inspect actual code
-   identify exact files
-   explain dependencies
-   implement minimally
-   test
-   report limitations

------------------------------------------------------------------------

40. CURRENT “DO NOT FORGET” SUMMARY

The following facts are especially important:

1.  Final product = personalized stock recommendation, not just price
    prediction.
2.  Final output = personalized Top 5 with explanations.
3.  Conservative and aggressive users may need different horizons and
    ranking preferences.
4.  Current dataset is primarily daily OHLCV.
5.  Current feature engineering is primarily daily technical features.
6.  Kiwoom provides separate intraday/minute chart data; daily bars
    cannot be reconstructed into minute bars.
7.  Real-time recommendation may use the current in-progress candle.
8.  Historical training must never use future information.
9.  Do not solve leakage by forcing real-time inference to use
    yesterday’s data.
10. Daily and intraday models/signals can coexist.
11. News and macro data are future planned inputs, not assumed already
    implemented.
12. External data should preferably be pre-collected/cached rather than
    fetched sequentially in the final recommendation critical path.
13. A rule-based baseline should exist before relying on complex ML.
14. Feature Selection requires a defined target and temporal evaluation
    setup.
15. Correlation alone is not sufficient for feature selection.
16. Backtesting is required to judge recommendation usefulness.
17. Accuracy alone does not prove investment usefulness.
18. Never fabricate explanations.
19. Never expose credentials.
20. Never tell the user to use Codex because Codex is unavailable/unused
    in their current workflow.
21. Do not repeatedly ask the user to resend context that is already
    available in project files/conversation when those sources can be
    inspected.
22. When unsure, inspect the actual project rather than inventing the
    current state.

------------------------------------------------------------------------

41. DEFINITION OF DONE

A meaningful feature is complete only when appropriate:

Implementation → correct data flow → validation → error handling → tests
→ leakage review → security review → performance consideration →
documentation → reproducible behavior

For financial/ML features, correctness and evaluation quality take
priority over feature count, code volume, or visual sophistication.

The goal is not to build the largest system.

The goal is to build a defensible, reproducible, explainable
personalized recommendation system incrementally.

MVP 목표: 과거 일봉 OHLCV로부터 기술적 특징을 생성하고, leakage-safe한 시계열 학습/검증 구조를 통해 미래 수익률 또는 방향을 예측하는 ML 모델을 구축한 뒤, 단순 rule-based baseline과 비교하여 실제로 유의미한 예측/추천 가능성이 있는지 검증한다.
