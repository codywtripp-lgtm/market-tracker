# Weekly buyer's brief

`pipeline/brief.py` runs in the Saturday nightly job (or any manual run of "Daily USDA fetch") and
writes `data/briefs/<monday>.html`. `scripts/build_site.py` publishes it at `/brief/` (latest),
`/brief/<monday>/` (archive) and `/brief/feed.xml` (RSS with the full text, for email services).

## What's in it
- **What matters this week**: up to two New York items with the largest expected 2-week move (≥5%),
  then the most unusual prices (≥15% from usual).
- **Early warnings**: current alerts (`alerts.json`, rules in `docs/alerts.md`).
- **New York table**: every produce item, using the best-covered terminal series (same automatic rule as the site).
- **LA / Chicago**: only items whose call isn't "Steady".
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
