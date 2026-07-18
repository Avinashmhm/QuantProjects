# QuantProjects

Quantitative finance work in Python (pandas, numpy, scipy, statsmodels, matplotlib). The focus is on measuring performance and risk correctly: proper annualization, drawdown and tail-risk statistics, and significance testing rather than bare point estimates.

## 1. Performance tear sheet generator

A Streamlit web app that builds a full performance and risk tear sheet for any Yahoo Finance symbol: stocks, ETFs, indexes (^GSPC), futures (ES=F), and crypto pairs (BTC-USD), with an optional benchmark overlay, an interactive chart panel, a complete risk table, and a PNG download. The ticker boxes suggest from a curated list of about 700 liquid names as you type, and the numbers come from a shared metrics library so every exhibit is computed the same way.

Live app: [performancesheet.streamlit.app](https://performancesheet.streamlit.app) | [Code and project folder](./Tear%20Sheets)

The project folder also holds a gallery of 28 pre-generated tear sheets for widely followed stocks, ETFs, and funds, with summary statistics and Newey-West significance tests.

## 2. Macro nowcasting and recession dashboard

A Streamlit web app that estimates the probability of a US recession within a chosen horizon from live FRED data: a logistic regression on the Treasury yield curve and a leading-indicator set (credit spreads, payrolls, jobless claims, building permits, consumer sentiment), with a probability gauge, an animated yield curve covering five decades, the Sahm Rule, and a hand-built financial-conditions index checked against the Chicago Fed NFCI. The model is evaluated honestly: features shifted to publication time, an embargoed 2006-to-present holdout, Newey-West standard errors, and a per-recession warning record that shows the misses as well as the hits.

Live app: [macronowcast.streamlit.app](https://macronowcast.streamlit.app) | [Code and project folder](./Macro%20Nowcasting)

The project folder also holds the full research notebook behind the app, with data validation, leakage audits, robustness checks, and a limitations section covering data-revision bias.

![Macro dashboard](./Macro%20Nowcasting/macro_hero_dashboard.png)

## 3. Pairs trading statistical arbitrage backtester

A research notebook that screens 12 large-cap US financials (66 pairs) for cointegration with the Engle-Granger test on rolling 24-month formation windows, filters candidates by Ornstein-Uhlenbeck half-life, and trades z-score entry and exit signals long-short over the following six months, strictly out of sample, with 5 bps per-leg transaction costs. From 2009 to mid-2026 the strategy earns a market-neutral 3.0% CAGR at 4.8% volatility (net Sharpe 0.64, Newey-West t = 2.81, SPY beta -0.01, max drawdown -10.4%), with the edge concentrated in 2009-2012 and its later decay reported rather than hidden. The notebook audits itself for look-ahead leaks, shows the circular in-sample version once as a warning, and closes with threshold grids, cost sweeps, formation-window sensitivity, and regime breakdowns.

[Code and project folder](./Pairs%20Trading)

![Pairs trading dashboard](./Pairs%20Trading/pairs_hero_dashboard.png)

## Built with

Python, pandas, numpy, scipy, statsmodels, matplotlib, seaborn, plotly, Streamlit.
