"""How much of a headline wholesale price, and its moves, comes from which growing areas USDA quoted that day?

Run: python scripts/audit_origin_mix.py
"""

import csv
import statistics
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pipeline import export, store  # noqa: E402


def main():
    head = {r["series_id"] for r in csv.DictReader(open(export.EXPORT / "series.csv", encoding="utf-8"))
            if r["headline"] == "Y" and r["market_type"] == "terminal"}
    grouped = export.load(r for r in store.iter_all() if r["market_type"] == "terminal")
    days = two = wide = 0
    moves = same_big = mix_big = 0
    per = {}
    latest = []
    for key, by_day in grouped.items():
        sid = export.series_id(key)
        if sid not in head:
            continue
        d_days = d_two = d_wide = 0
        prev = None
        big_same = big_mix = 0
        for d, rs in sorted(by_day.items()):
            if d < "2021-01-01":
                continue
            by_origin = defaultdict(list)
            for r in rs:
                p = export.fnum(r["unit_price"])
                if p is not None:
                    by_origin[r["origin"] or "?"].append(p)
            if not by_origin:
                continue
            o = {k: statistics.median(v) for k, v in by_origin.items()}
            price = statistics.median(p for v in by_origin.values() for p in v)
            days += 1
            d_days += 1
            if len(o) >= 2:
                two += 1
                d_two += 1
                if max(o.values()) / min(o.values()) >= 1.10:
                    wide += 1
                    d_wide += 1
            if prev:
                moves += 1
                if abs(price / prev[0] - 1) >= 0.10:
                    shared = set(o) & set(prev[1])
                    own = statistics.median(o[k] / prev[1][k] - 1 for k in shared) if shared else None
                    if set(o) != set(prev[1]) and (own is None or abs(own) < 0.05):
                        mix_big += 1
                        big_mix += 1
                    else:
                        same_big += 1
                        big_same += 1
            prev = (price, o)
        c0 = next(r for rs in by_day.values() for r in rs)
        per[(c0["commodity"], c0["market"])] = (d_days, d_two, d_wide, big_same, big_mix)
        last = max(by_day)
        o = defaultdict(list)
        for r in by_day[last]:
            p = export.fnum(r["unit_price"])
            if p is not None:
                o[r["origin"] or "?"].append(p)
        if len(o) >= 2:
            latest.append((c0["commodity"], c0["market"], last, {k: round(statistics.median(v), 2) for k, v in o.items()}))
    print(f"headline days since 2021: {days}; 2+ areas quoted {two / days:.0%}; areas 10%+ apart {wide / days:.0%}")
    print(f"day moves of 10%+: {same_big + mix_big} of {moves}; from a change in which areas were quoted, with quoted areas under 5%: {mix_big} "
          f"({mix_big / max(1, same_big + mix_big):.0%})")
    print("\nby item, market: days, % with 2+ areas, % areas 10%+ apart, real big moves, mix-only big moves")
    for k, (a, b, c, s, m) in sorted(per.items(), key=lambda kv: -kv[1][2] / max(1, kv[1][0])):
        print(f"  {k[0][:20]:20s} {k[1][:11]:11s} {a:5d} {b / a:4.0%} {c / a:4.0%} {s:4d} {m:4d}")
    print("\nlatest day with 2+ areas")
    for x in latest:
        print(" ", x)


if __name__ == "__main__":
    main()
