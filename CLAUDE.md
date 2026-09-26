# market-tracker

Tracks daily USDA produce prices (later meat/other commodities) to show what's cheap or expensive vs. historical norms. End state: free public website and/or Tableau Public dashboard; later seasonal + weather-driven forecasting.

## Owner
- Background in data viz/reporting; former produce buyer at Baldor (NYC). Knows the industry (packs, counts, terminal markets); new to GitHub and Claude Code.
- Works from phone. Keep updates short, lead with what matters, spell out any action needed (e.g., "merge PR #N").
- Work in small reviewable steps; flag assumptions about USDA formats rather than guessing.

## Phases
1. Data pipeline (current): explore → shortlist → schema → storage → daily GitHub Action → backfill → flat CSV export.
2. Later: static site (GitHub Pages / Cloudflare Pages), seasonal baselines (STL), NOAA weather by origin region, possible B2B buyer-cost comparison.

## Priority (owner, 2026-09-26)
**Primary user = food wholesale buyer.** Forecast quality comes first; the household/consumer view is nice-to-have, later.

## Hard rules
- **No private customer data in this repo, ever.** It is public. Keep architecture ready to separate public market data from any private data (separate repo/storage).
- Never commit the USDA API key. It lives in GitHub Actions secret `MARS_API_KEY` (and local env var of the same name).

## Target schema (per price row)
commodity, variety, pack_size (raw), count_size, unit_price (as reported), normalized_price (per lb or per unit; rules documented), market, market_type (terminal / shipping point / retail), origin, report_id (USDA slug), report_date, fetched_at.
Also keep: low/high/mostly prices, appearance/condition/quality (needed for dedup), properties (color/ripeness).

## Status / decisions
- 2026-09-25: Exploration done from the MMN website; see `docs/usda-exploration.md` for report IDs, formats and gotchas.
- 2026-09-26: Owner decisions:
  - Commodities: avocados, tomatoes, bell peppers, onions, lettuce (iceberg + romaine), strawberries. Beef and poultry wanted too (high-volume at Baldor) — sources TBD (boxed beef is on the LMR datamart `mpr.datamart.ams.usda.gov`, not MARS; chicken via MARS weekly/retail reports).
  - Terminal markets: New York (critical), Los Angeles, Chicago.
  - Backfill depth: 10 years.
  - `MARS_API_KEY` secret added to the GitHub repo. `scripts/probe_api.py` + `.github/workflows/probe.yml` is a throwaway exploration job (manual trigger) that verifies the API and measures reporting consistency.
- 2026-09-26: Owner wants the top 10–20 NY-volume items. Added potatoes, lemons, limes, cucumbers, broccoli, celery, carrots, bananas, blueberries, grapes (18 produce commodities total). Volume source = national movement report 3283 (import-biased; see shortlist doc) + judgment.
- 2026-09-26: Pipeline built (`pipeline/`): fetch → normalize → monthly CSV upsert. Workflows: `daily.yml` (cron), `backfill.yml` (manual, year range), `tests.yml` (pytest + real smoke fetch on PRs). No local Python on the owner's machine — tests run in GitHub Actions.
- 2026-09-26: Export built (`pipeline/export.py`, rules in `docs/export.md`): headline series auto-selected by coverage, `latest.csv` cheap/normal/expensive vs. same-week-of-year norm (needs 3+ prior years). PRs #1 → #2 → #3 must be merged by the owner (merging is blocked for Claude), then run the Backfill workflow for 2016–2026.
- 2026-09-26: Website live at https://codywtripp-lgtm.github.io/market-tracker/ (GitHub Pages, source = GitHub Actions, `pages.yml`). Owner's product vision recorded in `docs/roadmap.md`: **single-page** market report (owner rejected separate commodity pages — UX first): left filter rail (bottom sheet on phone) to add/remove/isolate commodities, backtested alerts at top, one-line "what's going on" per commodity, one shared chart (% vs usual when several selected; case price + usual range + forecast when one isolated), cheap/expensive list. Alerts on site and as GitHub issues. **Show prices per case/package (trade units), not per lb** — owner: nobody in the trade prices by weight for count packs.
- 2026-09-26: Owner: headline series per commodity = whichever is most consistently reported with real volume (keep automatic selection by coverage; no hand-picked packs).
- 2026-09-26: Backfill complete (2016-01 → 2026-09, every month; chicken from 2022-08 when USDA started it). Repo 89 MB.
- 2026-09-26: Alerts built (PR #7): `pipeline/alerts.py`, rules `data/signals/rules.csv` from `scripts/backtest_signals.py`, docs `docs/alerts.md`. Bar: ≥15 cases, ≥65% hit, ≥1.5× base rate → 67 qualifying combos. Signals: shipping point leads (terminal not yet moved), USDA tone. Round tomatoes/cucumbers/NY bell peppers don't qualify for sp_lead (multi-origin). **Alerts are website-only** (owner: no phone/GitHub/email notifications; the GitHub-issue step was removed). Next: forecasting (week-level ranges), household view, BLS retail layer.
- 2026-09-26: Forecast v1 (PR #10, `pipeline/forecast.py`, `docs/forecast.md`): 1–4 week terminal forecasts, pooled OLS on log change (seasonal, gap vs usual, momentum, shipping-point change, USDA tone), walk-forward 2021–2026. Beats no-change at all horizons (4w: 18.3% vs 19.9% MAE); 80% ranges cover 80.3%. Shared pandas helpers in `pipeline/signals.py`. Next model improvements listed in docs/forecast.md.
- 2026-09-26: Forecast v2 (PR #11): per commodity×market ridge-to-pooled regression + per-item choice vs "no change" (nested, honest). 4w MAE 17.9% vs no-change 19.9%; coverage 80.1%. GBM, sp_prev, other shrinkage strengths tried and dropped. Next gains need new data: weather (NOAA), shipment volumes (3283/1662).
- 2026-09-26: Shipment volumes added (PR #12): movement reports → `data/raw/movement/` (backfilled 2016–2026), weekly totals + "vs usual" in `pipeline/volumes.py` → `data/export/supply.csv`, shown on site. Tested as forecast input: **no improvement** (off). Gotchas: split entries summed; late additions (asw) credited to their date; Mexico/Miami moved to national report ~2024.
- 2026-09-26: Weather (PR #13): Open-Meteo daily at 25 growing regions → `data/raw/weather/` (nightly), commodity↔region↔season map in `pipeline/weather.py`. Open-Meteo is free for NON-commercial use only (paid plan or NOAA if this goes commercial). Tested in forecast: no gain (13.222 vs 13.229). Model switch now needs ≥1% relative gain (MIN_GAIN). Ideas left: event-window weather test, consistent-district volume retest, MXN/USD, holidays, FDA recalls, public forecast track record, household view.
- (older) Next: after backfill, backtest early-warning signals (shipping point → terminal lead, USDA tone text, shipment volume), then build alerts + front page.
- 2026-09-26: PRs #1–#3 merged. Backfill started (2021–2026, then 2016–2020).
- 2026-09-26: Tools: owner open to anything free (Tableau was just familiarity). Decided: Python for pipeline + forecasting, static GitHub Pages site with Observable Plot for the public site; Tableau/R optional for exploration. End goal is price prediction (seasonality → weather, supply, tariffs, demand). See `docs/roadmap.md`.
- 2026-09-26: API verified. Proposed shortlist + storage (slim monthly-partitioned CSV) in `docs/shortlist-and-storage.md` — awaiting owner approval before building parsers.

## API gotchas (verified)
- **Never filter commodity in `q=`** — commas in names ("Peppers, Bell Type") are parsed as OR. Filter client-side.
- Beef (LMR datamart 2453) prices are $/cwt, numbers are strings with commas. Chicken (3646, section `Report Detail`) is cents/lb, weekly.
- Market-specific labels for the same pack (strawberry flat = "extra large" in NY, "medium" in CHI; iceberg "24s film wrapped" vs "film lined 24s"). Map series per market.

## Data quirks (summary — details in docs/usda-exploration.md)
- Terminal, shipping-point and retail reports use different column names (`variety`/`var`, `package`/`pkg`, ...).
- Shipping point: `origin` blank, use `district`. Office name ≠ contents (Mexico avocados are in Fresno report 2390; Salinas lettuce in Phoenix report 2403).
- Near-duplicate rows differ only by appearance/condition/quality → include in dedup key.
- `properties` holds pepper color / tomato ripeness / onion type.
- Seasonal start/stop and rotating origins are normal; not failures.
