"""Turn a saved run (src/reporting/run_log.py) into PNG time-series figures.

    PYTHONPATH=. python3 scripts/plot_run.py                    # latest run
    PYTHONPATH=. python3 scripts/plot_run.py reports/runs/<dir>
    PYTHONPATH=. python3 scripts/plot_run.py --series "top_n=10"  # only matching series

Writes into <run_dir>/figures/:
    equity.png     compounded net equity per series, one subplot per panel (log y)
    drawdown.png   drawdown from running peak, same layout
    ic.png         rolling-mean daily rank IC (top row) and cumulative IC
                   (bottom row; its slope is the mean IC, so flattening = decay)
    summary.csv    per panel/series: cumulative return, MDD, hit rate,
                   mean period return, periods, mean IC

Reads only the files in the run directory -- never the dataset or the test split.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

from src.reporting.run_log import LoadedRun, _slug, latest_run_dir, load_run  # noqa: E402


def equity_curves(periods: pd.DataFrame) -> pd.DataFrame:
    """Long frame: panel, series, decision_date, equity (starts at 1.0), drawdown."""
    out = []
    for (panel, series), group in periods.groupby(["panel", "series"], sort=False):
        group = group.sort_values("decision_date")
        equity = (1.0 + group["period_return"]).cumprod()
        out.append(
            pd.DataFrame(
                {
                    "panel": panel,
                    "series": series,
                    "decision_date": group["decision_date"].to_numpy(),
                    "equity": equity.to_numpy(),
                    "drawdown": (equity / equity.cummax() - 1.0).to_numpy(),
                }
            )
        )
    return pd.concat(out, ignore_index=True)


def summarize(run: LoadedRun) -> pd.DataFrame:
    rows = []
    for (panel, series), group in run.periods.groupby(["panel", "series"], sort=False):
        r = group.sort_values("decision_date")["period_return"]
        equity = (1.0 + r).cumprod()
        rows.append(
            {
                "panel": panel,
                "series": series,
                "periods": len(r),
                "cum_return": float(equity.iloc[-1] - 1.0),
                "mean_period_return": float(r.mean()),
                "hit_rate": float((r > 0).mean()),
                "max_drawdown": float((equity / equity.cummax() - 1.0).min()),
            }
        )
    summary = pd.DataFrame(rows)
    if run.ic is not None and not run.ic.empty:
        # Same convention as summarize_ic(): undefined days count as 0.
        # IC is stored per strategy ("ml"), returns per strategy+setting
        # ("ml top_n=10"), so the IC is attached by strategy name.
        mean_ic = (
            run.ic.assign(ic=run.ic["ic"].fillna(0.0))
            .groupby(["panel", "series"], sort=False)["ic"].mean()
            .rename("mean_ic").reset_index()
            .rename(columns={"series": "strategy"})
        )
        summary["strategy"] = summary["series"].map(strategy_of)
        summary = summary.merge(mean_ic, on=["panel", "strategy"], how="left").drop(columns="strategy")
    return summary


def _panel_grid(n_panels: int, n_rows: int = 1, height: float = 3.6):
    fig, axes = plt.subplots(
        n_rows, n_panels, figsize=(5.2 * n_panels, height * n_rows), squeeze=False, sharey="row"
    )
    return fig, axes


def _finish(fig, axes, path: Path, title: str) -> None:
    handles, labels = [], []
    for ax in axes.flat:
        for h, l in zip(*ax.get_legend_handles_labels()):
            if l not in labels:
                handles.append(h)
                labels.append(l)
    if handles:
        fig.legend(handles, labels, loc="lower center", ncol=min(len(labels), 6), frameon=False)
    fig.suptitle(title)
    fig.tight_layout(rect=(0, 0.08 if handles else 0, 1, 0.95))
    fig.savefig(path, dpi=130)
    plt.close(fig)
    print(f"[plot_run] {path}")


def strategy_of(series: str) -> str:
    """"ml top_n=10" -> "ml": the part before the first space."""
    return str(series).split(" ", 1)[0]


_LINESTYLES = ("-", "--", ":", "-.")


def series_styles(names) -> dict[str, dict]:
    """Same strategy -> same color in every figure; settings -> line style."""
    names = list(dict.fromkeys(names))
    strategies = list(dict.fromkeys(strategy_of(n) for n in names))
    cmap = plt.get_cmap("tab10")
    styles, seen = {}, {}
    for name in names:
        strategy = strategy_of(name)
        k = seen.get(strategy, 0)
        seen[strategy] = k + 1
        styles[name] = {
            "color": cmap(strategies.index(strategy) % 10),
            "linestyle": _LINESTYLES[k % len(_LINESTYLES)],
        }
    return styles


def plot_equity_and_drawdown(
    curves: pd.DataFrame, out_dir: Path, title: str, log_y: bool, styles: dict[str, dict]
) -> None:
    panels = list(dict.fromkeys(curves["panel"]))

    for column, filename, ylabel in (
        ("equity", "equity.png", "equity (start = 1.0)"),
        ("drawdown", "drawdown.png", "drawdown"),
    ):
        fig, axes = _panel_grid(len(panels))
        for ax, panel in zip(axes[0], panels):
            sub = curves[curves["panel"] == panel]
            for series, group in sub.groupby("series", sort=False):
                ax.plot(group["decision_date"], group[column], label=series, lw=1.2, **styles[series])
            ax.set_title(panel, fontsize=10)
            ax.grid(alpha=0.3)
            if column == "equity":
                ax.axhline(1.0, color="gray", lw=0.8)
                if log_y:
                    ax.set_yscale("log")
                    ax.yaxis.set_major_formatter(matplotlib.ticker.FormatStrFormatter("%.2g"))
                    ax.yaxis.set_minor_formatter(matplotlib.ticker.FormatStrFormatter("%.2g"))
            else:
                ax.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0))
            ax.tick_params(axis="x", labelrotation=30, labelsize=8)
        axes[0][0].set_ylabel(ylabel)
        _finish(fig, axes, out_dir / filename, f"{title} - {column}")


def plot_ic(ic: pd.DataFrame, out_dir: Path, title: str, window: int, styles: dict[str, dict]) -> None:
    panels = list(dict.fromkeys(ic["panel"]))

    fig, axes = _panel_grid(len(panels), n_rows=2)
    for col, panel in enumerate(panels):
        sub = ic[ic["panel"] == panel]
        for series, group in sub.groupby("series", sort=False):
            group = group.sort_values("trade_date")
            filled = group["ic"].fillna(0.0)
            dates = group["trade_date"]
            axes[0][col].plot(
                dates, filled.rolling(window, min_periods=max(5, window // 3)).mean(),
                label=series, color=styles[series]["color"], lw=1.1,
            )
            axes[1][col].plot(dates, filled.cumsum(), label=series, color=styles[series]["color"], lw=1.1)
        axes[0][col].set_title(panel, fontsize=10)
        for row in (0, 1):
            axes[row][col].axhline(0.0, color="gray", lw=0.8)
            axes[row][col].grid(alpha=0.3)
            axes[row][col].tick_params(axis="x", labelrotation=30, labelsize=8)
    axes[0][0].set_ylabel(f"rolling {window}d mean IC")
    axes[1][0].set_ylabel("cumulative IC")
    _finish(fig, axes, out_dir / "ic.png", f"{title} - daily rank IC")


def _filter(df: pd.DataFrame | None, series: str | None, panel: str | None) -> pd.DataFrame | None:
    if df is None:
        return None
    if series:
        df = df[df["series"].str.contains(series, regex=False)]
    if panel:
        df = df[df["panel"].str.contains(panel, regex=False)]
    return df


def _filter_ic(ic: pd.DataFrame | None, periods: pd.DataFrame, panel: str | None) -> pd.DataFrame | None:
    """Keep IC of the strategies that survived the --series filter."""
    if ic is None:
        return None
    kept = {strategy_of(s) for s in periods["series"]}
    return _filter(ic[ic["series"].isin(kept)], None, panel)


def main(argv: list[str] | None = None) -> Path:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("run_dir", nargs="?", help="run directory (default: latest under reports/runs)")
    parser.add_argument("--series", help="keep only series whose name contains this text")
    parser.add_argument("--panel", help="keep only panels whose name contains this text")
    parser.add_argument("--ic-window", type=int, default=60, help="rolling window in trading days (default 60)")
    parser.add_argument("--linear", action="store_true", help="linear instead of log y-axis for equity")
    args = parser.parse_args(argv)

    run_dir = Path(args.run_dir) if args.run_dir else latest_run_dir()
    run = load_run(run_dir)
    periods = _filter(run.periods, args.series, args.panel)
    if periods.empty:
        raise SystemExit("No series left after filtering.")
    run = LoadedRun(
        run.run_dir, run.meta, periods,
        _filter(run.trades, args.series, args.panel),
        _filter_ic(run.ic, periods, args.panel),
    )

    # Filtered views go to their own folder so they never overwrite the full one.
    suffix = "_".join(_slug(v) for v in (args.series, args.panel) if v)
    out_dir = run_dir / (f"figures_{suffix}" if suffix else "figures")
    out_dir.mkdir(exist_ok=True)
    title = run.meta.get("run_name", run_dir.name)

    names = list(run.periods["series"]) + (list(run.ic["series"]) if run.ic is not None else [])
    styles = series_styles(names)
    plot_equity_and_drawdown(equity_curves(run.periods), out_dir, title, not args.linear, styles)
    if run.ic is not None and not run.ic.empty:
        plot_ic(run.ic, out_dir, title, args.ic_window, styles)

    summary = summarize(run)
    summary.to_csv(out_dir / "summary.csv", index=False)
    with pd.option_context("display.float_format", "{:.4f}".format, "display.width", 160):
        print(summary.to_string(index=False))
    return out_dir


if __name__ == "__main__":
    main()
