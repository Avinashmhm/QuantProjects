# Performance and Risk Tear Sheets

Standalone tear sheets for a range of widely-followed stocks, ETFs, and funds, each measured on its own with no benchmark comparison. Built from real Yahoo Finance adjusted-close data (from 2014, or from the ticker's inception if later, through 2024). Every tear sheet shows the growth of one dollar (log scale), the drawdown-from-peak underwater plot, a rolling six-month Sharpe ratio, a monthly-return heatmap, and the daily-return distribution against a normal curve.

The notebook that produces all of these is [`tear_sheets.ipynb`](tear_sheets.ipynb). It runs with no API keys and prints which data path is active.

## Interactive tear sheet app

Live at [performancesheet.streamlit.app](https://performancesheet.streamlit.app).

The [`app/`](app/) folder contains the Streamlit web app behind it, which generates the same house tear sheet on demand for any ticker: type a symbol, optionally pick a benchmark ticker and a date range, and the exhibit renders in the browser with an interactive chart panel, the full metrics table, and a PNG download. Bad tickers get a clear error rather than a chart of fallback data.

To run it locally from the repo root:

```
pip install -r requirements.txt
streamlit run "Tear Sheets/app/app.py"
```

To deploy it free on [Streamlit Community Cloud](https://share.streamlit.io), point a new app at this repo with `Tear Sheets/app/app.py` as the main file path.

## Summary statistics

Sharpe and Sortino use a flat 2% annual risk-free rate. HAC t is the Newey-West t-statistic that the mean daily return differs from zero (above about 2 is significant at the 5% level). Some series have shorter histories because they launched after 2014 (AIQ 2018, BOTZ 2016, PLTR and COIN 2020 to 2021), so their statistics cover a shorter window.

| Category | Series | Ticker | CAGR | Ann. vol | Sharpe | Sortino | Max drawdown | HAC t |
|---|---|---|---|---|---|---|---|---|
| Broad-market baselines | SPY (S&P 500 ETF) | SPY | 13.2% | 17.1% | 0.69 | 0.97 | -33.7% | 3.06 |
| Broad-market baselines | S&P 500 Index | ^GSPC | 11.3% | 17.3% | 0.59 | 0.82 | -33.9% | 2.68 |
| Semiconductor ETFs | VanEck Semiconductor ETF (SMH) | SMH | 26.5% | 29.6% | 0.87 | 1.26 | -45.3% | 3.62 |
| Semiconductor ETFs | iShares Semiconductor ETF (SOXX) | SOXX | 23.7% | 30.2% | 0.79 | 1.14 | -45.8% | 3.35 |
| AI-themed ETFs | Global X AI and Technology ETF (AIQ) | AIQ | 15.9% | 25.2% | 0.63 | 0.89 | -44.7% | 1.98 |
| AI-themed ETFs | Global X Robotics and AI ETF (BOTZ) | BOTZ | 10.3% | 25.4% | 0.44 | 0.61 | -55.5% | 1.46 |
| AI chips and hardware | NVIDIA (NVDA) | NVDA | 71.3% | 47.0% | 1.34 | 2.09 | -66.3% | 4.77 |
| AI chips and hardware | AMD | AMD | 36.7% | 57.3% | 0.79 | 1.24 | -65.4% | 2.88 |
| AI chips and hardware | Broadcom (AVGO) | AVGO | 45.1% | 37.0% | 1.14 | 1.75 | -48.3% | 4.55 |
| AI chips and hardware | TSMC (TSM) | TSM | 28.6% | 31.2% | 0.90 | 1.37 | -56.5% | 3.43 |
| AI chips and hardware | Micron (MU) | MU | 13.5% | 45.9% | 0.46 | 0.67 | -73.8% | 1.85 |
| AI platforms and software | Microsoft (MSFT) | MSFT | 26.9% | 26.5% | 0.96 | 1.42 | -37.1% | 4.43 |
| AI platforms and software | Alphabet (GOOGL) | GOOGL | 19.2% | 27.9% | 0.70 | 1.02 | -44.3% | 3.00 |
| AI platforms and software | Amazon (AMZN) | AMZN | 24.5% | 32.7% | 0.77 | 1.14 | -56.1% | 3.00 |
| AI platforms and software | Meta (META) | META | 24.3% | 37.3% | 0.72 | 1.04 | -76.7% | 2.89 |
| AI platforms and software | Apple (AAPL) | AAPL | 27.7% | 27.9% | 0.94 | 1.39 | -38.5% | 3.52 |
| AI platforms and software | Oracle (ORCL) | ORCL | 16.2% | 26.9% | 0.62 | 0.92 | -40.4% | 2.66 |
| AI platforms and software | Palantir (PLTR) | PLTR | 63.9% | 71.7% | 1.01 | 1.69 | -84.6% | 1.97 |
| Popular retail-trader tickers | Tesla (TSLA) | TSLA | 40.5% | 56.4% | 0.85 | 1.29 | -73.6% | 2.72 |
| Popular retail-trader tickers | GameStop (GME) | GME | 12.3% | 112.3% | 0.57 | 1.10 | -92.2% | 1.72 |
| Popular retail-trader tickers | AMC Entertainment (AMC) | AMC | -28.0% | 133.3% | 0.19 | 0.42 | -99.6% | 0.63 |
| Popular retail-trader tickers | Coinbase (COIN) | COIN | -6.5% | 89.4% | 0.34 | 0.53 | -90.9% | 0.67 |
| Popular retail-trader tickers | Strategy / MicroStrategy (MSTR) | MSTR | 33.8% | 66.8% | 0.74 | 1.15 | -89.3% | 2.35 |
| Popular retail-trader tickers | Ford (F) | F | 0.9% | 34.8% | 0.14 | 0.20 | -68.8% | 0.64 |
| Popular retail-trader tickers | Disney (DIS) | DIS | 4.4% | 27.1% | 0.22 | 0.32 | -60.7% | 0.98 |
| Popular retail-trader tickers | iShares Russell 2000 ETF (IWM) | IWM | 7.6% | 22.0% | 0.35 | 0.49 | -41.1% | 1.52 |
| Popular retail-trader tickers | SPDR Gold Shares (GLD) | GLD | 6.7% | 14.2% | 0.39 | 0.56 | -24.5% | 1.84 |
| Popular retail-trader tickers | iShares Silver Trust (SLV) | SLV | 2.9% | 26.3% | 0.17 | 0.24 | -47.1% | 0.81 |

## Broad-market baselines

### SPY (S&P 500 ETF)

![SPY (S&P 500 ETF) tear sheet](SPY_tear_sheet.png)

### S&P 500 Index

![S&P 500 Index tear sheet](SP500_tear_sheet.png)

## Semiconductor ETFs

### VanEck Semiconductor ETF (SMH)

![VanEck Semiconductor ETF (SMH) tear sheet](SMH_tear_sheet.png)

### iShares Semiconductor ETF (SOXX)

![iShares Semiconductor ETF (SOXX) tear sheet](SOXX_tear_sheet.png)

## AI-themed ETFs

### Global X AI and Technology ETF (AIQ)

![Global X AI and Technology ETF (AIQ) tear sheet](AIQ_tear_sheet.png)

### Global X Robotics and AI ETF (BOTZ)

![Global X Robotics and AI ETF (BOTZ) tear sheet](BOTZ_tear_sheet.png)

## AI chips and hardware

### NVIDIA (NVDA)

![NVIDIA (NVDA) tear sheet](NVDA_tear_sheet.png)

### AMD

![AMD tear sheet](AMD_tear_sheet.png)

### Broadcom (AVGO)

![Broadcom (AVGO) tear sheet](AVGO_tear_sheet.png)

### TSMC (TSM)

![TSMC (TSM) tear sheet](TSM_tear_sheet.png)

### Micron (MU)

![Micron (MU) tear sheet](MU_tear_sheet.png)

## AI platforms and software

### Microsoft (MSFT)

![Microsoft (MSFT) tear sheet](MSFT_tear_sheet.png)

### Alphabet (GOOGL)

![Alphabet (GOOGL) tear sheet](GOOGL_tear_sheet.png)

### Amazon (AMZN)

![Amazon (AMZN) tear sheet](AMZN_tear_sheet.png)

### Meta (META)

![Meta (META) tear sheet](META_tear_sheet.png)

### Apple (AAPL)

![Apple (AAPL) tear sheet](AAPL_tear_sheet.png)

### Oracle (ORCL)

![Oracle (ORCL) tear sheet](ORCL_tear_sheet.png)

### Palantir (PLTR)

![Palantir (PLTR) tear sheet](PLTR_tear_sheet.png)

## Popular retail-trader tickers

### Tesla (TSLA)

![Tesla (TSLA) tear sheet](TSLA_tear_sheet.png)

### GameStop (GME)

![GameStop (GME) tear sheet](GME_tear_sheet.png)

### AMC Entertainment (AMC)

![AMC Entertainment (AMC) tear sheet](AMC_tear_sheet.png)

### Coinbase (COIN)

![Coinbase (COIN) tear sheet](COIN_tear_sheet.png)

### Strategy / MicroStrategy (MSTR)

![Strategy / MicroStrategy (MSTR) tear sheet](MSTR_tear_sheet.png)

### Ford (F)

![Ford (F) tear sheet](F_tear_sheet.png)

### Disney (DIS)

![Disney (DIS) tear sheet](DIS_tear_sheet.png)

### iShares Russell 2000 ETF (IWM)

![iShares Russell 2000 ETF (IWM) tear sheet](IWM_tear_sheet.png)

### SPDR Gold Shares (GLD)

![SPDR Gold Shares (GLD) tear sheet](GLD_tear_sheet.png)

### iShares Silver Trust (SLV)

![iShares Silver Trust (SLV) tear sheet](SLV_tear_sheet.png)

## Notes and limitations

- These are descriptive tear sheets of single assets and funds, not strategies. Past compounding does not predict future returns.
- The S&P 500 index (^GSPC) is price only, so it excludes dividends. SPY is a total-return series (dividends reinvested through the adjusted close), which is why SPY shows a higher CAGR than the index over the same window.
- Some series launched after 2014, so their tear sheets cover shorter windows: AIQ (2018), BOTZ (2016), PLTR (2020), and COIN (2021). Shorter windows make their statistics less reliable than the full eleven-year names.
- Several of the retail-trader names are highly volatile (GME, AMC, MSTR, and COIN in particular), with very large drawdowns. High single-name volatility makes point estimates like Sharpe noisier.
- Sharpe and Sortino use a flat 2% annual risk-free rate, close to the average 3-month Treasury yield over the period.
- Yahoo adjusted closes are revised for splits and dividends after the fact, so they are not a point-in-time record of what a trader saw on the day.
