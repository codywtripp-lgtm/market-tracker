"""Growing-area changeovers: which shipping areas usually start or finish in the next few weeks.

Distributor market reports (Markon, FreshPoint, Sysco) tell buyers when supply moves from one area to the next
("broccoli tight until growers move to Yuma the week of November 15"): the weeks around a changeover are when
supply gaps and price jumps happen. USDA quotes an area at shipping point only while it ships in volume, so the
weeks it was quoted in past years give each area's usual season.

An area "usually" ships in a week when USDA quoted it that week in at least SHARE of the past YEARS seasons.
"""
import csv
import datetime as dt
import glob
import re
from collections import defaultdict

from . import config

YEARS = 6          # past seasons that set the usual calendar
MIN_YEARS = 4      # an area needs this many past seasons to say "usually"
SHARE = 0.6        # quoted that week in 60%+ of past seasons = usually shipping
OFF = 0.25         # quoted in 25% or fewer = usually not shipping
AHEAD = 5          # weeks ahead to look for a start or finish
GAP = 4            # a finish means at least this many quiet weeks after it

# USDA renamed and merged some districts over the years; one name per area so a rename isn't a start and a finish
ALIASES = [
    (r"IMPERIAL|COACHELLA|PALO VERDE|WESTERN ARIZONA", "DESERT"),
    (r"^SANTA MARIA", "SANTA MARIA CALIFORNIA"),
    (r"^SAN JOAQUIN VALLEY AND KERN", "SAN JOAQUIN VALLEY CALIFORNIA"),
    (r"^CENTRAL AND SOUTHERN CALIFORNIA AND ARIZONA$|^SOUTH AND CENTRAL DISTRICT CALIFORNIA$", "CALIFORNIA CITRUS"),
]
NAMES = {"DESERT": "The desert (Yuma, Imperial, Coachella)", "CALIFORNIA CITRUS": "California and Arizona"}


def area(commodity, district):
    for pat, to in ALIASES:
        if re.search(pat, district):
            return to
    if commodity == "Grapes" and district == "KERN DISTRICT CALIFORNIA":
        return "SAN JOAQUIN VALLEY CALIFORNIA"
    return district


def week_key(d):
    y, w = d.isocalendar()[:2]
    return y, min(w, 52)  # week 53 counts as 52


def scan(today, path="data/raw/shipping_point"):
    """(commodity, area) -> {(iso year, week)} quoted, for the past YEARS + 1 years."""
    first = today.year - YEARS - 1
    seen = defaultdict(set)
    for f in sorted(glob.glob(f"{path}/*/*.csv")):
        if int(re.search(r"(\d{4})-\d\d\.csv$", f.replace("\\", "/")).group(1)) < first:
            continue
        with open(f, encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                if r["market"] and r["organic"] not in ("Y", "Yes"):
                    c = config.base(r["commodity"])
                    seen[(c, area(c, r["market"]))].add(week_key(dt.date.fromisoformat(r["report_date"])))
    return seen


def shares(weeks, today):
    """Week of year (1-52) -> share of the past YEARS seasons the area was quoted that week, or None if too new."""
    cur = week_key(today)
    years = [y for y in range(cur[0] - YEARS, cur[0]) if any((y, w) in weeks for w in range(1, 53))]
    if len(years) < MIN_YEARS:
        return None
    # a season runs from this week of one year to the same week of the next, so a winter area counts once
    out = {}
    for w in range(1, 53):
        out[w] = sum((y + (w < cur[1]), w) in weeks for y in years) / len(years)
    return out


def ahead(w, k):
    return (w - 1 + k) % 52 + 1


def week_date(today, k):
    return today - dt.timedelta(days=today.weekday()) + dt.timedelta(weeks=k)


def events(seen, today):
    """commodity -> [{"area", "kind": "start" | "finish", "week": Monday of that week}], soonest first."""
    cur = week_key(today)[1]
    recent = {week_key(today - dt.timedelta(days=d)) for d in range(0, 11)}
    out = defaultdict(list)
    for (c, a), weeks in seen.items():
        s = shares(weeks, today)
        # USDA stops reporting some areas (Michigan celery after 2023): an area must have been quoted within a year
        if not s or not weeks & {week_key(today - dt.timedelta(weeks=k)) for k in range(52)}:
            continue
        now = bool(recent & weeks)
        if not now and s[cur] <= OFF:
            k = next((k for k in range(1, AHEAD + 1) if s[ahead(cur, k)] >= SHARE), None)
            if k:
                out[c].append({"area": a, "kind": "start", "week": week_date(today, k)})
        elif now and s[cur] >= SHARE:
            k = next((k for k in range(1, AHEAD + 1)
                      if all(s[ahead(cur, k + j)] <= OFF for j in range(GAP))), None)
            if k:
                out[c].append({"area": a, "kind": "finish", "week": week_date(today, k)})
    return {c: sorted(v, key=lambda e: e["week"]) for c, v in out.items()}


def when(d):
    d += dt.timedelta(days=3)  # the middle of the week
    part = "early" if d.day <= 10 else "mid" if d.day <= 20 else "late"
    return f"{part} {d:%B}"
