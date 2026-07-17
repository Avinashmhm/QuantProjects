"""quantlib.tearsheet - the standardized, house-styled performance tear sheet.

One fixed exhibit every time, from a returns OR price series: cumulative-vs-benchmark, an
underwater (drawdown) plot, rolling Sharpe, a monthly-returns heatmap, and a return
distribution - plus a headline metrics table. Two renderers share one theme and one metric
source (quantlib.metrics): a static matplotlib/seaborn figure (the README hero) and an
interactive plotly dashboard saved as a standalone HTML file.
"""
from __future__ import annotations

import os
import numpy as np
import pandas as pd

try:
    from quantlib import metrics
except Exception:                    # running as a loose script next to metrics.py
    import metrics

TRADING_DAYS = metrics.TRADING_DAYS

# --- the one house theme (palette shared across every chart) ---
PALETTE = {
    "portfolio": "#1f4e79", "benchmark": "#9aa3ad", "positive": "#2e7d32",
    "negative": "#c62828", "accent": "#e8833a", "neutral": "#4f5b66",
}
SOURCE_NOTE = "quantlib.tearsheet"


def set_house_theme() -> None:
    import matplotlib as mpl
    import seaborn as sns
    sns.set_theme(style="whitegrid", context="notebook")
    mpl.rcParams.update({
        "figure.dpi": 110, "savefig.dpi": 150, "figure.facecolor": "white",
        "axes.facecolor": "white", "axes.titlesize": 12, "axes.titleweight": "bold",
        "axes.labelsize": 10, "axes.edgecolor": "#444444", "font.size": 10,
        "legend.frameon": False, "lines.linewidth": 1.6,
    })


def rolling_sharpe(returns: pd.Series, window: int = 126,
                   rf_periodic: float = 0.0) -> pd.Series:
    ex = returns - rf_periodic
    return (ex.rolling(window).mean() / ex.rolling(window).std(ddof=1)) * np.sqrt(TRADING_DAYS)


def monthly_table(returns: pd.Series) -> pd.DataFrame:
    m = returns.resample("M").apply(lambda s: (1 + s).prod() - 1.0)
    df = m.to_frame("ret")
    df["Year"], df["Month"] = df.index.year, df.index.month
    return df.pivot(index="Year", columns="Month", values="ret")


def summary_table(returns: pd.Series, benchmark: pd.Series | None = None,
                  rf_periodic: float = 0.0) -> pd.DataFrame:
    rows = [metrics.performance_summary(returns, rf_periodic, name="Strategy")]
    if benchmark is not None:
        rows.append(metrics.performance_summary(benchmark, rf_periodic, name="Benchmark"))
    return pd.DataFrame(rows).set_index("Series")


def tear_sheet_static(data: pd.Series, benchmark: pd.Series | None = None,
                      rf_periodic: float = 0.0, title: str = "Performance Tear Sheet",
                      outpath: str | None = None, kind: str = "auto",
                      rolling_window: int = 126):
    """Render the static house tear sheet. Returns (fig, summary_df); saves PNG if outpath."""
    import matplotlib.pyplot as plt
    import matplotlib.gridspec as gridspec
    from matplotlib.ticker import PercentFormatter
    import seaborn as sns
    set_house_theme()

    r = metrics.to_returns(data, kind)
    b = metrics.to_returns(benchmark, kind) if benchmark is not None else None
    if b is not None:
        b = b.reindex(r.index).dropna()
        r = r.reindex(b.index)

    wealth = metrics.cumulative_wealth(r)
    dd = metrics.drawdown_series(r)
    rs = rolling_sharpe(r, rolling_window, rf_periodic)
    heat = monthly_table(r)

    fig = plt.figure(figsize=(15, 12))
    gs = gridspec.GridSpec(3, 2, height_ratios=[1.1, 1.0, 1.0], hspace=0.40, wspace=0.22)

    ax1 = fig.add_subplot(gs[0, :])
    ax1.plot(wealth.index, wealth, color=PALETTE["portfolio"], label="Strategy")
    if b is not None:
        ax1.plot(b.index, metrics.cumulative_wealth(b), color=PALETTE["benchmark"], label="Benchmark")
    ax1.set_yscale("log"); ax1.set_title("Growth of $1 (log scale)")
    ax1.set_ylabel("Cumulative value ($)"); ax1.legend(loc="upper left")

    ax2 = fig.add_subplot(gs[1, 0])
    ax2.fill_between(dd.index, dd.values, 0, color=PALETTE["negative"], alpha=0.35)
    ax2.plot(dd.index, dd.values, color=PALETTE["negative"], lw=1.0)
    ax2.yaxis.set_major_formatter(PercentFormatter(1.0))
    ax2.set_title("Underwater Plot (drawdown from peak)"); ax2.set_ylabel("Drawdown")

    ax3 = fig.add_subplot(gs[1, 1])
    ax3.plot(rs.index, rs.values, color=PALETTE["accent"]); ax3.axhline(0, color="#888", lw=0.8)
    ax3.set_title(f"Rolling Sharpe ({rolling_window}d)"); ax3.set_ylabel("Annualized Sharpe")

    ax4 = fig.add_subplot(gs[2, 0])
    sns.heatmap(heat, cmap="RdYlGn", center=0, cbar_kws={"shrink": 0.8}, linewidths=0.4, ax=ax4)
    ax4.set_title("Monthly Returns (Year x Month)"); ax4.set_xlabel("Month"); ax4.set_ylabel("Year")

    ax5 = fig.add_subplot(gs[2, 1])
    ax5.hist(r, bins=60, density=True, color=PALETTE["portfolio"], alpha=0.6, label="Strategy")
    from scipy import stats as _st
    xs = np.linspace(r.min(), r.max(), 200)
    ax5.plot(xs, _st.norm.pdf(xs, r.mean(), r.std(ddof=1)), color=PALETTE["negative"], lw=1.5, label="Normal")
    ax5.set_title("Return Distribution vs Normal"); ax5.set_xlabel("Return"); ax5.legend(fontsize=8)

    fig.suptitle(title, fontsize=16, weight="bold", y=0.995)
    fig.text(0.99, 0.005, SOURCE_NOTE, ha="right", va="bottom", fontsize=7, color=PALETTE["neutral"])
    if outpath:
        os.makedirs(os.path.dirname(outpath) or ".", exist_ok=True)
        fig.savefig(outpath, bbox_inches="tight", dpi=150)
    return fig, summary_table(r, b, rf_periodic)


def tear_sheet_interactive(data: pd.Series, benchmark: pd.Series | None = None,
                           rf_periodic: float = 0.0, title: str = "Performance Tear Sheet",
                           outpath_html: str | None = None, kind: str = "auto",
                           rolling_window: int = 126):
    """Render the interactive plotly dashboard. Returns the figure; saves standalone HTML."""
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots

    r = metrics.to_returns(data, kind)
    b = metrics.to_returns(benchmark, kind) if benchmark is not None else None
    if b is not None:
        b = b.reindex(r.index).dropna(); r = r.reindex(b.index)
    wealth = metrics.cumulative_wealth(r); dd = metrics.drawdown_series(r)
    rs = rolling_sharpe(r, rolling_window, rf_periodic); heat = monthly_table(r)

    fig = make_subplots(rows=3, cols=2, specs=[[{"colspan": 2}, None], [{}, {}], [{}, {}]],
                        subplot_titles=("Growth of $1 (log)", "Underwater (drawdown)",
                                        f"Rolling Sharpe ({rolling_window}d)",
                                        "Monthly Returns", "Return Distribution"),
                        vertical_spacing=0.09, horizontal_spacing=0.08)
    fig.add_trace(go.Scatter(x=wealth.index, y=wealth, name="Strategy",
                             line=dict(color=PALETTE["portfolio"])), row=1, col=1)
    if b is not None:
        fig.add_trace(go.Scatter(x=b.index, y=metrics.cumulative_wealth(b), name="Benchmark",
                                 line=dict(color=PALETTE["benchmark"])), row=1, col=1)
    fig.update_yaxes(type="log", row=1, col=1)
    fig.add_trace(go.Scatter(x=dd.index, y=dd, fill="tozeroy", name="Drawdown",
                             line=dict(color=PALETTE["negative"]), showlegend=False), row=2, col=1)
    fig.add_trace(go.Scatter(x=rs.index, y=rs, name="Rolling Sharpe",
                             line=dict(color=PALETTE["accent"]), showlegend=False), row=2, col=2)
    fig.add_trace(go.Heatmap(z=heat.values, x=[str(c) for c in heat.columns],
                             y=[str(i) for i in heat.index], colorscale="RdYlGn", zmid=0,
                             showscale=False), row=3, col=1)
    fig.add_trace(go.Histogram(x=r.values, histnorm="probability density", name="Returns",
                               marker_color=PALETTE["portfolio"], showlegend=False), row=3, col=2)
    fig.update_layout(title=dict(text=title, font=dict(size=18)), template="plotly_white",
                      height=950, width=1200, margin=dict(t=80))
    if outpath_html:
        os.makedirs(os.path.dirname(outpath_html) or ".", exist_ok=True)
        fig.write_html(outpath_html, include_plotlyjs=True)   # truly standalone
    return fig


def tear_sheet(data: pd.Series, benchmark: pd.Series | None = None, rf_periodic: float = 0.0,
               title: str = "Performance Tear Sheet", output_dir: str | None = None,
               slug: str = "tear_sheet", interactive: bool = True, kind: str = "auto"):
    """One call: static PNG (hero) + metrics table (CSV) + optional interactive HTML.

    output_dir defaults to env QUANT_OUTPUT_DIR or 'outputs'. Returns the summary DataFrame.
    """
    output_dir = output_dir or os.environ.get("QUANT_OUTPUT_DIR") or "outputs"
    os.makedirs(output_dir, exist_ok=True)
    fig, summary = tear_sheet_static(data, benchmark, rf_periodic, title,
                                     os.path.join(output_dir, f"{slug}_hero.png"), kind)
    summary.to_csv(os.path.join(output_dir, f"{slug}_metrics.csv"))
    if interactive:
        tear_sheet_interactive(data, benchmark, rf_periodic, title,
                               os.path.join(output_dir, f"{slug}_dashboard.html"), kind)
    return summary


if __name__ == "__main__":
    import matplotlib
    matplotlib.use("Agg")
    rng = np.random.default_rng(0)
    idx = pd.date_range("2016-01-01", periods=TRADING_DAYS * 8, freq="B")
    strat = pd.Series(rng.normal(0.0006, 0.011, len(idx)), index=idx)
    bench = pd.Series(rng.normal(0.0004, 0.010, len(idx)), index=idx)
    out = os.environ.get("QUANT_OUTPUT_DIR", "/tmp/ts_demo")
    s = tear_sheet(strat, bench, output_dir=out, slug="demo", title="Demo Tear Sheet")
    print(s.round(3).to_string())
    print("artifacts in", out, "->", sorted(os.listdir(out)))
