# Pairs Trading Backtester Web App - PRD

## 1. Executive Summary

A single-page Streamlit app that turns the pairs trading research notebook into an interactive backtest explorer. The heavy, slow part (screening all 66 bank-stock pairs for cointegration across 35 rolling formation windows) runs once and is cached; the fast part (signal thresholds, costs, pair count) is exposed as sidebar controls so a visitor can move a slider and watch the out-of-sample equity curve, trade ledger, and significance statistics recompute in about a second. The core value: the notebook proves the methodology once, while the app lets anyone stress the strategy live without reading code, and it gives the repo a third deployed portfolio piece alongside the tear sheet and macro apps.

## 2. Target Audience

- **Primary: the repo owner (student building a quant portfolio).** Wants a live demo link for the resume and README that shows the walk-forward machinery working, not just static screenshots.
- **Secondary: recruiters and quant researchers.** Pain point: a notebook takes minutes to read; an app communicates the strategy design (formation/trading split, costs, stops) in thirty seconds of slider-dragging, and the honesty of the result (modest Sharpe, decaying edge) is visible rather than claimed.
- **Tertiary: students learning stat-arb.** Can see, concretely, how entry/exit thresholds, transaction costs, and formation length change a pairs strategy's results.

## 3. SLC Definition

- **Simple:** one page, one fixed universe (12 large-cap US financials, 2007 to today), sidebar controls for entry z, exit z, stop z, cost per leg, max pairs, and formation window (12/24/36 months). No accounts, no uploads, no free-form tickers.
- **Lovable:** metric tiles for net Sharpe, CAGR, max drawdown, SPY beta, and the Newey-West t-stat; an interactive equity chart against SPY and the equal-weight bank basket; a pair explorer where any of the 66 pairs shows its rolling cointegration p-value, spread, z-score, and trade markers; a downloadable trade ledger.
- **Complete:** handles the realistic failure paths: Yahoo outage (clear error, stop), a parameter set that selects zero pairs (informative empty state rather than a crash), and a pair that was never selected (message plus its diagnostics anyway). Statistics match the research notebook's methodology exactly: same Engle-Granger screen, same OU half-life filter, same frozen formation parameters, same per-leg cost accounting.

## 4. Out of Scope

- Custom universes or user-typed tickers (the screen is quadratic in names; fixed universe keeps the app fast and the statistics comparable to the notebook)
- Johansen baskets, Kalman-filter hedge ratios, or any methodology beyond the notebook
- Intraday data, live trading signals, or broker connectivity
- User accounts, saved runs, or shareable permalinks
- Editing the selection filters (EG p-value bar, half-life bounds, beta bounds stay at the notebook's values so the multiple-testing story stays honest)

## 5. User Stories & UX

**Story 1: first visit (primary journey)**
1. User opens the app; a spinner explains the one-time screening step while prices download and the cointegration screen runs (cached for later visitors).
2. The page renders with notebook defaults (entry 2.0, exit 0.5, stop 3.0, 5 bps per leg, 5 pairs, 24-month formation): metric tiles, equity chart, drawdown chart.
3. User drags the cost slider from 5 to 15 bps and watches the net Sharpe tile and equity curve degrade in about a second.

**Story 2: pair explorer**
1. User opens the Pair explorer tab and picks a pair from the dropdown (defaults to the most-selected pair).
2. The app shows that pair's rolling Engle-Granger p-value with the selection bar marked, the stitched z-score across its traded windows with entry/exit/stop lines, and its trades table.
3. If the chosen pair was never selected, the app says so and still shows the rolling p-value so the user can see why.

**Story 3: empty result (edge case)**
1. User sets entry z to 3.0 with stop 3.0 (no trades possible).
2. The app explains that no trades were generated at these settings instead of showing empty charts, and suggests loosening the entry threshold.

**Story 4: data outage (edge case)**
1. Yahoo is unreachable; the app shows one clear error and stops rather than rendering a broken page.

## 6. Acceptance Criteria

- [ ] App runs locally with `streamlit run "Pairs Trading/app/app.py"` and deploys on Streamlit Community Cloud from the repo root requirements.txt with no extra config.
- [ ] First load completes the full screen and renders in under ~90 seconds on the free tier; subsequent parameter changes re-render in under ~3 seconds without re-screening.
- [ ] Default settings reproduce the notebook's out-of-sample results to rounding (net Sharpe about 0.64 with the same trade count) on the same end date.
- [ ] All results shown are walk-forward out of sample; nothing is fit on the window it trades. Signal decided at close t earns returns from t+1.
- [ ] Gross and net are both computed; the cost slider changes net only.
- [ ] Metric tiles include SPY beta and the Newey-West t-stat so the market-neutrality and significance claims are visible, not asserted.
- [ ] Entry z >= stop z and other degenerate settings produce an informative empty state, never an exception.
- [ ] Trade ledger downloads as CSV.
- [ ] Survivorship and cost caveats appear in an About tab, consistent with the notebook's limitations section.
- [ ] Works on pandas 2.x and 3.x (month-end alias helper) and current yfinance.

## Milestones

1. **Engine + main view:** port the notebook engine (screen, signals, accounting), cached data and screening, sidebar controls, metric tiles, equity and drawdown charts.
2. **Explorer + tables:** pair explorer tab (rolling p-value, z-score, trades), attribution and trade ledger with CSV download, About tab.
3. **Deploy:** push to GitHub, deploy on Streamlit Community Cloud, add the live link to the repo README.
