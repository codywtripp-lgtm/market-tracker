"""Assemble the static website into _site/ (deployed to GitHub Pages).

    python scripts/build_site.py

Copies site/ and writes the JSON the page loads:
  data/latest.json          every headline series: this week's price, status, blurb inputs
  data/s/<series_id>.json   weekly history for one series, loaded when it's shown in the chart:
                            [week_start, price, real_price, pct_vs_usual, usual_lo, usual_hi]
"""

import csv
import datetime as dt
import json
import shutil
import statistics
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXPORT = ROOT / "data" / "export"
OUT = ROOT / "_site"

# Same rule as pipeline/export.py: same ISO week +/-2, prior years only, at least 3 years.
WEEK_WINDOW = 2
MIN_YEARS = 3


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


def quantile(sorted_vals, q):
    pos = (len(sorted_vals) - 1) * q
    lo, hi = int(pos), min(int(pos) + 1, len(sorted_vals) - 1)
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (pos - lo)


def with_usual(weeks):
    """weeks: sorted [(date, price, real)] -> rows with % vs usual and the usual (25th-75th pct) range."""
    by_isoweek = defaultdict(list)  # iso week -> [(iso year, real)]
    for d, _, real in weeks:
        y, w = d.isocalendar()[:2]
        if real is not None:
            by_isoweek[w].append((y, real))
    out = []
    for d, price, real in weeks:
        y, w = d.isocalendar()[:2]
        pool, years = [], set()
        for o in range(-WEEK_WINDOW, WEEK_WINDOW + 1):
            for yy, v in by_isoweek.get((w - 1 + o) % 53 + 1, ()):
                if yy < y:
                    pool.append(v)
                    years.add(yy)
        if len(years) >= MIN_YEARS and real is not None:
            pool.sort()
            usual = statistics.median(pool)
            pct = round((real / usual - 1) * 100, 1) if usual else None
            lo, hi = round(quantile(pool, 0.25), 3), round(quantile(pool, 0.75), 3)
        else:
            pct = lo = hi = None
        out.append([d.isoformat(), price, real, pct, lo, hi])
    return out


def main():
    if OUT.exists():
        shutil.rmtree(OUT)
    shutil.copytree(ROOT / "site", OUT)
    (OUT / "data" / "s").mkdir(parents=True)

    series = {r["series_id"]: r for r in read("series.csv")}
    forecasts = EXPORT / "forecasts.json"
    fc = json.loads(forecasts.read_text())["series"] if forecasts.exists() else {}
    # typical 2-week forecast miss per commodity x market (walk-forward), shown next to forecasts
    card = {(r["commodity"], r["market"]): r for r in read("forecast_report_card.csv")}
    # last complete week's shipments vs. usual for this time of year, per commodity (all origins)
    supply = {r["commodity"]: num(r["vs_usual_pct"]) for r in read("supply.csv")}
    # Chicken is quoted in cents/lb; show it in dollars like everything else.
    scale = {sid: 0.01 if s["compare_unit"] == "cents/lb" else 1 for sid, s in series.items()}

    def price(sid, v):
        v = num(v)
        return None if v is None else round(v * scale.get(sid, 1), 4)

    # Latest day's USDA tone and origins per series (for the "what's going on" lines)
    last_day = {}
    for r in read("prices_daily_365.csv"):
        if r["date"] >= last_day.get(r["series_id"], {}).get("date", ""):
            last_day[r["series_id"]] = r

    latest = []
    for r in read("latest.csv"):
        sid = r["series_id"]
        s, day = series.get(sid, {}), last_day.get(sid, {})
        latest.append({
            "id": sid, "commodity": r["commodity"], "market": r["market"], "type": r["market_type"],
            "week": r["week_start"], "price": price(sid, r["compare_price"]),
            "unit": "per lb" if scale.get(sid) == 0.01 else r["compare_unit"],
            "norm": price(sid, r["seasonal_norm"]), "vsNorm": num(r["pct_vs_norm"]),
            "pctile": num(r["percentile"]), "status": r["status"], "years": num(r["years_of_history"]),
            "vs4w": num(r["pct_vs_4_weeks_ago"]), "vsYear": num(r["pct_vs_last_year"]),
            "variety": s.get("variety", ""), "pack": s.get("pack_size", ""), "size": s.get("item_size", ""),
            "props": s.get("properties", ""), "organic": s.get("organic", ""),
            "coverage": num(s.get("coverage_last_year")),
            "tone": day.get("market_tone", ""), "origins": day.get("origins", ""),
            "forecast": {p["h"]: [p["lo"], p["mid"], p["hi"]] for p in fc.get(sid, {}).get("points", [])},
            "fcMiss": num(card.get((r["commodity"], r["market"]), {}).get("forecast_miss_pct")),
            "fcStable": card.get((r["commodity"], r["market"]), {}).get("uses") == "no change",
            "supplyVsUsual": supply.get(r["commodity"]) if r["market_type"] in ("terminal", "shipping point") else None,
        })
    alerts = EXPORT / "alerts.json"
    if alerts.exists():
        shutil.copy(alerts, OUT / "data" / "alerts.json")
    else:
        (OUT / "data" / "alerts.json").write_text('{"alerts":[]}')
    as_of = max((x["week"] for x in latest), default="")
    (OUT / "data" / "latest.json").write_text(json.dumps({"asOf": as_of, "items": latest}, separators=(",", ":")))

    weekly = defaultdict(list)
    for r in read("prices_weekly.csv"):
        sid = r["series_id"]
        weekly[sid].append((dt.date.fromisoformat(r["week_start"]), price(sid, r["compare_price"]),
                            price(sid, r["real_compare_price"])))
    for sid, rows in weekly.items():
        rows.sort()
        (OUT / "data" / "s" / f"{sid}.json").write_text(json.dumps(with_usual(rows), separators=(",", ":")))
    print(f"site: {len(latest)} items, {len(weekly)} series histories")


if __name__ == "__main__":
    main()
