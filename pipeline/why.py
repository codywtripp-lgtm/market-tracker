"""Why an item is cheap or pricey right now, from what USDA reports about supply, not from history alone.

Signals (for the produce items USDA also covers at wholesale; the rest have none):
- shipments this week vs the same weeks last year (USDA movement reports, data/export/supply.csv)
- the New York wholesale price vs usual for the season and vs 4 weeks ago (data/export/latest.csv, headline series)
- growing areas reporting very short supply (pipeline/conditions.py)

The same signals hold back a two-week call that the cause says won't happen: tested 2022-2026, "likely to drop"
calls were right 67% of the time when shipments were 20%+ below last year (76% when normal) and 72% when wholesale
was climbing (87% when it was falling); "likely to rise" calls were right 65% when wholesale was falling.
"""

import csv

from . import store

TO_RETAIL = {"Lettuce, Iceberg": "Lettuce", "Lettuce, Romaine": "Lettuce", "Tomatoes, Plum Type": None}
SHIP, WHOLE, TREND = 15, 15, 10  # percent: what counts as a real difference worth naming


def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def signals():
    """retail commodity -> {"ship": % vs last year, "whole": NY wholesale % vs usual, "trend": % vs 4 weeks ago}."""
    ex = store.DATA / "export"
    out = {}
    if (ex / "supply.csv").exists():
        with open(ex / "supply.csv", newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                c = TO_RETAIL.get(r["commodity"], r["commodity"])
                if c:
                    out.setdefault(c, {})["ship"] = _num(r["vs_last_year_pct"])
    if (ex / "series.csv").exists() and (ex / "latest.csv").exists():
        with open(ex / "series.csv", newline="", encoding="utf-8") as f:
            head = {r["series_id"] for r in csv.DictReader(f) if r["headline"] == "Y" and r["market"] == "New York"}
        with open(ex / "latest.csv", newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                c = TO_RETAIL.get(r["commodity"], r["commodity"])
                if r["series_id"] in head and c:
                    out.setdefault(c, {}).update(whole=_num(r["pct_vs_norm"]), trend=_num(r["pct_vs_4_weeks_ago"]))
    return out


def reasons(i, sig, short=False):
    """Plain-language causes behind this week's price, in the direction of the price (empty if none are clear)."""
    s, out = sig or {}, []
    ship, whole = s.get("ship"), s.get("whole")
    if i["status"] == "high":
        if short:
            out.append("growing areas are reporting very short supplies")
        if ship is not None and ship <= -SHIP:
            out.append(f"shipments are {abs(round(ship))}% below last year")
        if whole is not None and whole >= WHOLE:
            out.append(f"wholesale prices at Hunts Point are {round(whole)}% above usual")
    elif i["status"] == "low":
        if ship is not None and ship >= SHIP:
            out.append(f"shipments are {round(ship)}% above last year")
        if whole is not None and whole <= -WHOLE:
            out.append(f"wholesale prices at Hunts Point are {abs(round(whole))}% below usual")
    return out


def sentence(parts):
    if not parts:
        return ""
    s = parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " and " + parts[-1]
    return "Why: " + s + "."


def holds_back(change, sig, short=False):
    """True when the supply picture says the two-week call shouldn't be made."""
    s = sig or {}
    ship, trend = s.get("ship"), s.get("trend")
    if change < 0:  # "likely to drop", but supply is still short or wholesale is still climbing
        return short or (ship is not None and ship <= -20) or (trend is not None and trend >= TREND)
    return trend is not None and trend <= -TREND  # "likely to rise", but wholesale is falling
