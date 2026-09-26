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
    # Chicken is quoted in cents/lb; show it in dollars like everything else.
    scale = {sid: 0.01 if s["compare_unit"] == "cents/lb" else 1 for sid, s in series.items()}

    def unit_of(sid, unit):
        return "per lb" if scale.get(sid) == 0.01 else unit

    def price(sid, v):
        v = num(v)
        return None if v is None else round(v * scale.get(sid, 1), 4)

    latest = []
    for r in read("latest.csv"):
        sid = r["series_id"]
        s = series.get(sid, {})
        latest.append({
            "id": sid, "label": r["label"], "commodity": r["commodity"], "market": r["market"],
            "type": r["market_type"], "week": r["week_start"], "price": price(sid, r["compare_price"]),
            "unit": unit_of(sid, r["compare_unit"]), "norm": price(sid, r["seasonal_norm"]),
            "vsNorm": num(r["pct_vs_norm"]),
            "pctile": num(r["percentile"]), "status": r["status"], "years": num(r["years_of_history"]),
            "vs4w": num(r["pct_vs_4_weeks_ago"]), "vsYear": num(r["pct_vs_last_year"]),
            "variety": s.get("variety", ""), "pack": s.get("pack_size", ""), "size": s.get("item_size", ""),
        })
    as_of = max((x["week"] for x in latest), default="")
    (OUT / "data" / "latest.json").write_text(json.dumps({"asOf": as_of, "items": latest}, separators=(",", ":")))

    weekly = defaultdict(list)
    for r in read("prices_weekly.csv"):
        sid = r["series_id"]
        weekly[sid].append([r["week_start"], price(sid, r["compare_price"]), price(sid, r["real_compare_price"])])
    for sid, rows in weekly.items():
        (OUT / "data" / "s" / f"{sid}.json").write_text(json.dumps(sorted(rows), separators=(",", ":")))
    print(f"site: {len(latest)} items, {len(weekly)} series histories")


if __name__ == "__main__":
    main()
