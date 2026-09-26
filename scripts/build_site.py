"""Assemble the static website into _site/ (deployed to GitHub Pages).

    python scripts/build_site.py

Copies site/ and writes small JSON files the page loads:
  data/latest.json            this week's status for every headline series
  data/s/<series_id>.json     weekly history for one series (loaded when tapped)
"""

import csv
import json
import shutil
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXPORT = ROOT / "data" / "export"
OUT = ROOT / "_site"


def read(name):
    path = EXPORT / name
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def num(s):
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def main():
    if OUT.exists():
        shutil.rmtree(OUT)
    shutil.copytree(ROOT / "site", OUT)
    (OUT / "data" / "s").mkdir(parents=True)

    series = {r["series_id"]: r for r in read("series.csv")}
    latest = []
    for r in read("latest.csv"):
        s = series.get(r["series_id"], {})
        latest.append({
            "id": r["series_id"], "label": r["label"], "commodity": r["commodity"], "market": r["market"],
            "type": r["market_type"], "week": r["week_start"], "price": num(r["compare_price"]),
            "unit": r["compare_unit"], "norm": num(r["seasonal_norm"]), "vsNorm": num(r["pct_vs_norm"]),
            "pctile": num(r["percentile"]), "status": r["status"], "years": num(r["years_of_history"]),
            "vs4w": num(r["pct_vs_4_weeks_ago"]), "vsYear": num(r["pct_vs_last_year"]),
            "variety": s.get("variety", ""), "pack": s.get("pack_size", ""), "size": s.get("item_size", ""),
        })
    as_of = max((x["week"] for x in latest), default="")
    (OUT / "data" / "latest.json").write_text(json.dumps({"asOf": as_of, "items": latest}, separators=(",", ":")))

    weekly = defaultdict(list)
    for r in read("prices_weekly.csv"):
        weekly[r["series_id"]].append([r["week_start"], num(r["compare_price"]), num(r["real_compare_price"])])
    for sid, rows in weekly.items():
        (OUT / "data" / "s" / f"{sid}.json").write_text(json.dumps(sorted(rows), separators=(",", ":")))
    print(f"site: {len(latest)} items, {len(weekly)} series histories")


if __name__ == "__main__":
    main()
