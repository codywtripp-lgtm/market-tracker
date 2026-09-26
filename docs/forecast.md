# Forecasts (next 1–4 weeks)

Code: `pipeline/forecast.py` (runs every night after the data update). Output: `data/export/forecasts.json`, scores in `data/export/forecast_backtest.csv`.

## What it predicts
For each headline terminal-market series (NY, LA, Chicago), the weekly **case price 1, 2, 3 and 4 weeks ahead**, as a middle estimate and an **80% range** ("likely between $X and $Y"). Week-level on purpose: annual averages hide the swings that matter to buyers.

## How
The model predicts the *change* in price (log change), not the price level, from:

| Input | Meaning |
|---|---|
| seasonal | the average move from this week of the year to h weeks later, in **prior years only** |
| gap | how far this week's price (today's dollars) sits from the usual price for this time of year — extremes tend to come back |
| mom1, mom4 | change over the last 1 and 4 weeks |
| sp | this week's shipping-point price change for the commodity |
| tone | USDA reporters' call at this market this week ("higher" +1 … "lower" −1) |

One linear regression per horizon, pooled across all series. Ranges come from the model's **own out-of-sample errors** (per commodity when there are enough, otherwise all commodities).

## How it was tested (walk-forward)
For each year 2021–2026: train only on data before that year, forecast every week of that year, score it. Nothing from the future is ever visible (seasonal and "usual" figures use earlier years only; changes that cross New Year are left out of seasonal averages).

First results (average miss in % of price, lower is better):

| Weeks ahead | Model | No change | Seasonal only |
|---|---|---|---|
| 1 | **7.5%** | 7.7% | 8.4% |
| 2 | **12.3%** | 13.0% | 13.8% |
| 3 | **15.8%** | 17.0% | 17.6% |
| 4 | **18.3%** | 19.9% | 20.4% |

- The model beats both simple baselines at every horizon, most at 3–4 weeks (~8% smaller misses than "no change").
- "Seasonal only" is worse than "no change": the typical seasonal move alone isn't reliable week to week; it helps only combined with where the price is now.
- 80% ranges contain the actual price **80.3%** of the time out of sample (quantiles widened slightly from 10/90 to 8.5/91.5 to get there).

Honest read: produce prices are volatile (a typical 4-week move is ~20%), so the **range** is the most useful output; the middle line is a modest improvement over "no change". The live method per horizon is whichever scored best (currently the model at all four).

## Next improvements (each kept only if the walk-forward score improves)
- Per-commodity coefficients (e.g. romaine reacts differently from limes).
- Nonlinear model (gradient boosting) for effects like "a freeze matters only in winter".
- Weather at origin (NOAA), shipment volumes (USDA 3283/1662), MXN/USD, diesel, holidays, FDA recalls.
- A public track record on the site (past forecasts vs. what happened).
