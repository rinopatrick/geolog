# Production economics

`POST /api/wells/{wid}/production/economics` fits exponential and hyperbolic
decline models to positive oil-rate history, then runs a seeded Monte Carlo
around `qi`, decline rate and hyperbolic `b`.

## Cash-flow model

Monthly net cash is:

```text
oil       = rate_at_mid_month * 30.4375
revenue   = oil * oil_price * (1 - royalty) * working_interest
opex      = oil * opex_per_bbl * working_interest
net       = (revenue - opex) * (1 - tax_rate) when positive
npv       = -capex * working_interest + sum(net / (1 + monthly_discount)^month)
```

`monthly_discount = (1 + annual_discount)^(1/12) - 1`.

The forecast stops at `economic_limit` or `years`, whichever comes first.
Payout is the first month where cumulative net cash covers working-interest
capex. P90/P50/P10 are the 10th/50th/90th percentiles of the Monte Carlo
sample; P90 is the conservative low case.

## Assumptions and limits

- Only oil rate is forecast. Gas, water, and shrinkage are not monetised.
- No inflation, mid-year discounting, abandonment cost, or fiscal regimes.
- `capex` is treated as net-to-working-interest at month zero.
- The model is a screening tool, not a reserves audit.

## Anomaly detection

`POST /api/wells/{wid}/production/anomalies` fits decline on the first
half of oil-rate history, forecasts the second half, and flags points
deviating beyond `threshold_pct`. A CUSUM on test-window residuals reports
`declining`, `growing`, or `stable` trend. A clean exponential decline
produces zero flags — verified by test. Needs at least 12 positive rate
points. Screening: single-well, oil-rate only, no operating-event context
(workovers, chokes, downtime explain real flags).
