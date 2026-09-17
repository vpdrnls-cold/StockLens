"""Check whether the HOLD/SELL position layer's thresholds
(``src.portfolio.optimizer.PositionConfig``) actually do anything
useful, per AGENTS.md 9's "Do not hard-code these as arbitrary weights
[or thresholds] and call them scientifically valid. Use backtesting
and experiments to determine whether [this] improves useful outcomes,"
which the optimizer module's own docstring says applies to its
thresholds just as much as to the personalization weights.

This mirrors scripts/evaluate_personalization.py exactly in spirit:
same universe, same top_n=2 model-scored stock selection, same costs,
same VALIDATION-only split (test period untouched, AGENTS.md 13). The
only thing that changes between rows is the *exit* rule.

Method
------
``run_baseline_backtest`` (the shared engine) always exits at a fixed
T+holding_days close. That is the "no early exit" baseline here --
identical to the 'neutral' row scripts/evaluate_personalization.py
already reported for this validation split.

``simulate_exit_rule`` below reuses the exact same decision grid,
top_n=2 selection (by plain model predicted_return, i.e. what the
'neutral' personalization profile also reduces to) and T+1 open entry,
but walks forward day by day from entry through T+holding_days,
calling ``src.portfolio.optimizer.evaluate_position`` once per day
with that day's actual close price, the model's predicted_return for
that day, and atr_pct for that day. It exits at the close of the first
day a SELL is returned, or at the original T+holding_days close if
SELL never fires. This isolates exactly what the exit rule changes,
with every other assumption held fixed.

Run from the repo root:
    PYTHONPATH=. python3 scripts/evaluate_position_thresholds.py
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from src.backtest.baseline import (
    BaselineConfig,
    Trade,
    calculate_net_return,
    calculate_performance,
    prepare_universe,
    trades_to_dataframe,
)
from src.data.dataset import build_combined_dataset, split_by_time
from src.data.storage import HistoricalStorage
from src.features.engineering import FEATURE_COLUMNS
from src.ml.strategy import make_model_score_fn, predictions_for_dataset
from src.models.predict import train_model
from src.portfolio.optimizer import (
    Decision,
    Position,
    PositionConfig,
    PositionSignal,
    evaluate_position,
)
from src.backtest.baseline import run_baseline_backtest

STOCK_CODES = ("000660", "005380", "005930", "035420", "035720")

CONFIG = BaselineConfig(
    lookback_days=5,
    holding_days=5,
    buy_fee=0.00015,
    sell_fee=0.00015,
    sell_tax=0.0020,
    buy_slippage=0.0010,
    sell_slippage=0.0010,
)
TOP_N = 2

SIGNAL_COLUMNS = ["trade_date", "stock_code", "atr_pct"]

# A stop-loss multiple large enough that unrealized_return <=
# -multiple*atr_pct essentially never fires within a 5-day window
# (atr_pct is typically a few percent, so 100x is a de-facto "off"
# switch) -- used to isolate the signal-reversal rule alone.
STOP_LOSS_DISABLED = 100.0
# A predicted_return threshold low enough that the signal-reversal
# rule (predicted_return <= threshold) essentially never fires --
# used to isolate the stop-loss rule alone.
REVERSAL_DISABLED = -1.0


def _load_priced_dataset() -> pd.DataFrame:
    storage = HistoricalStorage("data")

    stock_bars = {
        stock_code: storage.load_daily_bars(stock_code) for stock_code in STOCK_CODES
    }

    dataset = build_combined_dataset(stock_bars)
    dataset["trade_date"] = pd.to_datetime(dataset["trade_date"])
    dataset[list(FEATURE_COLUMNS)] = dataset[list(FEATURE_COLUMNS)].replace(
        [np.inf, -np.inf], np.nan
    )

    prices = [
        {
            "trade_date": pd.Timestamp(bar.trade_date),
            "stock_code": stock_code,
            "open_price": float(bar.open_price),
            "close_price": float(bar.close_price),
        }
        for stock_code, bars in stock_bars.items()
        for bar in bars
    ]

    return dataset.merge(
        pd.DataFrame(prices),
        on=["trade_date", "stock_code"],
        how="left",
        validate="one_to_one",
    )


def _to_data_by_stock(dataset: pd.DataFrame) -> dict[str, pd.DataFrame]:
    return {
        str(stock_code): (
            group[["stock_code", "trade_date", "open_price", "close_price"]]
            .sort_values("trade_date")
            .reset_index(drop=True)
        )
        for stock_code, group in dataset.groupby("stock_code")
    }


def _period_return_stats(trades: list[Trade]) -> tuple[float, float]:
    if not trades:
        return float("nan"), float("nan")

    trades_df = trades_to_dataframe(trades)
    period_returns = trades_df.groupby("decision_date").apply(
        lambda group: float((group["weight"] * group["net_return"]).sum())
    )
    return float(period_returns.mean()), float(period_returns.std())


@dataclass(frozen=True)
class ExitSimResult:
    trades: list[Trade]
    holding_days: list[int]
    exit_reasons: list[str]


def simulate_exit_rule(
    universe: pd.DataFrame,
    predictions_lookup: dict[tuple[pd.Timestamp, str], float],
    atr_lookup: dict[tuple[pd.Timestamp, str], float],
    stock_codes: list[str],
    baseline_config: BaselineConfig,
    position_config: PositionConfig,
    top_n: int,
    percentile_lookup: dict[tuple[pd.Timestamp, str], float] | None = None,
) -> ExitSimResult:
    """Same decision grid/entry/selection as ``run_baseline_backtest``
    with ``make_model_score_fn`` scoring, but the exit is decided by
    ``evaluate_position`` walking day by day instead of a fixed
    T+holding_days close. See module docstring.

    ``percentile_lookup`` is optional: pass it (from
    ``src.recommendation.scoring.add_predicted_return_percentile``)
    when ``position_config.sell_percentile_threshold`` is set, so each
    day's ``PositionSignal.predicted_return_percentile`` is populated.
    Omitted (``None``) for the absolute-threshold rule, matching the
    original behavior of this function.
    """
    if not (1 <= top_n <= len(stock_codes)):
        raise ValueError(f"top_n must be between 1 and {len(stock_codes)}, got {top_n}.")

    required_rows = baseline_config.lookback_days + 1 + baseline_config.holding_days
    if len(universe) < required_rows:
        return ExitSimResult(trades=[], holding_days=[], exit_reasons=[])

    trades: list[Trade] = []
    holding_days: list[int] = []
    exit_reasons: list[str] = []

    first_decision_index = baseline_config.lookback_days
    last_decision_index = len(universe) - baseline_config.holding_days - 1
    weight = 1.0 / top_n

    for decision_index in range(
        first_decision_index, last_decision_index + 1, baseline_config.holding_days
    ):
        decision_date = universe.iloc[decision_index]["trade_date"]

        scores = {
            code: predictions_lookup[(decision_date, code)] for code in stock_codes
        }
        selected_stocks = sorted(scores, key=scores.get, reverse=True)[:top_n]

        entry_index = decision_index + 1
        entry_date = universe.iloc[entry_index]["trade_date"]
        max_exit_index = decision_index + baseline_config.holding_days

        for stock_code in selected_stocks:
            entry_price = float(universe.iloc[entry_index][f"open_{stock_code}"])
            if entry_price <= 0:
                raise ValueError(f"Invalid entry price for {stock_code}")

            position = Position(stock_code=stock_code, entry_price=entry_price)

            exit_index = max_exit_index
            exit_reason = "max_holding_reached"

            # Monitor daily from the entry day's close through the
            # original fixed exit day's close.
            for day_index in range(entry_index, max_exit_index + 1):
                day_date = universe.iloc[day_index]["trade_date"]
                key = (day_date, stock_code)

                current_price = float(universe.iloc[day_index][f"close_{stock_code}"])
                signal = PositionSignal(
                    current_price=current_price,
                    predicted_return=predictions_lookup[key],
                    atr_pct=atr_lookup[key],
                    predicted_return_percentile=(
                        percentile_lookup[key] if percentile_lookup is not None else None
                    ),
                )
                decision = evaluate_position(position, signal, position_config)

                if decision.decision == Decision.SELL:
                    exit_index = day_index
                    exit_reason = (
                        "stop_loss" if "stop-loss" in decision.reason else "signal_reversal"
                    )
                    break

            exit_date = universe.iloc[exit_index]["trade_date"]
            exit_price = float(universe.iloc[exit_index][f"close_{stock_code}"])

            gross_return, net_return = calculate_net_return(
                entry_price, exit_price, baseline_config
            )

            trades.append(
                Trade(
                    decision_date=decision_date,
                    stock_code=stock_code,
                    score=scores[stock_code],
                    entry_date=entry_date,
                    entry_price=entry_price,
                    exit_date=exit_date,
                    exit_price=exit_price,
                    gross_return=gross_return,
                    net_return=net_return,
                    weight=weight,
                )
            )
            holding_days.append(exit_index - entry_index + 1)
            exit_reasons.append(exit_reason)

    return ExitSimResult(trades=trades, holding_days=holding_days, exit_reasons=exit_reasons)


def _print_row(name: str, trades: list[Trade], holding_days: list[int], exit_reasons: list[str]) -> None:
    perf = calculate_performance(trades)
    avg_period, std_period = _period_return_stats(trades)
    avg_holding = float(np.mean(holding_days)) if holding_days else float("nan")

    n = len(exit_reasons)
    stop_loss_pct = exit_reasons.count("stop_loss") / n if n else float("nan")
    reversal_pct = exit_reasons.count("signal_reversal") / n if n else float("nan")
    max_hold_pct = exit_reasons.count("max_holding_reached") / n if n else float("nan")

    print(
        f"{name:<28}{perf['total_return']:>11.2%} "
        f"{perf['win_rate']:>9.2%} {perf['max_drawdown']:>9.2%} "
        f"{avg_period:>11.4%} {std_period:>11.4%} "
        f"{avg_holding:>9.2f} "
        f"{stop_loss_pct:>9.1%} {reversal_pct:>9.1%} {max_hold_pct:>9.1%}"
    )


def main() -> None:
    dataset = _load_priced_dataset()
    splits = split_by_time(dataset)

    print("=== Training daily model (train -> validation early stopping) ===")
    trained = train_model(
        splits.train,
        splits.train["target_return_5d"],
        splits.validation,
        splits.validation["target_return_5d"],
    )
    print(f"Best iteration: {trained.best_iteration}")
    print()

    predictions = predictions_for_dataset(trained, splits.validation)
    signals = splits.validation[SIGNAL_COLUMNS].merge(
        predictions, on=["trade_date", "stock_code"], validate="one_to_one"
    )

    predictions_lookup = {
        (row.trade_date, row.stock_code): row.predicted_return
        for row in signals.itertuples(index=False)
    }
    atr_lookup = {
        (row.trade_date, row.stock_code): row.atr_pct
        for row in signals.itertuples(index=False)
    }

    data_by_stock = _to_data_by_stock(splits.validation)
    universe = prepare_universe(data_by_stock)
    stock_codes = list(data_by_stock.keys())

    print(f"=== HOLD/SELL exit-rule comparison on VALIDATION (top_n={TOP_N}) ===\n")
    print(
        f"{'config':<28}{'cum_return':>12}{'hit_rate':>10}{'mdd':>10}"
        f"{'avg_period':>12}{'std_period':>12}{'avg_hold_d':>10}"
        f"{'stop_loss':>10}{'reversal':>10}{'max_hold':>10}"
    )

    # 1) No early exit at all -- identical to evaluate_personalization.py's
    #    'neutral' row: same universe/top_n/costs, fixed T+5 close exit.
    baseline_score_fn = make_model_score_fn(predictions)
    baseline_trades = run_baseline_backtest(
        data_by_stock, config=CONFIG, score_fn=baseline_score_fn, top_n=TOP_N
    )
    _print_row(
        "no_early_exit (baseline)",
        baseline_trades,
        holding_days=[CONFIG.holding_days] * len(baseline_trades),
        exit_reasons=["max_holding_reached"] * len(baseline_trades),
    )

    # 2) Historical "default" row (3x ATR% stop-loss, absolute reversal
    #    rule at thr=0.0) -- this is what CURRENT_STATUS.md items 17/18
    #    documented as "default" before items 20/21 made the percentile
    #    rule the PositionConfig default; pinned explicitly here
    #    (sell_percentile_threshold=None) so this row keeps its original,
    #    documented meaning instead of silently switching rules.
    default_result = simulate_exit_rule(
        universe,
        predictions_lookup,
        atr_lookup,
        stock_codes,
        CONFIG,
        PositionConfig(sell_predicted_return_threshold=0.0, sell_percentile_threshold=None),
        TOP_N,
    )
    _print_row(
        "default (3.0x atr, thr=0.0)",
        default_result.trades,
        default_result.holding_days,
        default_result.exit_reasons,
    )

    # 3) Stop-loss multiplier grid, reversal rule fixed at the absolute
    #    0.0 threshold (sell_percentile_threshold=None pins this to the
    #    absolute rule so the grid isolates only the multiplier, as
    #    originally intended) -- isolates the multiplier's effect.
    for multiple in (1.0, 1.5, 2.0, 4.0, 6.0):
        cfg = PositionConfig(
            stop_loss_atr_multiple=multiple,
            sell_predicted_return_threshold=0.0,
            sell_percentile_threshold=None,
        )
        result = simulate_exit_rule(
            universe, predictions_lookup, atr_lookup, stock_codes, CONFIG, cfg, TOP_N
        )
        _print_row(
            f"stop_loss={multiple:g}x, thr=0.0",
            result.trades,
            result.holding_days,
            result.exit_reasons,
        )

    # 4) Stop-loss rule only (reversal rule effectively disabled;
    #    sell_percentile_threshold=None so this stays "no reversal rule
    #    at all" rather than silently becoming the percentile rule).
    stop_only_cfg = PositionConfig(
        stop_loss_atr_multiple=3.0,
        sell_predicted_return_threshold=REVERSAL_DISABLED,
        sell_percentile_threshold=None,
    )
    stop_only_result = simulate_exit_rule(
        universe, predictions_lookup, atr_lookup, stock_codes, CONFIG, stop_only_cfg, TOP_N
    )
    _print_row(
        "stop_loss=3.0x only",
        stop_only_result.trades,
        stop_only_result.holding_days,
        stop_only_result.exit_reasons,
    )

    # 5) Signal-reversal rule only (stop-loss effectively disabled;
    #    sell_percentile_threshold=None pins this to the absolute rule,
    #    matching its original "reversal_thr=0.0" label).
    reversal_only_cfg = PositionConfig(
        stop_loss_atr_multiple=STOP_LOSS_DISABLED,
        sell_predicted_return_threshold=0.0,
        sell_percentile_threshold=None,
    )
    reversal_only_result = simulate_exit_rule(
        universe, predictions_lookup, atr_lookup, stock_codes, CONFIG, reversal_only_cfg, TOP_N
    )
    _print_row(
        "reversal_thr=0.0 only",
        reversal_only_result.trades,
        reversal_only_result.holding_days,
        reversal_only_result.exit_reasons,
    )

    print(
        "\nInterpretation: compare each row's mdd/std_period against the "
        "'no_early_exit (baseline)' row -- the HOLD/SELL layer's whole "
        "justification (per src/portfolio/optimizer.py's docstring) is "
        "risk control, not return improvement. A config is only "
        "supported if it lowers mdd/std_period without giving back most "
        "of cum_return. avg_hold_d and the exit-reason columns show how "
        "often each rule actually fires within the 5-day window; a rule "
        "that almost never fires is not doing anything and a threshold "
        "that fires on nearly every trade is probably too tight."
    )


if __name__ == "__main__":
    main()
