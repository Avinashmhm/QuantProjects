# QuantProjects

Quantitative finance work in Python (pandas, numpy, scipy, statsmodels, matplotlib). The focus is on measuring performance and risk correctly: proper annualization, drawdown and tail-risk statistics, and significance testing rather than bare point estimates.

## 1. Performance tear sheet generator

A Streamlit web app that builds a full performance and risk tear sheet for any Yahoo Finance symbol: stocks, ETFs, indexes (^GSPC), futures (ES=F), and crypto pairs (BTC-USD), with an optional benchmark overlay, an interactive chart panel, a complete risk table, and a PNG download. The ticker boxes suggest from a curated list of about 700 liquid names as you type, and the numbers come from a shared metrics library so every exhibit is computed the same way.

Live app: [performancesheet.streamlit.app](https://performancesheet.streamlit.app) | [Code and project folder](./Tear%20Sheets)

The project folder also holds a gallery of 28 pre-generated tear sheets for widely followed stocks, ETFs, and funds, with summary statistics and Newey-West significance tests.

## Built with

Python, pandas, numpy, scipy, statsmodels, matplotlib, seaborn.
