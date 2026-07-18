"""Pairs Trading Backtester - Streamlit front end for the stat-arb research notebook.

Screens all pairs of 12 large-cap US financials for cointegration (Engle-Granger)
on rolling formation windows, filters by Ornstein-Uhlenbeck half-life, then trades
z-score signals on the following out-of-sample window with per-leg costs. The slow
screening step is cached; entry/exit/stop thresholds, costs, and pair count are
live controls. Same methodology as the research notebook in this folder: frozen
formation parameters, walk-forward evaluation, Newey-West significance, and an
empirical market-neutrality check against SPY.
"""
import itertools
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import statsmodels.api as sm
import streamlit as st
import yfinance as yf
from scipy import stats as scistats
from statsmodels.tsa.stattools import coint

NAVY, BLUE, RED, GOLD, GRAY, GREEN = ("#14364f", "#2f6db4", "#c0392b", "#d9a02b",
                                      "#6b7280", "#2e7d5b")
PURPLE = "#7a6a8a"

TICKERS = ["JPM", "BAC", "WFC", "C", "GS", "MS",
           "USB", "PNC", "TFC", "SCHW", "COF", "STT"]
BENCHMARK = "SPY"
START = "2007-01-01"
TRADE_DAYS = 126
TRADING_DAYS_PER_YEAR = 252
ANN = np.sqrt(TRADING_DAYS_PER_YEAR)

# Selection filters are fixed at the notebook's values so the multiple-testing
# story stays honest (see the About tab).
EG_PVALUE_MAX = 0.01
HALF_LIFE_MIN, HALF_LIFE_MAX = 5.0, 60.0
BETA_MIN, BETA_MAX = 0.4, 2.5
FORMATION_CHOICES = {"12 months": 252, "24 months (notebook default)": 504,
                     "36 months": 756}


# ------------------------------------------------------------------ data layer
@st.cache_data(ttl=24 * 3600, show_spinner=False)
def fetch_prices() -> pd.DataFrame:
    """Adjusted-close panel for the universe plus SPY. Raises on failure."""
    raw = yf.download(TICKERS + [BENCHMARK], start=START, auto_adjust=True,
                      progress=False)["Close"]
    raw = raw[TICKERS + [BENCHMARK]]
    clean = raw[~raw.index.duplicated(keep="first")].sort_index()
    clean = clean.ffill().dropna(how="any")
    if clean.shape[0] < 1000:
        raise RuntimeError(f"price history too short: {clean.shape}")
    return clean


# --------------------------------------------------------------------- engine
def engle_granger(log_y: pd.Series, log_x: pd.Series) -> Tuple[float, float, float]:
    """Engle-Granger p-value plus OLS intercept and hedge ratio (y on x, logs)."""
    fit = sm.OLS(log_y, sm.add_constant(log_x)).fit()
    alpha, beta = float(fit.params.iloc[0]), float(fit.params.iloc[1])
    p_value = float(coint(log_y, log_x, trend="c")[1])
    return p_value, alpha, beta


def ou_half_life(spread: pd.Series) -> float:
    """OU half-life in days from the AR(1) fit; inf when no reversion measured."""
    ds = spread.diff().dropna()
    lag = spread.shift(1).loc[ds.index]
    b = float(sm.OLS(ds, sm.add_constant(lag)).fit().params.iloc[1])
    if b >= 0:
        return float("inf")
    return float(np.log(2.0) / -np.log(1.0 + b))


def screen_window(log_px: pd.DataFrame) -> pd.DataFrame:
    """EG + OU stats for every pair of one formation window."""
    rows = []
    for a, b in itertools.combinations(log_px.columns, 2):
        p_value, alpha, beta = engle_granger(log_px[a], log_px[b])
        spread = log_px[a] - alpha - beta * log_px[b]
        rows.append({"pair": f"{a}/{b}", "leg_a": a, "leg_b": b, "pvalue": p_value,
                     "alpha": alpha, "beta": beta, "half_life": ou_half_life(spread),
                     "mu": float(spread.mean()), "sigma": float(spread.std(ddof=1))})
    return pd.DataFrame(rows)


@st.cache_data(ttl=24 * 3600, show_spinner=False)
def screen_all_windows(formation_days: int, asof: str) -> Dict[int, pd.DataFrame]:
    """The slow step: screen every formation window once. Cached per formation
    length and data vintage (asof keeps the cache honest across daily updates)."""
    px = fetch_prices()[TICKERS]
    log_px = np.log(px)
    idx = px.index
    screens: Dict[int, pd.DataFrame] = {}
    starts = [s for s in range(0, len(idx) - formation_days, TRADE_DAYS)
              if len(idx) - (s + formation_days) >= 21]
    for s in starts:
        screens[s] = screen_window(log_px.iloc[s:s + formation_days])
    return screens


def select_pairs(screen: pd.DataFrame, max_pairs: int) -> pd.DataFrame:
    """The notebook's selection funnel: EG bar, half-life band, beta bounds."""
    ok = screen[
        (screen["pvalue"] <= EG_PVALUE_MAX)
        & screen["half_life"].between(HALF_LIFE_MIN, HALF_LIFE_MAX)
        & screen["beta"].between(BETA_MIN, BETA_MAX)
        & (screen["sigma"] > 0)
    ]
    return ok.nsmallest(max_pairs, "pvalue").reset_index(drop=True)


def zscore_positions(z: pd.Series, entry: float, exit_band: float,
                     stop: float) -> pd.Series:
    """Unit spread position decided at close t; +1 long spread, -1 short, 0 flat.
    Stop at |z| >= stop locks the pair out until |z| <= exit_band; forced flat on
    the final day. The caller shifts by one day before applying returns."""
    u = np.zeros(len(z))
    state, locked = 0, False
    for t, z_t in enumerate(z.values):
        if state == 0:
            if locked:
                if abs(z_t) <= exit_band:
                    locked = False
            elif entry <= abs(z_t) < stop:
                state = -1 if z_t > 0 else 1
        else:
            if abs(z_t) >= stop:
                state, locked = 0, True
            elif abs(z_t) <= exit_band:
                state = 0
        u[t] = state
    if len(u):
        u[-1] = 0
    return pd.Series(u, index=z.index)


def backtest_pair_window(px_a: pd.Series, px_b: pd.Series, r_a: pd.Series,
                         r_b: pd.Series, params: Dict, entry: float,
                         exit_band: float, stop: float, cost_bps: float,
                         window_id: int) -> Tuple[pd.DataFrame, List[Dict]]:
    """One pair, one trading window, frozen formation parameters."""
    beta, alpha = params["beta"], params["alpha"]
    spread = np.log(px_a) - alpha - beta * np.log(px_b)
    z = (spread - params["mu"]) / params["sigma"]
    u = zscore_positions(z, entry, exit_band, stop)

    w_a = u / (1.0 + beta)
    w_b = -u * beta / (1.0 + beta)
    held_a, held_b = w_a.shift(1).fillna(0.0), w_b.shift(1).fillna(0.0)
    gross = held_a * r_a + held_b * r_b
    turnover = (w_a - held_a).abs() + (w_b - held_b).abs()
    net = gross - turnover * (cost_bps / 1e4)
    daily = pd.DataFrame({"gross": gross, "net": net, "turnover": turnover,
                          "u": u, "z": z})

    trades, prev_u, entry_t = [], 0, None
    for t in range(len(u)):
        u_t = int(u.iloc[t])
        if prev_u == 0 and u_t != 0:
            entry_t = t
        elif prev_u != 0 and u_t == 0 and entry_t is not None:
            if t == len(u) - 1 and exit_band < abs(z.iloc[t]) < stop:
                reason = "window end"
            elif abs(z.iloc[t]) >= stop:
                reason = "stop"
            else:
                reason = "reverted"
            trades.append({"window": window_id, "pair": params["pair"],
                           "side": "long spread" if prev_u > 0 else "short spread",
                           "entry": u.index[entry_t].date(), "exit": u.index[t].date(),
                           "entry z": round(float(z.iloc[entry_t]), 2),
                           "exit z": round(float(z.iloc[t]), 2),
                           "days": t - entry_t,
                           "net pnl (bps)": round(float(net.iloc[entry_t:t + 1].sum()) * 1e4, 1),
                           "exit reason": reason})
            entry_t = None
        prev_u = u_t
    return daily, trades


def run_walk_forward(px: pd.DataFrame, screens: Dict[int, pd.DataFrame],
                     formation_days: int, entry: float, exit_band: float,
                     stop: float, cost_bps: float, max_pairs: int) -> Dict:
    """Assemble the walk-forward portfolio from cached screens. Fast."""
    prices = px[TICKERS]
    rets = prices.pct_change().fillna(0.0)
    idx = prices.index
    gross_parts, net_parts, turn_parts, trades_all, selections = [], [], [], [], []
    pair_net_acc: Dict[str, List[pd.Series]] = {}

    for w_id, s in enumerate(sorted(screens)):
        trade_idx = idx[s + formation_days:min(s + formation_days + TRADE_DAYS, len(idx))]
        selected = select_pairs(screens[s], max_pairs)
        w_gross = pd.Series(0.0, index=trade_idx)
        w_net = pd.Series(0.0, index=trade_idx)
        w_turn = pd.Series(0.0, index=trade_idx)
        k = len(selected)
        for _, row in selected.iterrows():
            p = row.to_dict()
            daily, trades = backtest_pair_window(
                prices[p["leg_a"]].loc[trade_idx], prices[p["leg_b"]].loc[trade_idx],
                rets[p["leg_a"]].loc[trade_idx], rets[p["leg_b"]].loc[trade_idx],
                p, entry, exit_band, stop, cost_bps, w_id)
            w_gross += daily["gross"] / k
            w_net += daily["net"] / k
            w_turn += daily["turnover"] / k
            trades_all.extend(trades)
            pair_net_acc.setdefault(p["pair"], []).append(daily["net"] / k)
            selections.append({"window": w_id, "trade_start": trade_idx[0],
                               "trade_end": trade_idx[-1], **p})
        gross_parts.append(w_gross)
        net_parts.append(w_net)
        turn_parts.append(w_turn)

    gross, net = pd.concat(gross_parts), pd.concat(net_parts)
    pair_net = pd.DataFrame({p: pd.concat(chunks).reindex(gross.index).fillna(0.0)
                             for p, chunks in pair_net_acc.items()})
    return {"gross": gross, "net": net, "turnover": pd.concat(turn_parts),
            "trades": pd.DataFrame(trades_all),
            "selections": pd.DataFrame(selections), "pair_net": pair_net,
            "n_windows": len(screens)}


@st.cache_data(ttl=24 * 3600, show_spinner=False)
def rolling_pvalue(leg_a: str, leg_b: str, formation_days: int,
                   asof: str) -> pd.Series:
    """Rolling EG p-value for one pair, stepped every 21 days. Cached per pair."""
    log_px = np.log(fetch_prices()[[leg_a, leg_b]])
    vals = {}
    for e in range(formation_days, len(log_px), 21):
        win = log_px.iloc[e - formation_days:e]
        vals[log_px.index[e - 1]] = float(coint(win[leg_a], win[leg_b], trend="c")[1])
    return pd.Series(vals)


# ------------------------------------------------------------------ statistics
def sharpe(r: pd.Series) -> float:
    sd = r.std(ddof=1)
    return float(r.mean() / sd * ANN) if sd > 0 else float("nan")


def cagr(r: pd.Series) -> float:
    yrs = len(r) / TRADING_DAYS_PER_YEAR
    return float((1 + r).prod() ** (1 / yrs) - 1) if yrs > 0 else float("nan")


def max_drawdown(r: pd.Series) -> float:
    w = (1 + r).cumprod()
    return float((w / w.cummax() - 1).min())


def drawdown_series(r: pd.Series) -> pd.Series:
    w = (1 + r).cumprod()
    return w / w.cummax() - 1.0


def significance(net: pd.Series, spy: pd.Series) -> Dict[str, float]:
    """Newey-West t-stat on the mean, Lo CI on the Sharpe, HAC beta to SPY."""
    y = net.values
    m = sm.OLS(y, np.ones((len(y), 1))).fit(cov_type="HAC", cov_kwds={"maxlags": 21})
    sr_d = float(net.mean() / net.std(ddof=1))
    se = np.sqrt((1 + 0.5 * sr_d ** 2) / len(net))
    zq = scistats.norm.ppf(0.975)
    mkt = sm.OLS(y, sm.add_constant(spy.values)).fit(cov_type="HAC",
                                                     cov_kwds={"maxlags": 21})
    return {"t_nw": float(m.tvalues[0]), "p_nw": float(m.pvalues[0]),
            "sr": sr_d * ANN, "sr_lo": (sr_d - zq * se) * ANN,
            "sr_hi": (sr_d + zq * se) * ANN,
            "beta": float(mkt.params[1]), "t_beta": float(mkt.tvalues[1]),
            "alpha_ann": float(mkt.params[0]) * TRADING_DAYS_PER_YEAR,
            "t_alpha": float(mkt.tvalues[0])}


# ------------------------------------------------------------------ chart kit
def equity_chart(net: pd.Series, gross: pd.Series, spy: pd.Series,
                 ew: pd.Series) -> go.Figure:
    fig = go.Figure()
    for name, series, color, width, dash in [
        ("Pairs NET", net, NAVY, 2.4, None),
        ("Pairs gross", gross, BLUE, 1.2, "dash"),
        ("SPY", spy, GRAY, 1.4, None),
        ("Equal-weight banks", ew, PURPLE, 1.4, None),
    ]:
        wealth = (1 + series).cumprod()
        fig.add_trace(go.Scatter(x=wealth.index, y=wealth.values, name=name,
                                 line={"color": color, "width": width, "dash": dash},
                                 hovertemplate="%{x|%b %Y}: $%{y:.2f}<extra>" + name + "</extra>"))
    fig.update_layout(template="plotly_white", height=450,
                      title="Out-of-sample growth of $1 (log scale)",
                      yaxis={"type": "log"}, margin={"l": 40, "r": 20, "t": 50, "b": 30},
                      legend={"orientation": "h", "yanchor": "top", "y": -0.12})
    return fig


def drawdown_chart(net: pd.Series) -> go.Figure:
    dd = drawdown_series(net)
    fig = go.Figure(go.Scatter(x=dd.index, y=dd.values, fill="tozeroy",
                               line={"color": RED, "width": 1},
                               hovertemplate="%{x|%b %Y}: %{y:.1%}<extra></extra>"))
    fig.update_layout(template="plotly_white", height=260,
                      title="Drawdown from peak (net)",
                      yaxis={"tickformat": ".0%"},
                      margin={"l": 40, "r": 20, "t": 50, "b": 30}, showlegend=False)
    return fig


def zscore_chart(z: pd.Series, entry: float, exit_band: float, stop: float,
                 pair: str, n_windows: int) -> go.Figure:
    fig = go.Figure(go.Scatter(x=z.index, y=z.values, mode="lines",
                               line={"color": NAVY, "width": 1},
                               hovertemplate="%{x|%d %b %Y}: z=%{y:.2f}<extra></extra>"))
    for lv, color, dash in [(entry, GOLD, "dash"), (-entry, GOLD, "dash"),
                            (stop, RED, "dot"), (-stop, RED, "dot"),
                            (exit_band, GRAY, "dash"), (-exit_band, GRAY, "dash")]:
        fig.add_hline(y=lv, line={"color": color, "width": 1, "dash": dash})
    fig.update_layout(template="plotly_white", height=340,
                      title=f"{pair}: z-score across its {n_windows} traded windows "
                            "(gaps are windows where it did not qualify)",
                      yaxis_title="z (formation sigmas)",
                      margin={"l": 40, "r": 20, "t": 50, "b": 30}, showlegend=False)
    return fig


# ------------------------------------------------------------------------ app
def main() -> None:
    st.set_page_config(page_title="Pairs Trading Backtester", page_icon="chart_with_upwards_trend",
                       layout="wide")
    st.title("Pairs Trading Backtester")
    st.caption("Walk-forward statistical arbitrage on 12 large-cap US financials: "
               "Engle-Granger cointegration screening on rolling formation windows, "
               "OU half-life filtering, z-score long-short signals, per-leg costs. "
               "Everything shown is out of sample.")

    with st.sidebar:
        st.header("Strategy controls")
        form_label = st.selectbox("Formation window", list(FORMATION_CHOICES),
                                  index=1,
                                  help="History used to select pairs and freeze parameters. "
                                       "Changing this re-runs the screen (about a minute, then cached).")
        formation_days = FORMATION_CHOICES[form_label]
        entry = st.slider("Entry threshold |z|", 1.0, 3.0, 2.0, 0.25,
                          help="Open when the spread is at least this many formation sigmas from its mean.")
        exit_band = st.slider("Exit threshold |z|", 0.0, 1.5, 0.5, 0.25,
                              help="Close when the spread has reverted to within this band.")
        stop = st.slider("Stop threshold |z|", 2.0, 5.0, 3.0, 0.25,
                         help="Force out and lock the pair until it re-enters the exit band.")
        cost_bps = st.slider("Cost per leg (bps)", 0.0, 25.0, 5.0, 2.5,
                             help="One-way commission plus half-spread plus slippage. "
                                  "A round trip is four legs.")
        max_pairs = st.slider("Max pairs per window", 1, 10, 5)
        st.caption("Selection filters are fixed at the notebook's values: "
                   f"EG p <= {EG_PVALUE_MAX}, half-life {HALF_LIFE_MIN:.0f} to "
                   f"{HALF_LIFE_MAX:.0f} days, hedge ratio {BETA_MIN} to {BETA_MAX}.")

    if entry >= stop:
        st.warning("Entry threshold is at or beyond the stop, so no trade can open. "
                   "Lower the entry or raise the stop.")

    try:
        with st.spinner("Loading prices from Yahoo Finance..."):
            px = fetch_prices()
    except Exception:
        st.error("Could not load prices from Yahoo Finance. Try again in a minute.")
        st.stop()
    asof = str(px.index[-1].date())

    with st.spinner("Screening all 66 pairs across formation windows "
                    "(first run per formation length takes about a minute)..."):
        screens = screen_all_windows(formation_days, asof)

    res = run_walk_forward(px, screens, formation_days, entry, exit_band, stop,
                           cost_bps, max_pairs)
    net, gross = res["net"], res["gross"]
    rets_all = px.pct_change().fillna(0.0)
    spy = rets_all[BENCHMARK].loc[net.index]
    ew = rets_all[TICKERS].mean(axis=1).loc[net.index]
    n_trades = len(res["trades"])
    sig = significance(net, spy) if n_trades and net.std() > 0 else None

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("Net Sharpe", f"{sharpe(net):.2f}" if sig else "n/a",
              help="Annualized, zero risk-free rate. The Lo 95% interval is in the tile below the charts.")
    c2.metric("Net CAGR", f"{cagr(net):.1%}" if n_trades else "n/a")
    c3.metric("Max drawdown", f"{max_drawdown(net):.1%}" if n_trades else "n/a")
    c4.metric("Beta to SPY", f"{sig['beta']:+.2f}" if sig else "n/a",
              delta=(f"t = {sig['t_beta']:+.1f}" if sig else None), delta_color="off",
              help="Market neutrality check: HAC regression of daily net returns on SPY.")
    c5.metric("Newey-West t-stat", f"{sig['t_nw']:+.2f}" if sig else "n/a",
              delta=(f"p = {sig['p_nw']:.3f}" if sig else None), delta_color="off",
              help="Is the mean daily net return distinguishable from zero under autocorrelation-robust errors?")
    c6.metric("Round trips", f"{n_trades}",
              help=f"{res['n_windows']} walk-forward windows, "
                   f"{res['selections']['window'].nunique() if len(res['selections']) else 0} with a qualifying pair")

    if not n_trades:
        st.info("No trades at these settings. The entry threshold may be too strict "
                "relative to the stop, or too few pairs qualify. Try entry 2.0, "
                "stop 3.0, max pairs 5.")
        st.stop()

    st.plotly_chart(equity_chart(net, gross, spy, ew), use_container_width=True)
    st.plotly_chart(drawdown_chart(net), use_container_width=True)
    if sig:
        st.caption(f"Sample {net.index[0].date()} to {net.index[-1].date()} | "
                   f"net Sharpe {sig['sr']:.2f} with Lo 95% CI [{sig['sr_lo']:.2f}, "
                   f"{sig['sr_hi']:.2f}] | annualized alpha {sig['alpha_ann']:+.1%} "
                   f"(t = {sig['t_alpha']:+.2f}) | SPY and the equal-weight basket are "
                   f"shown over the same out-of-sample days, costless.")

    tab_pairs, tab_trades, tab_about = st.tabs(
        ["Pair explorer", "Trades and attribution", "About and method"])

    with tab_pairs:
        sel = res["selections"]
        default_pair = (sel["pair"].value_counts().idxmax()
                        if len(sel) else f"{TICKERS[0]}/{TICKERS[1]}")
        all_pairs = [f"{a}/{b}" for a, b in itertools.combinations(TICKERS, 2)]
        pair = st.selectbox("Pair", all_pairs, index=all_pairs.index(default_pair),
                            help="Defaults to the most frequently selected pair.")
        leg_a, leg_b = pair.split("/")

        with st.spinner("Computing the rolling cointegration p-value (cached per pair)..."):
            roll_p = rolling_pvalue(leg_a, leg_b, formation_days, asof)
        figp = go.Figure(go.Scatter(x=roll_p.index, y=roll_p.values, mode="lines",
                                    line={"color": NAVY, "width": 1.3},
                                    hovertemplate="%{x|%b %Y}: p=%{y:.3f}<extra></extra>"))
        figp.add_hline(y=0.05, line={"color": GOLD, "width": 1, "dash": "dash"})
        figp.add_hline(y=EG_PVALUE_MAX, line={"color": RED, "width": 1, "dash": "dash"})
        pair_sel = sel[sel["pair"] == pair] if len(sel) else sel
        for _, r_ in pair_sel.iterrows():
            figp.add_vrect(x0=r_["trade_start"], x1=r_["trade_end"],
                           fillcolor="rgba(217, 160, 43, 0.18)", line_width=0)
        figp.update_layout(template="plotly_white", height=330,
                           title=f"{pair}: rolling {form_label} Engle-Granger p-value "
                                 "(shaded spans are windows where it was traded)",
                           yaxis={"range": [0, 1]},
                           margin={"l": 40, "r": 20, "t": 50, "b": 30}, showlegend=False)
        st.plotly_chart(figp, use_container_width=True)

        if len(pair_sel):
            z_parts = []
            log_all = np.log(px)
            for _, r_ in pair_sel.iterrows():
                widx = net.index[(net.index >= r_["trade_start"])
                                 & (net.index <= r_["trade_end"])]
                s = (log_all[leg_a].loc[widx] - r_["alpha"]
                     - r_["beta"] * log_all[leg_b].loc[widx])
                z_parts.append((s - r_["mu"]) / r_["sigma"])
            z_stitched = pd.concat(z_parts)
            st.plotly_chart(zscore_chart(z_stitched, entry, exit_band, stop, pair,
                                         len(pair_sel)), use_container_width=True)
            pair_trades = res["trades"][res["trades"]["pair"] == pair]
            if len(pair_trades):
                st.dataframe(pair_trades.drop(columns="pair"), width="stretch",
                             hide_index=True)
            else:
                st.info("Selected in those windows, but no z-score excursion reached "
                        "the entry threshold.")
        else:
            st.info(f"{pair} never passed the selection funnel at these settings; "
                    "the rolling p-value above shows why. Cointegration comes and "
                    "goes, which is exactly why the strategy re-selects every window.")

    with tab_trades:
        tr = res["trades"]
        win_rate = float((tr["net pnl (bps)"] > 0).mean())
        a, b, c, d = st.columns(4)
        a.metric("Win rate", f"{win_rate:.0%}")
        b.metric("Median holding", f"{tr['days'].median():.0f} days")
        c.metric("Avg net P&L per trade", f"{tr['net pnl (bps)'].mean():.0f} bps",
                 help="Basis points of the pair's capital, net of costs")
        d.metric("Stopped out", f"{int((tr['exit reason'] == 'stop').sum())} of {len(tr)}")

        contrib = res["pair_net"].sum().sort_values()
        figc = go.Figure(go.Bar(x=contrib.values * 100, y=contrib.index,
                                orientation="h",
                                marker_color=[RED if v < 0 else GREEN for v in contrib.values],
                                hovertemplate="%{y}: %{x:.1f}%<extra></extra>"))
        figc.update_layout(template="plotly_white", height=max(300, 26 * len(contrib)),
                           title="Per-pair net contribution, all out-of-sample windows "
                                 "(% of portfolio capital)",
                           margin={"l": 40, "r": 20, "t": 50, "b": 30}, showlegend=False)
        st.plotly_chart(figc, use_container_width=True)

        st.dataframe(tr, width="stretch", hide_index=True)
        st.download_button("Download trade ledger (CSV)",
                           data=tr.to_csv(index=False).encode(),
                           file_name="pairs_trades.csv", mime="text/csv")

    with tab_about:
        st.markdown(
            f"**Universe**: {', '.join(TICKERS)} ({len(TICKERS)} names, 66 pairs), "
            f"benchmark {BENCHMARK}, daily adjusted closes from Yahoo Finance, "
            f"{START} to {asof}.\n\n"
            "**Method**: each formation window runs the Engle-Granger two-step test "
            "on log prices for all 66 pairs, keeps candidates with p <= 0.01 "
            "(strict, because 66 simultaneous tests at 0.05 would pass about three "
            "false positives by luck), an Ornstein-Uhlenbeck half-life between 5 and "
            "60 days, and a hedge ratio between 0.4 and 2.5, then trades the next "
            "six months with parameters frozen. Signals decided at one close earn "
            "returns from the next; costs are charged per leg on every trade. "
            "Nothing is ever fit on the window it trades.\n\n"
            "**Honest caveats**: the universe is today's surviving large-cap "
            "financials, so failed firms (Lehman, Wachovia, Washington Mutual) are "
            "absent and the 2009-2012 stretch is flattered. No borrow fees or "
            "short-availability constraints are modeled, which is materially wrong "
            "for financials in late 2008. Fills are at the daily close. The "
            "research notebook in this repo folder documents all of this plus "
            "look-ahead audits, an in-sample cautionary comparison, and robustness "
            "grids.\n\n"
            "**Related**: [research notebook and project folder]"
            "(https://github.com/Avinashmhm/QuantProjects/tree/main/Pairs%20Trading) | "
            "[performancesheet.streamlit.app](https://performancesheet.streamlit.app) | "
            "[macronowcast.streamlit.app](https://macronowcast.streamlit.app)")


if __name__ == "__main__":
    main()
