# Daily buyer's brief

`pipeline/brief.py` runs at the end of every nightly job (Mon–Sat, 23:30 UTC, after the terminal
reports) and writes `data/briefs/<market date>.html` (owner asked for daily, 2026-10-28). `scripts/build_site.py` publishes it at `/brief/` (latest),
`/brief/<date>/` (archive) and `/brief/feed.xml` (RSS with the full text).

## Design
Set like a trade market sheet, not an app (owner 2026-10-28: it must not look AI-made). Masthead with a double
rule, Source Serif 4 headings, Public Sans text with tabular figures, one paper colour, ruled sections and tables.
No rounded cards, pills, tinted tiles, icon circles, gradients or hero stat rows. Red = costs the buyer more,
green = costs less; always with an arrow and a word. Shared page frame (masthead, fonts, footer) is `page()` in
`scripts/build_site.py`; styles in `site/style.css`.
Per item: case price, season status word, a hairline meter placing today's price between the cheapest and highest
past years (same weeks; cut-offs match the 25th/75th-percentile status), a 12-week sparkline with the likely range
shaded, and the 2-week outlook. Every number is also in the text.

## What's in it
- **Opening sentence**: what's firming / softening / high at Hunts Point, written like a market reporter.
- **New York summary**: four ruled lines: firming, softening, high for the season, good value.
- **Today at the terminals**: headline items whose latest quote moved ≥5% from the previous one (with USDA's market tone).
- **Early warnings**: current alerts (`alerts.json`, rules in `docs/alerts.md`).
- **New York, item by item**: ruled entries grouped by direction, main trade pack per item.
- **LA / Chicago**: a table of items that are moving or out of the ordinary for the season.
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
Each entry also shows the case price for every count the market quotes in the same pack (e.g. 48s / 60s avocados).

## Not yet
No newsletter (owner decision 2026-10-28): the website and search are the channel. Commodity pages for search: `pipeline/pages.py`.

## Pitch page (/why/)
`scripts/value_stats.py` replays the brief's 2-week calls walk-forward on 2021–2026 (same model and per-item
model-vs-no-change choice as the live forecast) and writes `data/export/value.json`; `build_site.py` turns it into
/why/. Re-run it by hand after model changes (about a minute). Result 2026-10-28 (main trade packs): 73% of 8,698 calls right on
direction, 86% when the move was 10%+, $4.47/case average move in the called direction; alerts 75% vs. 33% base.
