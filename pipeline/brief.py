"""What the site says about each item, in trade terms: headline pack per market, season status,
two-week direction (firming / softening / steady) and what to do about it.

Reads the export files (latest prices vs. usual, forecasts, report card). pipeline/board.py lays
the result out as the website's pages. Rules for the calls: docs/brief.md
"""

import csv
import datetime as dt
import html
import json
import math
import re

from . import store

EXPORT = store.DATA / "export"

MARKETS = ["New York", "Los Angeles", "Chicago"]
MOVE = 0.05  # forecast change that counts as "rising" / "falling"
SUPPLY_NOTE = 15  # shipments vs. last year worth mentioning, %

PRODUCE_NAMES = {
    "Avocados": "Avocados", "Bananas": "Bananas", "Blueberries": "Blueberries", "Broccoli": "Broccoli",
    "Carrots": "Carrots", "Celery": "Celery", "Cucumbers": "Cucumbers", "Grapes": "Grapes",
    "Lemons": "Lemons", "Lettuce, Iceberg": "Iceberg", "Lettuce, Romaine": "Romaine", "Limes": "Limes",
    "Onions, Dry": "Onions", "Peppers, Bell Type": "Bell peppers", "Potatoes": "Potatoes",
    "Strawberries": "Strawberries", "Tomatoes": "Tomatoes", "Tomatoes, Plum Type": "Roma tomatoes",
}


def _read(name):
    path = EXPORT / name
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _json(name, default):
    path = EXPORT / name
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def _num(s):
    try:
        v = float(s)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(v) else v


def esc(s):
    return html.escape(str(s or ""), quote=True)


def money(v):
    if v is None:
        return "—"
    return f"${v:,.0f}" if v >= 100 else f"${v:,.2f}"


def whole(v):
    return f"${v:,.0f}" if v >= 10 else f"${v:,.2f}"


def day(d):
    return f"{d.strftime('%B')} {d.day}"


def pack(s):
    """'Seedless, 40 lb cartons, 175s' from USDA's 'SEEDLESS TYPE' / '40 lb cartons' / '175s'."""
    bits = [s.get("variety", ""), s.get("properties", ""), s.get("pack_size", ""), s.get("item_size", "")]
    bits = [re.sub(r"\s+TYPE$", "", b).lower() if b.isupper() else b for b in bits if b and b not in ("N/A", "NA")]
    text = ", ".join(bits)
    return text[:1].upper() + text[1:]


# Produce is bought for daily need, so "wait" is not an option. What a buyer can change is how
# deep to buy (only for items that hold in the cooler), whether to lock price with a supplier or
# stay on the open market, customer quotes, specials, and size / pack specs.
#
# Approximate storage life at the recommended temperature, from USDA Agriculture Handbook 66
# (Commercial Storage of Fruits, Vegetables...) as tabulated by the Engineering ToolBox storage
# table. Carrots = mature topped (the pack the terminals quote). An item "stores" only if even the
# LOW end is 4+ weeks, so buying a few days deeper is safe after time already spent in transit.
STORAGE_LIFE = {  # commodity -> (low end in weeks, as printed)
    "Avocados": (2, "2–4 weeks"), "Bananas": (1, "1–4 weeks green"), "Blueberries": (2, "about 2 weeks"),
    "Broccoli": (1.5, "10–14 days"), "Carrots": (30, "7–9 months"), "Celery": (8, "2–3 months"),
    "Cucumbers": (1.5, "10–14 days"), "Grapes": (2, "2–8 weeks"), "Lemons": (4, "1–6 months"),
    "Limes": (6, "6–8 weeks"), "Lettuce, Iceberg": (2, "2–3 weeks"), "Lettuce, Romaine": (2, "2–3 weeks"),
    "Onions, Dry": (4, "1–8 months"), "Peppers, Bell Type": (2, "2–3 weeks"), "Potatoes": (20, "5–10 months"),
    "Strawberries": (0.5, "3–7 days"), "Tomatoes": (0.5, "4–7 days ripe"), "Tomatoes, Plum Type": (0.5, "4–7 days ripe"),
}
STORES_WEEKS = 4


def stores(commodity):
    return STORAGE_LIFE.get(commodity, (0, ""))[0] >= STORES_WEEKS


def direction(change, stable):
    if stable or change is None or abs(change) < MOVE:
        return "steady"
    return "firming" if change > 0 else "softening"


def call(status, change, stable, commodity=""):
    """(market direction, what to do about it) in trade terms."""
    d = direction(change, stable)
    if d == "firming":
        first = (f"It stores ({STORAGE_LIFE[commodity][1]} cold): buy a few days deeper now," if stores(commodity)
                 else "Buy to need (it won't hold), but")
        return d, (f"{first} lock price with your supplier where you can, and update customer quotes "
                   "before it moves.")
    if d == "softening":
        return d, ("Keep inventory tight and stay on the open market; don't lock price at today's level."
                   + (" Relief is coming on a high market." if status == "expensive" else ""))
    if status == "expensive":
        return d, ("High for the season with no relief in sight. Look at other counts or packs, "
                   "and price quotes to cover it.")
    if status == "cheap":
        return d, "Good value for the season: a good item to feature on specials and promotions."
    return d, ""


def headline_items(latest, series, forecasts, card):
    """One row per commodity x terminal market: the headline (main trade pack) series, else best-covered."""
    best = {}
    for r in latest:
        if r["market_type"] != "terminal" or r["market"] not in MARKETS or r["commodity"] not in PRODUCE_NAMES:
            continue
        s = series.get(r["series_id"], {})
        key = (r["commodity"], r["market"])
        cov = (s.get("headline") == "Y", _num(s.get("coverage_last_year")) or 0)
        if key not in best or cov > best[key][0]:
            best[key] = (cov, r, s)
    items = []
    for (commodity, market), (_, r, s) in best.items():
        price = _num(r["compare_price"])
        fc = forecasts.get(r["series_id"], {})
        week = dt.date.fromisoformat(r["week_start"])
        # "next two weeks" = the forecast for the week after the coming one (2 weeks past the last full week)
        target = (week + dt.timedelta(weeks=2)).isoformat()
        point = next((p for p in fc.get("points", []) if p["week"] == target), None)
        stable = card.get((commodity, market), {}).get("uses") == "no change"
        change = (point["mid"] / price - 1) if point and price else None
        items.append({
            "series_id": r["series_id"], "commodity": commodity, "name": PRODUCE_NAMES[commodity], "market": market, "pack": pack(s),
            "price": price, "vs_norm": _num(r["pct_vs_norm"]), "status": r["status"],
            "pctile": _num(r["percentile"]), "week": week, "points": fc.get("points", []),
            "vs_4w": _num(r["pct_vs_4_weeks_ago"]), "range": (point["lo"], point["hi"]) if point else None,
            "change": 0.0 if stable and point else change, "stable": stable,
            **(dict(zip(("dir", "action"), call(r["status"], change, stable, commodity)))
               if point else {"dir": "", "action": ""}),
        })
    return items


def daily_moves(items):
    """Latest market day across the headline series, and the items that moved >= MOVE since their previous quote."""
    want = {i["series_id"]: i for i in items}
    days = {}
    for r in _read("prices_daily_365.csv"):
        if r["series_id"] in want and _num(r["compare_price"]) is not None:
            days.setdefault(r["series_id"], []).append((r["date"], _num(r["compare_price"]), r.get("market_tone", "")))
    if not days:
        return None, []
    as_of = max(max(d)[0] for d in days.values())
    moves = []
    for sid, d in days.items():
        d.sort()
        if len(d) < 2 or d[-1][0] != as_of or not d[-2][1]:
            continue
        chg = d[-1][1] / d[-2][1] - 1
        if abs(chg) >= MOVE:
            moves.append({**want[sid], "today": d[-1][1], "before": d[-2][1], "day_change": chg, "tone": d[-1][2]})
    moves.sort(key=lambda m: (MARKETS.index(m["market"]), -abs(m["day_change"])))
    return dt.date.fromisoformat(as_of), moves


def vs_usual(v):
    if v is None:
        return "—"
    if abs(v) < 5:
        return "about usual"
    return f"{abs(round(v))}% {'above' if v > 0 else 'below'}"


def weekly_history(items, weeks=12):
    """series_id -> last `weeks` weekly prices [(week, price)] for the sparklines."""
    want = {i["series_id"] for i in items}
    hist = {}
    for r in _read("prices_weekly.csv"):
        if r["series_id"] in want and _num(r["compare_price"]) is not None:
            hist.setdefault(r["series_id"], []).append((r["week_start"], _num(r["compare_price"])))
    return {sid: sorted(v)[-weeks:] for sid, v in hist.items()}


# ---------- other counts of the same pack ----------
def size_options(latest, series):
    """(commodity, market) -> [(count, size, price per piece)] when a market quotes the same pack in 2+ counts.

    Buyers can often spec a different count (48s or 60s avocados, 175s or 200s limes), so the
    brief shows the case price for each count side by side.
    """
    groups = {}
    for r in latest:
        s_ = series.get(r["series_id"], {})
        size, price = s_.get("item_size", ""), _num(r["compare_price"])
        m = re.search(r"(\d+)s\b", size) or re.search(r"(\d+) dozen", size)
        if r["market_type"] != "terminal" or not m or not price:
            continue
        count = int(m.group(1)) * (12 if "dozen" in size else 1)
        key = (r["commodity"], r["market"], s_.get("variety", ""), s_.get("pack_size", ""))
        label = size.replace("film bags ", "").replace("film wrapped", "").strip()
        groups.setdefault(key, []).append((count, label, price / count))
    out = {}
    for (c, mkt, _, _), opts in groups.items():
        if len({n for n, _, _ in opts}) >= 2:
            out.setdefault((c, mkt), sorted(opts))
    return out
