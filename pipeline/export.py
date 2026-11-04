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
FRESH_DAYS = 21        # a terminal headline must have been quoted this recently, if anything else has
MIN_COVERAGE_FRESH = 0.25  # a pack that replaced a stopped one has less than a year behind it
NORM_WEEK_WINDOW = 2   # seasonal norm uses the same ISO week +/- this many weeks
MIN_NORM_YEARS = 3     # need this many prior years for a seasonal norm
MAIN_AREA_DAYS = 28    # how far back to look when choosing a series' main growing area

# The pack the trade actually prices each item by (owner: "use the stuff with
# the big volume"). Field -> regex on the terminal row; the best-covered matching series in each market is
# the headline. Without a spec, or if no matching series is reported enough, the best-covered
# conventional series is used. Owner can correct any of these.
MAIN_PACK = {
    "Onions, Dry": {"variety": r"^YELLOW$", "pack_size": r"^50 lb sacks$", "item_size": r"^jumbo$"},
    "Potatoes": {"variety": r"^RUSSET$", "pack_size": r"^50 lb cartons$", "item_size": r"^(70|80)s$"},
    "Peppers, Bell Type": {"pack_size": r"^1 1/9 bushel cartons$", "item_size": r"^(jumbo|extra large)$",
                           "properties": r"^Green$"},
    "Tomatoes": {"variety": r"^MATURE GREENS$", "pack_size": r"^25 lb cartons loose$",
                 "item_size": r"^(5x6 size|extra large)$"},
    "Bananas": {"variety": r"^$", "pack_size": r"^40 lb cartons", "properties": r"^(|Yellow)$"},
    "Cucumbers": {"variety": r"^$", "pack_size": r"^1 1/9 bushel cartons$"},
    "Broccoli": {"variety": r"^$", "pack_size": r"^cartons$", "item_size": r"^bunched 14s$"},
    "Lettuce, Iceberg": {"item_size": r"24s"},
    "Carrots": {"variety": r"^(|TOPPED)$", "pack_size": r"^(25|50) lb sacks loose$", "item_size": r"^jumbo$"},
    "Blueberries": {"pack_size": r"1-pint"},
    "Avocados": {"pack_size": r"^cartons 2 layer$", "item_size": r"^48s$"},  # owner
    # 140s: quoted about daily in all three markets, and the size Sunkist's foodservice costing uses
    "Lemons": {"pack_size": r"^7/10 bushel cartons$", "item_size": r"^140s$"},
    # 200s: quoted daily in all three markets, the most lots overall, and the case foodservice sellers list
    "Limes": {"pack_size": r"^40 lb cartons$", "item_size": r"^200s$"},
    "Grapes": {"variety": r"^WHITE SEEDLESS", "pack_size": r"^18-19 lb containers bagged$"},
}
# Where a market trades something else. LA quotes mature greens under 4 months a year; vine ripes in 2-layer cartons
# are quoted daily. LA quotes 6-oz blueberries daily, pints about a quarter of the time.
MAIN_PACK_MARKET = {
    ("Tomatoes", "Los Angeles"): {"variety": r"^VINE RIPES$", "pack_size": r"^cartons 2 layer$", "item_size": r"^5x5s$",
                                  "properties": r"^Light Red-red$"},
    ("Blueberries", "Los Angeles"): {"pack_size": r"6-oz", "item_size": r"^medium-large$"},
}
# USDA splits these by type as growing areas rotate through the season (yellow onions: Hybrid / Spanish /
# Grano / Globe; russets: Norkotah / Burbank; mature greens: Light Red / Light Red-red). The trade quotes
# them as one item, so the type is dropped from the series and same-day quotes are combined (median).
# USDA's 18 lb (imports) and 19 lb (California) grape containers are one trade pack; split, each sits idle half the year.
MERGE_PACKS = {"Grapes": (r"^(18|19) lb containers bagged$", "18-19 lb containers bagged")}
MERGE_TYPES = {"Onions, Dry": r"^YELLOW$", "Potatoes": r"^RUSSET$", "Tomatoes": r"^MATURE GREENS$"}

# Rows describing off-grade or premium product are excluded from headline prices.
NON_STANDARD = re.compile(r"fair|poor|ordinary|holdover|decay|damage|scar|fine|mixed condition", re.I)


def canon(v):
    """USDA switched case on 2024-04-23 ("GREEN" -> "Green", a few weeks of "green" before that), which
    split 10-year series in two. Variety and properties are matched as 'Green', 'Light red-red'."""
    v = (v or "").strip()
    return v[:1].upper() + v[1:].lower()


def series_key(r):
    """Identity of a price series. Origin is deliberately NOT part of it (it rotates by season)."""
    mt = r["market_type"]
    if mt in ("terminal", "shipping point"):
        variety = canon(r["variety"])
        merge = mt == "terminal" and re.search(MERGE_TYPES.get(r["commodity"], "(?!)"), variety, re.I)
        rx, merged = MERGE_PACKS.get(r["commodity"], ("(?!)", ""))
        pack = merged if mt == "terminal" and re.search(rx, r["pack_size"]) else r["pack_size"]
        return (mt, r["market"], r["commodity"], variety, pack, r["item_size"],
                "" if merge else canon(r["properties"]), r["organic"])
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


def is_main_pack(key):
    """Terminal series that is the trade's main pack for its commodity (conventional only)."""
    _, market, commodity, variety, pack, size, prop, organic = key
    if organic in ("Y", "Yes"):
        return False
    spec = MAIN_PACK_MARKET.get((commodity, market), MAIN_PACK.get(commodity, {}))
    fields = {"variety": variety, "pack_size": pack, "item_size": size, "properties": prop}
    return all(re.search(rx, fields[f] or "", re.I) for f, rx in spec.items())


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

    fresh_from = (today - dt.timedelta(days=FRESH_DAYS)).isoformat()

    def stale(key):
        return max(grouped[key]) < fresh_from

    def weight(key, field):
        return sum(fnum(r[field]) or 0 for d, rs in grouped[key].items() if d >= year_ago for r in rs)

    chosen = {}  # insertion order: the first pick per bucket is its headline
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
            if mt == "terminal":  # main pack first, then conventional, then coverage
                ranked = sorted(keys, key=lambda k: (not is_main_pack(k), k[7] in ("Y", "Yes"), stale(k), -coverage(k)))
            else:
                ranked = sorted(keys, key=lambda k: -coverage(k))
            picks = [k for k in ranked if coverage(k) >= floor][:top]
            if mt == "terminal" and (not picks or stale(picks[0])):  # USDA stopped quoting that pack
                fresh = [k for k in ranked if not stale(k) and k[7] not in ("Y", "Yes") and coverage(k) >= MIN_COVERAGE_FRESH]
                picks = (fresh[:1] + picks)[:top]
            if mt == "terminal":  # a current main pack beats a better-covered other pack (LA white seedless grapes vs red)
                main = [k for k in ranked if is_main_pack(k) and not stale(k) and k[7] not in ("Y", "Yes") and coverage(k) >= MIN_COVERAGE_FRESH]
                picks = (main[:1] + [k for k in picks if k not in main[:1]])[:top]
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


def load_shipments():
    """(commodity, Monday, origin) -> pounds shipped that week, from USDA movement reports. The same shipment can be in
    two reports, so it counts once, as in pipeline/volumes.py."""
    same = {}
    for r in store.iter_all("movement"):
        lb = fnum(r["volume"])
        if lb and r["origin"]:
            key = (r["report_date"], r["commodity"], r["variety"], r["organic"], r["market"], r["origin"], r["other_attributes"])
            same[key] = max(same.get(key, 0), lb)
    out = defaultdict(float)
    for (d, commodity, _, _, _, origin, _), lb in same.items():
        out[commodity, iso_week_start(dt.date.fromisoformat(d)), origin.split("-")[0]] += lb
    return out


def shipped_before(shipments, commodity, area, day):
    """Pounds from `area` in the four full weeks before `day`. 'Idaho-Oregon' counts both; 'California' covers the
    reports' California-South and California-Central. Areas the reports leave out read zero."""
    week = iso_week_start(day)
    return sum(shipments.get((commodity, week - dt.timedelta(weeks=n), part), 0) for part in area.split("-") for n in range(1, 5))


def main_areas(by_day, shipped=None):
    """date -> the day's main growing area: of the areas quoted that day, the one quoted on the most of the previous
    MAIN_AREA_DAYS days. USDA often quotes several every day, so ties go to the most pounds shipped (shipped(area, day)),
    then yesterday's area, then the lower price. The movement reports leave some areas out (California carrots), so a
    tied area with no pounds wins if it was quoted the most over the past year. Areas can sit far apart (New York romaine on 2026-11-03: California $60,
    New Jersey $41), so a median across them is a price nobody quoted.
    scripts/backtest_main_area.py: forecasts are as accurate on this price as on the median."""
    out, seen, year, lead = {}, [], [], None
    for d, rows in sorted(by_day.items()):
        day = dt.date.fromisoformat(d)
        seen = [(q, areas) for q, areas in seen if (day - q).days <= MAIN_AREA_DAYS]
        year = [(q, areas) for q, areas in year if (day - q).days <= 365]
        counts = defaultdict(int)
        for _, areas in seen:
            for a in areas:
                counts[a] += 1
        prices = defaultdict(list)
        for r in rows:
            prices[r["origin"]].append(fnum(r["unit_price"]))
        tied = [a for a in prices if counts[a] == max(counts[b] for b in prices)]
        quoted = {a: sum(a in areas for _, areas in year) for a in tied}
        unlisted = {a for a in tied if shipped and not shipped(a, day) and quoted[a] and quoted[a] == max(quoted.values())}
        lead = min(prices, key=lambda a: (-counts[a], a not in unlisted, -(shipped(a, day) if shipped else 0), a != lead,
                                          statistics.median(prices[a])))
        out[d] = lead
        seen.append((day, set(prices)))
        year.append((day, set(prices)))
    return out


def quote_range(rows):
    """Every row's low and high; USDA leaves the high blank on a one-price quote, and that price still counts."""
    lows = [fnum(r["low_price"]) if fnum(r["low_price"]) is not None else fnum(r["unit_price"]) for r in rows]
    highs = [fnum(r["high_price"]) if fnum(r["high_price"]) is not None else low for r, low in zip(rows, lows)]
    return lows, highs


def areas_text(rows):
    """'California:60:60;New Jersey:40:42': each area's low and high that day, for the site."""
    by_area = defaultdict(list)
    for r in rows:
        by_area[r["origin"]].append(r)
    parts = []
    for area, rs in sorted(by_area.items()):
        lows, highs = quote_range(rs)
        parts.append(f"{area}:{min(lows)}:{max(highs)}")
    return ";".join(parts)


def daily_value(rows, area=None):
    """One value per series per day: the median quote from `area`, or across all rows without one."""
    every = rows
    if area is not None:
        rows = [r for r in rows if r["origin"] == area]
    price = statistics.median(fnum(r["unit_price"]) for r in rows)
    norms = [fnum(r["normalized_price"]) for r in rows if fnum(r["normalized_price"]) is not None]
    lows, highs = quote_range(rows)
    mostly_lows = [fnum(r["mostly_low_price"]) for r in rows if fnum(r["mostly_low_price"]) is not None]
    mostly_highs = [fnum(r["mostly_high_price"]) for r in rows if fnum(r["mostly_high_price"]) is not None]
    origins = sorted({r["origin"] for r in rows if r["origin"]})
    # USDA reporter's read of the market ("MARKET ABOUT STEADY", "Slightly Higher"); most common that day
    tones = [r["market_tone"] for r in rows if r["market_tone"]]
    return {
        "price": round(price, 4),
        "normalized_price": round(statistics.median(norms), 4) if norms else "",
        "low": min(lows) if lows else "",
        "high": max(highs) if highs else "",
        "mostly_low": min(mostly_lows) if mostly_lows else "",
        "mostly_high": max(mostly_highs) if mostly_highs else "",
        "origins": "; ".join(origins),
        "area": area or "",
        "areas": areas_text(every) if area is not None else "",
        "quotes": len(every),
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
        return {"seasonal_norm": "", "usual_low": "", "usual_high": "", "pct_vs_norm": "", "percentile": "",
                "status": "not enough history",
                "years_of_history": len(years)}
    norm = statistics.median(history)
    # mid-rank percentile: ties count half, so a flat history reads as 50th, not 0th
    pct = (sum(1 for h in history if h < value) + 0.5 * sum(1 for h in history if h == value)) / len(history)
    status = "cheap" if pct <= 0.25 else "expensive" if pct >= 0.75 else "normal"
    ranked = sorted(history)
    # the usual range: the middle half of past years, the same cutoffs that decide cheap / normal / expensive
    low, high = ranked[round(0.25 * (len(ranked) - 1))], ranked[round(0.75 * (len(ranked) - 1))]
    return {"seasonal_norm": round(norm, 4), "usual_low": round(low, 2), "usual_high": round(high, 2), "pct_vs_norm": round((value / norm - 1) * 100, 1) if norm else "",
            "percentile": round(pct * 100), "status": status, "years_of_history": len(years)}


def build(rows, today=None, deflator=None, shipments=None):
    today = today or dt.date.today()
    deflator = deflator or cpi.Deflator({})
    grouped = load(rows)
    chosen = select(grouped, today)

    series_rows, daily_rows, weekly_rows, latest_rows = [], [], [], []
    cutoff = (today - dt.timedelta(days=365)).isoformat()
    headline, seen = set(), set()
    for key in chosen:  # first pick per commodity x market (terminal) is what the site and brief show
        if key[0] == "terminal" and key[1:3] not in seen:
            seen.add(key[1:3])
            headline.add(key)
    for key, cov in sorted(chosen.items()):
        sid = series_id(key)
        mt, market, commodity, variety, pack, size, prop, organic = key
        any_row = next(iter(next(iter(grouped[key].values()))))
        base = {"series_id": sid, "commodity": commodity, "market": market, "market_type": mt}

        shipped = (lambda area, day, c=commodity: shipped_before(shipments, c, area, day)) if shipments else None
        leads = main_areas(grouped[key], shipped) if mt == "terminal" else {}
        by_day = {d: daily_value(rs, leads.get(d)) for d, rs in sorted(grouped[key].items())}
        # Compare in the trade's own unit (per case/package, $/cwt, ...): a series is one pack and
        # count, so per-lb conversion adds nothing and depends on assumed weights.
        unit = any_row["price_unit"]

        series_rows.append({**base, "label": label(key), "variety": variety, "pack_size": pack,
                            "item_size": size, "properties": prop, "organic": organic,
                            "price_unit": any_row["price_unit"], "compare_unit": unit,
                            "coverage_last_year": cov, "headline": "Y" if key in headline else "",
                            "first_date": min(by_day), "last_date": max(by_day)})

        weekly = defaultdict(list)
        for d, v in by_day.items():
            value = v["price"]
            weekly[iso_week_start(dt.date.fromisoformat(d))].append(value)
            if d >= cutoff:
                daily_rows.append({**base, "date": d, "price": v["price"], "price_unit": any_row["price_unit"],
                                   "compare_price": value, "compare_unit": unit, "low": v["low"],
                                   "high": v["high"], "mostly_low": v["mostly_low"], "mostly_high": v["mostly_high"],
                                   "area": v["area"], "areas": v["areas"],
                                   "normalized_price": v["normalized_price"],
                                   "normalized_unit": any_row["normalized_unit"],
                                   "origins": v["origins"], "quotes": v["quotes"],
                                   "market_tone": v["market_tone"]})
        weekly_avg = {w: round(statistics.mean(vs), 4) for w, vs in weekly.items()}
        # Same prices in today's dollars (CPI food at home), for fair multi-year comparisons.
        weekly_real = {w: round(v * deflator.factor(w.isoformat()), 4) for w, v in weekly_avg.items()}
        for w, v in sorted(weekly_avg.items()):
            weekly_rows.append({**base, "week_start": w.isoformat(), "compare_price": v, "last_price": weekly[w][-1],
                                "real_compare_price": weekly_real[w], "compare_unit": unit,
                                "days": len(weekly[w])})

        last_week = max(weekly_avg)
        if (today - last_week).days <= 14:  # skip series that stopped reporting
            value = weekly_avg[last_week]
            last_day = max(by_day)
            last_price = by_day[last_day]["price"]
            prev = weekly_avg.get(last_week - dt.timedelta(weeks=4))
            yago = weekly_avg.get(last_week - dt.timedelta(weeks=52))
            latest_rows.append({**base, "label": label(key), "week_start": last_week.isoformat(),
                                "compare_price": value, "compare_unit": unit, "last_price": last_price,
                                "last_date": last_day, "area": by_day[last_day]["area"],
                                "pct_vs_4_weeks_ago": round((value / prev - 1) * 100, 1) if prev else "",
                                "pct_vs_last_year": round((value / yago - 1) * 100, 1) if yago else "",
                                **seasonal_status(weekly_real, last_week, last_price * deflator.factor(last_day))})

    base_f = ["series_id", "commodity", "market", "market_type"]
    write_csv(EXPORT / "series.csv", base_f + ["label", "variety", "pack_size", "item_size", "properties",
              "organic", "price_unit", "compare_unit", "coverage_last_year", "headline", "first_date", "last_date"],
              series_rows)
    write_csv(EXPORT / "prices_daily_365.csv", base_f + ["date", "price", "price_unit", "compare_price",
              "compare_unit", "low", "high", "mostly_low", "mostly_high", "area", "areas", "normalized_price", "normalized_unit", "origins", "quotes", "market_tone"],
              daily_rows)
    write_csv(EXPORT / "prices_weekly.csv", base_f + ["week_start", "compare_price", "last_price", "real_compare_price",
              "compare_unit", "days"], weekly_rows)
    write_csv(EXPORT / "latest.csv", base_f + ["label", "week_start", "compare_price", "compare_unit", "last_price", "last_date", "area",
              "seasonal_norm", "usual_low", "usual_high", "pct_vs_norm", "percentile", "status", "years_of_history",
              "pct_vs_4_weeks_ago", "pct_vs_last_year"],
              sorted(latest_rows, key=lambda r: (r["pct_vs_norm"] == "", r["pct_vs_norm"] or 0)))
    return {"series": len(series_rows), "daily": len(daily_rows), "weekly": len(weekly_rows),
            "latest": len(latest_rows)}


def main():
    counts = build(store.iter_all(), deflator=cpi.Deflator(cpi.load()), shipments=load_shipments())
    print("export:", counts)


if __name__ == "__main__":
    main()
