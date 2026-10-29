"""Can we predict supermarket (advertised) prices 2 and 4 weeks ahead? Walk-forward test of the model in
pipeline/grocery_forecast.py and simpler versions of it, against "no change".

Result (2026-10-30, test years 2022-2026): seasonal + gap + momentum cut the no-change error by ~15% at 2 and 4
weeks; calls of a 10%+ move came true (5%+ that way) ~71% of the time vs a ~34% base rate, steady across years and
aisles (meat at 4 weeks is weakest, ~61-64%). The site uses 2 weeks.

Run: python scripts/backtest_grocery.py
"""

import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pipeline import cpi, grocery  # noqa: E402
from pipeline import grocery_forecast as gf  # noqa: E402

TEST_YEARS = (2022, 2023, 2024, 2025, 2026)
MODELS = {"seasonal only": ("seasonal",), "gap only": ("gap",), "seasonal + gap": ("seasonal", "gap"),
          "seasonal + gap + momentum": gf.FEATS}


def main():
    data = grocery.load(grocery.rows())
    pts = gf.series(data, cpi.Deflator(cpi.load()), grocery.main_pack)
    print(f"{len(pts)} items with 100+ weeks of ads")
    for h in (2, 4):
        rows = [r for p in pts.values() for r in gf.training_rows(p, h)]
        print(f"\n=== {h} weeks ahead: {len(rows):,} item-weeks ===")
        res, base = {m: [] for m in MODELS}, []
        for year in TEST_YEARS:
            train = [r for r in rows if r["date"].year < year]
            test = [r for r in rows if r["date"].year == year]
            if len(train) < 500 or not test:
                continue
            for m, feats in MODELS.items():
                w = gf.fit(train, feats)
                res[m] += [(r, gf.predict(w, r, feats)) for r in test]
            base += test
        mae0 = statistics.mean(abs(r["y"]) for r in base)
        print(f"test item-weeks {len(base):,}; no-change error {100 * mae0:.1f}%")
        for m, pairs in res.items():
            mae = statistics.mean(abs(r["y"] - p) for r, p in pairs)
            calls = [(r, p) for r, p in pairs if abs(p) >= gf.CALL]
            right = sum(1 for r, p in calls if (r["y"] >= gf.HIT if p > 0 else r["y"] <= -gf.HIT))
            base_rate = statistics.mean(abs(r["y"]) >= gf.HIT for r in base) / 2
            print(f"  {m:28s} error {100 * mae:.1f}% ({100 * (1 - mae / mae0):+.1f}% vs no-change); calls {len(calls):,}, "
                  f"right {100 * right / max(1, len(calls)):.0f}% (base rate ~{100 * base_rate:.0f}%)")


if __name__ == "__main__":
    main()
