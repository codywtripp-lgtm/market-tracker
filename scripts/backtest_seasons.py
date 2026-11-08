"""Replay the changeover calendar (pipeline/seasons.py) weekly over past years: did each "usually starts" area start,
and each "usually finishes" area stop, within two weeks of the week named?

    python scripts/backtest_seasons.py 2022 2025
"""
import datetime as dt
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pipeline import board, config, seasons  # noqa: E402

lo, hi = (int(a) for a in sys.argv[1:3]) if len(sys.argv) > 2 else (2022, 2025)
items = {config.base(c) for c in board.PAGES}
seen = seasons.scan(dt.date(hi + 1, 12, 31))
seen = {k: v for k, v in seen.items() if k[0] in items}
tally, errs = Counter(), Counter()
d = dt.date(lo, 1, 5)
while d.year <= hi:
    past = {k: {w for w in v if w <= seasons.week_key(d)} for k, v in seen.items()}
    for c, evs in seasons.events(past, d).items():
        for e in evs:
            weeks = seen[(c, e["area"])]
            span = [seasons.week_key(e["week"] + dt.timedelta(weeks=j)) for j in range(-2, 3)]
            if e["kind"] == "start":
                upto = [seasons.week_key(d + dt.timedelta(weeks=j)) for j in range(1, 8)]
                first = next((j + 1 for j, w in enumerate(upto) if w in weeks), None)
                ok = any(w in weeks for w in span[1:]) or (first is not None and first <= (e["week"] - d).days // 7 + 2)
            else:
                after = [seasons.week_key(e["week"] + dt.timedelta(weeks=j)) for j in (2, 3)]
                ok = not any(w in weeks for w in after)
            tally[(e["kind"], ok)] += 1
            if not ok:
                errs[(c, e["area"], e["kind"])] += 1
    d += dt.timedelta(weeks=1)
for kind in ("start", "finish"):
    n = tally[(kind, True)] + tally[(kind, False)]
    print(f"{kind}: {tally[(kind, True)]} of {n} right ({100 * tally[(kind, True)] / max(n, 1):.0f}%)")
print("most misses:", errs.most_common(12))
