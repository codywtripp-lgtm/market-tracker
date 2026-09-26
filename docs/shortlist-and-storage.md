# Proposed shortlist and storage (Phase 1, steps 2 and 4)

Status: **proposal, pending owner approval.** Evidence is in `usda-exploration.md`.

## Principle

Store **every row for our commodities** from the chosen reports (all packs and sizes), but build the headline "cheap vs. expensive" series only from the shortlist below. A series is keyed on **commodity + variety + pack + size + market** with origin kept as an attribute, because origin rotates with the season.

## Shortlist — terminal markets (NY, LA, Chicago; daily)

| Commodity | Series | Notes |
|---|---|---|
| Avocados | Hass, 2-layer carton, 48s and 60s | ~240+ days/yr everywhere. Mexico dominant; LA also California. |
| Strawberries | 8×1-lb clamshell flats | Size label differs by market; map per market. |
| Iceberg lettuce | 24s carton (film wrapped / film lined) | Pack wording differs by market. |
| Romaine | 24s carton; hearts 12×3 | Both very consistent. |
| Tomatoes | Roma 25 lb loose XL; round: LA/CHI vine-ripe 2-layer 4x5s, NY mature green 25 lb 5x6 | NY Romas/rounds less consistent (more size grades). |
| Bell peppers | Green, 1 1/9 bushel carton, XL (LA) / jumbo (CHI) / large+jumbo (NY) | NY ~168 days; consider colored 11-lb cartons for NY too. |
| Onions | Yellow 50 lb jumbo (all types combined); white 50 lb jumbo | |

## Shortlist — shipping point (FOB, daily)

| Commodity | Report | District(s) |
|---|---|---|
| Avocados (Hass 48s, 60s) | 2390 | Mexico crossings through Texas; South District California |
| Strawberries | 2390 | Salinas-Watsonville, Santa Maria, Oxnard (seasonal) |
| Iceberg, romaine | 2403 | Salinas-Watsonville, Santa Maria, South & Central CA (winter desert districts TBC) |
| Tomatoes (round, Roma) | 2403, 2400 | Mexico via Texas / Otay Mesa, Central CA, TN/VA, FL (seasonal) |
| Green bells | 2403, 2410, 2387 | San Joaquin Valley, Mexico via Texas, South Georgia, Michigan (seasonal) |
| Onions, dry | 2393 | Idaho & Malheur Co. OR, Columbia Basin WA |

## Shortlist — retail (weekly, National region)
Report 3324: Hass each, strawberries 1 lb, iceberg each, romaine each, tomatoes, green bell each, yellow onions per lb / 3 lb bag. Exact item labels to confirm when the parser is built.

## Shortlist — protein
- **Beef** (daily, LM_XB403 / 2453, $/cwt): Choice and Select cutout; Choice cuts — ribeye 112A, strip loin 180, tenderloin 189A, top sirloin 184, brisket 120, chuck roll 116A; ground beef 81/19.
- **Chicken** (weekly, 3646, cents/lb): Breast B/S, wings whole, tenders, leg quarters, whole birds. Plus retail chicken/beef ads (2756, 3228).

## Storage recommendation: slim CSV, partitioned by source and month

```
data/raw/terminal/2026/2026-09.csv
data/raw/shipping_point/2026/2026-09.csv
data/raw/retail/2026/2026-09.csv
data/raw/beef/2026/2026-09.csv
data/raw/chicken/2026/2026-09.csv
data/export/prices.csv          # flat file for Tableau / website
```

Why:
- **Size is fine.** Our commodities only: ~115,000 rows/year across all sources → ~1.2M rows for 10 years. At ~200 bytes/row that's ~230 MB of raw text, which Git compresses to roughly 30–50 MB. Well under GitHub's 1 GB guidance. (Estimate; will measure after backfill.)
- **Git-friendly.** Daily runs only append to the current month's file, so each commit is a small diff. SQLite or Parquet are binary: every daily change stores a whole new copy of the file in history, which bloats the repo over time.
- **Readable everywhere.** Tableau Public, a static site, Excel and Python all read CSV directly. You can open a file on GitHub from your phone.
- **Dedup is simple.** Each row gets a key (report + date + all descriptive fields incl. appearance/condition/quality); re-fetching a day rewrites only that day's rows.
- Drop narrative/comment columns from stored rows (they're ~80% of the raw size); keep `market_tone_comments` only.

If the repo ever grows too big, the same files can move to Parquet in a GitHub Release or Cloudflare R2 without changing the pipeline design.
