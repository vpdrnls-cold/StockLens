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
#   3. optional: mirror data/raw/kiwoom/ka10080 to $STOCKLENS_RAW_BACKUP_DIR
#   4. whenever daily bars were refreshed (Fridays by default): write the
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
export STOCKLENS_UNIVERSE=top50

status=0
{
  echo "=== $(TZ=Asia/Seoul date '+%Y-%m-%d %H:%M:%S KST') nightly ingest start ==="

  echo "--- [1/4] minute bars (ka10080) ---"
  "$PYTHON" scripts/ingest_kiwoom_minute_chart_universe.py --lookback-days 10 || status=1

  daily="${STOCKLENS_NIGHTLY_DAILY:-}"
  if [[ -z "$daily" ]]; then
    [[ "$(TZ=Asia/Seoul date +%u)" == "5" ]] && daily=1 || daily=0
  fi
  if [[ "$daily" == "1" ]]; then
    echo "--- [2/4] daily bars (ka10081, full adjusted history) ---"
    "$PYTHON" scripts/ingest_kiwoom_daily_chart_batch.py || status=1
  else
    echo "--- [2/4] daily bars skipped (Fridays only; STOCKLENS_NIGHTLY_DAILY=1 to force) ---"
  fi

  if [[ -n "${STOCKLENS_RAW_BACKUP_DIR:-}" ]]; then
    echo "--- [3/4] backup ka10080 raw -> $STOCKLENS_RAW_BACKUP_DIR ---"
    mkdir -p "$STOCKLENS_RAW_BACKUP_DIR"
    rsync -a data/raw/kiwoom/ka10080/ "$STOCKLENS_RAW_BACKUP_DIR/ka10080/" || status=1
  else
    echo "--- [3/4] backup skipped (STOCKLENS_RAW_BACKUP_DIR not set) ---"
  fi

  if [[ "$daily" == "1" ]]; then
    echo "--- [4/4] recommendation log (scripts/recommend.py) ---"
    "$PYTHON" scripts/recommend.py || status=1
  else
    echo "--- [4/4] recommendation skipped (daily bars not refreshed today) ---"
  fi

  echo "=== done, status=$status ==="
} >> "$LOG" 2>&1

exit $status
