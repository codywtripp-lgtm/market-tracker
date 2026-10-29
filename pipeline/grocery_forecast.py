"""Two-week outlook for supermarket prices: will this item's advertised price likely drop or rise?

Tested walk-forward in scripts/backtest_grocery.py before it went on the site (2022-2026): the model cut the error
of a "no change" guess by about 15%, and when it called a move of 10% or more, the price moved at least 5% that way
about 7 times in 10, against a base rate of about 1 in 3.

Model: ridge regression on the log change over the next HORIZON weeks, fit on every item's history, from
  seasonal  median change over the same calendar window in earlier years
  gap       log(price / usual), usual = median of the same weeks (+-15 days) in earlier years: sales end and
            spikes ease, so prices far from usual tend to come back
  momentum  log change over the last 2 weeks
Prices are the item's main pack (the one the grocery pages show), store-weighted, in today's dollars.
"""

import bisect
import datetime as dt
import math
import statistics

HORIZON = 2  # weeks
MIN_STORES = 200
CALL, HIT = 0.10, 0.05  # call a move of 10%+; it counts as right if the price then moved 5%+ that way
FEATS = ("seasonal", "gap", "mom")
RECORD = {"calls": 0, "right": 0, "since": None}  # walk-forward track record, set by outlook()


def series(data, deflator, main_pack):
    """item -> [(date, log real price, stores)] for its main pack. data: grocery.load(); main_pack(packs) -> key."""
    out = {}
    for commodity, packs in data.items():
        pts = []
        for d, xs in packs[main_pack(packs)].items():
            st = sum(s for _, s in xs)
            pts.append((dt.date.fromisoformat(d), math.log(sum(p * s for p, s in xs) / st * deflator.factor(d)), st))
        pts.sort()
        if len(pts) >= 100:
            out[commodity] = pts
    return out


def _near(dates, values, when, tol=3):
    i = bisect.bisect_left(dates, when - dt.timedelta(days=tol))
    best = None
    while i < len(dates) and dates[i] <= when + dt.timedelta(days=tol):
        if best is None or abs((dates[i] - when).days) < abs((dates[best] - when).days):
            best = i
        i += 1
    return None if best is None else values[best]


def features(dates, logp, k, h=HORIZON):
    d, v = dates[k], logp[k]
    seas, pool = [], []
    for back in range(1, 11):
        then = d - dt.timedelta(days=round(365.25 * back))
        a, b = _near(dates, logp, then, 7), _near(dates, logp, then + dt.timedelta(weeks=h), 7)
        if a is not None and b is not None:
            seas.append(b - a)
        lo = bisect.bisect_left(dates, then - dt.timedelta(days=15))
        hi = bisect.bisect_right(dates, then + dt.timedelta(days=15))
        pool += logp[lo:hi]
    if len(seas) < 2 or len(pool) < 6:
        return None
    prev = _near(dates, logp, d - dt.timedelta(weeks=2))
    return {"date": d, "seasonal": statistics.median(seas), "gap": v - statistics.median(pool),
            "mom": (v - prev) if prev is not None else 0.0}


def training_rows(pts, h=HORIZON):
    """Every week with a known outcome h weeks later (both weeks with MIN_STORES+ stores)."""
    dates, logp, stores = [p[0] for p in pts], [p[1] for p in pts], [p[2] for p in pts]
    out = []
    for k in range(len(pts)):
        if stores[k] < MIN_STORES:
            continue
        when = dates[k] + dt.timedelta(weeks=h)
        fut, fut_st = _near(dates, logp, when), _near(dates, stores, when)
        if fut is None or (fut_st or 0) < MIN_STORES:
            continue
        f = features(dates, logp, k, h)
        if f:
            out.append(dict(f, y=fut - logp[k]))
    return out


def fit(rows, feats=FEATS, lam=1.0):
    """Ridge regression (intercept not penalised), solved by Gaussian elimination."""
    n = len(feats) + 1
    A = [[0.0] * n for _ in range(n)]
    b = [0.0] * n
    for r in rows:
        x = [1.0] + [r[f] for f in feats]
        for i in range(n):
            b[i] += x[i] * r["y"]
            for j in range(n):
                A[i][j] += x[i] * x[j]
    for i in range(1, n):
        A[i][i] += lam
    for c in range(n):
        piv = max(range(c, n), key=lambda r: abs(A[r][c]))
        A[c], A[piv], b[c], b[piv] = A[piv], A[c], b[piv], b[c]
        for r in range(n):
            if r != c and A[c][c]:
                f = A[r][c] / A[c][c]
                A[r] = [x - f * y for x, y in zip(A[r], A[c])]
                b[r] -= f * b[c]
    return [b[i] / A[i][i] for i in range(n)]


def predict(w, r, feats=FEATS):
    return w[0] + sum(wi * r[f] for wi, f in zip(w[1:], feats))


def track_record(rows_by_item, first_year=2022):
    """Walk-forward share of calls that came true, so the site states the number the data supports today."""
    rows = [r for rs in rows_by_item.values() for r in rs]
    calls = right = 0
    for year in sorted({r["date"].year for r in rows}):
        if year < first_year:
            continue
        train = [r for r in rows if r["date"].year < year]
        if len(train) < 500:
            continue
        w = fit(train)
        for r in (r for r in rows if r["date"].year == year):
            p = predict(w, r)
            if abs(p) >= CALL:
                calls += 1
                right += r["y"] >= HIT if p > 0 else r["y"] <= -HIT
    return {"calls": calls, "right": right, "since": first_year}


def outlook(data, deflator, main_pack, today):
    """{commodity: predicted change over HORIZON weeks}, for items advertised by MIN_STORES+ stores this week; and
    the walk-forward track record."""
    global RECORD
    pts = series(data, deflator, main_pack)
    rows = {c: training_rows(p) for c, p in pts.items()}
    every = [r for rs in rows.values() for r in rs]
    if len(every) < 500:
        RECORD = {"calls": 0, "right": 0, "since": None}
        return {}, RECORD
    w = fit(every)
    out = {}
    for c, p in pts.items():
        dates, logp = [x[0] for x in p], [x[1] for x in p]
        k = len(p) - 1
        if (today - dates[k]).days > 6 or p[k][2] < MIN_STORES:
            continue
        f = features(dates, logp, k)
        if f:
            out[c] = math.exp(predict(w, f)) - 1
    RECORD = track_record(rows)
    return out, RECORD
