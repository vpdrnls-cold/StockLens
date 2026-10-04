"""Build the chart-card base-rate table (CURRENT_STATUS item 61).

    STOCKLENS_UNIVERSE=top50 PYTHONPATH=. python scripts/build_chart_base_rates.py

Reads the daily dataset, CUTS IT TO 2012-01-01 ~ VALIDATION_END_DATE FIRST,
purges the last 5 trade dates (labels reaching past the validation end), then
computes the pre-registered state base rates. Test and forward periods are
never read. Output: data/processed/analysts/chart_base_rates.json.
Reference layer only -- nothing here changes the model (AGENTS.md 43).
"""

from __future__ import annotations

from datetime import datetime
import json
import os
from pathlib import Path

import pandas as pd

from scripts.run_ml_backtest import STOCK_CODES, _load_priced_dataset
from src.analysts.chart import (
    BASE_RATE_START, STATE_SPECS, WINDOWS, base_rate_frame, compute_base_rates,
)
from src.data.dataset import DEFAULT_TARGET_HORIZON, VALIDATION_END_DATE

OUT = Path("data/processed/analysts/chart_base_rates.json")


def main() -> None:
    dataset = _load_priced_dataset()
    dataset["trade_date"] = pd.to_datetime(dataset["trade_date"])
    dataset = dataset[dataset["trade_date"] <= pd.Timestamp(VALIDATION_END_DATE)]  # cut before anything else
    frame = base_rate_frame(dataset, horizon=DEFAULT_TARGET_HORIZON)
    rows = compute_base_rates(frame)
    meta = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "universe": os.environ.get("STOCKLENS_UNIVERSE", "core5"),
        "n_stocks": len(STOCK_CODES),
        "period": f"{BASE_RATE_START}~{frame['trade_date'].max().date()} (purged {DEFAULT_TARGET_HORIZON} dates)",
        "windows": [list(w) for w in WINDOWS],
        "n_rows": int(len(frame)), "n_dates": int(frame["trade_date"].nunique()),
        "outcome": "target_return_5d (T+1 open -> T+5 close) minus same-day universe mean",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"meta": meta, "base_rates": rows}, ensure_ascii=False, indent=1,
                              default=lambda x: None), encoding="utf-8")

    print(f"period {meta['period']} | rows {meta['n_rows']:,} | dates {meta['n_dates']:,} | universe {meta['universe']}")
    print(f"{'state':<8}{'bucket':<16}{'n':>7}{'dates':>7}{'mean':>9}{'hit':>7}"
          + "".join(f"{w:>9}" for w, _, _ in WINDOWS) + "  verdict")
    for r in rows:
        print(f"{r['state']:<8}{r['bucket']:<16}{r['n_obs']:>7}{r['n_dates']:>7}"
              f"{r['mean_excess'] * 100:>+8.2f}%{r['hit_rate']:>7.1%}"
              + "".join(f"{r[f'mean_{w}'] * 100:>+8.2f}%" for w, _, _ in WINDOWS) + f"  {r['verdict']}")
    print(f"\nsaved: {OUT}")
    print("states:", ", ".join(s.key for s in STATE_SPECS))


if __name__ == "__main__":
    main()
