"""One-off exploration probe for the USDA MARS API.

Runs in GitHub Actions (where the MARS_API_KEY secret lives) and writes
findings to probe_output/ for download. Not part of the production pipeline.
"""

import collections
import csv
import datetime as dt
import json
import os
import sys
import time
from pathlib import Path

import requests

MARS = "https://marsapi.ams.usda.gov/services/v1.2"
DATAMART = "https://mpr.datamart.ams.usda.gov/services/v1.1"
OUT = Path("probe_output")
OUT.mkdir(exist_ok=True)

KEY = os.environ.get("MARS_API_KEY", "").strip()
if not KEY:
    sys.exit("MARS_API_KEY is not set")

session = requests.Session()
log_lines = []


def log(msg):
    print(msg, flush=True)
    log_lines.append(msg)


def get(url, params=None, auth=True, tries=3):
    for attempt in range(tries):
        try:
            r = session.get(url, params=params, auth=(KEY, "") if auth else None, timeout=180)
            if r.status_code == 200:
                return r.json()
            log(f"HTTP {r.status_code} for {r.url}: {r.text[:300]}")
            if r.status_code in (400, 401, 403, 404):
                return None
        except Exception as e:  # network hiccup; retry
            log(f"error {e!r} for {url}")
        time.sleep(5 * (attempt + 1))
    return None


def save(name, obj):
    (OUT / name).write_text(json.dumps(obj, indent=1, default=str))


def rows_of(payload):
    if payload is None:
        return []
    if isinstance(payload, dict):
        return payload.get("results", [])
    return payload


def mmddyyyy(d):
    return d.strftime("%m/%d/%Y")


today = dt.date.today()

# 1. Report catalog
catalog = rows_of(get(f"{MARS}/reports"))
log(f"catalog: {len(catalog)} reports")
save("catalog.json", catalog)

# 2. Samples of each report type (field names + a few rows)
SAMPLE_SLUGS = {
    "2314": "NY terminal fruit",
    "2315": "NY terminal veg",
    "2316": "NY terminal onions",
    "2390": "Fresno SP fruit (Mexico avocados)",
    "2403": "Phoenix SP veg (lettuce/tomato/pepper)",
    "2393": "Idaho Falls SP onions",
    "3324": "Retail specialty crops",
    "1662": "National SP trends",
    "3646": "Weekly national chicken",
    "2756": "Retail chicken",
    "3228": "Retail beef",
}
samples = {}
for slug, label in SAMPLE_SLUGS.items():
    data = get(f"{MARS}/reports/{slug}/Report Details", {"lastReports": 1})
    rows = rows_of(data)
    fields = sorted({k for r in rows for k in r})
    commodities = collections.Counter(r.get("commodity") for r in rows)
    samples[slug] = {
        "label": label,
        "n_rows": len(rows),
        "fields": fields,
        "commodities": commodities.most_common(80),
        "first_rows": rows[:3],
    }
    log(f"sample {slug} {label}: {len(rows)} rows, {len(fields)} fields")
save("samples.json", samples)

# 3. Which shipping-point reports carry each target commodity (last 20 reports)
TARGETS = ["Avocados", "Tomatoes", "Tomatoes, Plum Type", "Peppers, Bell Type",
           "Onions, Dry", "Lettuce, Iceberg", "Lettuce, Romaine", "Strawberries"]
sp_slugs = [r["slug_id"] for r in catalog
            if "Shipping Point" in (r.get("report_title") or r.get("report_name") or "")
            and "Discontinued" not in (r.get("report_title") or r.get("report_name") or "")]
sp_map = collections.defaultdict(list)
for slug in sp_slugs:
    rows = rows_of(get(f"{MARS}/reports/{slug}/Report Details", {"lastReports": 20}))
    for (c, d), n in collections.Counter((r.get("commodity"), r.get("district")) for r in rows).items():
        if c in TARGETS:
            sp_map[c].append({"slug": slug, "district": d, "rows": n})
save("shipping_point_map.json", sp_map)
log(f"shipping point reports scanned: {len(sp_slugs)}")

# 4. Consistency: one year of terminal data for the shortlist
TERMINALS = {
    "NY": {"fruit": "2314", "veg": "2315", "onion": "2316"},
    "LA": {"fruit": "2306", "veg": "2307", "onion": "2308"},
    "CHI": {"fruit": "2290", "veg": "2291", "onion": "2292"},
}
COMMODITY_GROUP = {
    "Avocados": "fruit", "Strawberries": "fruit",
    "Tomatoes": "veg", "Tomatoes, Plum Type": "veg", "Peppers, Bell Type": "veg",
    "Lettuce, Iceberg": "veg", "Lettuce, Romaine": "veg",
    "Onions, Dry": "onion",
}
start = today - dt.timedelta(days=365)
combo_days = collections.defaultdict(set)
combo_prices = collections.defaultdict(list)
fields_seen = set()
for market, groups in TERMINALS.items():
    for commodity, group in COMMODITY_GROUP.items():
        slug = groups[group]
        rows = []
        # quarterly chunks to stay well under the 100k row cap
        chunk_start = start
        while chunk_start < today:
            chunk_end = min(chunk_start + dt.timedelta(days=91), today)
            q = f"report_begin_date={mmddyyyy(chunk_start)}:{mmddyyyy(chunk_end)};commodity={commodity}"
            rows += rows_of(get(f"{MARS}/reports/{slug}/Report Details", {"q": q}))
            chunk_start = chunk_end + dt.timedelta(days=1)
        log(f"{market} {commodity}: {len(rows)} rows in last year")
        for r in rows:
            fields_seen.update(r)
            key = (market, commodity, r.get("variety"), r.get("package"), r.get("item_size"),
                   r.get("properties"), r.get("organic"))
            combo_days[key].add(r.get("report_date") or r.get("report_begin_date"))
            if r.get("origin"):
                combo_prices[key].append(r.get("origin"))

with open(OUT / "terminal_consistency.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["market", "commodity", "variety", "package", "item_size", "properties",
                "organic", "days_reported", "top_origins"])
    for key, days in sorted(combo_days.items(), key=lambda kv: -len(kv[1])):
        origins = collections.Counter(combo_prices[key]).most_common(3)
        w.writerow(list(key) + [len(days), "; ".join(f"{o}({n})" for o, n in origins)])
save("terminal_fields.json", sorted(fields_seen))

# 5. History depth check: earliest data for NY fruit
old = rows_of(get(f"{MARS}/reports/2314/Report Details",
                  {"q": "report_begin_date=01/02/2015:01/09/2015;commodity=Avocados"}))
log(f"NY avocados Jan 2015 rows: {len(old)}")
save("ny_avocado_2015_sample.json", old[:10])

# 6. Beef and poultry: LMR datamart (public, no key) + MARS poultry
dm_catalog = get(f"{DATAMART}/reports", auth=False)
save("datamart_catalog.json", dm_catalog)
dm_rows = dm_catalog if isinstance(dm_catalog, list) else rows_of(dm_catalog)
log(f"datamart catalog entries: {len(dm_rows)}")
for slug in ["2453", "2461", "2466"]:  # boxed beef cutout candidates
    info = get(f"{DATAMART}/reports/{slug}", auth=False)
    save(f"datamart_{slug}.json", info if info is None else (info if isinstance(info, dict) else {"results": info[:20]}))

(OUT / "log.txt").write_text("\n".join(log_lines))
log("done")
