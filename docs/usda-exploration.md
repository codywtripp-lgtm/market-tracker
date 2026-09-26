# USDA data exploration (Phase 1, step 1)

Explored 2026-09-25 via the MyMarketNews (MMN) public website. **Not yet verified against the MARS API itself** — the API requires a personal key we don't have yet. Field names below come from MMN's public data viewer, which is backed by the same API; expect them to match but confirm once we have a key.

## Access

- API: `https://marsapi.ams.usda.gov/services/v1.2/reports/{slug_id}[/{section}]?q=...`
- Auth: HTTP basic auth, API key as username, empty password. Free key via MMN account (USDA eAuth registration). Without a key: HTTP 403.
- Row cap: 100,000 rows per request (registered). No stated rate limit. Backfill must be chunked by date range.
- Filter syntax: `q=report_begin_date=MM/DD/YYYY:MM/DD/YYYY;commodity=X`. Dates are `MM/DD/YYYY`. Parameters are case-sensitive.
- Useful params: `lastReports=N`, `allSections=true`, `correctionsOnly=true`.
- Sections for price reports: `Report Header`, `Report Details` (the price rows). Retail also has `Report by Region`.
- The MMN *website* (mymarketnews.ams.usda.gov) timed out for non-browser clients from this machine; only use `marsapi` from code.

## Reports that exist for our 5 commodities

### Terminal markets (daily, weekdays, history back to 1998)
Each city has 4 reports: Fruit (`_FV010`), Vegetables (`_FV020`), Onions & Potatoes (`_FV030`), Nuts (`_FV040`).

| City | Fruit (avocados) | Vegetables (tomatoes, peppers, lettuce) | Onions |
|---|---|---|---|
| New York (Bronx / Hunts Point) | 2314 | 2315 | 2316 |
| Los Angeles | 2306 | 2307 | 2308 |
| Chicago | 2290 | 2291 | 2292 |
| Philadelphia | 2318 | 2319 | 2320 |
| Boston | 2285 | 2286 | 2287 |
| Atlanta | 2277 | 2278 | 2279 |
| Baltimore | 2281 | 2282 | 2283 |
| Detroit | 2302 | 2303 | 2304 |
| Miami | 2310 | 2311 | 2312 |
| Columbia SC | 2294 | 2295 | 2296 |
| Asheville NC | 3913 | 3914 | 3915 |

**Discontinued** (history only): San Francisco, St. Louis, Dallas, all international terminals (Montreal, Toronto, UK, EU, Mexico, Tokyo).

### Shipping point (daily FOB prices)
Organized by **reporting office, not by growing region** — the office name often doesn't match what's inside:

| Commodity | Where it was found (2026-09-24) | Slug |
|---|---|---|
| Avocados | Mexico crossings through Texas; South District California | 2390 (Fresno SP Fruit) |
| Lettuce (iceberg, romaine, leaf) | Salinas-Watsonville, Santa Maria, South & Central CA, Mexico via Texas | 2403 (Phoenix SP Veg) |
| Tomatoes (round, roma, grape) | Mexico via Otay Mesa, Mexico via Texas, Central CA | 2403 (Phoenix SP Veg) |
| Bell peppers | San Joaquin Valley CA, Mexico via Texas | 2403 (Phoenix SP Veg) |
| Onions, dry | Idaho & Malheur Co. OR, Columbia Basin WA / Umatilla OR, Peru imports | 2393 (Idaho Falls SP Onions & Potatoes) |

Other shipping-point reports carry these in other seasons (e.g., Florida tomatoes/peppers under Miami 2396 / Orlando 2400 / Thomasville 2410-2411; Georgia/Vidalia onions; Michigan under Benton Harbor 2387-2388). Districts rotate seasonally.

### National Shipping Point Trends — 1662 (weekly, Mondays, since 2021)
**No prices.** Per commodity × district: shipments for the last 3 weeks, movement/trading/price tone. Useful as a **volume signal** for picking what to track and for weighting. Shipment units not yet confirmed (likely 10,000-lb units; verify).

### National Retail Report — 3324 / FVWRETAIL (weekly, Fridays, since 2007)
Advertised feature prices from ~270 retailers / 29,000 stores. Regions: National, Northeast, Southeast, Midwest, Southcentral, Southwest, Northwest, Alaska, Hawaii.

## Row formats

### Terminal (`Report Details`)
`report_date, office_*, market_location_*, slug_id, slug_name, commodity (table grouping), variety, repack, package, storage, transportation mode, grade, unit sales, item size, appearance, quality, condition, organic, crop, origin, district, environment, properties, low_price, high_price, mostly_low_price, mostly_high_price, market tone comments, offerings comments, ...narratives`

Example (NY, 2026-09-24): `HASS | cartons 2 layer | 48s | origin=Mexico | 32.00–33.00`

### Shipping point (`Report Details`) — different column names
`var` (not variety), `pkg` (not package), `appear`, `cond`, `env`, `district`, `season`, `basis of sale`, `import export flag`, `rep cmt`, `supply tone comments`, `demand tone comments`, prices same as terminal. **`origin` is blank; `district` is the origin.**

### Retail (`Report Details`)
`variety, region, size (= unit: each / per lb / 3 lb bag / 4 count mesh bags), organic, environment, store count, wtd avg price, prior WK store count, prior WK wtd avg price, prior YR store count, prior YR wtd avg price`. No origin.

## Gotchas

1. **Near-duplicate rows.** Same variety/pack/size/origin can appear 2+ times with different prices, separated only by `appearance` ("Fine Appearance"), `condition` ("Holdovers"), or `quality` ("Fair Quality"). These must be part of the dedup key. For a "typical" price, prefer rows where these are N/A.
2. **Prices are ranges.** low/high always (when present); "mostly" low/high only sometimes. Rows with all-null prices exist (e.g., "supplies in too few hands", or size lines with no trading).
3. **Three different schemas** (terminal, shipping point, retail) → need a mapping layer to our common schema.
4. **`properties` is overloaded:** pepper color (Green/Red/Yellow/Orange), tomato ripeness ("Light Red-red", "On The Vine"), onion type ("Spanish Hybrid"), potato type.
5. **Free-text sizes and packs.** "exlarge-large", "XXLGE", "5x6 size", "24s film wrapped" vs "film lined 24s", "1 1/9 bushel cartons" vs "1 1/9 bushel cartons place pack". Needs a normalization table.
6. **Origin shifts with season.** NY bell peppers come from Canada, CA, Mexico and NJ in the same week; lettuce moves Salinas → Yuma/Imperial in winter. A "price vs. norm" series should probably be keyed on commodity + variety + pack + size + market, keeping origin as an attribute, not part of the series key.
7. **Origin values include "None" and "N/A".**
8. **Seasonal reports start and stop** (e.g., Benton Harbor onions: "LAST REPORT" on 2026-07-06). Missing days ≠ failure.
9. **Office metadata is messy** (Benton Harbor report showing office state ID / city Idaho Falls).
10. **Retail variety labels are inconsistent** ("HASS" vs "Hass-Marked Large"); units mixed in one table; prices are *advertised specials*, not everyday shelf prices; `store count` = number of stores running the ad.
11. **Coverage has shrunk.** Terminal markets like SF and St. Louis are discontinued, so multi-city averages will have composition changes over time.

## API verification (2026-09-26, via `scripts/probe_api.py` in GitHub Actions)

- Key works. API field names are snake_case: `commodity, variety, package, item_size, properties, origin, district, appearance, condition, quality, organic, low_price, high_price, mostly_low_price, mostly_high_price, report_date, ...` (terminal). `commodity` is a column.
- **Commodity filter gotcha:** names contain commas ("Peppers, Bell Type") and the API treats commas in `q=` as OR. `commodity=Tomatoes, Plum Type` silently returns all Tomatoes. **Always filter commodity client-side.**
- History: NY veg March 2016 returns full data (2,242 rows/week) → 10-year backfill is available. Boxed beef also has 2016 data.
- Volume: the 9 terminal reports (NY/LA/CHI × fruit/veg/onion) total ~12,400 rows/week, all commodities. Our commodities only: ~63,000 terminal rows/year.
- Raw JSON is ~1.3 KB/row (mostly repeated narrative text) → store a slim column set.

### Beef — LMR datamart (no key)
`https://mpr.datamart.ams.usda.gov/services/v1.1/reports/2453/{section}` — National Daily Boxed Beef Cutout, Negotiated, PM (LM_XB403), daily.
- `Current Cutout Values`: `choice_600_900_current`, `select_600_900_current`.
- `Choice Cuts` / `Select Cuts`: `item_description` includes IMPS code, e.g. "Rib, ribeye, bnls, heavy (112A  3)", plus `number_trades, total_pounds, price_range_low/high, weighted_average`.
- **Units: $/cwt (per 100 lb).** Numbers are strings with thousands separators ("1,357.22"). Empty/`.00` rows mean no trades.
- Other sections: Composite Primal Values, Ground Beef, Blended Ground Beef, Beef Trimmings, Current Volume.

### Chicken — MARS 3646 Weekly National Chicken Report
Section is `Report Detail` (singular). Fields: `item` ("Breast - B/S", "Wings - Whole", "Leg quarters - Bulk", ...), `trade_status` (Domestic/Export), `condition` (Fresh/Frozen), `low_price, high_price, wtd_avg_price, volume`. **Units: cents/lb**, volume in pounds (reported as thousands? unverified). Weekly.
Retail: 2756 (chicken) and 3228 (beef) weekly grocery feature reports: `region, type, price_unit, price_avg/min/max, store_count`.

## Terminal consistency (days reported, last 12 months, ~248 possible)

| Item | NY | LA | CHI |
|---|---|---|---|
| Avocado Hass 2-layer 48s | 242 | 239 | 248 |
| Avocado Hass 2-layer 60s | 242 | 239 | 248 |
| Strawberries 8×1-lb flats (size label varies: NY "extra large", LA "medium-large", CHI "medium") | 242 | 217 | 247 |
| Iceberg 24s (NY/CHI "24s film wrapped", LA "film lined 24s") | 244 | 246 | 248 |
| Romaine 24s (LA "cartons film lined") | 244 | 247 | 248 |
| Romaine hearts 12×3 | 244 | 247 | 248 |
| Roma 25 lb loose XL | 154 | 247 | 248 |
| Green bell 1 1/9 bu (NY large/jumbo, LA XL, CHI jumbo) | ~168 | 247 | 244 |
| Round tomato vine-ripe 2-layer 4x5s | — | 244 | 243 |
| Mature green 25 lb 5x6 (NY) | 174 | — | — |
| White onion 50 lb jumbo | 244 | 222 | 248 |
| Yellow onion 50 lb jumbo (split by type: Spanish/Hybrid/Grano) | 155–169 each | 205 | — |

NY is weaker on green bells and Romas because it splits them into more size grades and the colored 11-lb bells dominate there. Yellow onions are split by `properties` (Spanish Hybrid / Hybrid / Grano) as origin rotates; combining types gives a continuous series.
