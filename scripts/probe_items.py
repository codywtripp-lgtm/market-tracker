"""One-off: which USDA shipping-point reports carry the new items? Runs in GitHub Actions (MARS_API_KEY lives there)."""

import collections
import csv
import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pipeline import config, usda  # noqa: E402

WANT = {"Apples", "Watermelons", "Pineapples", "Cantaloupes", "Mangoes", "Pears", "Cabbage", "Oranges", "Corn, Sweet",
        "Cauliflower", "Sweet Potatoes", "Mushrooms"}
OUT = Path("probe_output")
OUT.mkdir(exist_ok=True)


def main():
    client = usda.Client()
    reports = client._rows(client._get(f"{config.MARS}/reports", {}, (client.api_key, "")))
    rows = []
    end = dt.date.today()
    spots = [r for r in reports if "shipping point" in str(r.get("report_title", "")).lower()]
    print(len(reports), "reports,", len(spots), "shipping point")
    for r in spots:
        slug = str(r.get("slug_id"))
        tally = collections.Counter()
        fields = {}
        try:
            for s, e in ((end - dt.timedelta(days=40), end), (dt.date(2026, 3, 1), dt.date(2026, 3, 20)), (dt.date(2017, 3, 1), dt.date(2017, 3, 20))):
                got = client.mars(slug, "Report Details", s, e)
                for x in got:
                    if x.get("commodity") in WANT:
                        tally[x.get("commodity"), s.year] += 1
                        fields = x
        except usda.USDAError as err:
            print(slug, "failed", str(err)[:100])
            continue
        if tally:
            rows.append({"slug": slug, "title": r.get("report_title"), "in_config": slug in config.SHIPPING_POINT_REPORTS,
                         "counts": dict((f"{k[0]} {k[1]}", v) for k, v in tally.items()), "sample_keys": sorted(fields)[:40]})
    with open(OUT / "sp.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["slug", "title", "in_config", "counts", "sample_keys"])
        w.writeheader()
        w.writerows(rows)


if __name__ == "__main__":
    main()
