"""The "usual" price for a week: same ISO week +/- 2 in earlier years (at least 3 years), in today's dollars.

Shared by the site builder (chart JSON) and the item pages (usual range drawn behind the price).
"""

import statistics
from collections import defaultdict

WEEK_WINDOW = 2
MIN_YEARS = 3


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
