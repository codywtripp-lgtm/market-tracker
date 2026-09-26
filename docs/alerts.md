# Price alerts

Alerts warn that a terminal-market price (NY, LA, Chicago) is likely to move soon. They're **only issued where the signal has a strong track record over the last 10 years** for that exact commodity, market and direction.

## Signals

| Signal | Fires when | Predicts |
|---|---|---|
| **Shipping point leads** (`sp_lead`) | The commodity's shipping-point price moved ≥10% (last 7 days vs. the 7 before) **and the terminal market hasn't moved 3% the same way yet** | Terminal moves ≥5% the same way within ~2 weeks |
| **USDA reporters' call** (`usda_tone`) | USDA's market comments at that terminal over the last 7 days say "higher/firmer/stronger" (or "lower/weaker") | Terminal moves ≥5% that way next week |

The shipping-point price index combines every standard-grade pack and size quoted at shipping points for that commodity (average week-over-week change). Off-grade and premium lots ("fair condition", "fine appearance", holdovers) are excluded.

## The bar an alert must clear

A signal/commodity/market/direction combination can alert only if, over the backtest (2016–2026):
- it fired at least **15** times,
- it was right at least **65%** of the time, and
- it was right at least **1.5×** as often as the base rate (how often that price moves 5% anyway).

Every alert quotes its record, e.g. *"New York followed 26 of the last 30 times (normally 32%)."*

As of the first backtest, qualifying NY examples: Roma tomatoes (both directions), celery, strawberries, romaine (up), broccoli, limes, iceberg. **Round tomatoes, cucumbers and bell peppers don't qualify** — NY sources them from many regions at once, so no single shipping point leads.

## Where alerts appear
- Top of the website.
- A GitHub issue titled "Price alerts YYYY-MM-DD" tagging the owner (GitHub sends a notification), only for **new** alerts. One alert per signal/item/market/direction per week, so a running signal isn't re-sent every day.
- `data/alerts/log.csv` keeps every alert ever issued. This becomes the public track record (did it come true?).

## Files
- Rules (track records): `data/signals/rules.csv` — produced by `scripts/backtest_signals.py` (Actions → "Backtest signals"). Re-run the backtest every few months and review before replacing the file.
- Code: `pipeline/alerts.py`; tests: `tests/test_alerts.py`.
