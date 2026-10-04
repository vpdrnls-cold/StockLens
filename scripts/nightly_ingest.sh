#!/usr/bin/env bash
# Nightly data collection for the forward holdout (CURRENT_STATUS item 46).
#
# Why this has to run every trading day:
#   ka10080 (minute bars) only serves about the last year. Anything not saved
#   locally eventually disappears from the API for good, and data/raw/ is
#   gitignored -- so this machine's copy (plus the optional backup below) is
#   the only record. From 2026-09-24 on, these files are also the forward
#   holdout for both the daily and the intraday track.
#
# What it does (after 20:00 KST, when the after-market session has closed):
#   1. minute bars (ka10080, 15-min) for the top50 universe, last 10 days
#   2. daily bars (ka10081) for the top50 universe -- FRIDAYS ONLY by default
#   3. index bars (ka20006: KOSPI, KOSPI200) + investor flows (ka10059) for
#      the universe, incremental (last 10 days, ~52 calls). Re-fetching 10 days
#      lets a later final value replace an earlier one (items 58/64).
#   4. optional: mirror data/raw/kiwoom/ka10080 to $STOCKLENS_RAW_BACKUP_DIR
#   5. whenever daily bars were refreshed (Fridays by default): write the
#      paper-trading pick log reports/daily_picks/<date>.csv (scripts/recommend.py)
#
# Why daily bars are not fetched every night:
#   ka10081 is requested with adjusted prices (upd_stkpc_tp=1), so every call
#   re-downloads each stock's WHOLE history (up to 60 pages per stock) -- an
#   incremental fetch would break adjustment consistency after a split or
#   rights issue. That takes many minutes for 50 stocks. Daily bars are also
#   re-fetchable at any time, unlike minute bars, so once a week is enough.
#   Force it on any day with STOCKLENS_NIGHTLY_DAILY=1, skip it with =0.
#
# Universes (item 68):
#   collection (steps 1-3) = STOCKLENS_COLLECT_UNIVERSE, default kospi200 (all 200
#   KOSPI200 common stocks, a superset of top50) -- minute bars exist only for the
#   last ~1 year, so a wider universe must be collected now to be usable later.
#   evaluation / paper log (step 5) = top50, unchanged. The extra stocks are not
#   used by any experiment or decision of the current cycle.
#
# Manual run (repo root):
#   bash scripts/nightly_ingest.sh
# Logs: logs/nightly_ingest_YYYYMMDD.log  (*.log is gitignored)

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT" || exit 1

PYTHON="${STOCKLENS_PYTHON:-$REPO_ROOT/.venv/bin/python}"
mkdir -p logs
LOG="logs/nightly_ingest_$(TZ=Asia/Seoul date +%Y%m%d).log"

export PYTHONPATH="$REPO_ROOT"
export STOCKLENS_UNIVERSE=top50   # evaluation universe (recommend.py)
COLLECT="${STOCKLENS_COLLECT_UNIVERSE:-kospi200}"
case "$COLLECT" in
  kospi200) COLLECT_FILE="config/universe_kospi200.json" ;;
  top50)    COLLECT_FILE="config/universe_kospi200_top50.json" ;;
  *) echo "unknown STOCKLENS_COLLECT_UNIVERSE=$COLLECT" >&2; exit 2 ;;
esac

status=0
{
  echo "=== $(TZ=Asia/Seoul date '+%Y-%m-%d %H:%M:%S KST') nightly ingest start ==="

  echo "--- [1/5] minute bars (ka10080) ---"
  echo "collection universe: $COLLECT ($COLLECT_FILE)"
  "$PYTHON" scripts/ingest_kiwoom_minute_chart_universe.py --universe "$COLLECT_FILE" --lookback-days 10 || status=1

  daily="${STOCKLENS_NIGHTLY_DAILY:-}"
  if [[ -z "$daily" ]]; then
    [[ "$(TZ=Asia/Seoul date +%u)" == "5" ]] && daily=1 || daily=0
  fi
  if [[ "$daily" == "1" ]]; then
    echo "--- [2/5] daily bars (ka10081, full adjusted history) ---"
    STOCKLENS_UNIVERSE="$COLLECT" "$PYTHON" scripts/ingest_kiwoom_daily_chart_batch.py || status=1
  else
    echo "--- [2/5] daily bars skipped (Fridays only; STOCKLENS_NIGHTLY_DAILY=1 to force) ---"
  fi

  echo "--- [3/5] index bars + investor flows (ka20006/ka10059, last 10 days) ---"
  STOCKLENS_UNIVERSE="$COLLECT" "$PYTHON" scripts/ingest_kiwoom_flow_index.py --lookback-days 10 || status=1

  if [[ -n "${STOCKLENS_RAW_BACKUP_DIR:-}" ]]; then
    echo "--- [4/5] backup ka10080 raw -> $STOCKLENS_RAW_BACKUP_DIR ---"
    mkdir -p "$STOCKLENS_RAW_BACKUP_DIR"
    rsync -a data/raw/kiwoom/ka10080/ "$STOCKLENS_RAW_BACKUP_DIR/ka10080/" || status=1
  else
    echo "--- [4/5] backup skipped (STOCKLENS_RAW_BACKUP_DIR not set) ---"
  fi

  if [[ "$daily" == "1" ]]; then
    echo "--- [5/5] recommendation log (scripts/recommend.py) ---"
    "$PYTHON" scripts/recommend.py || status=1
  else
    echo "--- [5/5] recommendation skipped (daily bars not refreshed today) ---"
  fi

  echo "=== done, status=$status ==="
} >> "$LOG" 2>&1

exit $status
