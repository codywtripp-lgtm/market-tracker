# market-tracker

Tracks daily USDA produce prices (later meat/other commodities) to show what's cheap or expensive vs. historical norms. End state: free public website and/or Tableau Public dashboard; later seasonal + weather-driven forecasting.

## Owner
- Background in data viz/reporting; former produce buyer at Baldor (NYC). Knows the industry (packs, counts, terminal markets); new to GitHub and Claude Code.
- Works from phone. Keep updates short, lead with what matters, spell out any action needed (e.g., "merge PR #N").
- Work in small reviewable steps; flag assumptions about USDA formats rather than guessing.

## Phases
1. Data pipeline (current): explore → shortlist → schema → storage → daily GitHub Action → backfill → flat CSV export.
2. Later: static site (GitHub Pages / Cloudflare Pages), seasonal baselines (STL), NOAA weather by origin region, possible B2B buyer-cost comparison.

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
