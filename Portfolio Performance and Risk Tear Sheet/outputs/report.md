# Portfolio Performance & Risk Tear Sheet — Research Report

*A reproducible, fund-grade tear sheet for a diversified 10-stock S&P 500 book vs SPY.*

## Question
How does an equal-weight, monthly-rebalanced book of large-cap S&P 500 names compare to SPY on a risk-adjusted, net-of-cost basis?

## Methodology
Weighted simple-return aggregation with drifted-weight monthly rebalancing; turnover-based costs (gross and net); a consistent metric engine (Sharpe = mean-excess/σ·√252, Sortino on downside deviation, Calmar = CAGR/|MDD|, historical VaR/ES); significance via Newey–West HAC t-stats, a Lo (2002) Sharpe CI, and a CAPM regression with HAC errors.

## Results (this run: synthetic (offline))
| Series | CAGR | Ann.Vol | Sharpe | Sortino | MaxDD |
|---|---|---|---|---|---|
| Portfolio (net) | 11.56% | 15.59% | 0.66 | 0.97 | -43.83% |
| SPY | 7.62% | 17.12% | 0.41 | 0.59 | -42.80% |

CAPM: alpha +5.93%/yr (t=1.73), beta 0.63, R²=0.48. Net Sharpe 95% CI [0.08, 1.24].

## Limitations
Survivorship/selection bias in the hindsight-chosen universe; descriptive rather than predictive; proportional costs without market impact; synthetic fallback numbers are illustrative only.
