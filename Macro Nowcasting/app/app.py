"""Macro Recession Dashboard - Streamlit front end for the recession nowcasting model.

Pulls live FRED data (no API key needed), fits a logistic regression of a strictly
forward-looking NBER recession label on the yield curve and a leading-indicator set,
and renders the probability gauge, the animated Treasury curve, the Sahm Rule, and a
financial-conditions index. Same methodology as the research notebook in this folder:
publication-lag alignment, embargoed out-of-sample split, HAC standard errors.
"""
import gzip
import io
import urllib.request
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import statsmodels.api as sm
import streamlit as st

NAVY, BLUE, RED, GOLD, GRAY, GREEN = ("#14364f", "#2f6db4", "#c0392b", "#d9a02b",
                                      "#6b7280", "#2e7d5b")
SHADE = "rgba(160, 168, 182, 0.35)"
START = "1976-01-01"
PUB_LAG = 1          # months between a macro month and its data release
TEST_START = pd.Timestamp("2006-01-01")
# FRED's CDN stalls terse bot-style user agents; the contact format passes.
USER_AGENT = "quantprojects-macro-dashboard/1.0 (avinmaha09@gmail.com)"

SERIES = {
    "DGS10": "10Y Treasury yield", "DGS2": "2Y Treasury yield", "DGS1": "1Y Treasury yield",
    "DGS5": "5Y Treasury yield", "DGS7": "7Y Treasury yield", "DGS30": "30Y Treasury yield",
    "TB3MS": "3M T-bill rate", "BAA": "Moody's Baa corporate yield",
    "UNRATE": "Unemployment rate", "PAYEMS": "Nonfarm payrolls",
    "ICSA": "Initial jobless claims", "PERMIT": "Building permits",
    "UMCSENT": "Consumer sentiment", "NFCI": "Chicago Fed NFCI",
    "USREC": "NBER recession indicator", "SAHMREALTIME": "Sahm Rule (real time)",
}
CRITICAL = ("DGS10", "TB3MS", "UNRATE", "USREC")
CURVE_YEARS = {"TB3MS": 0.25, "DGS1": 1, "DGS2": 2, "DGS5": 5, "DGS7": 7,
               "DGS10": 10, "DGS30": 30}
FULL_FEATURES = ["SPREAD_10Y3M", "CREDIT_SPREAD", "PAYEMS_G6M", "CLAIMS_CHG12M",
                 "PERMIT_CHG12M", "SENTIMENT_CHG12M"]


def month_end_alias() -> str:
    """Month-end resample alias for the running pandas ('ME' on 2.2+, 'M' before)."""
    try:
        pd.tseries.frequencies.to_offset("ME")
        return "ME"
    except Exception:
        return "M"


MONTH_END = month_end_alias()


@st.cache_data(ttl=24 * 3600, show_spinner=False)
def fetch_fred(sid: str) -> pd.Series:
    """One FRED series via the keyless public CSV endpoint. Raises on failure."""
    url = (f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}"
           f"&cosd={START}")
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    raw = b""
    for attempt in (1, 2):
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                raw = r.read()
            break
        except Exception:
            if attempt == 2:
                raise
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    df = pd.read_csv(io.BytesIO(raw))
    df.columns = ["DATE", sid]
    s = pd.to_numeric(df[sid].replace(".", np.nan), errors="coerce")
    s.index = pd.to_datetime(df["DATE"])
    s.name = sid
    return s.dropna()


@st.cache_data(ttl=24 * 3600, show_spinner=False)
def load_panel() -> Tuple[pd.DataFrame, List[str]]:
    """Monthly month-end panel of every available series, plus the list that failed."""
    raw: Dict[str, pd.Series] = {}
    failed: List[str] = []
    for sid in SERIES:
        try:
            raw[sid] = fetch_fred(sid)
        except Exception:
            failed.append(sid)
    if any(sid not in raw for sid in CRITICAL):
        raise RuntimeError(f"critical FRED series unavailable: "
                           f"{[s for s in CRITICAL if s not in raw]}")
    monthly = pd.DataFrame({sid: s.resample(MONTH_END).mean() for sid, s in raw.items()})
    monthly = monthly.loc[monthly.index >= START]
    if "UMCSENT" in monthly:
        monthly["UMCSENT"] = monthly["UMCSENT"].ffill(limit=2)  # quarterly before 1978
    monthly["USREC"] = monthly["USREC"].round()
    return monthly, failed


def recession_episodes(rec: pd.Series) -> List[Tuple[pd.Timestamp, pd.Timestamp]]:
    r = rec.fillna(0).astype(int)
    change = r.diff().fillna(r.iloc[0])
    starts = list(r.index[change == 1])
    ends = list(r.index[change == -1])
    if len(ends) < len(starts):
        ends.append(r.index[-1])
    return list(zip(starts, ends))


def build_features(monthly: pd.DataFrame) -> pd.DataFrame:
    """Model inputs, shifted so month t uses only data published by the end of month t."""
    feat = pd.DataFrame(index=monthly.index)
    feat["SPREAD_10Y3M"] = monthly["DGS10"] - monthly["TB3MS"]
    if "DGS2" in monthly:
        feat["SPREAD_10Y2Y"] = monthly["DGS10"] - monthly["DGS2"]
    if "BAA" in monthly:
        feat["CREDIT_SPREAD"] = monthly["BAA"] - monthly["DGS10"]
    if "PAYEMS" in monthly:
        feat["PAYEMS_G6M"] = (np.log(monthly["PAYEMS"]).diff(6) * 2 * 100).shift(PUB_LAG)
    if "ICSA" in monthly:
        c3 = monthly["ICSA"].rolling(3).mean()
        feat["CLAIMS_CHG12M"] = (np.log(c3).diff(12) * 100).shift(PUB_LAG)
    if "PERMIT" in monthly:
        feat["PERMIT_CHG12M"] = (np.log(monthly["PERMIT"]).diff(12) * 100).shift(PUB_LAG)
    if "UMCSENT" in monthly:
        feat["SENTIMENT_CHG12M"] = monthly["UMCSENT"].diff(12).shift(PUB_LAG)
    return feat


def build_label(usrec: pd.Series, horizon: int) -> pd.Series:
    """1 if a recession occurs in months t+1 .. t+horizon, NaN where the future is unknown."""
    label = usrec.rolling(horizon, min_periods=horizon).max().shift(-horizon)
    label.name = "TARGET"
    # Spot-check the shift direction so a refactor can never flip the label backward.
    rng = np.random.default_rng(0)
    valid = np.arange(horizon, len(usrec) - horizon)
    for i in rng.choice(valid, size=min(20, len(valid)), replace=False):
        manual = usrec.iloc[i + 1: i + 1 + horizon].max(skipna=False)
        assert (np.isnan(label.iloc[i]) and np.isnan(manual)) or label.iloc[i] == manual
    return label


def sahm_gap(unrate: pd.Series) -> pd.Series:
    u3 = unrate.rolling(3, min_periods=3).mean()
    return u3 - u3.shift(1).rolling(12, min_periods=12).min()


def expanding_z(s: pd.Series, min_periods: int = 60) -> pd.Series:
    mu = s.expanding(min_periods=min_periods).mean()
    sd = s.expanding(min_periods=min_periods).std()
    return (s - mu) / sd


def build_fci(monthly: pd.DataFrame, feat: pd.DataFrame) -> pd.Series:
    parts = {"SPREAD_10Y3M": -expanding_z(feat["SPREAD_10Y3M"])}
    if "CREDIT_SPREAD" in feat:
        parts["CREDIT_SPREAD"] = expanding_z(feat["CREDIT_SPREAD"])
    if "ICSA" in monthly:
        parts["CLAIMS"] = expanding_z(np.log(monthly["ICSA"]))
    if "UMCSENT" in monthly:
        parts["SENTIMENT"] = -expanding_z(monthly["UMCSENT"])
    fci = pd.DataFrame(parts).mean(axis=1)
    fci.name = "FCI"
    return fci


def make_design(feat: pd.DataFrame, cols: List[str],
                target: Optional[pd.Series] = None):
    if target is not None:
        joined = pd.concat([feat[cols], target], axis=1).dropna()
        return sm.add_constant(joined[cols], has_constant="add"), joined[target.name].astype(int)
    return sm.add_constant(feat[cols].dropna(), has_constant="add"), None


def fit_logit(y: pd.Series, X: pd.DataFrame, hac_lags: int = 12):
    def _fit(**kw):
        try:
            return sm.Logit(y, X).fit(disp=0, maxiter=200, **kw)
        except Exception:
            return sm.Logit(y, X).fit(disp=0, maxiter=500, method="bfgs", **kw)
    return _fit(), _fit(cov_type="HAC", cov_kwds={"maxlags": hac_lags})


def auc_score(y: np.ndarray, p: np.ndarray) -> float:
    """Rank-based ROC AUC (Mann-Whitney), no sklearn dependency."""
    ranks = pd.Series(p).rank(method="average").to_numpy()
    n1 = y.sum()
    n0 = len(y) - n1
    if n1 == 0 or n0 == 0:
        return float("nan")
    return float((ranks[y == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))


def precision_recall(y: np.ndarray, p: np.ndarray, thr: float) -> Tuple[float, float]:
    yhat = (p >= thr).astype(int)
    tp = int(((yhat == 1) & (y == 1)).sum())
    fp = int(((yhat == 1) & (y == 0)).sum())
    fn = int(((yhat == 0) & (y == 1)).sum())
    prec = tp / (tp + fp) if tp + fp else float("nan")
    rec = tp / (tp + fn) if tp + fn else float("nan")
    return prec, rec


@st.cache_data(ttl=24 * 3600, show_spinner=False)
def compute_model(horizon: int, feature_key: str) -> Dict:
    """Everything the page needs for one (horizon, feature set) choice."""
    monthly, failed = load_panel()
    feat = build_features(monthly)
    usrec = monthly["USREC"]
    label = build_label(usrec, horizon)
    episodes = recession_episodes(usrec)

    cols = (["SPREAD_10Y3M"] if feature_key == "curve"
            else [c for c in FULL_FEATURES if c in feat.columns])
    X_all, y_all = make_design(feat, cols, label)

    # Production fit on every labeled month, then nowcast on the feature-only tail.
    res, res_hac = fit_logit(y_all, X_all)
    X_now, _ = make_design(feat, cols)
    prob = res.predict(X_now)
    prob.name = "P_RECESSION"

    # Embargoed out-of-sample evaluation: training labels never touch the test window.
    train_end = TEST_START - pd.DateOffset(months=horizon + 1)
    tr, te = X_all.index <= train_end, X_all.index >= TEST_START
    metrics = {}
    if y_all.loc[tr].nunique() == 2 and y_all.loc[te].nunique() == 2:
        res_tr, _ = fit_logit(y_all.loc[tr], X_all.loc[tr])
        p_te = res_tr.predict(X_all.loc[te]).to_numpy()
        y_te = y_all.loc[te].to_numpy()
        base_rate = float(y_all.loc[tr].mean())
        metrics = {
            "auc": auc_score(y_te, p_te),
            "brier": float(np.mean((p_te - y_te) ** 2)),
            "brier_climatology": float(np.mean((base_rate - y_te) ** 2)),
            "y_te": y_te, "p_te": p_te,
            "test_start": str(TEST_START.date()), "n_test": int(te.sum()),
        }

    # Leave-one-recession-out warning leads.
    loro_rows = []
    for s, e in episodes:
        lo = s - pd.DateOffset(months=24 + horizon)
        hi = e + pd.DateOffset(months=12)
        mask = (X_all.index < lo) | (X_all.index > hi)
        if mask.sum() < 120 or y_all.loc[mask].nunique() < 2:
            continue
        res_l, _ = fit_logit(y_all.loc[mask], X_all.loc[mask])
        scan = (X_all.index >= s - pd.DateOffset(months=24)) & (X_all.index < s)
        p_scan = res_l.predict(X_all.loc[scan])
        crossed = p_scan[p_scan >= 0.5]
        first = crossed.index[0] if len(crossed) else None
        lead = ((s.year - first.year) * 12 + (s.month - first.month)) if first is not None else None
        loro_rows.append({
            "Recession start": s.strftime("%Y-%m"),
            "First 50% signal": first.strftime("%Y-%m") if first is not None else "no signal",
            "Lead (months)": lead,
            "Peak P in prior 24m": round(float(p_scan.max()), 2) if len(p_scan) else None,
        })

    coefs = pd.DataFrame({
        "Coefficient": res.params, "SE (default)": res.bse,
        "SE (HAC-12)": res_hac.bse, "p-value (HAC-12)": res_hac.pvalues,
    })

    sahm = sahm_gap(monthly["UNRATE"])
    fci = build_fci(monthly, feat)
    nfci_corr = float("nan")
    if "NFCI" in monthly:
        both = pd.concat([fci, monthly["NFCI"]], axis=1).dropna()
        if len(both) > 24:
            nfci_corr = float(both.corr().iloc[0, 1])

    return {
        "monthly": monthly, "feat": feat, "failed": failed, "episodes": episodes,
        "prob": prob, "coefs": coefs, "metrics": metrics,
        "loro": pd.DataFrame(loro_rows), "sahm": sahm, "fci": fci,
        "nfci_corr": nfci_corr, "n_obs": int(len(y_all)),
        "sample": (str(X_all.index.min().date()), str(X_all.index.max().date())),
    }


def shade(fig: go.Figure, episodes) -> None:
    for s, e in episodes:
        fig.add_vrect(x0=s, x1=e, fillcolor=SHADE, line_width=0, layer="below")


def line_chart(series_map: Dict[str, Tuple[pd.Series, str]], episodes, title: str,
               ytitle: str, hline: Optional[float] = None) -> go.Figure:
    fig = go.Figure()
    shade(fig, episodes)
    for name, (s, color) in series_map.items():
        fig.add_trace(go.Scatter(x=s.index, y=s.values, name=name, mode="lines",
                                 line={"color": color, "width": 1.6}))
    if hline is not None:
        fig.add_hline(y=hline, line={"color": RED, "width": 1, "dash": "dash"})
    fig.update_layout(template="plotly_white", title=title, yaxis_title=ytitle,
                      height=380, margin={"l": 40, "r": 20, "t": 50, "b": 30},
                      legend={"orientation": "h", "y": 1.12})
    return fig


def curve_animation(monthly: pd.DataFrame, episodes) -> go.Figure:
    cols = [c for c in CURVE_YEARS if c in monthly.columns]
    curve = monthly[cols].dropna()
    years = [CURVE_YEARS[c] for c in cols]
    idx = curve.index[::3]
    rec = monthly["USREC"].reindex(curve.index).fillna(0)
    y_max = float(np.nanmax(curve.values)) * 1.08

    def style(ts):
        inverted = curve.loc[ts, "DGS10"] - curve.loc[ts, cols[0]] < 0
        return (RED if inverted else NAVY,
                " | INVERTED" if inverted else (" | recession" if rec.loc[ts] else ""))

    frames = []
    for ts in idx:
        color, tag = style(ts)
        frames.append(go.Frame(
            name=ts.strftime("%Y-%m"),
            data=[go.Scatter(x=years, y=curve.loc[ts].values, mode="lines+markers",
                             line={"color": color, "width": 3})],
            layout=go.Layout(title_text=f"US Treasury curve | {ts.strftime('%b %Y')}{tag}")))
    color0, tag0 = style(idx[-1])
    fig = go.Figure(
        data=[go.Scatter(x=years, y=curve.loc[idx[-1]].values, mode="lines+markers",
                         line={"color": color0, "width": 3})],
        frames=frames)
    fig.update_layout(
        template="plotly_white", height=480,
        title=f"US Treasury curve | {idx[-1].strftime('%b %Y')}{tag0}",
        xaxis={"title": "Maturity (years)", "type": "log", "tickvals": years,
               "ticktext": [str(y) for y in years]},
        yaxis={"title": "Yield (%)", "range": [0, y_max]},
        updatemenus=[{"type": "buttons", "showactive": False, "x": 0.03, "y": 1.15,
                      "buttons": [
                          {"label": "Play", "method": "animate",
                           "args": [None, {"frame": {"duration": 90, "redraw": True},
                                           "fromcurrent": True,
                                           "transition": {"duration": 0}}]},
                          {"label": "Pause", "method": "animate",
                           "args": [[None], {"frame": {"duration": 0},
                                             "mode": "immediate"}]}]}],
        sliders=[{"steps": [{"label": f.name, "method": "animate",
                             "args": [[f.name], {"frame": {"duration": 0, "redraw": True},
                                                 "mode": "immediate"}]}
                            for f in frames[::4]],
                  "currentvalue": {"prefix": "Month: "}, "len": 0.92}])
    return fig


def main() -> None:
    st.set_page_config(page_title="Macro Recession Dashboard",
                       page_icon=":bar_chart:", layout="wide")
    st.title("US Recession Probability Dashboard")
    st.caption(
        "A live nowcast of the probability that the US economy enters an NBER recession "
        "within the chosen horizon, estimated from the Treasury yield curve and a set of "
        "leading indicators. Data: [FRED](https://fred.stlouisfed.org) (St. Louis Fed), "
        "refreshed daily and cached. Methodology mirrors the research notebook in this "
        "project folder: publication-lag alignment, an embargoed out-of-sample split, "
        "and Newey-West standard errors.")

    with st.expander("What am I looking at?"):
        st.markdown(
            "- **The model** is a logistic regression trained on monthly data since 1976. "
            "Its target asks: is the economy in recession at any point in the next N months? "
            "Its main input is the 10-year minus 3-month Treasury spread; when short rates "
            "sit above long rates (an inverted curve), recessions have historically followed "
            "within a year or two.\n"
            "- **The Sahm Rule** confirms, almost in real time, that a recession has already "
            "begun: it fires when the 3-month average unemployment rate rises half a point "
            "above its low from the prior year. It detects rather than predicts.\n"
            "- **The financial-conditions index** aggregates credit spreads, jobless claims, "
            "sentiment and the curve into one tightness score, validated against the Chicago "
            "Fed's NFCI.\n"
            "- **Honest caveats**: FRED serves revised data, so labor inputs look cleaner "
            "than they did in real time; the curve inverted in 2022-23 without a recession "
            "following (visible in the charts); and the 2020 pandemic recession was not "
            "foreseeable by any macro-financial signal.")

    c1, c2, c3 = st.columns([1, 1.4, 1.2])
    horizon = c1.selectbox("Horizon (months ahead)", [6, 12, 18], index=1)
    feature_label = c2.radio("Model inputs", ["Yield curve + leading indicators",
                                              "Yield curve only"], horizontal=True)
    threshold = c3.slider("Alarm threshold", 0.10, 0.90, 0.50, 0.05,
                          help="Probability level treated as a recession alarm")
    feature_key = "curve" if feature_label == "Yield curve only" else "full"

    try:
        with st.spinner("Fetching FRED data and fitting the model..."):
            R = compute_model(horizon, feature_key)
    except RuntimeError as exc:
        st.error(f"FRED data is unavailable right now ({exc}). Try again in a minute.")
        st.stop()
    except urllib.error.URLError:
        st.error("Could not reach FRED. Check your connection and try again.")
        st.stop()

    prob, episodes = R["prob"], R["episodes"]
    now_p = float(prob.iloc[-1])
    now_date = prob.index[-1]
    sahm_now = float(R["sahm"].dropna().iloc[-1])
    spread_now = float(R["feat"]["SPREAD_10Y3M"].dropna().iloc[-1])
    fci_now = float(R["fci"].dropna().iloc[-1])

    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric(f"P(recession in {horizon}m)", f"{now_p:.0%}",
              help=f"Model nowcast as of {now_date.strftime('%b %Y')}")
    m2.metric("Out-of-sample AUC", f"{R['metrics'].get('auc', float('nan')):.2f}",
              help=f"Discrimination on the {R['metrics'].get('test_start', '2006')}+ holdout")
    m3.metric("10Y-3M spread", f"{spread_now:+.2f}pp",
              delta="inverted" if spread_now < 0 else "normal", delta_color="off")
    m4.metric("Sahm gap", f"{sahm_now:+.2f}pp",
              delta="triggered" if sahm_now >= 0.5 else "quiet", delta_color="off")
    m5.metric("Financial conditions", f"{fci_now:+.2f}",
              delta="tight" if fci_now > 0 else "easy", delta_color="off")

    g1, g2 = st.columns([1, 2.1])
    gauge = go.Figure(go.Indicator(
        mode="gauge+number", value=round(now_p * 100, 1),
        number={"suffix": "%", "font": {"size": 42}},
        title={"text": f"Recession within {horizon} months<br>"
                       f"<span style='font-size:0.75em;color:{GRAY}'>as of "
                       f"{now_date.strftime('%b %Y')}</span>"},
        gauge={"axis": {"range": [0, 100], "ticksuffix": "%"},
               "bar": {"color": NAVY},
               "steps": [{"range": [0, 25], "color": "#dcebdc"},
                         {"range": [25, 50], "color": "#f4ecd2"},
                         {"range": [50, 100], "color": "#f3d9d3"}],
               "threshold": {"line": {"color": RED, "width": 3},
                             "value": threshold * 100}}))
    gauge.update_layout(height=330, margin={"l": 30, "r": 30, "t": 60, "b": 10})
    g1.plotly_chart(gauge, use_container_width=True)

    hist = go.Figure()
    shade(hist, episodes)
    hist.add_trace(go.Scatter(x=prob.index, y=prob.values, mode="lines",
                              line={"color": NAVY, "width": 1.6},
                              hovertemplate="%{x|%b %Y}: %{y:.0%}<extra></extra>"))
    hist.add_hline(y=threshold, line={"color": RED, "width": 1, "dash": "dash"})
    hist.update_layout(template="plotly_white", height=330,
                       title="Probability history (shaded bands are NBER recessions)",
                       yaxis={"tickformat": ".0%", "range": [-0.02, 1.02]},
                       margin={"l": 40, "r": 20, "t": 50, "b": 30}, showlegend=False)
    g2.plotly_chart(hist, use_container_width=True)

    tab_curve, tab_ind, tab_model, tab_about = st.tabs(
        ["Yield curve", "Indicators", "Model detail", "About and data"])

    with tab_curve:
        st.plotly_chart(curve_animation(R["monthly"], episodes), use_container_width=True)
        st.caption("Press Play to replay five decades of curve shapes. The curve turns red "
                   "whenever the 10-year yield sits below the 3-month rate.")

    with tab_ind:
        feat = R["feat"]
        spreads = {"10Y-3M": (feat["SPREAD_10Y3M"].dropna(), NAVY)}
        if "SPREAD_10Y2Y" in feat:
            spreads["10Y-2Y"] = (feat["SPREAD_10Y2Y"].dropna(), BLUE)
        st.plotly_chart(line_chart(spreads, episodes,
                                   "Treasury term spreads (below zero = inverted)",
                                   "Spread (pp)", hline=0.0), use_container_width=True)
        st.plotly_chart(line_chart({"Sahm gap": (R["sahm"].dropna(), GREEN)}, episodes,
                                   "Sahm Rule gap (0.50pp confirms a recession has started)",
                                   "Gap (pp)", hline=0.5), use_container_width=True)
        fci_map = {"Hand-built FCI": (R["fci"].dropna(), NAVY)}
        if "NFCI" in R["monthly"]:
            fci_map["Chicago Fed NFCI"] = (R["monthly"]["NFCI"].dropna(), GOLD)
        corr_txt = "" if np.isnan(R["nfci_corr"]) else f" | corr with NFCI: {R['nfci_corr']:.2f}"
        st.plotly_chart(line_chart(fci_map, episodes,
                                   f"Financial conditions (higher = tighter){corr_txt}",
                                   "Index (z)", hline=0.0), use_container_width=True)

    with tab_model:
        met = R["metrics"]
        if met:
            prec, rec = precision_recall(met["y_te"], met["p_te"], threshold)
            a, b, c, d = st.columns(4)
            a.metric("OOS AUC", f"{met['auc']:.2f}")
            b.metric("OOS Brier", f"{met['brier']:.3f}",
                     help="Lower is better; compare with the base-rate benchmark")
            c.metric("Base-rate Brier", f"{met['brier_climatology']:.3f}",
                     help="Always predicting the historical recession frequency")
            d.metric(f"Precision / recall at {threshold:.0%}",
                     f"{prec:.2f} / {rec:.2f}")
            st.caption(
                f"Out-of-sample window: {met['test_start']} onward ({met['n_test']} months), "
                f"with training data embargoed so no training label overlaps the test "
                f"window. The holdout contains 2008, 2020 and the 2022-23 inversion false "
                f"alarm, so treat every number as an honest but noisy estimate from very "
                f"few recessions.")
        st.subheader("Coefficients")
        st.dataframe(R["coefs"].style.format("{:.3f}"), width="stretch")
        st.caption("HAC (Newey-West, 12 lags) standard errors correct for the serial "
                   "correlation created by overlapping label windows; they are the ones "
                   "to trust.")
        if len(R["loro"]):
            st.subheader("Warning record, recession by recession")
            st.dataframe(R["loro"], width="stretch", hide_index=True)
            st.caption("Each row refits the model with that recession (and a buffer around "
                       "it) excluded, then asks when the excluded recession's probability "
                       "first crossed 50%.")

    with tab_about:
        st.markdown(
            f"**Sample**: {R['sample'][0]} to {R['sample'][1]}, {R['n_obs']} labeled months, "
            f"{len(episodes)} NBER recessions.\n\n"
            "**Method**: logistic regression of a strictly forward-looking recession label "
            "on features shifted to publication time. Market-priced inputs (term and credit "
            "spreads) carry no revision bias; labor and survey inputs are revised vintages, "
            "which flatters any backtest. The institutional fix is ALFRED vintage data.\n\n"
            "**Related**: the full research notebook (with validation, robustness and "
            "limitations sections) lives in this repo folder, and the companion tear sheet "
            "app is at [performancesheet.streamlit.app](https://performancesheet.streamlit.app).")
        if R["failed"]:
            st.warning(f"Optional series unavailable this run: {', '.join(R['failed'])}")
        prov = pd.DataFrame({
            "Series": list(R["monthly"].columns),
            "Description": [SERIES.get(c, "") for c in R["monthly"].columns],
            "First": [str(R["monthly"][c].first_valid_index().date())
                      for c in R["monthly"].columns],
            "Last": [str(R["monthly"][c].last_valid_index().date())
                     for c in R["monthly"].columns],
        })
        st.dataframe(prov, width="stretch", hide_index=True)
        st.download_button(
            "Download probability history (CSV)",
            data=prob.to_frame().to_csv().encode(),
            file_name="recession_probability.csv", mime="text/csv")
        st.download_button(
            "Download monthly data panel (CSV)",
            data=R["monthly"].to_csv().encode(),
            file_name="macro_monthly_panel.csv", mime="text/csv")


if __name__ == "__main__":
    main()
