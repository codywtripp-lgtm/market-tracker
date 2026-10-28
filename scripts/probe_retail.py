"""One-off probe: which USDA MARS reports carry weekly retail (supermarket feature) prices beyond produce?

Lists every report, keeps titles about retail, and for each pulls the last few weeks to show its sections,
field names, commodities and a few rows. Output: probe_output/retail_*.json and retail_summary.txt.
"""

import datetime as dt
import json
import os
import sys
from pathlib import Path

import requests

MARS = "https://marsapi.ams.usda.gov/services/v1.2"
OUT = Path("probe_output")
OUT.mkdir(exist_ok=True)
KEY = os.environ.get("MARS_API_KEY", "").strip() or sys.exit("MARS_API_KEY is not set")
s = requests.Session()
lines = []


def log(m):
    print(m, flush=True)
    lines.append(str(m))


def get(url, params=None):
    r = s.get(url, params=params, auth=(KEY, ""), timeout=300)
    return r.json() if r.status_code == 200 else None


reports = get(f"{MARS}/reports") or []
(OUT / "all_reports.json").write_text(json.dumps(reports, indent=1))
cands = [r for r in reports if "retail" in json.dumps(r).lower()]
log(f"{len(reports)} reports, {len(cands)} mention retail")
end = dt.date.today()
start = end - dt.timedelta(days=21)
for r in cands:
    slug = r.get("slug_id") or r.get("slug_name")
    log(f"\n=== {slug} | {r.get('report_title')} | {r.get('market_types')} | {r.get('published_date')}")
    meta = get(f"{MARS}/reports/{slug}")
    sections = []
    if isinstance(meta, dict):
        sections = [k for k in meta if k not in ("results", "stats")] if "results" not in meta else []
    for section in ["Report Details", "Report Detail", None]:
        url = f"{MARS}/reports/{slug}" + (f"/{section}" if section else "")
        data = get(url, {"q": f"report_begin_date={start:%m/%d/%Y}:{end:%m/%d/%Y}"})
        rows = data.get("results", []) if isinstance(data, dict) else (data or [])
        if rows:
            keys = sorted(rows[0].keys())
            comm = sorted({str(x.get("commodity")) for x in rows})[:60]
            log(f"  section={section!r} rows={len(rows)} keys={keys}")
            log(f"  commodities={comm}")
            (OUT / f"retail_{slug}.json").write_text(json.dumps(rows[:40], indent=1))
            break
(OUT / "retail_summary.txt").write_text("\n".join(lines))
