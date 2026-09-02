# StockLens - Codex Project Context

## 1. Project goal
StockLens is a real-time Korean stock analysis and recommendation platform.
The product should analyze market data and recommend stocks to a user with clear, explainable reasons.

**Important scope constraint:** StockLens is an analysis/recommendation product, not an automatic trading bot. Do not implement actual order execution unless the project scope is explicitly changed later.

## 2. Core pipeline
The intended architecture is:

historical data
→ preprocessing / feature engineering
→ baseline scoring
→ backtesting
→ ML prediction
→ real-time Kiwoom inference
→ user risk profile / personalization
→ recommendation
→ explanation / visualization

The baseline should remain useful even before ML is introduced.

## 3. Development phases
### Phase 1: Rule-based baseline
Build a transparent stock score using signals such as:
- momentum
- volume / trading activity
- volatility
- valuation (PER, etc.)
- profitability / financial quality (e.g. ROE, growth)
- market/sector context where data is available

Personalize the final recommendation according to the user's risk profile.

### Phase 2: Backtesting
Use real historical data to evaluate the baseline before trusting it on live data.
Measure performance, drawdown, hit rate, turnover, and other appropriate metrics.
Avoid look-ahead bias and survivorship bias.

### Phase 3: ML prediction
Add ML models for return/direction/risk prediction only after the baseline and backtesting pipeline are stable.
Compare ML performance against the rule-based baseline rather than assuming ML is automatically better.

### Phase 4: Real-time system
Use Kiwoom REST/WebSocket data for current market inference and personalized recommendations.
The real-time path must be designed for low latency, with expensive work precomputed or cached whenever possible.

## 4. Kiwoom API file
`config/kiwoom-rest-api-spec.json` is the downloaded Kiwoom API specification provided for this project.
It contains 342 API definitions: 311 HTTPS endpoints and 31 WebSocket-related endpoints. All entries use POST in this specification.

Important examples include:
- `au10001`: 접근토큰 발급
- `au10002`: 접근토큰폐기
- `ka10001`: 주식기본정보요청
- `ka10003`: 체결정보요청
- `ka10004`: 주식호가요청
- `ka10005`: 주식일주월시분요청
- `ka10006`: 주식시분요청
- `ka10008`: 주식외국인종목별매매동향
- `ka10010`: 업종프로그램요청
- `ka10011`: 신주인수권전체시세요청

The specification includes both production HTTPS domain `https://api.kiwoom.com` and WebSocket domain `wss://api.kiwoom.com:10000`.

Do not hard-code credentials. Tokens/API secrets belong in environment variables or a secure secret store.

## 5. Real-time signal design
The recommendation engine is expected to eventually combine:
- price / volume / order-book information
- technical and statistical features
- financial/valuation features
- news sentiment and event signals
- macro signals such as interest rates and oil prices
- market/sector regime
- user risk preference

News and macro variables should be treated as features/signals in the feature engineering and inference layers, not bolted onto the UI after the score is calculated.

For latency, external news/macro retrieval should generally be asynchronous and preprocessed into a fast local/cache layer. The final recommendation request should read prepared features instead of waiting on multiple external APIs.

## 6. Latency target
The desired user-facing recommendation latency is roughly sub-second, ideally around 1 second or less for the final inference/recommendation path.
This is a design target, not a claim that every external data source can respond within 1 second.

Design principle:
- ingest continuously
- normalize continuously
- calculate expensive features ahead of time
- cache frequently used features
- keep final scoring/inference lightweight

## 7. Architecture principles
- Separate data ingestion, preprocessing, features, models, recommendation, and presentation.
- Keep API-specific code isolated under `src/api`.
- Keep raw provider responses separate from normalized internal data models.
- Make transformations deterministic and testable.
- Log data quality and model/recommendation decisions.
- Never leak API keys or account information into Git.
- Prefer reproducible experiments and explicit configuration over hidden global state.

## 8. What Codex should do next
Do not immediately build the whole system.
First inspect the repository and Kiwoom specification, then implement the project incrementally.
The first practical milestone is a clean Kiwoom client/authentication layer plus a small historical-data ingestion path that can feed the preprocessing/feature pipeline.

Before implementing an endpoint, inspect its exact request/response schema in `config/kiwoom-rest-api-spec.json` rather than guessing field names.
