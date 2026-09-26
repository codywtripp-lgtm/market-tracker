"""Build the flat files that Tableau Public and the website read.

    python -m pipeline.export

Reads data/raw/**, picks "headline" series, and writes data/export/:

  series.csv                one row per headline series (what it is, how often it's reported)
  prices_daily_365.csv      daily price per series, last 365 days
  prices_weekly.csv         weekly average per series, full history (for seasonality)
  latest.csv                this week vs. the seasonal norm: cheap / normal / expensive

Rules are documented in docs/export.md.
"""

import csv
import datetime as dt
import re
import statistics
from collections import defaultdict
from pathlib import Path

from . import cpi, store

EXPORT = store.DATA / "export"

TERMINAL_MARKETS = {"New York", "Los Angeles", "Chicago"}

# How many headline series to keep per group.
TOP_TERMINAL = 2       # per commodity x market
TOP_SHIPPING = 2       # per commodity
TOP_RETAIL = 2         # per commodity (National, conventional)
TOP_BEEF_CUTS = 12     # by pounds traded, plus both cutout values
TOP_CHICKEN = 8        # by volume

MIN_COVERAGE = 0.5     # share of report days in the last year a series must appear on
MIN_COVERAGE_SHIPPING = 0.3  # shipping-point districts are seasonal (e.g. Salinas lettuce ~8 months)
NORM_WEEK_WINDOW = 2   # seasonal norm uses the same ISO week +/- this many weeks
MIN_NORM_YEARS = 3     # need this many prior years for a seasonal norm

# Rows describing off-grade or premium product are excluded from headline prices.
NON_STANDARD = re.compile(r"fair|poor|ordinary|holdover|decay|damage|scar|fine|mixed condition", re.I)


def series_key(r):
    """Identity of a price series. Origin is deliberately NOT part of it (it rotates by season)."""
    mt = r["market_type"]
    if mt in ("terminal", "shipping point"):
        return (mt, r["market"], r["commodity"], r["variety"], r["pack_size"], r["item_size"],
                r["properties"], r["organic"])
    if mt == "retail":
        return (mt, r["market"], r["commodity"], r["variety"], r["pack_size"], "", r["other_attributes"], r["organic"])
    # beef / chicken
    return (mt, r["market"], r["commodity"], r["variety"], r["pack_size"], r["item_size"], r["grade"], "")


def series_id(key):
    parts = [p for p in key if p]
    return re.sub(r"[^a-z0-9]+", "-", " ".join(parts).lower()).strip("-")[:120]


def label(key):
    mt, market, commodity, variety, pack, size, prop, organic = key
    bits = [commodity, variety, prop, pack, size, "organic" if organic in ("Y", "Yes") else ""]
    return f"{' '.join(b for b in bits if b)} — {market}"


def is_standard(r):
    return not any(NON_STANDARD.search(r[f]) for f in ("appearance", "condition", "quality"))


def fnum(s):
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def load(rows):
    """Group usable rows by series and date. Returns {key: {date: [rows]}}."""
    out = defaultdict(lambda: defaultdict(list))
    for r in rows:
        if fnum(r["unit_price"]) is None:
            continue
        mt = r["market_type"]
        if mt == "terminal" and r["market"] not in TERMINAL_MARKETS:
            continue
        if mt in ("terminal", "shipping point") and not is_standard(r):
            continue
        if mt == "retail" and (r["market"] != "National" or r["organic"] not in ("No", "N")):
            continue
        if r["commodity"] == "Chicken" and r["origin_detail"] not in ("", "Domestic"):
            continue
        out[series_key(r)][r["report_date"]].append(r)
    return out


def select(grouped, today):
    """Pick headline series. Returns {key: coverage}."""
    year_ago = (today - dt.timedelta(days=365)).isoformat()

    def calendar(key):
        # Beef is daily and chicken weekly, so wholesale calendars are per commodity.
        return (key[0], key[2] if key[0] == "wholesale" else "")

    report_days = defaultdict(set)  # calendar -> dates with any data in the last year
    for key, by_date in grouped.items():
        for d in by_date:
            if d >= year_ago:
                report_days[calendar(key)].add(d)

    def coverage(key):
        days = sum(1 for d in grouped[key] if d >= year_ago)
        total = len(report_days[calendar(key)]) or 1
        return days / total

    def weight(key, field):
        return sum(fnum(r[field]) or 0 for d, rs in grouped[key].items() if d >= year_ago for r in rs)

    chosen = {}
    buckets = defaultdict(list)
    for key in grouped:
        mt, market, commodity = key[0], key[1], key[2]
        if mt == "terminal":
            buckets[(mt, market, commodity)].append(key)
        elif mt in ("shipping point", "retail"):
            buckets[(mt, commodity)].append(key)
        else:
            buckets[(mt, commodity)].append(key)

    for bucket, keys in buckets.items():
        mt, commodity = bucket[0], bucket[-1]
        if mt in ("terminal", "shipping point"):
            top = TOP_TERMINAL if mt == "terminal" else TOP_SHIPPING
            floor = MIN_COVERAGE if mt == "terminal" else MIN_COVERAGE_SHIPPING
            ranked = sorted(keys, key=lambda k: -coverage(k))
            picks = [k for k in ranked if coverage(k) >= floor][:top]
        elif mt == "retail":
            ranked = sorted(keys, key=lambda k: -weight(k, "store_count"))
            picks = [k for k in ranked if coverage(k) >= MIN_COVERAGE][:TOP_RETAIL]
        elif commodity == "Beef":
            cutout = [k for k in keys if k[3].startswith("Cutout")]
            cuts = sorted((k for k in keys if k not in cutout), key=lambda k: -weight(k, "volume"))
            picks = cutout + [k for k in cuts if coverage(k) >= MIN_COVERAGE][:TOP_BEEF_CUTS]
        else:  # chicken
            ranked = sorted(keys, key=lambda k: -weight(k, "volume"))
            picks = [k for k in ranked if coverage(k) >= MIN_COVERAGE][:TOP_CHICKEN]
        for k in picks:
            chosen[k] = round(coverage(k), 3)
    return chosen


def daily_value(rows):
    """One value per series per day: median across quotes (several origins can quote the same pack)."""
    price = statistics.median(fnum(r["unit_price"]) for r in rows)
    norms = [fnum(r["normalized_price"]) for r in rows if fnum(r["normalized_price"]) is not None]
    lows = [fnum(r["low_price"]) for r in rows if fnum(r["low_price"]) is not None]
    highs = [fnum(r["high_price"]) for r in rows if fnum(r["high_price"]) is not None]
    origins = sorted({r["origin"] for r in rows if r["origin"]})
    # USDA reporter's read of the market ("MARKET ABOUT STEADY", "Slightly Higher"); most common that day
    tones = [r["market_tone"] for r in rows if r["market_tone"]]
    return {
        "price": round(price, 4),
        "normalized_price": round(statistics.median(norms), 4) if norms else "",
        "low": min(lows) if lows else "",
        "high": max(highs) if highs else "",
        "origins": "; ".join(origins),
        "quotes": len(rows),
        "market_tone": max(tones, key=tones.count) if tones else "",
    }


def iso_week_start(d):
    return d - dt.timedelta(days=d.weekday())


def write_csv(path, fields, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def seasonal_status(weekly, week, value):
    """Compare a week's value with the same weeks in prior years."""
    iso_year, iso_wk = week.isocalendar()[:2]
    history, years = [], set()
    for w, v in weekly.items():
        y, wk = w.isocalendar()[:2]
        dist = min(abs(wk - iso_wk), 52 - abs(wk - iso_wk))
        if y < iso_year and dist <= NORM_WEEK_WINDOW:
            history.append(v)
            years.add(y)
    if len(years) < MIN_NORM_YEARS:
        return {"seasonal_norm": "", "pct_vs_norm": "", "percentile": "", "status": "not enough history",
                "years_of_history": len(years)}
    norm = statistics.median(history)
    # mid-rank percentile: ties count half, so a flat history reads as 50th, not 0th
    pct = (sum(1 for h in history if h < value) + 0.5 * sum(1 for h in history if h == value)) / len(history)
    status = "cheap" if pct <= 0.25 else "expensive" if pct >= 0.75 else "normal"
    return {"seasonal_norm": round(norm, 4), "pct_vs_norm": round((value / norm - 1) * 100, 1) if norm else "",
            "percentile": round(pct * 100), "status": status, "years_of_history": len(years)}


def build(rows, today=None, deflator=None):
    today = today or dt.date.today()
    deflator = deflator or cpi.Deflator({})
    grouped = load(rows)
    chosen = select(grouped, today)

    series_rows, daily_rows, weekly_rows, latest_rows = [], [], [], []
    cutoff = (today - dt.timedelta(days=365)).isoformat()
    for key, cov in sorted(chosen.items()):
        sid = series_id(key)
        mt, market, commodity, variety, pack, size, prop, organic = key
        any_row = next(iter(next(iter(grouped[key].values()))))
        base = {"series_id": sid, "commodity": commodity, "market": market, "market_type": mt}

        by_day = {d: daily_value(rs) for d, rs in sorted(grouped[key].items())}
        # Compare in the trade's own unit (per case/package, $/cwt, ...): a series is one pack and
        # count, so per-lb conversion adds nothing and depends on assumed weights.
        unit = any_row["price_unit"]

        series_rows.append({**base, "label": label(key), "variety": variety, "pack_size": pack,
                            "item_size": size, "properties": prop, "organic": organic,
                            "price_unit": any_row["price_unit"], "compare_unit": unit,
                            "coverage_last_year": cov, "first_date": min(by_day), "last_date": max(by_day)})

        weekly = defaultdict(list)
        for d, v in by_day.items():
            value = v["price"]
            weekly[iso_week_start(dt.date.fromisoformat(d))].append(value)
            if d >= cutoff:
                daily_rows.append({**base, "date": d, "price": v["price"], "price_unit": any_row["price_unit"],
                                   "compare_price": value, "compare_unit": unit, "low": v["low"],
                                   "high": v["high"], "normalized_price": v["normalized_price"],
                                   "normalized_unit": any_row["normalized_unit"],
                                   "origins": v["origins"], "quotes": v["quotes"],
                                   "market_tone": v["market_tone"]})
        weekly_avg = {w: round(statistics.mean(vs), 4) for w, vs in weekly.items()}
        # Same prices in today's dollars (CPI food at home), for fair multi-year comparisons.
        weekly_real = {w: round(v * deflator.factor(w.isoformat()), 4) for w, v in weekly_avg.items()}
        for w, v in sorted(weekly_avg.items()):
            weekly_rows.append({**base, "week_start": w.isoformat(), "compare_price": v,
                                "real_compare_price": weekly_real[w], "compare_unit": unit,
                                "days": len(weekly[w])})

        last_week = max(weekly_avg)
        if (today - last_week).days <= 14:  # skip series that stopped reporting
            value = weekly_avg[last_week]
            prev = weekly_avg.get(last_week - dt.timedelta(weeks=4))
            yago = weekly_avg.get(last_week - dt.timedelta(weeks=52))
            latest_rows.append({**base, "label": label(key), "week_start": last_week.isoformat(),
                                "compare_price": value, "compare_unit": unit,
                                "pct_vs_4_weeks_ago": round((value / prev - 1) * 100, 1) if prev else "",
                                "pct_vs_last_year": round((value / yago - 1) * 100, 1) if yago else "",
                                **seasonal_status(weekly_real, last_week, weekly_real[last_week])})

    base_f = ["series_id", "commodity", "market", "market_type"]
    write_csv(EXPORT / "series.csv", base_f + ["label", "variety", "pack_size", "item_size", "properties",
              "organic", "price_unit", "compare_unit", "coverage_last_year", "first_date", "last_date"], series_rows)
    write_csv(EXPORT / "prices_daily_365.csv", base_f + ["date", "price", "price_unit", "compare_price",
              "compare_unit", "low", "high", "normalized_price", "normalized_unit", "origins", "quotes", "market_tone"],
              daily_rows)
    write_csv(EXPORT / "prices_weekly.csv", base_f + ["week_start", "compare_price", "real_compare_price",
              "compare_unit", "days"], weekly_rows)
    write_csv(EXPORT / "latest.csv", base_f + ["label", "week_start", "compare_price", "compare_unit",
              "seasonal_norm", "pct_vs_norm", "percentile", "status", "years_of_history",
              "pct_vs_4_weeks_ago", "pct_vs_last_year"],
              sorted(latest_rows, key=lambda r: (r["pct_vs_norm"] == "", r["pct_vs_norm"] or 0)))
    return {"series": len(series_rows), "daily": len(daily_rows), "weekly": len(weekly_rows),
            "latest": len(latest_rows)}


def main():
    counts = build(store.iter_all(), deflator=cpi.Deflator(cpi.load()))
    print("export:", counts)


if __name__ == "__main__":
    main()
