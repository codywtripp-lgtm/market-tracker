# Daily buyer's brief

`pipeline/brief.py` runs at the end of every nightly job (Mon–Sat, 23:30 UTC, after the terminal
reports) and writes `data/briefs/<market date>.html` (owner asked for daily, 2026-10-28). `scripts/build_site.py` publishes it at `/brief/` (latest),
`/brief/<date>/` (archive) and `/brief/feed.xml` (RSS with the full text).

## Design
Built for buyers who aren't data people: big type, one idea per block, and every color paired with an icon and
a word (✓ / ✕ / !, ▲ / ▼, CHEAP / NORMAL / HIGH). Up = bad for the buyer (red), down = good (green).
Per item: price, status pill, a meter placing today's price between the cheapest and priciest past years
(same weeks; cut-offs match the 25th/75th-percentile status), a 12-week sparkline with the likely range shaded,
and the 2-week outlook. Inline SVG charts; every number is also in the text.

## What's in it
- **At a glance (NY)**: four tiles: firming, softening, high for the season, good value.
- **Today at the terminals**: headline items whose latest quote moved ≥5% from the previous one (with USDA's market tone).
- **Early warnings**: current alerts (`alerts.json`, rules in `docs/alerts.md`).
- **New York, item by item**: cards grouped by what to do, best-covered terminal series per item.
- **LA / Chicago**: compact rows, only items that aren't steady.
- **Supply**: shipments ≥15% off last year (`supply.csv`).
- **Track record**: live forecast range hits and alert results (`track_record.json`).

## Calls (trade terms)
Produce is bought for daily need, so the brief never says "wait" or "buy now". It says which way the market is
going and what a buyer can actually change. Owner feedback 2026-10-28.

Direction = forecast midpoint for 2 weeks after the last full week vs. last week's price: **firming** ≥ +5%,
**softening** ≤ −5%, else **steady** (also steady where "no change" forecasts best, `forecast_report_card.csv`).

| | What the brief says to do |
|---|---|
| Firming, item that stores (onions, potatoes, carrots, celery, lemons, limes) | It stores: buy a few days deeper; lock price; update quotes |
| Firming, perishable | Buy to need, but lock price with the supplier and update quotes |
| Softening | Keep inventory tight, stay on the open market, don't lock at today's level |
| Steady, high for season | No relief in sight: check other sizes/packs, price quotes to cover it |
| Steady, low for season | Good value: feature on specials and promotions |

"Stores" = the low end of USDA Agriculture Handbook 66 storage life is 4+ weeks (`STORAGE_LIFE` in `pipeline/brief.py`).
Grapes (2–8 weeks), avocados (2–4), lettuce and peppers (2–3) fall short, so they stay "buy to need".
Each card also shows the case price for every count the market quotes in the same pack (e.g. 48s / 60s avocados).

## Not yet
No newsletter (owner decision 2026-10-28): the website and search are the channel. Commodity pages for search: `pipeline/pages.py`.

## Pitch page (/why/)
`scripts/value_stats.py` replays the brief's 2-week calls walk-forward on 2021–2026 (same model and per-item
model-vs-no-change choice as the live forecast) and writes `data/export/value.json`; `build_site.py` turns it into
/why/. Re-run it by hand after model changes (about a minute). Result 2026-10-28: 71% of 7,917 calls right on
direction, 85% when the move was 10%+, $4.23/case average move in the called direction; alerts 75% vs. 33% base.
