# Roadmap and tool choices

## Tools (decided 2026-09-26)

| Job | Tool | Why |
|---|---|---|
| Data pipeline | **Python** in GitHub Actions | Already built; free; runs daily without a computer. |
| Public website | **Static site on GitHub Pages**, charts with **Observable Plot** (or Observable Framework) reading `data/export/*.csv` | Free, mobile-first, rebuilt automatically by the daily job, no server. |
| Forecasting | **Python**: `statsmodels` (STL seasonal decomposition) → gradient boosting (`lightgbm`) with weather/trade features | One language for everything; runs free in Actions; biggest ecosystem for this kind of model. |
| Ad-hoc exploration | Tableau Public, R, Excel — any of them | The export CSVs work in all of them. Optional, not part of the automated system. |

Why not Tableau Public as the main output: it doesn't refresh automatically from a GitHub CSV (only from Google Sheets), and its dashboards are awkward on phones. Why not R: excellent for stats (`fable`, `ggplot2`), but a public R site needs a Shiny server (paid/limited) and it would split the project across two languages.

## Product vision (owner, 2026-09-26)

**One page. No clicking through per-commodity pages** (owner, 2026-09-26: "nobody is going to have the patience to click through separate pages — think about the user experience first; this has to be something the user loves interacting with").

Layout (desktop: filter rail on the left; phone: the same filters in a bottom sheet behind a "Filters" button):

- **Filter rail**: commodities (checkboxes, with "only this" to isolate one), market (NY / LA / CHI / shipping point / retail), time range (3 mo / 1 yr / 5 yr / all), view (price vs. "% vs usual"). Selections live in the URL so a view can be shared or bookmarked.
- **Main column, top to bottom**:
  1. **Alerts** — only moves that clear a high bar ("Romaine: Salinas FOB +25% in 5 days; NY usually follows within ~a week"), each with its reason and how often that signal has been right historically. Tapping an alert isolates that commodity in the chart.
  2. **What's going on** — one short line per selected commodity: price vs. normal, direction, what USDA reporters say, current origins, what to expect.
  3. **The chart** — every selected commodity together. With several selected it plots **% vs usual for this time of year** (one shared scale, so avocados and onions are comparable); with one isolated it plots the actual case price with the usual range and the **forecast band**.
  4. **Cheap / expensive list** — tapping a row adds or isolates it in the chart.
- **Alert delivery**: on the page + a GitHub issue per alert batch (push notification to the owner) now; public email/SMS signup later (needs a small free email service).

Principles:
- **Prices in the trade's own units** (per case/package with pack and count, $/cwt for beef). Buyers think "$33 for 48s", not per lb; per-lb is secondary.
- **Alerts must be backtested**: a signal ships only if it would have called moves well over the 10-year history. False alarms are worse than none.
- **Blurbs start as data-driven templates** (always accurate, free). LLM-written blurbs (Claude API, ~a few $/month) later, grounded in the same numbers.

Early-warning signals to test first (all from data we already collect):
1. Shipping-point price moves leading terminal prices (measure the lag per commodity).
2. USDA market tone text ("higher", "supplies light", "demand exceeds") as a direction signal.
3. Shipment volume drops (movement report 3283, trends 1662) leading price rises.
4. Later: weather at origin, tariffs/trade events, holidays.

### Forecasting approach (owner: "our other big differentiator")
- **Owner: forecasts must be week-level.** Annual averages are useless (huge within-year variance). Priorities: (1) next 1–4 weeks, week by week, as ranges; (2) turning points / spike risk ("chance of +30% in the next month"); (3) the seasonal calendar — which weeks are usually cheapest/dearest and why (crop transitions).
- **Horizons**: 1–2 weeks (strong: shipping point, loads, USDA tone, recent weather already in the pipeline); 1–3 months (fair: seasonality, crop transitions, NASS acreage/progress, seasonal outlooks); longer = seasonal range only.
- **Driver candidates (free data)**: NOAA / Mexico SMN weather at origins; USDA shipments & border crossings (3283, 1662); NASS acreage/crop progress; shipping-point prices & USDA tone; trade/tariff events (dated list); MXN/USD (FRED); diesel (EIA) & truck rates (USDA 2375); holiday/demand calendar; FDA recalls (e.g. romaine E. coli).
- **Method**: baseline = seasonal pattern + recent trend; add one driver at a time; keep it only if it improves **out-of-sample** backtests.
- **Trust**: forecasts are ranges, and the site publishes its own **track record** (past forecasts vs. what happened).

### Two audiences, one page (owner, 2026-09-26)
A switch at the top — **Buying for: Business | Household** — remembered per visitor.
- **Business**: wholesale case prices (current design).
- **Household**: prices in the unit people buy (one 1-lb clamshell, one avocado, one head, per lb). Sources: weekly grocery ad prices (report 3324), BLS monthly average retail prices, and wholesale translated per unit ("stores pay ~$1.40 per clamshell; typical ad $2.99"). Alerts in shopper language ("expect store specials in 1–2 weeks") — only after backtesting how long wholesale moves take to reach retail ads.
- Per-unit conversion reuses `normalized_price` (count-based "per each" and pack-based "per lb" = per 1-lb clamshell).

### Ideas from Macrotrends (2026-09-26)
Macrotrends' food pages (e.g. /3710/us-strawberry-prices) chart a single national monthly *retail* average (likely BLS Average Price data) over decades. Different product from ours (wholesale, daily, pack-level, forward-looking), but worth borrowing:
1. **BLS average retail prices** (monthly, back to the 1980s, same free BLS API as CPI) as a "grocery shelf price" layer — long-run context and a view of wholesale → retail pass-through.
2. **Search-findable landing page per commodity** (e.g. `/strawberries/`) that opens the one-page dashboard pre-filtered. Keeps the single-page UX while getting search traffic.
3. **Yearly summary table** (average price per year, % change) under the chart.
4. Keep it that simple: plain sentences, one clear chart.

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
