"""One-off probe: how much of our 30 items does each other USDA terminal market quote, and how far back?"""

import collections
import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, ".")
from pipeline import config, usda  # noqa: E402

SECTION = sys.argv[1] if len(sys.argv) > 1 else "Report Details"
CITIES = {"New York": (2314, 2315, 2316), "Philadelphia": (2318, 2319, 2320), "Boston": (2285, 2286, 2287), "Atlanta": (2277, 2278, 2279),
          "Baltimore": (2281, 2282, 2283), "Detroit": (2302, 2303, 2304), "Miami": (2310, 2311, 2312),
          "Columbia SC": (2294, 2295, 2296), "Asheville": (3913, 3914, 3915)}
client = usda.Client()
today = dt.date.today()
lines = []
for city, slugs in CITIES.items():
    days, items, rows_n = set(), collections.defaultdict(set), 0
    for slug in slugs:
        try:
            rows = client.mars(str(slug), SECTION, today - dt.timedelta(days=365), today)
        except usda.USDAError as e:
            lines.append(f"{city} {slug} FAILED {e}")
            continue
        rows = [r for r in rows if r.get("commodity") in config.PRODUCE_COMMODITIES]
        rows_n += len(rows)
        for r in rows:
            days.add(r["report_date"])
            items[r["commodity"]].add(r["report_date"])
    back = {}
    for year in (2016, 2019, 2021, 2023):
        n = 0
        for slug in slugs:
            try:
                n += len(client.mars(str(slug), SECTION, dt.date(year, 3, 1), dt.date(year, 3, 31)))
            except usda.USDAError:
                pass
        back[year] = n
    steady = sorted(c for c, d in items.items() if len(d) >= 100)
    lines.append(f"{city}: days {len(days)}, rows {rows_n}, items 100+ days {len(steady)}/30, missing {sorted(config.PRODUCE_COMMODITIES - set(steady))}, March rows {back}")
    print(lines[-1], flush=True)
Path("probe_output").mkdir(exist_ok=True)
Path("probe_output/cities.txt").write_text("\n".join(lines), encoding="utf-8")
