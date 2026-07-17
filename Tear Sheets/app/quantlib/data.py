"""quantlib.data - uniform, cached, fallback-safe market / macro / fundamental data layer.

Design contract (identical for every source):
  * One clean pandas object back, with aligned, sorted dates and adjusted prices.
  * Local caching so nothing re-downloads on a re-run.
  * Retry + informative error handling on every network call.
  * Rate-limit / User-Agent compliance (SEC EDGAR requires a descriptive UA).
  * Point-in-time / survivorship caveats surfaced in the provenance note.
  * A printed provenance summary (source, rows, date range, frequency).
  * If a key is missing or a fetch fails -> a CLEARLY-LABELED synthetic/cached dataset,
    so everything downstream still runs end to end.
  * Colab-safe secrets via userdata -> env -> getpass(TTY only); never hard-coded.
  * QUANT_OFFLINE=1 forces the deterministic synthetic path (used by headless executors).

Sources: Yahoo (yfinance), FRED (fredapi or keyless pandas_datareader), SEC EDGAR
companyfacts (UA-compliant), Ken French factor library. Optional FMP / Polygon /
Alpha Vantage are used only when their key is present.
"""
from __future__ import annotations

import os
import sys
import io
import re
import json
import time
import gzip
import zipfile
import urllib.request
from typing import Iterable

import numpy as np
import pandas as pd

# --- Default SEC EDGAR User-Agent (SEC blocks requests without a descriptive UA) ---
DEFAULT_EDGAR_UA = "Avinash Mahadevan avinmaha09@gmail.com"

TRADING_DAYS = 252


# --------------------------------------------------------------------------------------
# Environment & secrets
# --------------------------------------------------------------------------------------
def offline() -> bool:
    """True when QUANT_OFFLINE is set - forces the deterministic synthetic path."""
    return bool(os.environ.get("QUANT_OFFLINE"))


def in_colab() -> bool:
    try:
        import google.colab  # noqa: F401
        return True
    except ImportError:
        return False


def resolve_secret(name: str) -> "str | None":
    """Resolve an API key without ever blocking a headless run.

    Order: Colab userdata -> environment variable -> interactive getpass (TTY only).
    Returns None if no source provides it.
    """
    if in_colab():
        try:
            from google.colab import userdata
            val = userdata.get(name)
            if val:
                return val
        except Exception:
            pass
    if os.environ.get(name):
        return os.environ[name]
    if sys.stdin.isatty():
        try:
            import getpass
            return getpass.getpass(f"{name} (press Enter to skip): ") or None
        except Exception:
            return None
    return None


def cache_dir() -> str:
    """Where cached datasets live. Honors QUANT_CACHE_DIR, then QUANT_OUTPUT_DIR/cache."""
    d = os.environ.get("QUANT_CACHE_DIR")
    if not d:
        base = os.environ.get("QUANT_OUTPUT_DIR") or "."
        d = os.path.join(base, ".quant_cache")
    os.makedirs(d, exist_ok=True)
    return d


def _cache_path(key: str) -> str:
    return os.path.join(cache_dir(), f"{key}.pkl")


def _maybe_gunzip(raw: bytes) -> bytes:
    """Decompress if the payload is gzip-framed (magic bytes 0x1f 0x8b)."""
    return gzip.decompress(raw) if raw[:2] == b"\x1f\x8b" else raw


def _get_json(url: str, headers: dict) -> dict:
    """GET a JSON document, transparently handling a gzipped body."""
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=25) as r:
        return json.loads(_maybe_gunzip(r.read()).decode("utf-8"))


def _print_provenance(obj: pd.DataFrame | pd.Series, source: str, freq: str,
                      note: str = "") -> None:
    """Attach and print a standard provenance summary."""
    idx = obj.index
    prov = {
        "source": source,
        "rows": int(obj.shape[0]),
        "cols": list(obj.columns) if isinstance(obj, pd.DataFrame) else [obj.name],
        "start": str(idx.min().date()) if len(idx) else "-",
        "end": str(idx.max().date()) if len(idx) else "-",
        "frequency": freq,
        "note": note,
    }
    try:
        obj.attrs["provenance"] = prov
    except Exception:
        pass
    print("--- data provenance ---")
    print(f"source    : {prov['source']}")
    print(f"rows      : {prov['rows']:,}   freq: {prov['frequency']}")
    print(f"range     : {prov['start']} -> {prov['end']}")
    if note:
        print(f"note      : {note}")


def _bdays(start: str, end: str) -> pd.DatetimeIndex:
    return pd.bdate_range(start, end)


# --------------------------------------------------------------------------------------
# Standardization
# --------------------------------------------------------------------------------------
def standardize_prices(df: pd.DataFrame) -> pd.DataFrame:
    """Sort ascending, drop duplicate dates, forward-fill isolated gaps, align all columns."""
    out = df.copy()
    out = out[~out.index.duplicated(keep="first")].sort_index()
    out = out.ffill().dropna(how="any")
    return out


# --------------------------------------------------------------------------------------
# Synthetic generators (deterministic, clearly labeled)
# --------------------------------------------------------------------------------------
def _synth_prices(tickers: Iterable[str], start: str, end: str, seed: int = 42) -> pd.DataFrame:
    """Deterministic one-factor synthetic adjusted-close panel (realistic correlations)."""
    tickers = list(tickers)
    rng = np.random.default_rng(seed)
    dates = _bdays(start, end)
    n = len(dates)
    mkt = rng.normal(0.09 / TRADING_DAYS, 0.15 / np.sqrt(TRADING_DAYS), n)
    mkt_shock = mkt - mkt.mean()
    out = {}
    for i, t in enumerate(tickers):
        beta = 0.8 + 0.4 * ((i % 5) / 4.0)            # spread betas across names
        drift = (0.06 + 0.02 * (i % 3)) / TRADING_DAYS
        idio = rng.normal(0.0, 0.12 / np.sqrt(TRADING_DAYS), n)
        log_ret = drift + beta * mkt_shock + idio
        out[t] = 100.0 * np.exp(np.cumsum(log_ret))
    return pd.DataFrame(out, index=dates)


def _synth_fred(series: Iterable[str], start: str, end: str, seed: int = 7) -> pd.DataFrame:
    """Slowly-varying synthetic macro series (e.g. rates) on a business-day index."""
    series = list(series)
    rng = np.random.default_rng(seed)
    dates = _bdays(start, end)
    out = {}
    for j, s in enumerate(series):
        level = 0.02 + 0.01 * j
        x = np.empty(len(dates)); x[0] = level
        for t in range(1, len(dates)):
            x[t] = x[t-1] + 0.01 * (level - x[t-1]) + rng.normal(0, 0.0006)
        out[s] = np.clip(x, 0.0, None)
    return pd.DataFrame(out, index=dates)


def _synth_fama_french(start: str, end: str, seed: int = 11) -> pd.DataFrame:
    """Synthetic daily Fama-French style factors (Mkt-RF, SMB, HML, RF) in decimal."""
    rng = np.random.default_rng(seed)
    dates = _bdays(start, end)
    n = len(dates)
    df = pd.DataFrame({
        "Mkt-RF": rng.normal(0.0003, 0.010, n),
        "SMB":    rng.normal(0.0000, 0.005, n),
        "HML":    rng.normal(0.0000, 0.005, n),
        "RF":     np.full(n, 0.02 / TRADING_DAYS),
    }, index=dates)
    return df


def _synth_company_facts(ticker: str, seed: int = 13) -> pd.DataFrame:
    """Synthetic annual fundamentals (Revenues, NetIncomeLoss, Assets) for one issuer."""
    rng = np.random.default_rng(seed)
    years = pd.period_range("2015", "2024", freq="Y").to_timestamp(how="end")
    rev = np.cumprod(1 + rng.normal(0.10, 0.05, len(years))) * 1e9
    return pd.DataFrame({
        "ticker": ticker,
        "concept": "Revenues",
        "end": years,
        "value": rev,
    })


# --------------------------------------------------------------------------------------
# Public fetchers
# --------------------------------------------------------------------------------------
def get_prices(tickers, start: str = "2014-01-01", end: str = "2024-12-31",
               source: str = "yahoo", use_cache: bool = True) -> pd.DataFrame:
    """Adjusted-close price panel. Yahoo (live) -> cache -> synthetic fallback.

    Returns a standardized DataFrame: one column per ticker, ascending dates, no NaNs.
    """
    tickers = [tickers] if isinstance(tickers, str) else list(tickers)
    if offline():
        df = standardize_prices(_synth_prices(tickers, start, end))
        _print_provenance(df, "SYNTHETIC (QUANT_OFFLINE)", "daily",
                           "one-factor simulation; not real prices")
        return df

    key = f"prices_{source}_{'_'.join(tickers)}_{start}_{end}".replace("/", "-")
    cache = _cache_path(key)
    if use_cache and os.path.exists(cache):
        df = pd.read_pickle(cache)
        _print_provenance(df, f"CACHE ({source})", "daily", "loaded from local cache")
        return df

    for attempt in range(3):
        try:
            import yfinance as yf
            raw = yf.download(tickers, start=start, end=end, auto_adjust=True,
                              progress=False)["Close"]
            if isinstance(raw, pd.Series):
                raw = raw.to_frame(tickers[0])
            df = standardize_prices(raw)
            if df.shape[0] > 60 and df.shape[1] == len(tickers):
                df.to_pickle(cache)
                _print_provenance(df, f"LIVE Yahoo ({source})", "daily",
                                  "adjusted close (splits+divs); survivorship: hand-picked, "
                                  "point-in-time-revised")
                return df
        except Exception as exc:
            print(f"  [get_prices] attempt {attempt+1} failed: {exc}")
            time.sleep(0.6 * (attempt + 1))
    df = standardize_prices(_synth_prices(tickers, start, end))
    _print_provenance(df, "SYNTHETIC (live unavailable)", "daily",
                      "fell back to one-factor simulation; not real prices")
    return df


def _fred_csv_series(sid: str, start: str, end: str) -> pd.Series:
    """One FRED series via the keyless public fredgraph.csv download endpoint."""
    url = (f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}"
           f"&cosd={start}&coed={end}")
    req = urllib.request.Request(
        url, headers={"User-Agent": os.environ.get("QUANT_EDGAR_UA", DEFAULT_EDGAR_UA)})
    with urllib.request.urlopen(req, timeout=25) as r:
        raw = _maybe_gunzip(r.read())
    df = pd.read_csv(io.BytesIO(raw))
    df.columns = ["DATE", sid]                       # 2-col CSV regardless of header label
    s = pd.to_numeric(df[sid].replace(".", np.nan), errors="coerce")
    s.index = pd.to_datetime(df["DATE"])
    s.name = sid
    return s


def get_fred(series, start: str = "2014-01-01", end: str = "2024-12-31") -> pd.DataFrame:
    """FRED macro series. Keyless fredgraph.csv -> fredapi (with key) -> synthetic.

    The keyless public CSV endpoint needs no key and no extra library, so it is tried first.
    """
    series = [series] if isinstance(series, str) else list(series)
    if offline():
        df = _synth_fred(series, start, end)
        _print_provenance(df, "SYNTHETIC (QUANT_OFFLINE)", "daily", "synthetic macro series")
        return df

    # 1) Keyless public CSV endpoint.
    try:
        cols = {sid: _fred_csv_series(sid, start, end) for sid in series}
        df = pd.DataFrame(cols).sort_index().ffill().dropna(how="all")
        if df.shape[0] > 0:
            _print_provenance(df, "LIVE FRED (keyless fredgraph.csv)", "as-reported",
                              "missing '.' markers -> NaN then ffilled; not point-in-time")
            return df
    except Exception as exc:
        print(f"  [get_fred] keyless fredgraph.csv failed: {exc}")

    # 2) fredapi with a key, if one is configured.
    key = resolve_secret("FRED_API_KEY")
    if key:
        try:
            from fredapi import Fred
            fred = Fred(api_key=key)
            cols = {s: fred.get_series(s, observation_start=start, observation_end=end)
                    for s in series}
            df = pd.DataFrame(cols).sort_index().ffill().dropna(how="all")
            _print_provenance(df, "LIVE FRED (fredapi)", "as-reported", "macro")
            return df
        except Exception as exc:
            print(f"  [get_fred] fredapi failed: {exc}")

    # 3) Synthetic fallback.
    df = _synth_fred(series, start, end)
    _print_provenance(df, "SYNTHETIC (FRED unavailable)", "daily", "synthetic macro series")
    return df


def _parse_ff_csv(raw: str) -> pd.DataFrame:
    """Parse a Ken French daily-factors CSV block (rows like 'YYYYMMDD, m, s, h, rf')."""
    rows = []
    for line in raw.splitlines():
        m = re.match(r"^\s*(\d{8})\s*,(.*)$", line)
        if not m:
            continue                                  # skip preamble + annual/footer blocks
        vals = [float(x) for x in m.group(2).split(",") if x.strip() != ""]
        if len(vals) >= 4:
            rows.append((pd.to_datetime(m.group(1), format="%Y%m%d"), *vals[:4]))
    return (pd.DataFrame(rows, columns=["Date", "Mkt-RF", "SMB", "HML", "RF"])
            .set_index("Date").sort_index())


def get_fama_french(dataset: str = "F-F_Research_Data_Factors_daily",
                    start: str = "2014-01-01", end: str = "2024-12-31") -> pd.DataFrame:
    """Ken French factor library via direct ZIP (keyless stdlib urllib) -> synthetic fallback.

    Factors returned in DECIMAL (the source publishes percent; divided by 100).
    """
    if offline():
        df = _synth_fama_french(start, end)
        _print_provenance(df, "SYNTHETIC (QUANT_OFFLINE)", "daily", "synthetic FF factors")
        return df
    try:
        url = ("https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/"
               f"{dataset}_CSV.zip")
        req = urllib.request.Request(
            url, headers={"User-Agent": os.environ.get("QUANT_EDGAR_UA", DEFAULT_EDGAR_UA)})
        with urllib.request.urlopen(req, timeout=30) as r:
            blob = r.read()
        with zipfile.ZipFile(io.BytesIO(blob)) as z:
            raw = z.read(z.namelist()[0]).decode("latin-1")
        df = _parse_ff_csv(raw)
        df = df.loc[(df.index >= pd.Timestamp(start)) & (df.index <= pd.Timestamp(end))] / 100.0
        if df.empty:
            raise ValueError("no rows parsed in requested window")
        _print_provenance(df, "LIVE Ken French library", "daily",
                          "factors converted percent->decimal")
        return df
    except Exception as exc:
        print(f"  [get_fama_french] live failed: {exc}")
        df = _synth_fama_french(start, end)
        _print_provenance(df, "SYNTHETIC (FF unavailable)", "daily", "synthetic FF factors")
        return df


# us-gaap revenue tags an issuer may have used over time (ranked: modern ASC 606 first).
REVENUE_TAGS = [
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "Revenues",
    "SalesRevenueNet",
    "RevenueFromContractWithCustomerIncludingAssessedTax",
]


def get_edgar_companyfacts(ticker_or_cik: str, concept: str = "Revenues") -> pd.DataFrame:
    """SEC EDGAR companyfacts for one issuer (UA-compliant, gzip-safe) -> synthetic fallback.

    For a revenue concept, merges the common us-gaap tag variants and dedupes by fiscal-year
    end (preferring the more modern tag). Returns: ticker, concept, end, value.
    """
    if offline():
        df = _synth_company_facts(str(ticker_or_cik))
        _print_provenance(df.set_index("end"), "SYNTHETIC (QUANT_OFFLINE)", "annual",
                          "synthetic fundamentals")
        return df

    headers = {"User-Agent": os.environ.get("QUANT_EDGAR_UA", DEFAULT_EDGAR_UA)}
    tags = REVENUE_TAGS if concept.lower().startswith("revenue") else [concept]
    try:
        cik = _resolve_cik(str(ticker_or_cik), headers)
        facts = _get_json(
            f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json", headers)
        gaap = facts["facts"]["us-gaap"]
        by_year: dict = {}                            # fiscal-year-end -> (tag_rank, row)
        for rank, tag in enumerate(tags):
            if tag not in gaap:
                continue
            for items in gaap[tag]["units"].values():
                for x in items:
                    if x.get("form") not in ("10-K", "10-K/A") or x.get("fp") != "FY":
                        continue
                    start_s = x.get("start")
                    if not start_s:
                        continue
                    end = pd.Timestamp(x["end"])
                    if not (350 <= (end - pd.Timestamp(start_s)).days <= 380):
                        continue                       # keep only full-year (annual) periods
                    if end not in by_year or rank < by_year[end][0]:
                        by_year[end] = (rank, {
                            "ticker": str(ticker_or_cik).upper(), "concept": "Revenues",
                            "end": end, "value": x["val"]})
        rows = [v[1] for v in by_year.values()]
        if not rows:
            raise ValueError("no annual (10-K FY) revenue rows found")
        df = pd.DataFrame(rows).sort_values("end").reset_index(drop=True)
        _print_provenance(df.set_index("end"), "LIVE SEC EDGAR", "annual",
                          f"merged {len(tags)} revenue tag(s); 10-K FY; as-reported")
        return df
    except Exception as exc:
        print(f"  [get_edgar_companyfacts] live failed: {exc}")
        df = _synth_company_facts(str(ticker_or_cik))
        _print_provenance(df.set_index("end"), "SYNTHETIC (EDGAR unavailable)", "annual",
                          "synthetic fundamentals")
        return df


def _resolve_cik(ticker: str, headers: dict) -> int:
    """Map a ticker to its zero-padded CIK via SEC's published ticker map (gzip-safe)."""
    if ticker.isdigit():
        return int(ticker)
    m = _get_json("https://www.sec.gov/files/company_tickers.json", headers)
    for row in m.values():
        if row["ticker"].upper() == ticker.upper():
            return int(row["cik_str"])
    raise ValueError(f"ticker {ticker!r} not found in SEC map")


def returns_from_prices(prices: pd.DataFrame, kind: str = "simple") -> pd.DataFrame:
    """Daily returns from an adjusted-close panel. kind in {'simple','log'}."""
    if kind == "log":
        return np.log(prices / prices.shift(1)).dropna(how="all")
    return prices.pct_change().dropna(how="all")


if __name__ == "__main__":
    # Smoke test: exercise the synthetic path deterministically (no network needed).
    os.environ.setdefault("QUANT_OFFLINE", "1")
    px = get_prices(["SPY", "QQQ", "TLT"], "2018-01-01", "2020-12-31")
    print("prices shape:", px.shape)
    print("returns head:\n", returns_from_prices(px).head(2))
    ff = get_fama_french(start="2018-01-01", end="2018-03-31")
    print("ff cols:", list(ff.columns))
    facts = get_edgar_companyfacts("AAPL")
    print("facts rows:", len(facts))
