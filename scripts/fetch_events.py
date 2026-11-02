"""Download public government event records for the forecast tests (scripts/backtest_event_signals.py).

FDA recalls (openFDA), Federal Register trade documents, NOAA Storm Events crop damage. Saved as weekly-ready CSVs
in data/raw/events/. Bird flu (APHIS) is not here: its site refused automated requests (HTTP 403).

Run: python scripts/fetch_events.py
"""

import csv
import gzip
import io
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pipeline import store  # noqa: E402

OUT = store.DATA / "raw" / "events"
TERMS = {"Avocados": "avocado", "Bananas": "banana", "Blueberries": "blueberries", "Broccoli": "broccoli",
         "Carrots": "carrots", "Celery": "celery", "Cucumbers": "cucumber", "Grapes": "grapes", "Lemons": "lemons",
         "Lettuce, Iceberg": "lettuce", "Lettuce, Romaine": "romaine", "Limes": "limes", "Onions, Dry": "onions",
         "Peppers, Bell Type": "peppers", "Potatoes": "potatoes", "Strawberries": "strawberries",
         "Tomatoes": "tomatoes", "Tomatoes, Plum Type": "tomatoes"}
NOAA = "https://www.ncei.noaa.gov/pub/data/swdi/stormevents/csvfiles/"


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "producepricetracker.com research"})
    with urllib.request.urlopen(req, timeout=180) as r:
        return r.read()


def fda():
    rows = []
    for commodity, term in TERMS.items():
        skip = 0
        while True:
            q = urllib.parse.urlencode({"search": f'product_description:"{term}"', "limit": 1000, "skip": skip})
            try:
                j = json.loads(get(f"https://api.fda.gov/food/enforcement.json?{q}"))
            except urllib.error.HTTPError as e:
                if e.code == 404:  # no more results
                    break
                raise
            for r in j["results"]:
                rows.append({"commodity": commodity, "report_date": r.get("report_date", ""),
                             "started": r.get("recall_initiation_date", ""), "class": r.get("classification", ""),
                             "reason": r.get("reason_for_recall", "")[:120]})
            skip += 1000
            if skip >= j["meta"]["results"]["total"] or skip >= 25000:
                break
            time.sleep(1)
        print("fda", commodity, len(rows), flush=True)
        time.sleep(1)
    return rows


def federal_register():
    rows, seen = [], set()
    for commodity, term in {**TERMS, "All imports": "mexico"}.items():
        for word in ("tariff", "antidumping", "quarantine"):
            q = urllib.parse.urlencode({"conditions[term]": f"{term} {word}", "conditions[publication_date][gte]": "2016-01-01",
                                        "per_page": 1000, "order": "oldest"})
            q += "&fields[]=publication_date&fields[]=type&fields[]=title&fields[]=document_number"
            j = json.loads(get(f"https://www.federalregister.gov/api/v1/documents.json?{q}"))
            for r in j.get("results", []):
                key = (commodity, r["document_number"])
                if key not in seen:
                    seen.add(key)
                    rows.append({"commodity": commodity, "date": r["publication_date"], "type": r["type"], "title": r["title"][:120]})
            time.sleep(1)
        print("fedreg", commodity, len(rows), flush=True)
    return rows


def money(s):
    m = re.match(r"([\d.]+)([KMB]?)", s or "")
    return float(m.group(1)) * {"": 1, "K": 1e3, "M": 1e6, "B": 1e9}[m.group(2)] if m else 0.0


def noaa():
    names = sorted(set(re.findall(r"StormEvents_details-ftp_v1\.0_d\d{4}_c\d+\.csv\.gz", get(NOAA).decode())))
    rows = []
    for year in range(2016, 2027):
        name = [n for n in names if f"_d{year}_" in n][-1]
        text = gzip.decompress(get(NOAA + name)).decode("latin-1")
        n = 0
        for r in csv.DictReader(io.StringIO(text)):
            dmg = money(r["DAMAGE_CROPS"])
            if dmg > 0:
                ym = r["BEGIN_YEARMONTH"]
                rows.append({"date": f"{ym[:4]}-{ym[4:]}-{int(r['BEGIN_DAY']):02d}", "state": r["STATE"].title(),
                             "type": r["EVENT_TYPE"], "crop_damage": dmg})
                n += 1
        print("noaa", year, n, flush=True)
    return rows


def save(name, rows):
    OUT.mkdir(parents=True, exist_ok=True)
    with open(OUT / f"{name}.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


if __name__ == "__main__":
    if not (OUT / "fda_recalls.csv").exists():
        save("fda_recalls", fda())
    save("federal_register", federal_register())
    save("noaa_crop_damage", noaa())
