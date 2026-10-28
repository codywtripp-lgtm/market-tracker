# Daily buyer's brief

`pipeline/brief.py` runs at the end of every nightly job (Mon–Sat, 23:30 UTC, after the terminal
reports) and writes `data/briefs/<market date>.html` (owner asked for daily, 2026-10-28). `scripts/build_site.py` publishes it at `/brief/` (latest),
`/brief/<monday>/` (archive) and `/brief/feed.xml` (RSS with the full text, for email services).

## Design
Built for buyers who aren't data people: big type, one idea per block, and every color paired with an icon and
a word (✓ / ✕ / !, ▲ / ▼, CHEAP / NORMAL / HIGH). Up = bad for the buyer (red), down = good (green).
Per item: price, status pill, a meter placing today's price between the cheapest and priciest past years
(same weeks; cut-offs match the 25th/75th-percentile status), a 12-week sparkline with the likely range shaded,
and the 2-week outlook. Inline SVG renders on the site; email clients that block SVG still get every number as text.

## What's in it
- **At a glance (NY)**: three tiles: good time to buy, wait if you can, early warnings.
- **Today at the terminals**: headline items whose latest quote moved ≥5% from the previous one (with USDA's market tone).
- **Early warnings**: current alerts (`alerts.json`, rules in `docs/alerts.md`).
- **New York, item by item**: cards grouped by what to do, best-covered terminal series per item.
- **LA / Chicago**: compact rows, only items that aren't steady.
- **Supply**: shipments ≥15% off last year (`supply.csv`).
- **Track record**: live forecast range hits and alert results (`track_record.json`).

## Calls
"Change" = forecast midpoint for 2 weeks after the last full week, vs. last week's price.
Items where "no change" forecasts best (`forecast_report_card.csv`, `uses = no change`) count as steady.

| Change | Cheap | Normal | Expensive |
|---|---|---|---|
| ≥ +5% | Buy ahead | Book ahead if you can | Book ahead if you can |
| ≥ −5% | Hold off where you can | Hold off where you can | Buy as needed |
| smaller / steady | Good value, holding steady | Steady | High, no relief expected yet |

## Not yet
Email delivery needs a newsletter account (owner action). Paid tier only after there are readers.

## Pitch page (/why/)
`scripts/value_stats.py` replays the brief's 2-week calls walk-forward on 2021–2026 (same model and per-item
model-vs-no-change choice as the live forecast) and writes `data/export/value.json`; `build_site.py` turns it into
/why/. Re-run it by hand after model changes (about a minute). Result 2026-10-28: 71% of 7,917 calls right on
direction, 85% when the move was 10%+, $4.23/case average move in the called direction; alerts 75% vs. 33% base.
