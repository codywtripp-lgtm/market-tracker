"""One-off probe (round 3): rank commodities by volume to pick the NY shortlist.

- National shipment volume: WA_FV170 (slug 3283), USDA's national truck/air/boat
  movement report, summed by commodity over the last 12 months.
- NY coverage: days each commodity appears in the NY terminal reports.
Writes probe_output/volume_rank.csv.
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
OUT = Path("probe_output")
OUT.mkdir(exist_ok=True)
KEY = os.environ.get("MARS_API_KEY", "").strip()
if not KEY:
    sys.exit("MARS_API_KEY is not set")
session = requests.Session()


def get(url, params=None, tries=3):
    for attempt in range(tries):
        try:
            r = session.get(url, params=params, auth=(KEY, ""), timeout=300)
            if r.status_code == 200:
                return r.json()
            print(f"HTTP {r.status_code} for {r.url}: {r.text[:200]}", flush=True)
            if r.status_code in (400, 401, 403, 404):
                return None
        except Exception as e:
            print(f"error {e!r}", flush=True)
        time.sleep(5 * (attempt + 1))
    return None


def rows_of(p):
    return p.get("results", []) if isinstance(p, dict) else (p or [])


def fetch_range(slug, start, end, section, chunk_days=31):
    rows, s = [], start
    while s <= end:
        e = min(s + dt.timedelta(days=chunk_days - 1), end)
        q = f"report_begin_date={s:%m/%d/%Y}:{e:%m/%d/%Y}"
        rows += rows_of(get(f"{MARS}/reports/{slug}/{section}", {"q": q}))
        s = e + dt.timedelta(days=1)
    return rows


today = dt.date.today()
start = today - dt.timedelta(days=365)

# Discover the movement report's sections and fields
meta = get(f"{MARS}/reports/3283")
sections = meta.get("reportSections", []) if isinstance(meta, dict) else []
print("3283 sections:", sections, flush=True)
detail = next((s for s in sections if "Detail" in s), "Report Details")
move = fetch_range("3283", start, today, detail)
print(f"movement rows: {len(move)}", flush=True)
(OUT / "movement_sample.json").write_text(json.dumps(move[:20], indent=1))

# Guess the volume field from the data
num_fields = collections.Counter()
for r in move[:500]:
    for k, v in r.items():
        try:
            float(str(v).replace(",", ""))
            num_fields[k] += 1
        except (TypeError, ValueError):
            pass
print("numeric fields:", num_fields.most_common(15), flush=True)
vol_field = "1 lb units"  # shipments in pounds (round 3a finding)
unit_field = None
print("volume field:", vol_field, "unit field:", unit_field, flush=True)

volume = collections.Counter()
units = collections.defaultdict(collections.Counter)
for r in move:
    try:
        v = float(str(r.get(vol_field)).replace(",", ""))
    except (TypeError, ValueError):
        continue
    c = r.get("commodity")
    volume[c] += v
    if unit_field:
        units[c][r.get(unit_field)] += 1

# NY coverage
ny_days = collections.defaultdict(set)
for slug in ("2314", "2315", "2316"):
    for r in fetch_range(slug, start, today, "Report Details"):
        ny_days[r.get("commodity")].add(r.get("report_date"))
    print(f"NY {slug} done", flush=True)

names = set(volume) | set(ny_days)
with open(OUT / "volume_rank.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["commodity", "national_volume_12mo", "volume_unit", "ny_days_reported"])
    for c in sorted(names, key=lambda c: -volume.get(c, 0)):
        unit = units[c].most_common(1)[0][0] if units.get(c) else ""
        w.writerow([c, round(volume.get(c, 0)), unit, len(ny_days.get(c, ()))])
print("done", flush=True)
