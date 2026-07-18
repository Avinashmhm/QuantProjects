"""Tear Sheet Generator - Streamlit front end for the quantlib tear sheet pipeline.

Type any ticker, optionally pick a benchmark and a date range, and the standard
house tear sheet renders in the browser. All numbers come from quantlib.metrics,
so the output matches the published static tear sheets in this folder.
"""
import contextlib
import datetime as dt
import io
import os
import sys

import matplotlib
matplotlib.use("Agg")

import streamlit as st

# Make the vendored quantlib importable regardless of the launch directory.
APP_DIR = os.path.dirname(os.path.abspath(__file__))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from quantlib import data as qdata
from quantlib import tearsheet as qts

st.set_page_config(page_title="Tear Sheet Generator", page_icon=":chart_with_upwards_trend:",
                   layout="wide")

st.title("Performance Tear Sheet Generator")
st.caption("Enter any [Yahoo Finance](https://finance.yahoo.com) symbol for a house-style "
           "performance and risk tear sheet. Type in the boxes below to see suggestions, or "
           "enter any symbol that is not on the list. "
           "Data: Yahoo Finance adjusted close, cached after the first fetch.")

with st.expander("New to tickers? How to type different asset types"):
    st.markdown(
        "- **Stocks and ETFs**: just the ticker, like `NVDA` for NVIDIA or `SPY` for an "
        "S&P 500 fund.\n"
        "- **Market indexes** start with a caret `^`: `^GSPC` is the S&P 500 index itself, "
        "`^IXIC` is the Nasdaq Composite, `^VIX` is the volatility index. An index is the "
        "measuring stick for a market, not a fund you can buy, so it leaves out dividends.\n"
        "- **Futures** end in `=F`: `ES=F` is S&P 500 futures, `GC=F` is gold, `CL=F` is "
        "crude oil. Futures are the contracts traders use to bet on where a price is headed. "
        "Yahoo chains the expiring contracts into one continuous history, so treat long-run "
        "futures numbers as approximate.\n"
        "- **Crypto** is written as a pair: `BTC-USD` is Bitcoin priced in dollars, "
        "`ETH-USD` is Ethereum.\n"
        "- Anything Yahoo Finance recognizes works here, even if it does not appear in the "
        "suggestions.")


@st.cache_data
def load_symbol_options():
    """Suggestion list: US-listed stocks and ETFs plus common indexes, futures, and crypto."""
    import csv
    options = []
    with open(os.path.join(APP_DIR, "tickers.csv"), newline="") as f:
        for row in csv.reader(f):
            options.append(f"{row[0]}  ({row[1]})" if len(row) > 1 and row[1] else row[0])
    return options


OPTIONS = load_symbol_options()


def default_index(symbol: str) -> int:
    prefix = f"{symbol}  ("
    for i, option in enumerate(OPTIONS):
        if option == symbol or option.startswith(prefix):
            return i
    return 0


def symbol_of(selection) -> str:
    """The symbol from a suggestion label, or the raw typed value, uppercased."""
    return str(selection).split()[0].strip().upper() if selection else ""


with st.form("inputs"):
    c1, c2, c3, c4 = st.columns([1.2, 1.2, 1, 1])
    ticker = symbol_of(c1.selectbox(
        "Ticker", OPTIONS, index=default_index("NVDA"), accept_new_options=True,
        help="Type to search the list, or enter any Yahoo Finance symbol"))
    benchmark = symbol_of(c2.selectbox(
        "Benchmark ticker", OPTIONS, index=default_index("SPY"), accept_new_options=True,
        help="Type to search the list, or enter any Yahoo Finance symbol"))
    start = c3.date_input("Start date", dt.date(2015, 1, 1), min_value=dt.date(1980, 1, 1))
    end = c4.date_input("End date", dt.date.today())
    use_bench = st.checkbox("Compare to a benchmark", value=True)
    submitted = st.form_submit_button("Generate Tear Sheet", type="primary")

if not submitted:
    st.info("Set your inputs and click Generate Tear Sheet.")
    st.stop()

if not ticker:
    st.error("Enter a ticker symbol.")
    st.stop()
if start >= end:
    st.error("Start date must be before end date.")
    st.stop()
if use_bench and benchmark == ticker:
    st.warning(f"Benchmark is the same as the ticker ({ticker}); showing {ticker} on its own.")
    use_bench = False

tickers = [ticker] + ([benchmark] if use_bench and benchmark else [])


@st.cache_data(show_spinner=False, ttl=60 * 60)
def fetch_prices(symbols: tuple, start_iso: str, end_iso: str):
    """Fetch adjusted closes via quantlib and capture its provenance printout."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        px = qdata.get_prices(list(symbols), start=start_iso, end=end_iso)
    return px, buf.getvalue()


with st.spinner(f"Fetching {', '.join(tickers)}..."):
    prices, provenance = fetch_prices(tuple(tickers), str(start), str(end))

# quantlib falls back to clearly labeled synthetic data when a fetch fails.
# In the app that means a bad ticker or an outage, so stop rather than plot fake prices.
if "SYNTHETIC" in provenance:
    fetch_prices.clear()
    st.error(f"Could not fetch real price data for {', '.join(tickers)}. "
             "Check the ticker spelling (Yahoo Finance symbols) and the date range "
             "(needs at least ~3 months of history), then try again.")
    st.stop()

returns = prices[ticker].pct_change().dropna()
bench_returns = prices[benchmark].pct_change().dropna() if use_bench else None

title = f"{ticker} vs {benchmark}" if use_bench else ticker
window_note = (f"{prices.index[0].date()} to {prices.index[-1].date()}, "
               f"{len(prices):,} trading days")

summary = qts.summary_table(returns, bench_returns)
strat = summary.iloc[0]

m1, m2, m3, m4, m5 = st.columns(5)
m1.metric("CAGR", f"{strat['CAGR']:.1%}")
m2.metric("Ann. Vol", f"{strat['Ann.Vol']:.1%}")
m3.metric("Sharpe", f"{strat['Sharpe']:.2f}")
m4.metric("Max Drawdown", f"{strat['MaxDrawdown']:.1%}")
m5.metric("Hit Rate", f"{strat['HitRate']:.1%}")
st.caption(f"{title} | {window_note}")

fig = qts.tear_sheet_interactive(returns, bench_returns, kind="returns",
                                 title=f"{title} Performance Tear Sheet")
fig.update_layout(width=None, autosize=True)
st.plotly_chart(fig)

st.subheader("Full metrics")
pct_cols = ["CAGR", "Ann.Vol", "MaxDrawdown", "HitRate", "VaR95", "CVaR95",
            "BestDay", "WorstDay"]
ratio_cols = ["Sharpe", "Sortino", "Calmar", "Skew", "Kurtosis"]
styled = summary.style.format({c: "{:.2%}" for c in pct_cols} |
                              {c: "{:.2f}" for c in ratio_cols})
st.dataframe(styled, width="stretch")

png_buf = io.BytesIO()
static_fig, _ = qts.tear_sheet_static(returns, bench_returns, kind="returns",
                                      title=f"{title} Performance Tear Sheet")
static_fig.savefig(png_buf, format="png", bbox_inches="tight", dpi=150)
slug = f"{ticker}_vs_{benchmark}" if use_bench else ticker
st.download_button("Download PNG tear sheet", data=png_buf.getvalue(),
                   file_name=f"{slug}_tear_sheet.png", mime="image/png")
