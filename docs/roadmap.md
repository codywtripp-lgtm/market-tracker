# Roadmap and tool choices

## Tools (decided 2026-09-26)

| Job | Tool | Why |
|---|---|---|
| Data pipeline | **Python** in GitHub Actions | Already built; free; runs daily without a computer. |
| Public website | **Static site on GitHub Pages**, charts with **Observable Plot** (or Observable Framework) reading `data/export/*.csv` | Free, mobile-first, rebuilt automatically by the daily job, no server. |
| Forecasting | **Python**: `statsmodels` (STL seasonal decomposition) → gradient boosting (`lightgbm`) with weather/trade features | One language for everything; runs free in Actions; biggest ecosystem for this kind of model. |
| Ad-hoc exploration | Tableau Public, R, Excel — any of them | The export CSVs work in all of them. Optional, not part of the automated system. |

Why not Tableau Public as the main output: it doesn't refresh automatically from a GitHub CSV (only from Google Sheets), and its dashboards are awkward on phones. Why not R: excellent for stats (`fable`, `ggplot2`), but a public R site needs a Shiny server (paid/limited) and it would split the project across two languages.

## Phases

1. **Data pipeline** — done: daily fetch, 10-year backfill, export with cheap/normal/expensive.
2. **Website** — "what's cheap this week" list + a trend chart per item, from `latest.csv` and `prices_weekly.csv`.
3. **Inflation adjustment** — deflate by BLS CPI (food at home / food away from home) so 2016 prices compare fairly with today.
4. **Forecasting v1: seasonality** — STL per series: trend + seasonal + residual; forecast = seasonal pattern + recent trend; show a range, not a single number. Backtest against held-out years.
5. **Forecasting v2: drivers** (each is a feature added to a gradient-boosting model, kept only if it improves backtests):
   - **Weather** at the growing origin (NOAA daily temps/precip, freeze and heat events) — joined via `origin` / shipping-point `district`.
   - **Supply/volume** — USDA shipments (movement report 3283, shipping-point trends 1662): a drop in loads usually leads price up.
   - **Trade** — tariffs and policy events (e.g. Mexican tomato suspension agreement, avocado import inspections) as dated event flags; import volumes from USDA/Census.
   - **Demand** — holidays (Cinco de Mayo & Super Bowl avocados, Thanksgiving), retail ad activity (`store_count` from report 3324).
   - **Costs** — diesel (EIA) and truck rates (USDA report 2375).
6. **B2B option** — compare a buyer's own purchase costs with market prices. Private data lives in a separate private repo/storage; this public repo only ever holds public USDA data.
