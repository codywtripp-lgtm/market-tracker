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

**Shipment volumes (tested 2026-09-26, not used):** adding "shipments vs. usual for this time of year" and "shipments vs. the last 2 weeks" (from the USDA movement reports, last complete week) did not improve forecasts (average miss 13.24% vs 13.23% without; tiny gains for strawberries, limes and peppers only). **Caveat:** USDA's movement coverage changed a lot 2023–2025 (import ports added to the national report), so "vs usual" compared different sets of shipments across years; that test wasn't fully fair. A fairer re-test would use only districts reported consistently for all 10 years (e.g. Salinas lettuce via El Centro, Idaho potatoes). Volumes are still collected nightly and shown on the site vs. **the same weeks last year** (comparable coverage).

**Weather (tested 2026-09-26, not used):** daily weather at 25 growing regions (Open-Meteo; `pipeline/weather.py`), turned into weekly freeze nights, heat days (≥35 °C), heavy-rain days (≥20 mm) and rainfall vs. normal, averaged over the regions in season for each commodity (this week and last week). Average miss 13.222% vs 13.229% without — noise. A more complex variant now has to beat the base model by ≥1% to be used. **Event-week test (2026-09-26, PR #15, closed):** flagged weeks with a freeze night, 2+ days ≥35 °C or 2+ days ≥20 mm rain in a region in season (this week or last). The current forecast was *more* accurate in those weeks than in others (e.g. 2 weeks ahead: 10.6% vs 12.9% miss), and weather inputs didn't improve them (10.6% either way). The flags were too common (~20% of weeks; heat and heavy rain are normal in Sinaloa, Imperial, Veracruz, Guatemala). If revisited: flag only weather **unusual for that region and week** (e.g. above its 95th percentile). Pausing weather work: three tests (volumes, weather, weather events) agree that shipping-point prices absorb supply shocks within days.

Honest read: produce prices are volatile (a typical 4-week move is ~20%), so the **range** is the most useful output. More model tuning now gives tiny gains; the next real improvement needs **new information** (weather, shipment volumes).

## Next improvements (each kept only if the walk-forward score improves)
- MXN/USD, diesel, holidays, FDA recalls. (Shipment volumes and simple weather: tested, didn't help on average; see above for targeted re-tests.)
- A public track record on the site (past forecasts vs. what happened).

**USDA notes, peso and government events (tested 2026-11-02, not used):** added one at a time to the live wholesale model, walk-forward 2021-2026 (average miss 13.37% and 69.4% of calls right without them). Short-supply notes, disruption mentions, reporters' tone notes, growing areas starting or finishing, and the peso: 13.37-13.47%, no gain (`scripts/backtest_wholesale_signals.py`). FDA recalls, Federal Register trade documents, and NOAA crop damage (an upper bound, since NOAA publishes months late): 13.36-13.38%, 69.3-69.4% right (`scripts/backtest_event_signals.py`). These records are frequent and mostly minor (a recall in 27% of item-weeks, crop damage in 39%), so as simple counts they don't separate the rare shock from the routine. USDA's bird flu site refused automated requests, so bird flu is untested. What did help is holding back calls when signals disagree (`forecast.held`).

## 2026-11-02: blended model (live)
Tested in `scripts/backtest_methods.py`, `backtest_methods2.py`, `backtest_hold_rule.py`. Walk-forward 2021-2026, with the per-item choice vs no change.

| | Old | New |
|---|---|---|
| Average miss, 1-4 weeks | 13.15% | 12.60% |
| Two-week miss | 11.99% | 11.50% |
| Calls right (5%+ moves, before the hold rule) | 72.2% | 77.3% |
| Average miss with only Monday-Wednesday known | 13.68% | 13.33% |

Better in every test year. The live model is a plain average of two forecasts: a per-item regression fit for absolute error (Huber) and gradient boosting on absolute error. New input: the latest day's price vs the week's average (`last_price` in prices_weekly.csv).

Why these: the score is absolute error, and the best forecast for absolute error is the median, not the mean (Gneiting 2011). Simple averages of forecasts are hard to beat (Timmermann 2006). Gradient boosting is the family that won M5 (Makridakis et al. 2022). A weekly average hides a move late in the week (Working 1960).

No better: median-based seasonals, weighting recent years, shrinking toward no change.

Limits: the Monday-Wednesday test still uses the full week's shipping-point move and USDA tone, so it flatters both models somewhat.

### Hold rule
A call is held as Unsettled when shipping points moved 10%+ against it over two weeks, or it is a rise after 8 weeks 10%+ below usual and USDA does not call the market firm. Picked on 2021-2023, checked on 2024-2026, against the old 5% rule on the new model: calls 3,531 -> 4,083, right 77.9% -> 77.5%, big swings called ahead 36.5% -> 41.5%, called the wrong way 4.6% -> 5.4%. Full replay (`scripts/value_stats.py`): 78.9% of 7,971 calls right, 43.5% of big moves called ahead, 5.0% wrong way (was 75.9% of 6,645, 35.4%, 4.7%).

## 2026-11-02: grocery outlook
Tested in `scripts/backtest_grocery_methods.py`, walk-forward 2022-2026. Live now: per-item regression shrunk toward the shared one, fit with Huber loss. Miss 9.48% -> 9.36%, calls right 77.3% -> 77.7%, better in every year. An average with gradient boosting reached 9.28% with no better calls, under the 1% bar over the simpler model, so it stays off. Absolute-error fit alone and shrinking toward no change: smaller gains.

## 2026-11-04: the price shown is a real quote
The site's big price was the week's average, a median across every growing area quoted. New York romaine read $50.50 when USDA had California at $60 and New Jersey at $41. Areas sit 10%+ apart on 19% of headline days since 2021, up to 93% for Chicago carrots (`scripts/audit_origin_mix.py`). Now each terminal series follows its main growing area, the one quoted most over the previous 28 days, chosen with no look-ahead, and the site shows that area's latest quote.

Walk-forward 2021-2026, `scripts/backtest_main_area.py`, headline series. On the main-area price: main-area model miss 12.08%, wrong way on big moves 5.3%; blended model 12.12%, 5.7%. Week-to-week noise is about the same either way.

Calls now run from the latest quote, since that is the number on the page. The published record fell with this stricter, truer measure (`scripts/value_stats.py`): 78.9% of 7,971 calls right -> 74.6% of 6,362; big moves called ahead 43.5% -> 34.7%; wrong way stays 5.0%; average move $4.94 -> $4.61 a case. The test assumes the whole week is known; the site also forecasts midweek.

Same day: USDA often quotes several areas every day, and the tie went to the lowest price (Chicago onions read California; Washington and Idaho ship the most). Ties now go to the most pounds shipped in the four full weeks before, from the movement reports (`export.load_shipments`). Areas the reports leave out read zero, so California lemons and carrots can lose a tie they might deserve. Record: 75.0% of 6,450 calls right, big moves called ahead 35.2%, wrong way 4.7%, average move $4.64 a case. `scripts/backtest_main_area.py` compares against whatever `prices_weekly.csv` holds, so its blend side only means the blend on an export from before 2026-11-04.

Same day, grapes and carrots: USDA's 18 and 19 lb grape containers are one series (`MERGE_PACKS`), and a current main pack beats a better-covered other pack. A tied area with no pounds wins if quoted the most over the past year, since the movement reports leave out California carrots. Only grapes changed headline; only grapes and carrots changed price. Record: 74.4% of 6,409 calls right, big moves called ahead 34.3%, wrong way 4.9%, average move $4.58 a case.

## 2026-11-05: wholesale meat

`pipeline/meat.py`, test `scripts/backtest_meat.py`. Two-week calls on 22 boxed and ground beef prices and 8 chicken prices: the blend above without shipping-point or USDA tone inputs, fitted separately for beef and chicken, the same 5% call line, and the same per-item choice against "no change". Each year is fitted only on earlier years.

| | Tested | Calls | Right | 10%+ swings called ahead | Average miss | No change |
|---|---|---|---|---|---|---|
| Beef | 2021-2026 | 559 | 82.5% | 23.8% | 4.01% | 4.33% |
| Chicken | 2025-2026 | 111 | 98.2% | 53.6% | 3.21% | 3.98% |

Read these with care:
- Calls are measured from the latest quote, as the site shows them. One noisy beef quote can snap back, which flatters the score: against the week's average, beef is 78.5%.
- Chicken history starts in August 2022, so only two years could be tested, and the 111 calls come from about 31 separate moves. Expect the live number to come down.
- Beef moves little, so the 5% line makes calls on only about 8% of weeks and most prices read steady. The edge over "no change" is small.

Tried and dropped: Huber regression alone (beef miss 4.18% vs the blend's 4.07% before the per-item choice), and the grocery rule of no call against an 8-week run (beef calls 83.6% -> 77.2% right).

These calls don't count in the produce record. Live calls are logged to `data/forecasts/meat_log.csv`; scoring them on the site is still to do.
