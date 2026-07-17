"""quantlib.metrics - the single source of truth for performance & risk statistics.

Pure, type-hinted functions on a periodic *return* series (simple returns by default).
Used by tearsheet.py and by rigor.py so every project computes Sharpe, drawdown, VaR, etc.
the same way. State your return convention; everything here assumes simple returns unless noted.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

TRADING_DAYS = 252


def to_returns(series: pd.Series, kind: str = "auto") -> pd.Series:
    """Coerce a price OR return series into simple returns.

    kind='returns' takes it as-is; 'prices' takes pct_change; 'auto' guesses: a series whose
    values are mostly well above 1 (and strictly positive) looks like a price/equity curve.
    """
    s = series.dropna()
    if kind == "returns":
        return s
    if kind == "prices":
        return s.pct_change().dropna()
    looks_like_price = (s > 0).all() and (s.abs().median() > 5 or float(s.max()) > 10)
    return s.pct_change().dropna() if looks_like_price else s


def cumulative_wealth(returns: pd.Series) -> pd.Series:
    """Wealth index W_t = prod(1+r), starting at 1.0."""
    return (1.0 + returns).cumprod()


def cagr(returns: pd.Series, periods: int = TRADING_DAYS) -> float:
    yrs = len(returns) / periods
    return float(cumulative_wealth(returns).iloc[-1] ** (1.0 / yrs) - 1.0) if yrs > 0 else np.nan


def ann_vol(returns: pd.Series, periods: int = TRADING_DAYS) -> float:
    return float(returns.std(ddof=1) * np.sqrt(periods))


def sharpe(returns: pd.Series, rf_periodic: float = 0.0, periods: int = TRADING_DAYS) -> float:
    ex = returns - rf_periodic
    sd = ex.std(ddof=1)
    return float(ex.mean() / sd * np.sqrt(periods)) if sd > 0 else np.nan


def downside_deviation(returns: pd.Series, target: float = 0.0,
                       periods: int = TRADING_DAYS) -> float:
    downside = np.minimum(returns - target, 0.0)
    return float(np.sqrt((downside ** 2).mean()) * np.sqrt(periods))


def sortino(returns: pd.Series, rf_periodic: float = 0.0, periods: int = TRADING_DAYS) -> float:
    dd = downside_deviation(returns, 0.0, periods)
    ex = (returns - rf_periodic).mean() * periods
    return float(ex / dd) if dd > 0 else np.nan


def drawdown_series(returns: pd.Series) -> pd.Series:
    w = cumulative_wealth(returns)
    return w / w.cummax() - 1.0


def max_drawdown(returns: pd.Series) -> float:
    return float(drawdown_series(returns).min())


def calmar(returns: pd.Series, periods: int = TRADING_DAYS) -> float:
    mdd = max_drawdown(returns)
    return float(cagr(returns, periods) / abs(mdd)) if mdd < 0 else np.nan


def hit_rate(returns: pd.Series) -> float:
    return float((returns > 0).mean())


def var_historical(returns: pd.Series, conf: float = 0.95) -> float:
    """Historical 1-period Value-at-Risk as a positive loss magnitude."""
    return float(-returns.quantile(1.0 - conf))


def cvar_historical(returns: pd.Series, conf: float = 0.95) -> float:
    """Historical Conditional VaR / Expected Shortfall (positive loss magnitude)."""
    q = returns.quantile(1.0 - conf)
    tail = returns[returns <= q]
    return float(-tail.mean()) if len(tail) else np.nan


def best_period(returns: pd.Series) -> float:
    return float(returns.max())


def worst_period(returns: pd.Series) -> float:
    return float(returns.min())


def skew(returns: pd.Series) -> float:
    from scipy import stats as _st
    return float(_st.skew(returns.dropna()))


def kurtosis(returns: pd.Series) -> float:
    from scipy import stats as _st
    return float(_st.kurtosis(returns.dropna(), fisher=True))


def performance_summary(returns: pd.Series, rf_periodic: float = 0.0,
                        periods: int = TRADING_DAYS, name: str = "", conf: float = 0.95) -> dict:
    """The full headline metric set for one return series, as an ordered dict."""
    return {
        "Series": name,
        "CAGR": cagr(returns, periods),
        "Ann.Vol": ann_vol(returns, periods),
        "Sharpe": sharpe(returns, rf_periodic, periods),
        "Sortino": sortino(returns, rf_periodic, periods),
        "Calmar": calmar(returns, periods),
        "MaxDrawdown": max_drawdown(returns),
        "HitRate": hit_rate(returns),
        f"VaR{int(conf*100)}": var_historical(returns, conf),
        f"CVaR{int(conf*100)}": cvar_historical(returns, conf),
        "BestDay": best_period(returns),
        "WorstDay": worst_period(returns),
        "Skew": skew(returns),
        "Kurtosis": kurtosis(returns),
    }


if __name__ == "__main__":
    rng = np.random.default_rng(0)
    idx = pd.date_range("2015-01-01", periods=TRADING_DAYS * 5, freq="B")
    r = pd.Series(rng.normal(0.0005, 0.01, len(idx)), index=idx)
    s = performance_summary(r, name="demo")
    for k, v in s.items():
        print(f"{k:>12}: {v}")
