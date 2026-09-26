# Export files (for Tableau Public and the website)

Built by `python -m pipeline.export` after every daily fetch. All in `data/export/`.

| File | One row per | Use it for |
|---|---|---|
| `latest.csv` | headline series | **"What's cheap this week."** Latest weekly price vs. the seasonal norm, with `status` = cheap / normal / expensive. |
| `prices_daily_365.csv` | series × day, last 365 days | Recent trend charts. |
| `prices_weekly.csv` | series × week, full history | Seasonality, year-over-year, forecasting. |
| `series.csv` | headline series | What each series is (commodity, pack, size, market, units, coverage). |

Join the price files to `series.csv` on `series_id`.

## Headline series

The raw data has hundreds of pack/size/origin combinations. The export keeps the most useful:

- **Terminal** (NY, LA, Chicago): per commodity and market, the 2 pack+size combinations reported on the most days in the last year (at least 50% of days).
- **Shipping point**: per commodity, the 2 district+pack+size combinations reported most (at least 30% of days, because districts are seasonal).
- **Retail**: National region, conventional only; per commodity the 2 items with the most store ads.
- **Beef**: Choice and Select cutout, plus the 12 cuts with the most pounds traded.
- **Chicken**: domestic, the 8 items with the most volume.

A series is **commodity + variety + pack + size (+ color/type) + market**. Origin is *not* part of it, because origin rotates with the season (e.g. NY bell peppers from Florida, Georgia, Canada, New Jersey). The origins quoted each day are listed in `origins`.

Excluded from headline prices: rows marked Fair/Poor/Ordinary/Fine appearance or condition, holdovers, decay or damage. Those are off-grade or premium lots (e.g. $5 fair-condition strawberry flats next to $37 fine ones). They're still in `data/raw/`.

## Prices

- `price` = the day's median representative price across quotes (see [normalization.md](normalization.md)), in `price_unit` (usually $/package).
- `compare_price` = the same in **$/lb or $/each** (`compare_unit`) when every day of the series can be converted; otherwise the package price. Use this for charts and comparisons.

## Cheap vs. expensive (`latest.csv`)

- This week's value = average `compare_price` for the latest week (Mon–Sun).
- **Seasonal norm** = median of that series' weekly values in the **same week of the year ±2 weeks, in all prior years**.
- `percentile` = where this week sits among those past values (ties count half).
- `status`: **cheap** ≤ 25th percentile, **expensive** ≥ 75th, otherwise **normal**. Needs at least 3 prior years; else "not enough history".
- Also: `pct_vs_norm`, `pct_vs_4_weeks_ago`, `pct_vs_last_year`.

Not yet adjusted for inflation; a later step can deflate by CPI so a 2016 price compares fairly with today.
