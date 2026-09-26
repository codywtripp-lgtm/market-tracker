"""One-off exploration probe for the USDA MARS API (round 2).

Runs in GitHub Actions (where the MARS_API_KEY secret lives) and writes
findings to probe_output/ for download. Not part of the production pipeline.

Round 1 finding: commodity names contain commas ("Peppers, Bell Type") and the
API treats commas in q= as OR, so commodity filters are applied client-side here.
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
            r = session.get(url, params=params, auth=(KEY, "") if auth else None, timeout=300)
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


def fetch_range(slug, start, end, section="Report Details", chunk_days=31):
    rows = []
    s = start
    while s <= end:
        e = min(s + dt.timedelta(days=chunk_days - 1), end)
        q = f"report_begin_date={mmddyyyy(s)}:{mmddyyyy(e)}"
        rows += rows_of(get(f"{MARS}/reports/{slug}/{section}", {"q": q}))
        s = e + dt.timedelta(days=1)
    return rows


today = dt.date.today()

# 1. Terminal consistency for the comma-named commodities (client-side filter)
TERMINALS = {
    "NY": {"veg": "2315", "onion": "2316"},
    "LA": {"veg": "2307", "onion": "2308"},
    "CHI": {"veg": "2291", "onion": "2292"},
}
WANTED = {
    "veg": {"Tomatoes", "Tomatoes, Plum Type", "Peppers, Bell Type", "Lettuce, Iceberg", "Lettuce, Romaine"},
    "onion": {"Onions, Dry"},
}
start = today - dt.timedelta(days=365)
combo_days = collections.defaultdict(set)
combo_origins = collections.defaultdict(collections.Counter)
rows_per_day = collections.Counter()
for market, groups in TERMINALS.items():
    for group, slug in groups.items():
        rows = [r for r in fetch_range(slug, start, today) if r.get("commodity") in WANTED[group]]
        log(f"{market} {group} ({slug}): {len(rows)} wanted rows in last year")
        for r in rows:
            day = r.get("report_date") or r.get("report_begin_date")
            rows_per_day[(market, day)] += 1
            key = (market, r.get("commodity"), r.get("variety"), r.get("package"), r.get("item_size"),
                   r.get("properties"), r.get("organic"))
            combo_days[key].add(day)
            combo_origins[key][r.get("origin")] += 1

with open(OUT / "terminal_consistency_veg.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["market", "commodity", "variety", "package", "item_size", "properties",
                "organic", "days_reported", "top_origins"])
    for key, days in sorted(combo_days.items(), key=lambda kv: -len(kv[1])):
        origins = combo_origins[key].most_common(3)
        w.writerow(list(key) + [len(days), "; ".join(f"{o}({n})" for o, n in origins)])

# 2. Size estimate: all rows per report for one recent week (whole reports, unfiltered)
week_start = today - dt.timedelta(days=7)
size = {}
for slug in ["2314", "2315", "2316", "2306", "2307", "2308", "2290", "2291", "2292",
             "2390", "2403", "2393", "3324"]:
    rows = fetch_range(slug, week_start, today, chunk_days=8)
    size[slug] = {"rows_last_7_days": len(rows),
                  "approx_bytes_as_json": len(json.dumps(rows))}
    log(f"size {slug}: {len(rows)} rows last 7 days")
save("size_estimate.json", size)

# 3. History depth: 10 years back for NY veg
for year in (2016, 2017):
    rows = fetch_range("2315", dt.date(year, 3, 1), dt.date(year, 3, 7), chunk_days=8)
    peppers = [r for r in rows if r.get("commodity") == "Peppers, Bell Type"]
    log(f"NY veg first week of March {year}: {len(rows)} rows, {len(peppers)} bell pepper rows")
    save(f"ny_veg_{year}_peppers.json", peppers[:15])

# 4. Chicken: report metadata + sections for the weekly national chicken report
meta = get(f"{MARS}/reports/3646")
save("chicken_3646_meta.json", meta if isinstance(meta, dict) else {"results": rows_of(meta)[:5]})
sections = meta.get("reportSections", []) if isinstance(meta, dict) else []
log(f"3646 sections: {sections}")
for sec in sections:
    rows = rows_of(get(f"{MARS}/reports/3646/{sec}", {"lastReports": 1}))
    save(f"chicken_3646_{sec.replace(' ', '_').replace('/', '-')}.json", rows[:40])
    log(f"3646 section {sec}: {len(rows)} rows")

# 5. Beef: boxed beef cutout sections (LMR datamart, no key)
for sec in ["Current Cutout Values", "Choice Cuts", "Composite Primal Values"]:
    rows = rows_of(get(f"{DATAMART}/reports/2453/{sec}", {"q": f"report_date={mmddyyyy(today - dt.timedelta(days=1))}"}, auth=False))
    if not rows:
        rows = rows_of(get(f"{DATAMART}/reports/2453/{sec}", {"lastReports": 1}, auth=False))
    save(f"beef_2453_{sec.replace(' ', '_')}.json", rows[:60])
    log(f"2453 section {sec}: {len(rows)} rows")
old = rows_of(get(f"{DATAMART}/reports/2453/Current Cutout Values",
                  {"q": "report_date=03/01/2016:03/07/2016"}, auth=False))
log(f"2453 cutout rows first week of March 2016: {len(old)}")
save("beef_2453_2016.json", old[:10])

(OUT / "log.txt").write_text("\n".join(log_lines))
log("done")
