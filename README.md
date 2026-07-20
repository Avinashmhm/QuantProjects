# QuantProjects

Quantitative finance projects in Python. Each folder holds one project: a research notebook that explains the method, runs it on real data, and checks its own statistics, plus (for most projects) a small web app you can try in a browser. The common thread is careful measurement. Results come with significance tests, out-of-sample checks, and a plain list of what could be wrong, because a backtest that only shows its wins is advertising, not research.

## 1. Performance tear sheet generator

Type in any stock, fund, index, or crypto symbol and get a one-page report card of how it has performed: the growth of a dollar invested, how far it fell from its peaks (drawdowns), how bumpy the ride was (volatility), and the standard risk and return statistics used on trading desks, with an optional benchmark to compare against.

The ticker boxes suggest matches from about 13,000 US-listed symbols as you type, and every number is computed by one shared metrics library, so the same statistic always means the same thing across the site.

Live app: [performancesheet.streamlit.app](https://performancesheet.streamlit.app) | [Code and project folder](./Tear%20Sheets)

The folder also holds a gallery of 28 ready-made tear sheets for widely followed stocks and funds, with significance tests behind the headline statistics.

## 2. Macro nowcasting and recession dashboard

Estimates the probability that the US economy enters a recession within a chosen horizon, using live data from FRED, the Federal Reserve's public database. Under the hood is a logistic regression on the Treasury yield curve plus a set of leading indicators: credit spreads, payrolls, jobless claims, building permits, and consumer sentiment. The dashboard shows the current probability as a gauge, an animated yield curve covering five decades, the Sahm Rule recession indicator, and a hand-built financial conditions index checked against the Chicago Fed's official version.

The evaluation is honest about timing. Every input is shifted to the date it was actually published (you cannot trade on a number before it exists), the 2006-to-present test period is walled off from model fitting, and the write-up shows the recessions the model missed as well as the ones it caught.

Live app: [macronowcast.streamlit.app](https://macronowcast.streamlit.app) | [Code and project folder](./Macro%20Nowcasting)

![Macro dashboard](./Macro%20Nowcasting/macro_hero_dashboard.png)

## 3. Pairs trading statistical arbitrage backtester

Tests a classic hedge fund idea: find two bank stocks that historically move together, and when the gap between them stretches unusually wide, bet on the gap closing. The notebook screens 12 large US financial stocks (66 possible pairs) for statistically stable relationships (cointegration, tested with the Engle-Granger method), keeps only pairs whose gaps close at a reasonable speed, and then trades them on data the selection step never saw, with realistic transaction costs charged on every trade.

From 2009 to mid-2026 the strategy earned 3.0% a year at 4.8% volatility while staying essentially immune to stock market direction (net Sharpe 0.64, Newey-West t = 2.81, SPY beta -0.01, worst drawdown -10.4%). Most of the edge came in 2009 to 2012 and faded afterward. The notebook reports that decay instead of hiding it, audits itself for look-ahead leaks, and closes with sensitivity checks on every major parameter.

Live app: [pairsbacktest.streamlit.app](https://pairsbacktest.streamlit.app) | [Code and project folder](./Pairs%20Trading)

![Pairs trading dashboard](./Pairs%20Trading/pairs_hero_dashboard.png)

## 4. NLP sentiment signals from SEC filings

Every US public company must file an annual report, called a 10-K, with the SEC. This project downloads about 320 of them (32 large companies, ten years) straight from the SEC's EDGAR system, has code read the two most informative sections (management's discussion of the year, and the list of risk factors), and turns the text into two numbers per filing: how positive or negative the wording is, scored with a dictionary built specifically for financial language and with the FinBERT neural network, and how much the filing changed compared with last year's. Published research ("Lazy Prices") found that companies quietly rewriting their filings tend to do worse afterward.

The project then tests whether either number actually predicted returns. Filings are sorted into thirds by each signal, the stocks' market-beating returns are tracked for the 30 trading days after each filing, and the observed gap between the top and bottom thirds is compared against 1,000 shuffled versions of the signal to see whether it beats pure chance. The verdict on this sample: tone made no measurable difference, but companies that heavily rewrote their filings went on to beat the ones that barely changed them by about 3 percentage points over the next 30 trading days, a gap only 20 in 1,000 shuffles matched. Interestingly that is the reverse of the published finding, so the notebook treats it as a lead to test on more data, not a trading rule, and explains why (small sample, surviving mega caps only, and the decade when the biggest filing rewrites came from companies transforming their businesses).

Live app: [nlpsignals.streamlit.app](https://nlpsignals.streamlit.app) | [Code and project folder](./SEC%20Filings%20NLP)

![Event study dashboard](./SEC%20Filings%20NLP/sec_nlp_hero_event_study.png)

## Built with

Python, pandas, numpy, scipy, statsmodels, scikit-learn, matplotlib, seaborn, plotly, Streamlit, requests, BeautifulSoup, and yfinance. Data comes from Yahoo Finance, FRED, and SEC EDGAR.
