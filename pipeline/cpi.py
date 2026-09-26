"""Consumer Price Index (BLS), used to restate old prices in today's dollars.

    python -m pipeline.cpi

Series CUUR0000SAF11: CPI-U, Food at home, U.S. city average, not seasonally adjusted.
BLS public API v1 needs no key (limit: 25 requests/day, 10 years per request).
Writes data/raw/cpi/food_at_home.csv (month, value). On failure the existing file is kept.
"""

import csv
import datetime as dt
import logging

import requests

from . import store

SERIES = "CUUR0000SAF11"
URL = "https://api.bls.gov/publicAPI/v1/timeseries/data/"
FIRST_YEAR = 2006
PATH = store.DATA / "raw" / "cpi" / "food_at_home.csv"

log = logging.getLogger(__name__)


def fetch(first_year=FIRST_YEAR, last_year=None):
    last_year = last_year or dt.date.today().year
    values = {}
    start = first_year
    while start <= last_year:
        end = min(start + 9, last_year)
        r = requests.post(URL, json={"seriesid": [SERIES], "startyear": str(start), "endyear": str(end)},
                          timeout=120)
        r.raise_for_status()
        body = r.json()
        if body.get("status") != "REQUEST_SUCCEEDED":
            raise RuntimeError(f"BLS: {body.get('status')} {body.get('message')}")
        for p in body["Results"]["series"][0]["data"]:
            if not p["period"].startswith("M") or p["period"] == "M13":
                continue
            try:
                values[f"{p['year']}-{p['period'][1:]}"] = float(p["value"])
            except ValueError:
                # BLS publishes "-" for months with no data (e.g. Oct 2025 shutdown);
                # Deflator.factor falls back to the previous month.
                log.warning("CPI %s-%s missing (%r), skipped", p["year"], p["period"], p["value"])
        start = end + 1
    return values


def save(values):
    PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(PATH, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["month", "cpi_food_at_home"])
        for month in sorted(values):
            w.writerow([month, values[month]])


def load():
    """{'YYYY-MM': value}; empty if the file doesn't exist yet."""
    if not PATH.exists():
        return {}
    with open(PATH, newline="", encoding="utf-8") as f:
        return {r["month"]: float(r["cpi_food_at_home"]) for r in csv.DictReader(f)}


class Deflator:
    """Converts a price on a date into dollars of the latest CPI month."""

    def __init__(self, values):
        self.values = values
        self.base_month = max(values) if values else ""
        self.base = values[self.base_month] if values else None

    def factor(self, date_iso):
        if not self.values:
            return 1.0
        month = date_iso[:7]
        if month in self.values:
            v = self.values[month]
        elif month > self.base_month:
            v = self.base  # CPI for recent months isn't published yet
        else:
            earlier = [m for m in self.values if m <= month]
            v = self.values[max(earlier)] if earlier else self.values[min(self.values)]
        return self.base / v


def main():
    logging.basicConfig(level=logging.INFO)
    try:
        values = fetch()
        save(values)
        log.info("CPI saved: %d months, latest %s", len(values), max(values))
    except Exception as e:  # keep the old file; export still works with it
        log.error("CPI fetch failed, keeping existing file: %s", e)


if __name__ == "__main__":
    main()
