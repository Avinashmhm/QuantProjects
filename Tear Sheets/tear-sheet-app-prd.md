# Tear Sheet Generator Web App - PRD

## 1. Executive Summary

A single-page Streamlit web app that turns the existing batch tear sheet pipeline into an on-demand tool. A user types any ticker, optionally picks a benchmark ticker and a date range, and gets the standard house tear sheet rendered in the browser: growth of $1, underwater drawdown, rolling Sharpe, monthly returns heatmap, return distribution, and the headline metrics table. The core value: what previously required editing and re-running a notebook for a fixed list of 28 assets now works for any ticker in seconds, and the app is deployable to Streamlit Community Cloud as a shareable portfolio piece.

## 2. Target Audience

- **Primary: the repo owner (student building a quant portfolio).** Pain point: generating a tear sheet for a new ticker means editing a notebook cell, running the whole pipeline, and pulling the PNG out of a folder. Wants a live demo link for a resume and GitHub README.
- **Secondary: recruiters and other visitors.** Pain point: static PNGs show output but not that the tool works. A live app lets them test any ticker themselves.
- **Tertiary: retail investors or classmates.** Want a quick, readable risk and performance summary for a stock or ETF without writing code.

## 3. SLC Definition

- **Simple:** one page, four inputs (ticker, benchmark on/off, benchmark ticker, date range), one button. No accounts, no saved state, no settings pages.
- **Lovable:** the interactive Plotly tear sheet renders inline with hover detail, headline stats show as metric tiles, and a one-click button downloads the static PNG in the same house style as the existing 28 published tear sheets.
- **Complete:** handles the full happy path plus the realistic failure paths: unknown ticker, benchmark same as ticker, date range too short, and data source outage. All computation reuses quantlib (data.py, metrics.py, tearsheet.py) so numbers match the published sheets exactly.

## 4. Out of Scope

- Multi-asset portfolios or weighted baskets (single ticker vs single benchmark only)
- Custom uploaded return series (CSV upload deferred)
- Factor regressions, alpha/beta attribution, or any new analytics beyond the existing tear sheet
- User accounts, saved history, or shareable permalinks
- Intraday or non-daily data frequencies
- Theming or layout customization by the end user

## 5. User Stories & UX

**Story 1: ticker with benchmark (primary journey)**
1. User opens the app and sees inputs pre-filled (ticker NVDA, benchmark SPY, dates 2015-01-01 to today).
2. User types their own ticker, leaves "Compare to a benchmark" checked, and clicks Generate.
3. A spinner shows while prices download (cached on repeat runs).
4. Headline metric tiles appear (CAGR, Sharpe, Max Drawdown), followed by the interactive five-panel tear sheet and the full metrics table with the benchmark row.
5. User clicks "Download PNG" and gets the static house-style tear sheet image.

**Story 2: ticker without benchmark**
1. User unchecks "Compare to a benchmark"; the benchmark input disables.
2. Generate produces the same exhibit with the strategy series only and a one-row metrics table.

**Edge cases**
- Unknown or misspelled ticker: the app detects that the data layer fell back to synthetic data and shows a clear error naming the ticker, instead of silently plotting fake prices.
- Benchmark identical to the ticker: benchmark is ignored with a visible note.
- Date range yielding under ~60 trading days (data layer minimum): treated as a failed fetch with guidance to widen the range.
- Ticker newer than the start date (recent IPO): charts render from first available data; comparison window note shows actual dates used.
- Yahoo outage: same error path as unknown ticker, wording asks the user to retry.

## 6. Acceptance Criteria

1. Entering AAPL with benchmark SPY over 2015-2025 renders metric tiles, the interactive tear sheet, and a two-row metrics table; every number matches quantlib.metrics output for the same inputs.
2. Unchecking the benchmark renders a one-row table and no benchmark trace on the growth chart.
3. Entering ticker ZZZZZFAKE shows an error message and renders no charts (verified: synthetic fallback never displays as real data).
4. Setting benchmark equal to the ticker renders the no-benchmark view with a note.
5. The PNG download returns the static tear sheet for the exact inputs shown on screen.
6. `streamlit run` works from a clean clone of the repo with only `pip install -r requirements.txt` (the app folder vendors its own copy of quantlib, no imports from outside the repo).
7. Repeat generation of the same inputs completes noticeably faster via the local price cache.

**Milestones**
- Phase 1: working local app (inputs, fetch, interactive exhibit, metrics table, error paths)
- Phase 2: PNG download, README section, commit and push
- Phase 3: deploy to Streamlit Community Cloud (owner action, instructions provided)
