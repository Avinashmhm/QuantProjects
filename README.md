# QuantProjects

A portfolio of quantitative-finance projects — each self-contained in its own section, with a runnable notebook and exported results. Built in Python (pandas, numpy, scipy, statsmodels, matplotlib, plotly) with an emphasis on statistical honesty: correct annualization, no look-ahead bias, transaction costs reported gross **and** net, and significance testing rather than bare point estimates.

## Projects

### 1. [Portfolio Performance and Risk Tear Sheet](./Portfolio%20Performance%20and%20Risk%20Tear%20Sheet)

The exhibit on the first page of every fund's investor letter: a diversified 10-stock, equal-weight S&P 500 book — monthly-rebalanced and cost-aware — measured against SPY, with a full suite of risk-adjusted and tail-risk statistics.

![Hero tear sheet](./Portfolio%20Performance%20and%20Risk%20Tear%20Sheet/outputs/portfolio_tear_sheet_hero.png)

- **Notebook:** [`portfolio_tear_sheet.ipynb`](./Portfolio%20Performance%20and%20Risk%20Tear%20Sheet/portfolio_tear_sheet.ipynb) — runs top to bottom with no API keys (labeled synthetic fallback); pulls live Yahoo Finance + FRED data on Colab.
- **Methods:** CAGR, annualized volatility, Sharpe, Sortino, Calmar, max drawdown, historical VaR / Expected Shortfall; Newey–West (HAC) *t*-statistics, a Lo (2002) Sharpe confidence interval, and a CAPM alpha/beta decomposition; walk-forward stability plus transaction-cost, rebalance-frequency, and market-regime robustness checks.
- **Outputs:** hero tear sheet, headline metrics CSV, interactive Plotly dashboard, and a written report + résumé bullets in [`outputs/`](./Portfolio%20Performance%20and%20Risk%20Tear%20Sheet/outputs).

> Results embedded in the committed notebook come from the deterministic **synthetic** data path (so the repo renders end-to-end with no keys). Re-run the notebook in Google Colab for live-market numbers — the notebook prints which data path is active.

### 2. [Semiconductor Portfolio Tear Sheet](./Semiconductor%20Portfolio%20Tear%20Sheet)

The same tear-sheet engine applied to a concentrated, **real-data** book of four semiconductor/tech names — **NVDA, AMD, AAPL, MU** — equal-weight, monthly-rebalanced, vs SPY (2014–2024). A case study in high-return, high-risk concentration, honestly framed by its selection bias.

![Hero tear sheet](./Semiconductor%20Portfolio%20Tear%20Sheet/outputs/semiconductor_tear_sheet_hero.png)

- **Notebook:** [`semiconductor_tear_sheet.ipynb`](./Semiconductor%20Portfolio%20Tear%20Sheet/semiconductor_tear_sheet.ipynb) — embeds **real** Yahoo Finance data via a keyless chart-API layer (synthetic fallback if offline).
- **Headline (real, net of costs):** 41.0% CAGR at 35.4% volatility → Sharpe **1.09** vs SPY's 0.69, but a **−49.5%** max drawdown; CAPM alpha +20.4%/yr (t=3.07), beta 1.54.
- **Honest caveat:** these four are hindsight-selected decade winners — the alpha is selection bias, not a repeatable strategy (see the notebook's Limitations).

## How to run any project

Open the project's `.ipynb` in [Google Colab](https://colab.research.google.com/) and choose **Runtime → Run all**. No API keys are required; each notebook degrades gracefully to a labeled synthetic dataset and writes its figures/tables to that project's `outputs/` folder.

## Built with

Python · pandas · numpy · scipy · statsmodels · matplotlib · seaborn · plotly
