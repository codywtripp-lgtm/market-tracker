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

**v2 (current):** one regression per horizon **per commodity × market**, shrunk toward the pooled regression (a group is pulled toward the overall pattern as if the overall pattern were worth 1,000 extra rows of data, so thin groups stay close to it). Then, **per commodity × market, the model is used only where it has beaten "no change"** in past years; stable items (onions, bananas, carrots, potatoes, lemons, grapes, NY Romas) are forecast as "about the same". Ranges come from the chosen method's **own out-of-sample errors** (per commodity when there are enough, otherwise all commodities). v1 was a single pooled regression.

## How it was tested (walk-forward)
For each year 2021–2026: train only on data before that year, forecast every week of that year, score it. Nothing from the future is ever visible (seasonal and "usual" figures use earlier years only; changes that cross New Year are left out of seasonal averages).

Results (average miss in % of price, lower is better; the per-item choice for each test year uses only earlier years):

| Weeks ahead | **v2 per item** | v1 pooled | No change | Seasonal only |
|---|---|---|---|---|
| 1 | **7.1%** | 7.5% | 7.7% | 8.4% |
| 2 | **11.8%** | 12.3% | 13.0% | 13.8% |
| 3 | **15.4%** | 15.8% | 17.0% | 17.6% |
| 4 | **17.9%** | 18.3% | 19.9% | 20.4% |

- v2 is 7–10% better than "no change" at every horizon (v1: 2–8%).
- 80% ranges contain the actual price **80.1%** of the time out of sample (quantiles widened slightly from 10/90 to 8.5/91.5 to get there).
- "Seasonal only" is worse than "no change": the typical seasonal move alone isn't reliable week to week; it helps only combined with where the price is now.
- Per-item report card: `data/export/forecast_report_card.csv`. NY, 2 weeks ahead: biggest gains on limes (−25% miss vs no change), celery and broccoli (−22%), romaine, iceberg, blueberries (−16%), strawberries (−15%). Stable items use "no change".

Tried and dropped on 2026-09-26 (no improvement): last week's shipping-point move as an extra input; gradient boosting (worse at 2–4 weeks); weaker (250 rows) or stronger (4,000 rows) pull toward the pooled pattern.

Honest read: produce prices are volatile (a typical 4-week move is ~20%), so the **range** is the most useful output. More model tuning now gives tiny gains; the next real improvement needs **new information** (weather, shipment volumes).

## Next improvements (each kept only if the walk-forward score improves)
- Weather at origin (NOAA), shipment volumes (USDA 3283/1662), MXN/USD, diesel, holidays, FDA recalls.
- A public track record on the site (past forecasts vs. what happened).
