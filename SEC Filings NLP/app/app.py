"""SEC Filings NLP - Streamlit front end for the filing-sentiment research notebook.

Loads the notebook's scored 10-K dataset (32 large caps, fiscal 2016 onward:
Loughran-McDonald tone, year-over-year filing similarity, event dates), pulls
daily prices live, and rebuilds the market-adjusted event study interactively:
CAR curves by signal tercile, per-bucket significance, yearly information
coefficients, and a company-level explorer. Methodology matches the research
notebook in this folder: day 0 from the EDGAR acceptance timestamp with a 4pm
ET cutoff, market-adjusted abnormal returns vs SPY, within-cohort terciles.
"""
import os
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf
from scipy import stats

NAVY, BLUE, RED, GOLD, GRAY, GREEN = ("#14364f", "#2f6db4", "#c0392b", "#d9a02b",
                                      "#6b7280", "#2e7d5b")
BUCKET_COLORS = [RED, GRAY, GREEN]
BENCHMARK = "SPY"
PRICE_START = "2015-06-01"

SIGNALS = {
    "lm_tone_mdna": "Loughran-McDonald tone (MD&A)",
    "sim_mdna": "Year-over-year similarity (MD&A)",
    "lm_tone_risk": "Loughran-McDonald tone (Risk Factors)",
}

st.set_page_config(page_title="SEC Filings NLP", page_icon=":page_facing_up:",
                   layout="wide")


# ------------------------------------------------------------------ data layer
@st.cache_data(show_spinner=False)
def load_scored() -> pd.DataFrame:
    """Bundled per-filing dataset produced by the research notebook."""
    here = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(here, "..", "sec_nlp_scored_filings.csv")
    df = pd.read_csv(path, parse_dates=["day0", "report_date"])
    df = df.dropna(subset=["day0"])
    df["cohort_year"] = df["day0"].dt.year
    return df


@st.cache_data(ttl=24 * 3600, show_spinner=False)
def fetch_prices(tickers: Tuple[str, ...]) -> pd.DataFrame:
    """Adjusted-close panel for the universe plus SPY."""
    raw = yf.download(list(tickers), start=PRICE_START, auto_adjust=True,
                      progress=False)["Close"]
    clean = raw[~raw.index.duplicated(keep="first")].sort_index()
    idx = pd.to_datetime(clean.index)
    clean.index = idx.tz_localize(None) if idx.tz is not None else idx
    if clean.shape[0] < 500:
        raise RuntimeError(f"price history too short: {clean.shape}")
    return clean


# --------------------------------------------------------------------- engine
def bucket_within_cohort(df: pd.DataFrame, col: str, n_buckets: int) -> pd.Series:
    """Quantile buckets of a signal within each filing-year cohort (0 = lowest).

    Ranking is done inside each filing year so tone from different years is never
    mixed. A year needs at least 3 * n_buckets filings to split; thinner years
    return NaN (and are dropped by the caller).
    """
    def _q(x: pd.Series) -> pd.Series:
        if x.notna().sum() < 3 * n_buckets:
            return pd.Series(np.nan, index=x.index)
        return pd.qcut(x.rank(method="first"), n_buckets, labels=False)
    return df.groupby("cohort_year")[col].transform(_q)


def event_windows(ev: pd.DataFrame, ar: pd.DataFrame, cal: pd.DatetimeIndex,
                  pre: int, post: int) -> pd.DataFrame:
    """Market-adjusted return windows: one row per event, columns -pre..+post."""
    positions = cal.searchsorted(ev["day0"].values)
    rows, keep = [], []
    for (idx, e), p in zip(ev.iterrows(), positions):
        p = int(p)
        if p >= len(cal) or cal[p] != e["day0"] or p - pre < 0 or p + post >= len(cal):
            continue
        if e["ticker"] not in ar.columns:
            continue
        w = ar[e["ticker"]].iloc[p - pre: p + post + 1].to_numpy()
        if np.isnan(w).any():
            continue
        rows.append(w)
        keep.append(idx)
    return pd.DataFrame(rows, index=keep, columns=range(-pre, post + 1))


def yearly_ic(ev: pd.DataFrame, sig: str) -> Tuple[pd.Series, Dict[str, float]]:
    """Yearly Spearman IC of the signal vs the forward market-adjusted return."""
    d = ev.dropna(subset=[sig, "fwd_madj"])
    if "fwd_overlap" in d.columns:
        d = d[~d["fwd_overlap"].astype(bool)]
    ics = {}
    for y, g in d.groupby("cohort_year"):
        if len(g) >= 10:
            ics[y] = stats.spearmanr(g[sig], g["fwd_madj"]).correlation
    s = pd.Series(ics).sort_index()
    n = len(s)
    if n < 2:
        return s, {"mean": np.nan, "t": np.nan, "p": np.nan, "lo": np.nan, "hi": np.nan}
    se = s.std(ddof=1) / np.sqrt(n)
    t = s.mean() / se
    half = stats.t.ppf(0.975, df=n - 1) * se
    return s, {"mean": s.mean(), "t": t, "p": 2 * stats.t.sf(abs(t), df=n - 1),
               "lo": s.mean() - half, "hi": s.mean() + half}


# ------------------------------------------------------------------------- UI
st.title("NLP signals from SEC filings")
st.caption("Does 10-K language predict returns? Tone and filing-change signals for "
           "32 large caps, tested with a market-adjusted event study. "
           "Research notebook in this folder has the full methodology.")

scored = load_scored()
tickers = tuple(sorted(scored["ticker"].unique()) + [BENCHMARK])

with st.spinner("Loading prices from Yahoo Finance..."):
    try:
        prices = fetch_prices(tickers)
    except Exception as exc:
        st.error(f"Price download failed: {exc}. Try reloading in a minute.")
        st.stop()

returns = prices.pct_change().iloc[1:]
ar = returns.drop(columns=[BENCHMARK]).sub(returns[BENCHMARK], axis=0)
cal = returns.index

tab_event, tab_company, tab_about = st.tabs(
    ["Event study", "Company explorer", "About the method"])

# ------------------------------------------------------------ event study tab
with tab_event:
    c1, c2, c3, c4 = st.columns([2.2, 1.2, 1.2, 1.4])
    sig = c1.selectbox("Signal", list(SIGNALS), format_func=SIGNALS.get)
    post = c2.slider("Days after filing", 10, 60, 30, step=5)
    n_buckets = c3.radio("Buckets", [3, 5], horizontal=True)
    sectors = c4.multiselect("Sectors", sorted(scored["sector"].unique()))

    pool = scored if not sectors else scored[scored["sector"].isin(sectors)]
    ev = pool.dropna(subset=[sig]).copy()
    ev["bucket"] = bucket_within_cohort(ev, sig, n_buckets)
    ev = ev.dropna(subset=["bucket"])

    if ev.empty:
        # Buckets are ranked WITHIN each filing year (so 2016 tone is never compared
        # against 2024 tone), which needs at least 3 * n_buckets filings in a year.
        # A single sector has at most 8 companies (one 10-K each per year), so no year
        # clears the bar and every filing is dropped. Explain it instead of crashing.
        max_year = int(pool.dropna(subset=[sig]).groupby("cohort_year").size().max() or 0)
        st.info(
            f"**This selection is too small to form {n_buckets} buckets.** "
            f"Filings are ranked into buckets *within each filing year* (so tone from "
            f"different years is never mixed), which needs at least {3 * n_buckets} "
            f"filings in a year. The busiest year here has only {max_year}. "
            f"Pick more than one sector, or clear the sector filter for the full "
            f"universe, to see the event study. (Most pairs of sectors are enough.)"
        )
    else:
        panel = event_windows(ev, ar, cal, pre=5, post=post)
        car = panel.cumsum(axis=1)

        if len(panel) < 30:
            st.warning("Fewer than 30 usable events with this filter; treat the "
                       "result as noise rather than evidence.")

        fig = go.Figure()
        labels = ({0: "T1 (lowest)", n_buckets - 1: f"T{n_buckets} (highest)"}
                  if n_buckets > 3 else {0: "T1 (lowest)", 1: "T2", 2: "T3 (highest)"})
        for k in range(n_buckets):
            rows = car.loc[car.index.intersection(ev.index[ev["bucket"] == k])]
            if rows.empty:
                continue
            mean = 100 * rows.mean(axis=0)
            band = 100 * 1.96 * rows.std(axis=0) / np.sqrt(len(rows))
            color = BUCKET_COLORS[0] if k == 0 else (
                BUCKET_COLORS[2] if k == n_buckets - 1 else GRAY)
            name = labels.get(k, f"T{k + 1}")
            fig.add_trace(go.Scatter(x=list(mean.index), y=list(mean + band),
                                     mode="lines", line=dict(width=0), showlegend=False,
                                     hoverinfo="skip"))
            fig.add_trace(go.Scatter(x=list(mean.index), y=list(mean - band),
                                     mode="lines", line=dict(width=0), fill="tonexty",
                                     fillcolor=f"rgba{tuple(list(int(color[i:i+2], 16) for i in (1, 3, 5)) + [0.12])}",
                                     showlegend=False, hoverinfo="skip"))
            fig.add_trace(go.Scatter(x=list(mean.index), y=list(mean), mode="lines",
                                     line=dict(color=color, width=2.4),
                                     name=f"{name} (n={len(rows)})",
                                     hovertemplate="day %{x}: %{y:.2f}%<extra></extra>"))
        fig.add_vline(x=0, line_dash="dot", line_color=GRAY)
        fig.add_hline(y=0, line_color=GRAY, line_width=1)
        fig.update_layout(template="plotly_white", height=480,
                          title=f"Cumulative abnormal return by {SIGNALS[sig]} bucket",
                          xaxis_title="trading days relative to filing day 0",
                          yaxis_title="mean CAR (%), market-adjusted vs SPY")
        st.plotly_chart(fig, width="stretch")

        # per-bucket stats + spread
        car_final = car.iloc[:, -1]
        stats_rows = []
        for k in range(n_buckets):
            vals = car_final.loc[car_final.index.intersection(ev.index[ev["bucket"] == k])]
            if len(vals) < 2:
                continue
            t, p = stats.ttest_1samp(vals, 0.0)
            stats_rows.append({"bucket": labels.get(k, f"T{k + 1}"), "events": len(vals),
                               "mean CAR %": 100 * vals.mean(), "t-stat": t, "p-value": p})
        top = car_final.loc[car_final.index.intersection(ev.index[ev["bucket"] == n_buckets - 1])]
        bot = car_final.loc[car_final.index.intersection(ev.index[ev["bucket"] == 0])]
        if len(top) > 1 and len(bot) > 1:
            t, p = stats.ttest_ind(top, bot, equal_var=False)
            stats_rows.append({"bucket": "Top minus bottom", "events": len(top) + len(bot),
                               "mean CAR %": 100 * (top.mean() - bot.mean()),
                               "t-stat": t, "p-value": p})
        if stats_rows:
            st.dataframe(pd.DataFrame(stats_rows).set_index("bucket").round(3),
                         width="stretch")
        else:
            st.caption("Not enough events per bucket to tabulate bucket statistics.")

        ic_series, ic_sum = yearly_ic(ev, sig)
        lc, rc = st.columns([1.4, 1])
        with lc:
            icfig = go.Figure(go.Bar(x=list(ic_series.index), y=list(ic_series.values),
                                     marker_color=BLUE))
            icfig.add_hline(y=float(ic_series.mean()) if len(ic_series) else 0,
                            line_dash="dash", line_color=NAVY)
            icfig.update_layout(template="plotly_white", height=320,
                                title="Information coefficient by filing year",
                                xaxis_title="filing year",
                                yaxis_title="Spearman IC vs +1..+63d return")
            st.plotly_chart(icfig, width="stretch")
        with rc:
            st.metric("Mean yearly IC", f"{ic_sum['mean']:+.3f}" if pd.notna(ic_sum["mean"]) else "n/a")
            st.metric("t-statistic", f"{ic_sum['t']:.2f}" if pd.notna(ic_sum["t"]) else "n/a")
            if pd.notna(ic_sum["p"]):
                verdict = ("statistically significant at 5%" if ic_sum["p"] < 0.05 else
                           "not distinguishable from zero")
                st.write(f"95% CI [{ic_sum['lo']:+.3f}, {ic_sum['hi']:+.3f}], "
                         f"p = {ic_sum['p']:.3f}: **{verdict}** on this sample.")
            else:
                st.write("Too few filing years in this selection to estimate a "
                         "reliable information coefficient.")
            st.caption("With ~10 yearly observations only a large, steady IC clears "
                       "conventional significance. A null is the expected honest result "
                       "at this sample size.")

# ------------------------------------------------------- company explorer tab
with tab_company:
    tk = st.selectbox("Company", sorted(scored["ticker"].unique()))
    hist = scored[scored["ticker"] == tk].sort_values("day0")

    c1, c2 = st.columns(2)
    with c1:
        f1 = go.Figure()
        f1.add_trace(go.Scatter(x=hist["day0"], y=hist["lm_tone_mdna"],
                                mode="lines+markers", line=dict(color=BLUE),
                                name="LM tone (MD&A)"))
        f1.update_layout(template="plotly_white", height=340,
                         title=f"{tk}: filing tone by year",
                         yaxis_title="LM net tone")
        st.plotly_chart(f1, width="stretch")
    with c2:
        f2 = go.Figure()
        f2.add_trace(go.Scatter(x=hist["day0"], y=hist["sim_mdna"],
                                mode="lines+markers", line=dict(color=GOLD),
                                name="YoY similarity"))
        f2.update_layout(template="plotly_white", height=340,
                         title=f"{tk}: how much the MD&A repeats last year's",
                         yaxis_title="TF-IDF cosine similarity")
        st.plotly_chart(f2, width="stretch")

    px = prices[tk].dropna()
    f3 = go.Figure()
    f3.add_trace(go.Scatter(x=px.index, y=px.values, mode="lines",
                            line=dict(color=NAVY), name=f"{tk} adjusted close"))
    for _, e in hist.iterrows():
        f3.add_vline(x=e["day0"], line_dash="dot", line_color=GRAY, opacity=0.6)
    f3.update_layout(template="plotly_white", height=380,
                     title=f"{tk}: price with 10-K filing dates (dotted)",
                     yaxis_title="price (USD)", yaxis_type="log")
    st.plotly_chart(f3, width="stretch")

    show_cols = {"fy": "fiscal year", "day0": "event day 0",
                 "lm_tone_mdna": "LM tone (MD&A)", "sim_mdna": "YoY similarity",
                 "car_0_30": "CAR 0..+30", "fwd_madj": "fwd return +1..+63",
                 "parse7_ok": "MD&A parsed"}
    tbl = hist[list(show_cols)].rename(columns=show_cols).set_index("fiscal year")
    st.dataframe(tbl.round(4), width="stretch")

# ----------------------------------------------------------------- about tab
with tab_about:
    st.markdown("""
### What this app shows

Public companies file an annual report (a 10-K) with the SEC every year. The research
notebook behind this app downloaded about 320 of those filings for 32 large US
companies, read two sections of each one with code (the part where management explains
the year, and the part listing risks), and turned the text into numbers:

- **Tone**: how positive or negative the wording is, counted with the
  Loughran-McDonald dictionary, a word list built specifically for financial documents.
- **Change**: how similar this year's filing is to last year's. Research
  ("Lazy Prices", Cohen-Malloy-Nguyen 2020) found that companies that quietly rewrite
  their filings tend to do worse than companies that repeat themselves.

The **event study** tab checks what happened to each stock in the days after it filed,
compared with the market (SPY). Filings are grouped into buckets by tone or change,
and the chart shows the average market-adjusted path per bucket. If the top bucket
reliably beats the bottom one, the signal carries information.

Buckets are formed *within each filing year*, so tone from different years is never
mixed. That needs enough filings per year, which is why the sector filter works best
with more than one sector (or the full universe): a single sector has only a handful
of companies, too few to split a year into buckets.

### How to read the numbers

- **CAR** (cumulative abnormal return): the stock's return minus the market's, added
  up day by day from just before the filing.
- **IC** (information coefficient): the rank correlation between the signal and the
  next quarter's market-adjusted return, computed within each filing year. Values
  near zero mean the signal did not rank winners over losers.
- **t-stat / p-value**: whether the measured effect is larger than what pure noise
  would produce. On ~300 filings, small real effects are invisible; the notebook
  says so plainly rather than dressing up noise.

### Honest limitations

Only 32 surviving mega caps (survivorship bias works against the tone signal), about
300 events (low statistical power), dictionary scoring ignores negation ("not
profitable" counts as positive), and the market adjustment assumes every stock moves
one-for-one with SPY. The research notebook documents each of these and the
safeguards used (permutation baseline, no-look-ahead audits, parse-rate reporting).

Data: SEC EDGAR (filings, scored offline in the notebook), Yahoo Finance (prices,
fetched live). Nothing here is investment advice.
""")
