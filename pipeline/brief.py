"""Daily buyer's brief, written after every nightly run (Mon-Sat, after the terminal reports).

    python -m pipeline.brief

Turns the export files (latest prices vs. usual, forecasts, alerts, shipments, track record)
into one short article for wholesale buyers: what moved today, what's cheap or expensive,
where prices are likely heading over the next two weeks, and what that means for pricing, inventory depth and specs.

Writes data/briefs/<market date>.html, an HTML fragment dated by the latest terminal-market
day in the data. scripts/build_site.py wraps each one into a page under /brief/ and an RSS feed
(which an email newsletter service can send automatically). Re-running the same day overwrites it.

Rules for the calls: docs/brief.md
"""

import csv
import datetime as dt
import html
import json
import math
import re

from . import store

EXPORT = store.DATA / "export"
OUT = store.DATA / "briefs"

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
    bits = [s.get("variety", ""), s.get("properties", ""), s.get("pack_size", ""), s.get("item_size", "")]
    return " · ".join(b for b in bits if b and b not in ("N/A", "NA"))


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
        return d, ("High for the season with no relief in sight. Check other sizes or packs below, "
                   "and price quotes to cover it.")
    if status == "cheap":
        return d, "Good value for the season: a good item to feature on specials and promotions."
    return d, ""


def headline_items(latest, series, forecasts, card):
    """One row per commodity x terminal market: the best-covered series."""
    best = {}
    for r in latest:
        if r["market_type"] != "terminal" or r["market"] not in MARKETS or r["commodity"] not in PRODUCE_NAMES:
            continue
        s = series.get(r["series_id"], {})
        key = (r["commodity"], r["market"])
        cov = _num(s.get("coverage_last_year")) or 0
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


# ---------- visual pieces (built for a reader who wants the answer at a glance) ----------
# Every color comes with an icon and a word, so nothing depends on color alone.
GROUP_HEAD = {  # market direction over the next two weeks
    "firming": ("▲", "Firming", "Expected up 5% or more within two weeks."),
    "softening": ("▼", "Softening", "Expected down 5% or more within two weeks."),
    "steady": ("=", "Steady", "No big move expected."),
}
DIR_WORD = {"firming": "▲ Firming", "softening": "▼ Softening", "steady": "Steady"}


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


def pill(status):
    icon, word = {"cheap": ("▼", "Low for season"), "expensive": ("▲", "High for season")}.get(status, ("●", "Normal"))
    cls = {"cheap": "good", "expensive": "bad"}.get(status, "neutral")
    return f'<span class="pill {cls}"><span aria-hidden="true">{icon}</span> {word}</span>'


def plain_pctile(p):
    """Where today's price ranks among the same weeks in past years, in words."""
    if p is None:
        return "Not enough history to compare yet"
    # cut-offs match the cheap / normal / high status (pipeline/export.py: 25th and 75th percentile)
    if p <= 10:
        return "Cheaper than almost every past year at this time"
    if p <= 25:
        return "Cheaper than most past years at this time"
    if p < 75:
        return "About the usual price for this time of year"
    if p < 90:
        return "Pricier than most past years at this time"
    return "Pricier than almost every past year at this time"


def meter(i):
    """Position of today's price between the cheapest and priciest past years (same weeks), with a 'usual' tick."""
    p = i["pctile"]
    if p is None:
        return ""
    cls = {"cheap": "good", "expensive": "bad"}.get(i["status"], "neutral")
    pos = min(max(p, 3), 97)
    return (f'<div class="meter" role="img" aria-label="{esc(plain_pctile(p))}">'
            f'<div class="track"><span class="usual"></span><span class="dot {cls}" style="left:{pos:.0f}%"></span></div>'
            '<div class="ends"><span>Cheapest</span><span>Usual</span><span>Priciest</span></div></div>')


def spark(hist, i):
    """Last 12 weeks (solid) and the next weeks' likely range (shaded) with its middle (dashed)."""
    if len(hist) < 3:
        return ""
    last_week = hist[-1][0]
    fut = [p for p in i["points"] if p["week"] > last_week]
    vals = [v for _, v in hist] + [p["lo"] for p in fut] + [p["hi"] for p in fut]
    lo, hi = min(vals), max(vals)
    span = (hi - lo) or 1
    n = len(hist) + len(fut)
    W, H, pad = 220, 56, 5
    x = lambda k: pad + k * (W - 2 * pad) / max(n - 1, 1)  # noqa: E731
    y = lambda v: H - pad - (v - lo) / span * (H - 2 * pad)  # noqa: E731
    line = "M" + "L".join(f"{x(k):.1f},{y(v):.1f}" for k, (_, v) in enumerate(hist))
    k0, v0 = len(hist) - 1, hist[-1][1]
    out = ""
    if fut:
        top = [(x(k0), y(v0))] + [(x(k0 + 1 + j), y(p["hi"])) for j, p in enumerate(fut)]
        bot = [(x(k0 + 1 + j), y(p["lo"])) for j, p in reversed(list(enumerate(fut)))] + [(x(k0), y(v0))]
        out += '<path class="band" d="M' + "L".join(f"{a:.1f},{b:.1f}" for a, b in top + bot) + 'Z"/>'
        out += ('<path class="mid" d="M' + f"{x(k0):.1f},{y(v0):.1f}"
                + "".join(f"L{x(k0 + 1 + j):.1f},{y(p['mid']):.1f}" for j, p in enumerate(fut)) + '"/>')
    out += f'<path class="line" d="{line}"/><circle class="now" cx="{x(k0):.1f}" cy="{y(v0):.1f}" r="4"/>'
    label = (f"{i['name']}, last 12 weeks: {money(hist[0][1])} to {money(v0)}"
             + (f"; likely {whole(fut[-1]['lo'])}–{whole(fut[-1]['hi'])} by {fut[-1]['week']}" if fut else ""))
    return (f'<svg class="spark" viewBox="0 0 {W} {H}" role="img" aria-label="{esc(label)}">'
            f"<title>{esc(label)}</title>{out}</svg>")


def outlook(i):
    if not i["range"]:
        return ""
    if i["stable"] or i["change"] is None or abs(i["change"]) < MOVE:
        icon, word, cls = "=", "Steady", "neutral"
    elif i["change"] > 0:
        icon, word, cls = "▲", "Firming", "bad"
    else:
        icon, word, cls = "▼", "Softening", "good"
    return (f'<div class="outlook"><span class="arrow {cls}" aria-hidden="true">{icon}</span>'
            f'<span><strong>Next 2 weeks: {word}</strong><br>likely {whole(i["range"][0])}–{whole(i["range"][1])} a case</span></div>')


def sizes_line(opts):
    if not opts:
        return ""
    bits = " · ".join(f"<strong>{esc(o[1])}</strong> {money(o[2] * o[0])}" for o in opts)
    return f'<div class="sizes">Case price by size today: {bits}</div>'


def item_card(i, hist, opts=None):
    return (f'<div class="item">'
            f'<div class="item-head"><div><div class="item-name">{esc(i["name"])}</div>'
            f'<div class="item-pack">{esc(i["pack"])}</div></div>'
            f'<div class="item-price">{money(i["price"])}<small>per case</small></div></div>'
            f'<div class="item-status">{pill(i["status"])} <span>{esc(plain_pctile(i["pctile"]))}</span></div>'
            f'{meter(i)}'
            f'<div class="item-trend">{spark(hist, i)}{outlook(i)}</div>'
            + (f'<p class="action">{esc(i["action"])}</p>' if i["action"] else "") +
            f'{sizes_line(opts)}'
            f'</div>')


def compact_rows(rows):
    return '<div class="rows">' + "".join(
        f'<div class="row"><span class="row-name">{esc(i["name"])}</span>'
        f'<span class="row-price">{money(i["price"])}</span>{pill(i["status"])}'
        f'<span class="row-call">{esc(DIR_WORD.get(i["dir"], ""))}'
        f'{(" · likely " + whole(i["range"][0]) + "–" + whole(i["range"][1])) if i["range"] else ""}</span></div>'
        for i in rows) + "</div>"


def build():
    latest = _read("latest.csv")
    if not latest:
        raise SystemExit("no data/export/latest.csv; run pipeline.export first")
    series = {r["series_id"]: r for r in _read("series.csv")}
    forecasts = _json("forecasts.json", {}).get("series", {})
    card = {(r["commodity"], r["market"]): r for r in _read("forecast_report_card.csv")}
    alerts = _json("alerts.json", {}).get("alerts", [])
    record = _json("track_record.json", {})
    supply = _read("supply.csv")

    items = headline_items(latest, series, forecasts, card)
    hist = weekly_history(items)
    data_week = max(dt.date.fromisoformat(r["week_start"]) for r in latest)
    as_of, today = daily_moves(items)
    as_of = as_of or data_week + dt.timedelta(days=6)
    sizes = size_options(latest, series)
    ny = [i for i in items if i["market"] == "New York" and i["dir"]]
    rank = lambda i: -abs(i["change"] or 0) - abs(i["vs_norm"] or 0) / 100  # noqa: E731
    groups = {g: sorted((i for i in ny if i["dir"] == g), key=rank) for g in GROUP_HEAD}
    value = sorted((i for i in ny if i["status"] == "cheap"), key=lambda i: i["pctile"] or 0)
    high = sorted((i for i in ny if i["status"] == "expensive"), key=lambda i: -(i["pctile"] or 0))

    parts = [
        f"<h1>Produce Buyer's Brief: {as_of.strftime('%A')}, {day(as_of)}, {as_of.year}</h1>",
        '<p class="lede">Wholesale case prices from USDA Market News, compared with the same weeks of the last '
        '10 years, and where they are likely to be in two weeks.</p>',
    ]

    # 1. At a glance: three tiles a reader can act on without scrolling
    def names(rows, n=5):
        if not rows:
            return "<span class=\"none\">Nothing today</span>"
        more = f" <span class=\"more\">+{len(rows) - n} more</span>" if len(rows) > n else ""
        return " ".join(f'<span class="chip">{esc(i["name"])}</span>' for i in rows[:n]) + more
    def tile(cls, icon, head, sub, rows):
        return (f'<div class="tile {cls}"><div class="tile-head"><span class="ico" aria-hidden="true">{icon}</span>'
                f'{head}</div><div class="tile-sub">{sub}</div><div class="tile-n">{len(rows)}</div>{names(rows)}</div>')
    parts.append(
        '<h2>At a glance: New York</h2><div class="glance">'
        + tile("up", "▲", "Firming", "Likely higher in 2 weeks", groups["firming"])
        + tile("down", "▼", "Softening", "Likely lower in 2 weeks", groups["softening"])
        + tile("high", "!", "High for the season", "Priced above most past years", high)
        + tile("value", "★", "Good value", "Priced below most past years", value)
        + "</div>")

    # 2. Today's moves
    if today:
        lines = "".join(
            f'<div class="move"><span class="arrow {"bad" if m["day_change"] > 0 else "good"}" aria-hidden="true">'
            f'{"▲" if m["day_change"] > 0 else "▼"}</span>'
            f'<span><strong>{esc(m["name"])}</strong> · {esc(m["market"])}<br>'
            f'{money(m["before"])} → <strong>{money(m["today"])}</strong> a case, '
            f'{"up" if m["day_change"] > 0 else "down"} {abs(round(100 * m["day_change"]))}%'
            + (f'<br><small>USDA: “{esc(m["tone"].capitalize())}”</small>' if m["tone"] else "")
            + "</span></div>" for m in today[:8])
        parts += ["<h2>What moved today</h2>", f'<div class="moves">{lines}</div>']
    else:
        parts += ["<h2>What moved today</h2>", '<p class="quiet">A quiet day: nothing moved 5% or more.</p>']

    # 3. Early warnings in full
    if alerts:
        al = "".join(
            f'<div class="warn"><span class="arrow {"bad" if a["direction"] == "up" else "good"}" aria-hidden="true">'
            f'{"▲" if a["direction"] == "up" else "▼"}</span><span><strong>{esc(a["expect"])}</strong><br>'
            f'{esc(a["headline"])}<br><small>{esc(a["record"])}</small></span></div>' for a in alerts[:6])
        parts += ["<h2>Early warnings</h2>",
                  '<p class="quiet">Only signals that have called the next move right at least 65% of the time over 10 years.</p>',
                  f'<div class="moves">{al}</div>']

    # 4. New York item by item, grouped by market direction
    parts.append("<h2>New York, item by item</h2>")
    for g, (icon, head, sub) in GROUP_HEAD.items():
        if groups[g]:
            parts += [f'<h3 class="group {g}"><span class="ico" aria-hidden="true">{icon}</span>{head}'
                      f' <small>{sub}</small></h3>',
                      '<div class="items">' + "".join(item_card(i, hist.get(i["series_id"], []), sizes.get((i["commodity"], i["market"])))
                                                     for i in groups[g]) + "</div>"]

    # 5. Other markets: just what's not steady
    for market in MARKETS[1:]:
        rows = sorted((i for i in items if i["market"] == market and (i["dir"] in ("firming", "softening")
                                                                       or i["status"] in ("cheap", "expensive"))),
                      key=lambda i: (i["dir"] != "firming", i["dir"] != "softening", i["name"]))
        if rows:
            parts += [f"<h2>{market}: worth a look</h2>", compact_rows(rows)]

    # 6. Supply as simple bars (more or less shipped than this week last year)
    notes = [r for r in supply if _num(r["vs_last_year_pct"]) is not None and abs(_num(r["vs_last_year_pct"])) >= SUPPLY_NOTE]
    if notes:
        notes.sort(key=lambda r: _num(r["vs_last_year_pct"]))
        bars = "".join(
            f'<div class="sbar"><span class="sname">{esc(PRODUCE_NAMES.get(r["commodity"], r["commodity"]))}</span>'
            f'<span class="strack"><span class="sfill {"less" if v < 0 else "more"}" style="width:{min(abs(v), 100) / 2:.0f}%"></span></span>'
            f'<span class="sval">{abs(round(v))}% {"less" if v < 0 else "more"}</span></div>'
            for r in notes for v in [_num(r["vs_last_year_pct"])])
        parts += ["<h2>Supply: shipped vs. a year ago</h2>",
                  f'<p class="quiet">USDA-reported shipments, week of {day(dt.date.fromisoformat(notes[0]["week"]))}. '
                  'Less supply usually means firmer prices.</p>', f'<div class="supply">{bars}</div>']

    # 7. Track record as two numbers
    live, al_rec = record.get("forecasts_live", {}), record.get("alerts", {})
    tiles = []
    if live.get("scored"):
        tiles.append(f'<div class="stat"><strong>{live["in_range_pct"]:.0f}%</strong>'
                     f'<span>of {live["scored"]:,} price forecasts landed in their range (aim: 80%)</span></div>')
    if al_rec.get("decided"):
        tiles.append(f'<div class="stat"><strong>{al_rec["came_true"]} of {al_rec["decided"]}</strong>'
                     '<span>early warnings came true</span></div>')
    if tiles:
        parts += ["<h2>How we've done so far</h2>", f'<div class="stats">{"".join(tiles)}</div>']
    parts.append(
        '<p class="fine">How to read this: prices are the USDA “mostly” price per case for the pack shown (the most '
        "consistently reported pack in each market). “Cheap” and “High” compare with the same weeks in past years, "
        "adjusted for inflation. The chart shows the last 12 weeks; the shaded part is where the price will likely be "
        "(80% of the time). Market prices, not your supplier's quote; a guide, not a guarantee.</p>")
    return as_of, "\n".join(parts) + "\n"


def main():
    as_of, body = build()
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"{as_of.isoformat()}.html"
    path.write_text(body, encoding="utf-8")
    print(f"brief: {path.relative_to(store.DATA.parent)}")


if __name__ == "__main__":
    main()
