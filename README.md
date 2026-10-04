# StockLens

Real-time stock analysis and personalized stock recommendation project.

See [`CODEX_CONTEXT.md`](CODEX_CONTEXT.md) for the project context and development rules.

## Current status (2026-10-04)

Research / validation stage, not production. A fixed daily XGBoost ranking
model scores the 50 largest KOSPI200 stocks; the strategy holds the top 10
for 5 trading days with a turnover buffer. It has not yet been checked on
clean out-of-sample data -- a one-time forward evaluation is scheduled for
early January 2027. Nothing here is investment advice.

- Current state, open issues and the work log: [`CURRENT_STATUS.md`](CURRENT_STATUS.md)
  (summary in sections 1-8, latest item at the end).
- Permanent development rules: [`AGENTS.md`](AGENTS.md); short guide for
  Claude Code: [`CLAUDE.md`](CLAUDE.md).
- Daily picks (paper-trading log only): `scripts/recommend.py`.

The sections below are the original Kiwoom connectivity notes and still work.

## Scope
- Stock analysis and recommendation
- Historical backtesting
- ML-based prediction as a later phase
- Real-time Kiwoom data integration
- Explainable recommendation output

This project does **not** execute real buy/sell orders.

## Kiwoom REST connectivity check

Copy `.env.example` to `.env`, set `KIWOOM_APP_KEY` and `KIWOOM_SECRET_KEY`, then run:

```bash
python3 scripts/check_kiwoom_quote.py 005930
```

The script requests an access token (`au10001`) and basic stock information
(`ka10001`), then prints the current price fields. It does not place orders.

For a safe authentication diagnosis, optionally add the public IP registered
in the matching Kiwoom App Key portal as `KIWOOM_REGISTERED_IP` and run:

```bash
python3 scripts/check_kiwoom_quote.py 005930 --diagnose
```

The diagnostic prints the configured environment, API URL, a one-way App Key
fingerprint, and whether the current public IP matches the configured IP. It
never prints an App Secret, access token, account number, or request body.

## Kiwoom daily-chart connectivity check

Inspect the raw `ka10081` daily-chart response for Samsung Electronics:

```bash
python3 scripts/check_kiwoom_daily_chart.py 005930
```

Use `--print-json` to print the full market-data JSON response. The script
uses an adjusted-price request (`upd_stkpc_tp: "1"`) and does not store or
convert the response into a DataFrame.

## Historical daily-chart ingestion

Fetch `ka10081`, validate its response, and keep raw and normalized data in
separate local locations:

```bash
python3 scripts/ingest_kiwoom_daily_chart.py 005930
```

Raw provider JSON is stored under `data/raw/kiwoom/ka10081/<stock_code>/`.
Validated provider-neutral daily bars are merged by date into
`data/processed/historical/<stock_code>.json`. No DataFrame, features,
recommendations, or models are created by this step.

## Multi-symbol daily-chart validation

Run the existing ingestion flow for Samsung Electronics, SK hynix, Hyundai
Motor, NAVER, and Kakao, then verify provider-neutral schema, stock codes, and
separate raw/normalized storage:

```bash
python3 scripts/validate_kiwoom_daily_chart_symbols.py
```

## Batch historical ingestion

Sequentially collect, validate, and store daily charts for the five default
symbols without introducing parallel processing or a scheduler:

```bash
python3 scripts/ingest_kiwoom_daily_chart_batch.py
```

Provide a different sequential batch or historical base date when needed:

```bash
python3 scripts/ingest_kiwoom_daily_chart_batch.py 005930 000660 --base-date 20260831
```
