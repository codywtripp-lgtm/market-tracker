# market-tracker

Tracks USDA wholesale and retail prices for high-volume produce, beef and chicken, so you can see what's cheap or expensive right now compared with its usual price.

## What's in here

| Folder | What it is |
|---|---|
| `data/raw/` | Every price row we've collected, one CSV file per month. Open any file on GitHub to see it as a table. |
| `pipeline/` | The Python code that downloads and cleans USDA data. |
| `docs/` | How the data works: which USDA reports we use, quirks, and how prices are converted to $/lb or $/each. |
| `.github/workflows/` | The automatic jobs GitHub runs for us (see below). |

## Where the data comes from

- **Terminal markets** (wholesale, daily): New York (Hunts Point), Los Angeles, Chicago.
- **Shipping point** (FOB at the growing region, daily): e.g. Salinas, Mexico crossings through Texas, Idaho.
- **Retail** (weekly): advertised grocery store prices by region.
- **Beef** (daily boxed beef cutout and cuts) and **chicken** (weekly national parts prices).

All from USDA Agricultural Marketing Service, Market News. Details in [docs/usda-exploration.md](docs/usda-exploration.md).

Commodities: avocados, strawberries, iceberg, romaine, tomatoes (round and Roma), bell peppers, dry onions, potatoes, lemons, limes, cucumbers, broccoli, celery, carrots, bananas, blueberries, grapes, plus beef and chicken. To add one, edit `pipeline/config.py`.

## The automatic jobs

You can see these in the repo's **Actions** tab.

- **Daily USDA fetch**: runs every evening (Mon–Sat). It re-downloads the last 10 days (to catch late reports and USDA corrections) and commits any new or changed rows. If one USDA report fails, the others still save; the failure is listed in the run summary and retried the next day.
- **Backfill history**: run by hand to load past years. In **Actions → Backfill history → Run workflow**, pick the years. It saves after each year.
- **Tests**: runs on every pull request. It checks the code and does a small real download from USDA so we can see it works before merging.

## The USDA API key

USDA requires a free personal key. It's stored as a GitHub secret named `MARS_API_KEY` (**Settings → Secrets and variables → Actions**). Never paste it into a file in this repo — the repo is public.

## Privacy

This repo is public and only holds public USDA data. Any private data (for example a business's own purchase costs) must live somewhere else.
