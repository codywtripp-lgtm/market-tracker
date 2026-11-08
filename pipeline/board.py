"""The site's two main views, as HTML fragments: the market board (home) and the item pages.

    python -m pipeline.board

Built for a buyer who has a minute: what to do today first, then every item in a watchlist they
can scan like a stock app (price, today's change, 12-week trend, where it's heading), then one
page per item with a real chart. Numbers come from pipeline.brief (headline packs, forecasts,
calls in trade terms); this module only lays them out.

Links are written as "@/path/"; scripts/build_site.py swaps "@/" for each page's relative root.
Writes data/board/home.html, data/board/market-<key>.html and data/board/items/<slug>[--<market>].html.
"""

import datetime as dt
import json
import re

from . import brief, config, store
from .brief import esc, money, whole
from .usual import with_usual

OUT = store.DATA / "board"
MARKETS = brief.MARKETS
MKEY = {"New York": "ny", "Los Angeles": "la", "Chicago": "chi", "Philadelphia": "phl", "Boston": "bos", "Atlanta": "atl",
        "Detroit": "det", "Miami": "mia"}
AT = {m: "at Hunts Point" if m == "New York" else f"in {m}" for m in MARKETS}
MARKET_LONG = {m: "New York (Hunts Point)" if m == "New York" else m for m in MARKETS}
# market landing pages for search ("hunts point produce prices") and per-market item page suffixes
MARKET_SLUG = {m: m.lower().replace(" ", "-") for m in MARKETS}
MARKET_PAGES = {m: "hunts-point-produce-prices" if m == "New York" else f"{MARKET_SLUG[m]}-produce-prices" for m in MARKETS}

# commodity -> (url slug, singular name used in titles); same slugs as scripts/build_site.py (tested)
PAGES = {
    "Avocados": ("avocado-prices", "Avocado"), "Strawberries": ("strawberry-prices", "Strawberry"),
    "Lettuce, Iceberg": ("iceberg-lettuce-prices", "Iceberg lettuce"),
    "Lettuce, Romaine": ("romaine-lettuce-prices", "Romaine lettuce"),
    "Tomatoes": ("tomato-prices", "Tomato"), "Tomatoes, Plum Type": ("roma-tomato-prices", "Roma tomato"),
    "Peppers, Bell Type": ("bell-pepper-prices", "Bell pepper"), "Onions, Dry": ("onion-prices", "Onion"),
    "Potatoes": ("potato-prices", "Potato"), "Lemons": ("lemon-prices", "Lemon"), "Limes": ("lime-prices", "Lime"),
    "Cucumbers": ("cucumber-prices", "Cucumber"), "Broccoli": ("broccoli-prices", "Broccoli"),
    "Celery": ("celery-prices", "Celery"), "Carrots": ("carrot-prices", "Carrot"), "Bananas": ("banana-prices", "Banana"),
    "Blueberries": ("blueberry-prices", "Blueberry"), "Grapes": ("grape-prices", "Grape"),
    "Apples, Gala": ("gala-apple-prices", "Gala apple"),
    "Apples, Honeycrisp": ("honeycrisp-apple-prices", "Honeycrisp apple"),
    "Apples, Granny Smith": ("granny-smith-apple-prices", "Granny Smith apple"),
    "Apples, Red Delicious": ("red-delicious-apple-prices", "Red Delicious apple"),
    "Apples, Fuji": ("fuji-apple-prices", "Fuji apple"),
    "Watermelons": ("watermelon-prices", "Watermelon"),
    "Pineapples": ("pineapple-prices", "Pineapple"), "Cantaloupes": ("cantaloupe-prices", "Cantaloupe"),
    "Mangoes": ("mango-prices", "Mango"), "Pears": ("pear-prices", "Pear"), "Cabbage": ("cabbage-prices", "Cabbage"),
    "Oranges": ("orange-prices", "Orange"), "Corn, Sweet": ("sweet-corn-prices", "Sweet corn"),
    "Cauliflower": ("cauliflower-prices", "Cauliflower"), "Sweet Potatoes": ("sweet-potato-prices", "Sweet potato"),
    "Mushrooms": ("mushroom-prices", "Mushroom"),
}
GROCERY = {  # the grocery page for the same item (pipeline/grocery.py slugs)
    "Avocados": "avocados", "Strawberries": "strawberries", "Tomatoes": "tomatoes", "Tomatoes, Plum Type": "tomatoes",
    "Peppers, Bell Type": "bell-peppers", "Onions, Dry": "onions", "Potatoes": "potatoes", "Lemons": "lemons",
    "Limes": "limes", "Cucumbers": "cucumbers", "Broccoli": "broccoli", "Celery": "celery", "Carrots": "carrots",
    "Bananas": "bananas", "Blueberries": "blueberries", "Grapes": "grapes", "Lettuce, Iceberg": "lettuce",
    "Lettuce, Romaine": "lettuce", "Apples, Gala": "apples", "Apples, Honeycrisp": "apples", "Apples, Granny Smith": "apples", "Apples, Red Delicious": "apples", "Apples, Fuji": "apples", "Watermelons": "watermelons", "Pineapples": "pineapples",
    "Cantaloupes": "cantaloupes", "Mangoes": "mangoes", "Pears": "pears", "Cabbage": "cabbage", "Oranges": "oranges",
    "Corn, Sweet": "sweet-corn", "Cauliflower": "cauliflower", "Sweet Potatoes": "sweet-potatoes", "Mushrooms": "mushrooms",
}
DISPLAY = {  # full names for rows and headings
    "Lettuce, Iceberg": "Iceberg lettuce", "Lettuce, Romaine": "Romaine lettuce", "Tomatoes": "Tomatoes",
    "Tomatoes, Plum Type": "Roma tomatoes", "Peppers, Bell Type": "Bell peppers", "Onions, Dry": "Onions",
    "Corn, Sweet": "Sweet corn", "Sweet Potatoes": "Sweet potatoes",
    "Apples, Gala": "Apples, Gala",
    "Apples, Honeycrisp": "Apples, Honeycrisp",
    "Apples, Granny Smith": "Apples, Granny Smith",
    "Apples, Red Delicious": "Apples, Red Delicious",
    "Apples, Fuji": "Apples, Fuji",
}
APPLE_HUB = ("apple-prices", "Apple")  # /apple-prices/ lists the varieties (pipeline/board.apple_hub)
MASS = {"Lettuce, Iceberg", "Lettuce, Romaine", "Broccoli", "Celery", "Cabbage", "Cauliflower", "Corn, Sweet"}  # "romaine is", "limes are"

DIR = {  # direction over the next two weeks: (arrow, word, tone)
    "firming": ("▲", "Firming", "up"), "softening": ("▼", "Softening", "down"), "steady": ("", "Steady", "flat"),
    "topping": ("▲▼", "Topping out", "up"), "bottoming": ("▼▲", "Bottoming out", "down"),
    "unsettled": ("", "Unsettled", "flat"),
}
SEASON = {"expensive": ("High for the season", "up"), "cheap": ("Low for the season", "down"),
          "normal": ("Normal for the season", "flat")}


def name(commodity):
    return DISPLAY.get(commodity, commodity)


def in_sentence(commodity):
    if commodity.startswith("Apples, "):  # lists say "Apples, Gala" (A to Z); sentences say "Gala apples"
        return commodity.removeprefix("Apples, ") + " apples"
    n = name(commodity).lower()
    return n.replace("roma ", "Roma ")


def item_link(commodity, market="New York"):
    slug = PAGES[commodity][0]
    return f"@/{slug}/" + ("" if market == "New York" else f"{MARKET_SLUG[market]}/")


def pct(v, signed=True):
    return f"{'+' if signed and v > 0 else ''}{round(v)}%"


NEW_AREA = "new area"


def area_list(text):
    """'California:60.0:60.0;New Jersey:40.0:42.0' -> [('California', 60.0, 60.0), ...]"""
    out = []
    for part in (text or "").split(";"):
        if part.count(":") == 2:
            area, low, high = part.split(":")
            out.append((area, float(low), float(high)))
    return out


def day_changes(items):
    """series_id -> (change vs the previous quote from the same growing area, or NEW_AREA); latest market day only.
    Comparing across areas would report a switch from California to New Jersey as a price move."""
    want = {i["series_id"] for i in items}
    days = {}
    for r in brief._read("prices_daily_365.csv"):
        if r["series_id"] in want and brief._num(r["compare_price"]) is not None:
            days.setdefault(r["series_id"], []).append((r["date"], brief._num(r["compare_price"]), r.get("area", ""), r.get("areas", "")))
    if not days:
        return None, {}
    as_of = max(max(d)[0] for d in days.values())
    out = {}
    for sid, d in days.items():
        d.sort()
        if len(d) < 2 or d[-1][0] != as_of or not d[-2][1]:
            continue
        before = {a: (low + high) / 2 for a, low, high in area_list(d[-2][3])}
        if d[-1][2] == d[-2][2] or not d[-1][2]:
            out[sid] = d[-1][1] / d[-2][1] - 1
        elif d[-1][2] in before:
            out[sid] = d[-1][1] / before[d[-1][2]] - 1
        else:
            out[sid] = NEW_AREA
    return dt.date.fromisoformat(as_of), out


def latest_quotes(items):
    """series_id -> USDA's latest day from the main growing area, and the other areas quoted that day."""
    want = {i["series_id"] for i in items}
    out = {}
    for r in brief._read("prices_daily_365.csv"):
        day = dt.date.fromisoformat(r["date"])
        if r["series_id"] in want and brief._num(r["compare_price"]) is not None and (
                r["series_id"] not in out or day >= out[r["series_id"]]["date"]):
            out[r["series_id"]] = {"date": day, "price": brief._num(r["compare_price"]),
                                   "area": r.get("area", ""), "areas": area_list(r.get("areas")), "lot": r.get("lot", ""),
                                   "other_lots": area_list(r.get("other_lots")),
                                   **{k: brief._num(r.get(k)) for k in ("low", "high", "mostly_low", "mostly_high")}}
    return out


def price_range(low, high):
    return money(low) if not high or low >= high else f"{money(low)} to {money(high)}"


def quote_text(q):
    """USDA's latest day in the trade's words: 'California, Shippers First Grade, USDA on Nov 3: $38.00 to $40.00, mostly ...'."""
    s = ", ".join(x for x in (q.get("area"), q.get("lot"), "USDA") if x)
    s += f" on {q['date']:%b} {q['date'].day}: {price_range(q['low'] or q['price'], q['high'])}"
    if q["mostly_low"] and q["mostly_high"] and q["mostly_low"] < q["mostly_high"]:
        s += f", mostly {money(q['mostly_low'])} to {money(q['mostly_high'])}"
    return s


def other_areas(q):
    rows = q.get("other_lots", []) + [a for a in q.get("areas", []) if a[0] != q.get("area")]
    if not rows:
        return ""
    return ('<div class="q-areas"><p>Also quoted that day</p><ul>'
            + "".join(f"<li>{esc(a or 'Not stated')} <b>{price_range(low, high)}</b></li>" for a, low, high in rows) + "</ul></div>")


def history(items, weeks=56):
    """series_id -> [(week date, price, price in today's dollars)], the last `weeks` weeks."""
    want = {i["series_id"] for i in items}
    rows = {}
    for r in brief._read("prices_weekly.csv"):
        if r["series_id"] in want and brief._num(r["compare_price"]) is not None:
            rows.setdefault(r["series_id"], []).append(
                (dt.date.fromisoformat(r["week_start"]), brief._num(r["compare_price"]), brief._num(r["real_compare_price"])))
    out = {}
    for sid, v in rows.items():
        v.sort()
        usual = with_usual(v)  # needs every year, then keep the tail
        out[sid] = [(d, p, u[4], u[5]) for (d, p, _), u in zip(v, usual)][-weeks:]
    return out


# ---------- small pieces ----------
def change(v, unit=""):
    if v is None:
        return '<span class="chg flat">Not quoted today</span>' if unit == "today" else ""
    if v == NEW_AREA:
        return '<span class="chg flat">New growing area</span>'
    if abs(v) < 0.005:
        return '<span class="chg flat">Unchanged</span>'
    tone, arrow = ("up", "▲") if v > 0 else ("down", "▼")
    return f'<span class="chg {tone}">{arrow} {abs(round(100 * v))}%</span>'


def expected(i):
    """(expected case price in two weeks, change) or (None, None). The 80% range is too wide to say in words
    (iceberg: $37 to $70), so text gives the expected price; the range is only the chart's shading."""
    if not i["range"] or i["change"] is None:
        return None, None
    return i["price"] * (1 + i["change"]), i["change"]


def expect_text(i, unit=" a case"):
    mid, chg = expected(i)
    if mid is None:
        return ""
    move = "" if abs(chg) < 0.02 else f", {'up' if chg > 0 else 'down'} about {abs(round(100 * chg))}%"
    return f"about {whole(mid)}{unit}{move}"


def day_note(v):
    """Under a row's price: today's move if there was one, else the unit."""
    return change(v) if v is not None and v != NEW_AREA and abs(v) >= 0.005 else '<small class="unit">a case</small>'


def outlook(i):
    if not i["range"]:
        return '<span class="out flat">No forecast</span>'
    arrow, word, tone = DIR[i["dir"] or "steady"]
    return (f'<span class="out {tone}"><b>{arrow + " " if arrow else ""}{word}</b>'
            f'<small>{"about " + whole(expected(i)[0]) if expected(i)[0] is not None else ""}</small></span>')


def usual_range(i):
    """'$33 to $58' for a normal item: three labels plus the range, as Google Flights does (low / typical / high). A
    percent next to "Normal" reads as a contradiction for items that swing widely (avocados 29% below the median,
    still inside the middle half of past years)."""
    if i["status"] == "normal" and i.get("usual_low") and i.get("usual_high"):
        return f"{whole(i['usual_low'])} to {whole(i['usual_high'])}"
    return ""


def season(i):
    if i["status"] not in SEASON:  # pack too new to USDA for a seasonal norm: compare with a year ago
        v = i.get("vs_year")
        if v is None:
            return '<span class="season flat"><b>New pack</b><small>no history to compare yet</small></span>'
        word = "about last year's price" if abs(v) < 5 else f"{abs(round(v))}% {'above' if v > 0 else 'below'} last year"
        tone = "flat" if abs(v) < 5 else ("up" if v > 0 else "down")
        return f'<span class="season {tone}"><b>{cap(word)}</b><small>same week, last year</small></span>'
    word, tone = SEASON.get(i["status"], ("Not enough history", "flat"))
    vs = i["vs_norm"]
    sub = brief.vs_usual(vs) + (" usual" if vs is not None and abs(vs) >= 5 else "") if vs is not None else ""
    if usual_range(i):
        sub = f"usually {usual_range(i)}"
    return f'<span class="season {tone}"><b>{word}</b>{f"<small>{esc(sub)}</small>" if sub else ""}</span>'


def spark(hist, i, w=120, h=36):
    """Last 12 weeks (line) and the next two weeks' likely range (shaded)."""
    pts = [(d, p) for d, p, _, _ in hist[-12:]]
    if len(pts) < 3:
        return '<span class="spark-none"></span>'
    last = pts[-1][0].isoformat()
    fut = [p for p in i["points"] if p["week"] > last][:2]
    vals = [p for _, p in pts] + [p["lo"] for p in fut] + [p["hi"] for p in fut]
    lo, hi = min(vals), max(vals)
    span = (hi - lo) or 1
    n = len(pts) + len(fut)
    pad = 3
    x = lambda k: pad + k * (w - 2 * pad) / max(n - 1, 1)  # noqa: E731
    y = lambda v: h - pad - (v - lo) / span * (h - 2 * pad)  # noqa: E731
    k0, v0 = len(pts) - 1, pts[-1][1]
    out = ""
    if fut:
        top = [(x(k0), y(v0))] + [(x(k0 + 1 + j), y(p["hi"])) for j, p in enumerate(fut)]
        bot = [(x(k0 + 1 + j), y(p["lo"])) for j, p in reversed(list(enumerate(fut)))]
        out += f'<path class="fc {DIR[i["dir"] or "steady"][2]}" d="M' + "L".join(f"{a:.1f},{b:.1f}" for a, b in top + bot) + 'Z"/>'
    out += '<path class="ln" d="M' + "L".join(f"{x(k):.1f},{y(v):.1f}" for k, (_, v) in enumerate(pts)) + '"/>'
    out += f'<circle class="dot" cx="{x(k0):.1f}" cy="{y(v0):.1f}" r="2.5"/>'
    label = f"Last 12 weeks: {money(pts[0][1])} to {money(v0)}"
    return f'<svg class="spark" viewBox="0 0 {w} {h}" role="img" aria-label="{esc(label)}"><title>{esc(label)}</title>{out}</svg>'


def chart(hist, i, noun="case price", money_fn=None, label=None):
    """One year of weekly prices, the usual range for each week (25th-75th pct of past years) and the forecast."""
    money_ = money_fn or money
    pts = [r for r in hist if r[1] is not None]
    if len(pts) < 8:
        return ""
    last = pts[-1][0]
    fut = [p for p in i["points"] if p["week"] > last.isoformat()]
    W, H = 720, 280
    L, R, T, B = 64, 16, 14, 34
    vals = [p for _, p, _, _ in pts] + [v for _, _, lo, hi in pts for v in (lo, hi) if v is not None]
    vals += [p["lo"] for p in fut] + [p["hi"] for p in fut]
    lo_v, hi_v = min(vals), max(vals)
    # round the scale to tidy steps
    raw = (hi_v - lo_v) / 4 or 1
    mag = 10 ** len(str(int(raw))) / 10 if raw >= 1 else 0.1
    step = next(s * mag for s in (1, 2, 2.5, 5, 10) if s * mag >= raw)
    y0 = step * int(lo_v // step)
    y1 = step * (int(hi_v // step) + 1)
    weeks = [d for d, *_ in pts] + [dt.date.fromisoformat(p["week"]) for p in fut]
    t0, t1 = weeks[0], weeks[-1]
    span = (t1 - t0).days or 1
    x = lambda d: L + (d - t0).days / span * (W - L - R)  # noqa: E731
    y = lambda v: T + (y1 - v) / (y1 - y0) * (H - T - B)  # noqa: E731
    g = []
    v = y0
    while v <= y1 + 1e-9:
        g.append(f'<line class="grid" x1="{L}" x2="{W - R}" y1="{y(v):.1f}" y2="{y(v):.1f}"/>'
                 f'<text class="ylab" x="{L - 8}" y="{y(v) + 4:.1f}">{"$" + (f"{v:,.0f}" if step >= 1 else f"{v:,.2f}")}</text>')
        v += step
    # month ticks
    m = dt.date(t0.year, t0.month, 1)
    while m <= t1:
        if m >= t0:
            odd = " odd" if m.month % 2 else ""  # every other month is hidden on phones
            g.append(f'<text class="xlab{odd}" x="{x(m):.1f}" y="{H - 8}">{m:%b}{" " + str(m.year)[2:] if m.month == 1 else ""}</text>')
        m = dt.date(m.year + (m.month == 12), m.month % 12 + 1, 1)
    band = [(d, lo, hi) for d, _, lo, hi in pts if lo is not None]
    if band:
        top = "L".join(f"{x(d):.1f},{y(hi):.1f}" for d, _, hi in band)
        bot = "L".join(f"{x(d):.1f},{y(lo):.1f}" for d, lo, _ in reversed(band))
        g.append(f'<path class="usual" d="M{top}L{bot}Z"/>')
    line = "L".join(f"{x(d):.1f},{y(p):.1f}" for d, p, _, _ in pts)
    if fut:
        tone = DIR[i["dir"] or "steady"][2]
        d0, v0 = last, pts[-1][1]
        top = [(x(d0), y(v0))] + [(x(dt.date.fromisoformat(p["week"])), y(p["hi"])) for p in fut]
        bot = [(x(dt.date.fromisoformat(p["week"])), y(p["lo"])) for p in reversed(fut)]
        g.append(f'<path class="fc {tone}" d="M' + "L".join(f"{a:.1f},{b:.1f}" for a, b in top + bot) + 'Z"/>')
        g.append(f'<path class="fcmid {tone}" d="M{x(d0):.1f},{y(v0):.1f}'
                 + "".join(f"L{x(dt.date.fromisoformat(p['week'])):.1f},{y(p['mid']):.1f}" for p in fut) + '"/>')
    g.append(f'<path class="price" d="M{line}"/>')
    g.append(f'<circle class="now" cx="{x(last):.1f}" cy="{y(pts[-1][1]):.1f}" r="4.5"/>')
    label = (label or f"{name(i['commodity'])} in {i['market']}, weekly case price over the last year") + (
        f", from {money_(pts[0][1])} to {money_(pts[-1][1])}")
    legend = (f'<div class="legend"><span><i class="k-price"></i>Weekly {noun}</span>'
              '<span><i class="k-usual"></i>Usual range for the time of year</span>'
              + (f'<span><i class="k-fc {DIR[i["dir"] or "steady"][2]}"></i>Forecast; shading is where 8 in 10 outcomes land</span>' if fut else "")
              + "</div>")
    rows = "".join(f"<tr><td>{d:%b} {d.day}, {d.year}</td><td>{money_(p)}</td>"
                   f"<td>{(money_(lo) + ' to ' + money_(hi)) if lo is not None else ''}</td></tr>" for d, p, lo, hi in reversed(pts))
    return (f'<figure class="chart"><svg viewBox="0 0 {W} {H}" role="img" aria-label="{esc(label)}">'
            f"<title>{esc(label)}</title>{''.join(g)}</svg>{legend}"
            f'<details class="numbers"><summary>Show the numbers</summary><table class="t"><thead><tr><th>Week of</th>'
            f'<th>{noun.capitalize()}</th><th>Usual range</th></tr></thead><tbody>{rows}</tbody></table></details></figure>')


# ---------- the market board (home) ----------
def name_list(rows):
    names = [in_sentence(i["commodity"]) for i in rows]
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def verb(rows):
    return "is" if len(rows) == 1 and rows[0]["commodity"] in MASS else "are"


def cap(s):
    return s[:1].upper() + s[1:]


def lede(rows, market):
    firm = sorted((i for i in rows if i["dir"] == "firming"), key=lambda i: -(i["change"] or 0))[:3]
    soft = sorted((i for i in rows if i["dir"] == "softening"), key=lambda i: i["change"] or 0)[:3]
    top = [i for i in rows if i["dir"] == "topping"][:3]
    high = [i for i in rows if i["status"] == "expensive" and i["dir"] == "steady"][:3]
    open_ = [i for i in rows if i["dir"] == "unsettled"][:3]
    bits = []
    if firm and soft:
        bits.append(f"{cap(name_list(firm))} {verb(firm)} firming {AT[market]}, while {name_list(soft)} {verb(soft)} softening.")
    elif firm or soft:
        g, word = (firm, "firming") if firm else (soft, "softening")
        bits.append(f"{cap(name_list(g))} {verb(g)} {word} {AT[market]}{"." if open_ else "; the rest look steady."}")
    else:
        bits.append(f"No clear moves {AT[market]} for the next two weeks." if open_ else
                    f"Prices {AT[market]} look steady across the board for the next two weeks.")
    if top:
        bits.append(f"{cap(name_list(top))} {verb(top)} still firm this week but likely topping out, with relief "
                    "in two to four weeks.")
    if high:
        bits.append(f"{cap(name_list(high))} {verb(high)} high for the season with no relief in sight.")
    if open_:
        bits.append(f"{cap(name_list(open_))} {verb(open_)} unsettled.")
    return " ".join(bits)


ACTIONS = [  # (key, title, what to do, tone)
    ("firming", "▲ Firming", "Lock price with your supplier and get customer quotes out before it moves. "
                             "Buy a few days deeper only on items that keep.", "up"),
    ("softening", "▼ Softening", "Stay on the open market and keep inventory tight. Don't lock price at today's level. "
                                 "Some are still firm this week before they ease.", "down"),
    ("high", "High for the season", "No relief in sight. Price quotes to cover it and look at other counts or packs.",
     "up"),
    ("value", "Good value", "Cheaper than most years at this time. A good item to feature on specials.", "down"),
    ("unsettled", "Unsettled", "Recent prices and shipping points disagree on direction, so there's no call. "
                               "Stay close to your supplier on price.", "flat"),
]


def actions(rows, market):
    groups = {
        "firming": sorted((i for i in rows if i["dir"] in ("firming", "bottoming")), key=lambda i: -(i["change"] or 0)),
        "softening": sorted((i for i in rows if i["dir"] in ("softening", "topping")), key=lambda i: i["change"] or 0),
        "high": [i for i in rows if i["status"] == "expensive" and i["dir"] == "steady"],
        "value": [i for i in rows if i["status"] == "cheap" and i["dir"] not in ("firming", "unsettled")],
        "unsettled": [i for i in rows if i["dir"] == "unsettled"],
    }
    cards = []
    for key, title, todo, tone in ACTIONS:
        items = groups[key]
        if items:
            lis = "".join(
                f'<li><a href="{item_link(i["commodity"], market)}"><span>{esc(name(i["commodity"]))}'
                + {"topping": ' <small class="turn">firm this week first</small>',
                   "bottoming": ' <small class="turn">easing this week first</small>'}.get(i["dir"], "")
                + '</span>'
                f'<span class="num">{money(i["price"])}'
                + (f' <span class="to">to about {whole(expected(i)[0])}</span>'
                   if key in ("firming", "softening") and expected(i)[0] is not None else "")
                + "</span></a></li>" for i in items)
        else:
            lis = '<li class="none">Nothing today</li>'
        cards.append(f'<section class="act {tone}"><h3>{title}</h3><p>{todo}</p><ul>{lis}</ul></section>')
    return '<div class="acts">' + "".join(cards) + "</div>"


def board_rows(rows, hist, today, market):
    head = ('<div class="bhead" aria-hidden="true"><span>Item</span><span>For the season</span><span>12 weeks</span>'
            '<span class="r">Case price</span><span>Next 2 weeks</span></div>')
    body = "".join(
        f'<a class="brow" href="{item_link(i["commodity"], market)}">'
        f'<span class="b-item"><b>{esc(name(i["commodity"]))}</b><small>{esc(i["pack"])}</small></span>'
        f'<span class="b-season">{season(i)}</span>'
        f'<span class="b-spark">{spark(hist.get(i["series_id"], []), i)}</span>'
        f'<span class="b-price"><b>{money(i["price"])}</b>{day_note(today.get(i["series_id"]))}</span>'
        f'<span class="b-out">{outlook(i)}</span></a>'
        for i in sorted(rows, key=lambda i: name(i["commodity"])))
    return f'<div class="board">{head}{body}</div>'


def backed(alerts, items):
    """Signs the headline pack's two-week forecast agrees with. scripts/backtest_signs_vs_calls.py: 2021-2026, those
    moved the called way 79-84% of the time, the rest about 46-59%, and a sign beside "Steady" reads as a contradiction."""
    calls = {(i["commodity"], i["market"]): i["dir"] for i in items}
    return [a for a in alerts if calls.get((a["commodity"], a["market"])) == ("firming" if a["direction"] == "up" else "softening")]


def warnings(alerts, market=None, commodity=None):
    """Signs of a move, in plain words: what it is, why, and how often that sign has been right."""
    rows = [a for a in alerts if (market is None or a["market"] == market) and (commodity is None or a["commodity"] == commodity)]
    if not rows:
        return ""
    lis = []
    for a in rows:
        up = a["direction"] == "up"
        when = "next week" if a["signal"] == "usda_tone" else "within two weeks"
        what = f"{name(a['commodity'])} likely to {'rise' if up else 'ease'} {when}"
        if a["signal"] == "usda_tone":
            tone = re.search(r"“(.*?)”", a["headline"])
            why = (f"USDA's market reporters in {a['market']} are calling it {'higher' if up else 'lower'}"
                   + (f" (“{tone.group(1)}”)." if tone else "."))
        else:
            why = cap(a["headline"].split(": ", 1)[-1].replace("shipping point", "prices where it's grown"))
        hits = re.search(r"(\d+) of the last (\d+)", a["record"])
        rec = f"This sign was right {hits.group(1)} of the last {hits.group(2)} times." if hits else a["record"]
        lis.append(f'<li class="{"up" if up else "down"}"><b>{"▲" if up else "▼"} {esc(what)}</b>'
                   f'<span>{esc(why)}</span><small>{esc(rec)}</small></li>')
    return f'<ul class="warns">{"".join(lis)}</ul>'


# ---------- supply news (what the growing areas and shipments say) ----------
STATES = ("California", "Arizona", "Florida", "Georgia", "Texas", "Washington", "Oregon", "Idaho", "Colorado",
          "Michigan", "New York", "North Carolina", "Virginia", "Tennessee", "New Jersey", "Wisconsin", "Minnesota",
          "Mexico", "Canada", "Peru", "Chile")


ABBR = {"California": "CA", "Arizona": "AZ", "Florida": "FL", "Georgia": "GA", "Texas": "TX", "Washington": "WA",
        "Oregon": "OR", "Idaho": "ID", "Colorado": "CO", "Michigan": "MI", "New York": "NY", "North Carolina": "NC",
        "Virginia": "VA", "Tennessee": "TN", "New Jersey": "NJ", "Wisconsin": "WI", "Minnesota": "MN"}


def short_place(district):
    """'MEXICO CROSSINGS THROUGH OTAY MESA CALIFORNIA' -> 'Mexico via Otay Mesa, CA'."""
    t = place(district)
    t = re.sub(r"^Mexico Crossings through ", "Mexico via ", t)
    t = re.sub(r"^(\w+) Imports - Ports of Entry ", lambda m: f"{m.group(1)} imports via ", t)
    t = t.replace(" district", "")
    for st, ab in ABBR.items():
        t = re.sub(rf", {st}$", f", {ab}", t)
    t = re.sub(r"^((?:South and )?Central), CA$", r" California", t)
    return t.replace("via South, FL", "via South Florida")


def place(district):
    """'SALINAS-WATSONVILLE CALIFORNIA' -> 'Salinas-Watsonville, California'."""
    t = " ".join(w.capitalize() for w in district.lower().split())
    t = "-".join(p[:1].upper() + p[1:] for p in t.split("-"))
    for small in (" And ", " Through ", " Of ", " District"):
        t = t.replace(small, small.lower())
    for st in STATES:
        before = t[: -len(st) - 1].split(" ")[-1] if t.endswith(" " + st) else ""
        if before and before not in ("and", "through", "of", "-") and not before.endswith(","):
            t = t[: -len(st) - 1] + ", " + st
            break
    return t


# names that keep their capital inside a sentence ("Mexico", "California") once USDA's casing is undone
PROPER = {"mexico", "california", "arizona", "texas", "florida", "georgia", "washington", "oregon", "idaho", "michigan",
          "peru", "chile", "canada", "guatemala", "honduras", "colombia", "ecuador", "brazil", "argentina", "spain",
          "salinas", "watsonville", "oxnard", "yuma", "imperial", "coachella", "san", "joaquin", "valley", "santa",
          "maria", "central", "southern", "northern", "western", "eastern"}


def _tone_words(t):
    """USDA's supply and demand words in sentence case: they arrive as "LIGHT", "Very Light and in few hands." or
    "Carton 40-80s exceeds supply , others moderate."."""
    t = " ".join((t or "").replace(" ,", ",").split()).strip().rstrip(".")
    words = [w.capitalize() if w.lower().strip(",") in PROPER and w.lower() != w else w.lower() for w in t.split(" ")]
    return " ".join(words)


def _simple_tone(t):
    """USDA market tone in a few words: 'slightly higher', 'higher on some packs', 'mixed'."""
    t = _tone_words(t).lower()
    if re.fullmatch(r"(slightly |much |about |generally )?(higher|lower|steady|firm|firmer|weak|weaker)", t):
        return t
    up, down = bool(re.search(r"higher|firm", t)), bool(re.search(r"lower|weak", t))
    some = " on some packs" if "steady" in t else ""
    return "mixed" if up and down else f"higher{some}" if up else f"lower{some}" if down else "steady"


def _rating(t):
    """USDA's supply or demand rating without its side remarks: "Shippers First Grade light." -> "light"."""
    t = re.sub(r"^shippers first grade\s+", "", (t or "").strip(), flags=re.I)
    return _tone_words(t.split(". ")[0])


def shipments_by_place(as_of):
    """commodity -> {movement report place: pounds shipped in the last 4 weeks}."""
    since = (as_of - dt.timedelta(days=28)).isoformat()
    rows = []
    for d in {as_of, as_of.replace(day=1) - dt.timedelta(days=1)}:
        rows += store.read_partition(store.partition_path("movement", d.isoformat())).values()
    same = {}  # the same shipment can be in two reports: count it once, as pipeline/volumes.py does
    for r in rows:
        if r["report_date"] >= since:
            key = (r["report_date"], r["commodity"], r["variety"], r["organic"], r["market"], r["origin"], r["other_attributes"])
            same[key] = max(same.get(key, 0), brief._num(r["volume"]) or 0)
    out = {}
    for key, lb in same.items():
        places = out.setdefault(key[1], {})
        places[key[4]] = places.get(key[4], 0) + lb
    return out


def _ships_from(area, place):
    """Does a movement report place belong to a shipping-point area? They name places differently: 'MEXICO CROSSINGS
    THROUGH PHARR TEXAS' is in 'MEXICO CROSSINGS THROUGH TEXAS', 'FLORIDA' is in 'FLORIDA WEST AND GEORGIA DISTRICT'."""
    a = set(re.findall(r"[A-Z]+", area.upper()))
    p = set(re.findall(r"[A-Z]+", place.upper())) - {"DISTRICT", "AND", "THROUGH"}
    if "MEXICO" in p:
        return "MEXICO" in a and place.upper().split()[-1] in a
    if "IMPORTS" in p:
        return "IMPORTS" in a
    return "IMPORTS" not in a and "MEXICO" not in a and p <= a


def main_areas(areas, shipped, floor=0.25):
    """The areas that matter for an item, biggest first: each with 25%+ of the shipments matched to an area. USDA's
    movement reports leave some areas out (no California lemons), so an area with none on record stays in, last."""
    pounds = {a: sum(lb for place, lb in shipped.items() if _ships_from(a, place)) for a in areas}
    total = sum(pounds.values())
    if not total:
        return sorted(areas)
    keep = [a for a in areas if pounds[a] >= floor * total or not pounds[a]]
    return sorted(keep, key=lambda a: (not pounds[a], -pounds[a], a))


def supply_notes(as_of):
    """commodity -> (how notable, size of shipment change, one or two plain sentences)."""
    since = (as_of - dt.timedelta(days=7)).isoformat()
    rows = []
    for d in {as_of, as_of.replace(day=1) - dt.timedelta(days=1)}:
        rows += store.read_partition(store.partition_path("shipping_point", d.isoformat())).values()
    by_c = {}
    for r in rows:
        c = config.item_of(r["commodity"], r.get("variety"))
        if r["report_date"] >= since and c in PAGES and r.get("organic", "") not in ("Y", "Yes"):
            by_c.setdefault(c, []).append(r)
    ship = {r["commodity"]: (brief._num(r["vs_last_year_pct"]), r["week"]) for r in brief._read("supply.csv")}
    shipped = shipments_by_place(as_of)
    notes = {}
    for c in PAGES:
        bits, flag = [], 0
        rs = by_c.get(c, [])
        if rs:
            main = main_areas({r["market"] for r in rs if r["market"]}, shipped.get(config.base(c), {}))
            rs = [r for r in rs if r["market"] in main]
            last = max((r["report_date"] for r in rs), default="")
            day_rows = [r for r in rs if r["report_date"] == last]
            moving = {}
            for r in day_rows:
                tone = _simple_tone(r["market_tone"])
                if re.search(r"higher|lower|firm|weak", tone) and r["market"]:
                    moving.setdefault(tone, set()).add(short_place(r["market"]))
            short = sorted({short_place(r["market"]) for r in day_rows
                            if re.search(r"insufficient|too few hands", r["reporter_comment"], re.I) and r["market"]})
            rated = {}  # each area's latest rating this week: USDA doesn't repeat it every day
            recent = (as_of - dt.timedelta(days=3)).isoformat()  # an older rating may be from an area that has finished
            for r in sorted(rs, key=lambda r: r["report_date"]):
                if r.get("supply_tone") and r["report_date"] >= recent:
                    rated[r["market"]] = (_rating(r["supply_tone"]), _rating(r.get("demand_tone", "")))
            if moving:
                d = dt.date.fromisoformat(last)
                tone, where = max(moving.items(), key=lambda kv: len(kv[1]))
                where = sorted(where)
                w = where[0] if len(where) == 1 else ", ".join(where[:-1]) + " and " + where[-1]
                bits.append(f"Shipping points {tone} in {w} ({d:%b} {d.day}).")
                flag += 1
            for area in [a for a in main if a in rated][:2]:
                s_, d_ = rated[area]
                bits.append(f"{short_place(area)}: supplies {s_}" + (f", demand {d_}." if d_ else "."))
            flag += any(re.search(r"light|short|limited", s_) for s_, _ in rated.values())
            short = [a for a in short if a not in {short_place(m) for m in rated}]
            if short:
                bits.append(f"{short[0]}: too little supply to quote.")
                flag += 1
        pct_, week = ship.get(config.base(c), (None, None))
        if pct_ is not None and abs(pct_) >= 10:
            w = dt.date.fromisoformat(week)
            bits.append(f"Shipments {abs(round(pct_))}% {'below' if pct_ < 0 else 'above'} last year.")
            flag += abs(pct_) >= 15
        if bits:
            notes[c] = (flag, abs(pct_ or 0), " ".join(bits))
    return notes


def notes_section(notes, limit=5):
    top = sorted(((c, n) for c, n in notes.items() if n[0] > 0), key=lambda cn: (-cn[1][0], -cn[1][1]))[:limit]
    if not top:
        return ""
    lis = "".join(f'<li><a href="{item_link(c)}">{esc(name(c))}</a><span>{esc(n[2])}</span></li>' for c, n in top)
    return ('<h2>Supply news</h2><p class="note">From this week\'s USDA shipping-point and shipment reports.</p>'
            f'<ul class="notes">{lis}</ul>')


def market_panel(market, rows, hist, today, alerts, notes):
    k = MKEY[market]
    return (f'<section class="panel" id="m-{k}">'
            f'<p class="lede">{esc(lede(rows, market))}</p>'
            f'<h2>What to do today</h2>{actions(rows, market)}'
            + notes_section(notes)
            + (f'<h2>Signs of a move</h2><p class="note">Patterns that came before a price move at least two times in '
               f'three over the last 10 years. They only show here when the forecast agrees.</p>{warnings(alerts, market)}'
               if warnings(alerts, market) else "")
            + f'<h2>All prices, {esc(MARKET_LONG[market])}</h2><p class="note">USDA’s latest quote for each item’s main growing area.</p>{board_rows(rows, hist, today, market)}'
            "</section>")


def market_links(markets, current, href, remember=False):
    """Eight markets are too many for a row of tabs on a phone, so plain links that wrap. `remember`: the page is
    the unmarked default, and tabs.js sends a returning buyer to the market they last chose."""
    links = []
    for m in markets:
        mark = ' aria-current="page"' if m == current else ""
        links.append(f'<a href="{href(m)}" data-m="{MKEY[m]}"{mark}>{m}</a>')
    return f'<nav class="mkts" aria-label="Market"{" data-remember" if remember else ""}>{"".join(links)}</nav>'


def dateline(as_of):
    return f'<p class="date">{as_of:%A}, {as_of:%B} {as_of.day}, {as_of.year}. USDA terminal market prices, updated every market evening.</p>'


def home(items, hist, today, alerts, as_of, record, notes, only=None):
    market = only or MARKETS[0]
    h1 = ("Wholesale produce prices today" if not only else
          f"{'Hunts Point' if only == 'New York' else only} wholesale produce prices today")
    parts = [f'<div class="pagehead"><h1>{h1}</h1>{dateline(as_of)}'
             + market_links(MARKETS, market, lambda m: f"@/{MARKET_PAGES[m]}/", remember=not only) + "</div>",
             market_panel(market, [i for i in items if i["market"] == market], hist, today, alerts, notes)]
    live = record.get("forecasts_live", {})
    if live.get("scored"):
        parts.append(f'<p class="record">Since going live, {live["in_range_pct"]:.0f}% of {live["scored"]:,} price '
                     f'forecasts landed inside their range. <a href="@/why/">See the full track record</a></p>')
    return "\n".join(parts) + "\n"


# ---------- item pages ----------
def pack_in_sentence(pack):
    """'Hass, cartons 2 layer, 48s' stays 'Hass, ...'; 'Cartons, film bags 30s' becomes 'cartons, film bags 30s'."""
    from .grocery import KEEP_CAPS
    first = pack.split(",")[0].split()[0] if pack else ""
    return pack if first in KEEP_CAPS or first.isupper() else pack[:1].lower() + pack[1:]


def answer(i):
    q = i.get("quote") or {}
    s = (("" if not q else f"On {q['date']:%B} {q['date'].day}, {q['date'].year}, ")
         + f"wholesale {in_sentence(i['commodity'])} ({esc(pack_in_sentence(i['pack']))})"
         + (f" from {esc(q['area'])}" if q.get("area") else "")
         + f" traded at <strong>{money(i['price'])} a case</strong> in {MARKET_LONG[i['market']]}")
    s = s[0].upper() + s[1:]
    if i["vs_norm"] is not None:
        s += (f", inside its usual range of {usual_range(i)} for this time of year" if usual_range(i) else
              f", {esc(brief.vs_usual(i['vs_norm']))}{' the usual price' if abs(i['vs_norm']) >= 5 else ''} for this time of year")
    s += "."
    if i["dir"] == "unsettled":
        s += " The market is <strong>unsettled</strong>: recent prices and shipping points disagree on direction."
    elif i["range"]:
        word = {"firming": "is <strong>firming</strong>", "softening": "is <strong>softening</strong>",
                "topping": "is <strong>topping out</strong> (still firm this week)",
                "bottoming": "is <strong>bottoming out</strong> (still easing this week)"}.get(
            i["dir"], "looks <strong>steady</strong>")
        s += f" The market {word}: in two weeks, expect {expect_text(i)}."
    return s


def quote(i, hist, today, opts, note=""):
    rng = expect_text(i)
    arrow, word, tone = DIR[i["dir"] or "steady"]
    sz = ""
    if opts:
        sz = ('<h2 class="sh">Other counts today</h2><table class="t sizes"><thead><tr><th>Count</th><th>Case price</th></tr></thead><tbody>'
              + "".join(f"<tr><td>{esc(o[1])}</td><td>{money(o[2] * o[0])}</td></tr>" for o in opts) + "</tbody></table>")
    return (f'<div class="quote"><div class="q-main"><span class="q-price">{money(i["price"])}</span>'
            f'<span class="q-unit">a case</span><span class="q-pack">{esc(i["pack"])}</span>'
            + (f'<span class="q-range">{esc(quote_text(i["quote"]))}</span>{other_areas(i["quote"])}' if i.get("quote") else "") + '</div>'
            '<dl class="q-facts">'
            f'<div><dt>Today</dt><dd>{change(today.get(i["series_id"]), "today")}</dd></div>'
            f'<div><dt>For the season</dt><dd>{season(i)}</dd></div>'
            f'<div><dt>Next 2 weeks</dt><dd><span class="out {tone}"><b>{arrow + " " if arrow else ""}{word}</b>'
            f'{f"<small>{rng}</small>" if rng else ""}</span></dd></div>'
            + (f'<div class="path"><dt>Week by week</dt><dd>' + ", ".join(
                f'{"next week" if h == 1 else f"in {h} weeks"} <b>about {whole(v)}</b>'
                for h, v in sorted(i["path"].items()) if h in (1, 2, 4)) + "</dd></div>" if i.get("path") else "")
            + "</dl></div>"
            + (f'<div class="todo {tone}"><h2>What to do</h2><p>{esc(i["action"])}</p></div>' if i["action"] else "")
            + (f'<div class="supply-note"><h2>Supply news</h2><p>{esc(note)}</p></div>' if note else "")
            + chart(hist.get(i["series_id"], []), i) + sz)


def faq(commodity, rows):
    ny = rows[0]
    lower = in_sentence(commodity)
    single = PAGES[commodity][1] if commodity.startswith("Apples, ") else PAGES[commodity][1].lower().replace("roma ", "Roma ")
    v = "is" if commodity in MASS else "are"
    qa = [(f"How much does a case of {lower} cost wholesale right now?",
           " ".join(f"{money(i['price'])} in {i['market']} ({pack_in_sentence(i['pack'])}"
                    + (f", {i['quote']['area']}" if i.get("quote") and i["quote"].get("area") else "") + ")." for i in rows))]
    if ny["vs_norm"] is not None:
        qa.append((f"Are {single} prices high right now?",
                   f"In {ny['market']}, {lower} {v} inside the usual range of {usual_range(ny)} for this time of year."
                   if usual_range(ny) else
                   f"In {ny['market']}, {lower} {v} {brief.vs_usual(ny['vs_norm'])}"
                   f"{' the usual price' if abs(ny['vs_norm']) >= 5 else ''} for this time of year, "
                   f"{SEASON.get(ny['status'], ('normal for the season',))[0].lower()}."))
    if ny["range"]:
        word = {"firming": "go up", "softening": "come down", "topping": "hold firm this week, then come down",
                "bottoming": "ease a little more this week, then go up"}.get(ny["dir"], "stay about the same")
        qa.append((f"Will {single} prices go up or down?",
                   ("The market is unsettled: recent prices and shipping points disagree, so there's no two-week call. "
                    if ny["dir"] == "unsettled" else
                    f"The two-week forecast for {ny['market']} says prices should {word}: {expect_text(ny)}. ")
                   + "When it calls a firming or softening market, it was right about 3 times in 4 in testing (2021 to 2026)."))
    return qa


def item_page(commodity, rows, hist, today, sizes, alerts, as_of, notes, only=None):
    """rows: this item's headline row per market (New York first)."""
    title = name(commodity)
    lead = next(r for r in rows if r["market"] == only) if only else rows[0]
    h1 = f"{PAGES[commodity][1]} prices today" + (f", {only}" if only else "")  # "Strawberry prices today"
    parts = [f'<nav class="crumbs" aria-label="Breadcrumb"><a href="@/wholesale/">Wholesale prices</a><span>/</span>'
             + (f'<a href="@/{PAGES[commodity][0]}/">{esc(title)}</a><span>/</span>{esc(only)}' if only else esc(title))
             + "</nav>",
             f'<div class="pagehead"><h1>{esc(h1)}</h1>'
             f'<p class="date">Wholesale price per case, updated {as_of:%A}, {as_of:%B} {as_of.day}, {as_of.year}</p>'
             f'<p class="answer">{answer(lead)}</p>'
             + (market_links([r["market"] for r in rows], lead["market"], lambda m: item_link(commodity, m), remember=not only)
                if len(rows) > 1 else "") + "</div>",
             f'<section class="panel" id="m-{MKEY[lead["market"]]}">'
             + quote(lead, hist, today, sizes.get((commodity, lead["market"])), notes.get(commodity, (0, 0, ""))[2])
             + warnings(alerts, lead["market"], commodity) + "</section>"]
    if len(rows) > 1:
        body = "".join(
            f'<tr><td><a href="{item_link(commodity, i["market"])}">{esc(MARKET_LONG[i["market"]])}</a><small>{esc(i["pack"])}{esc(", " + i["quote"]["area"]) if i.get("quote") and i["quote"].get("area") else ""}</small></td>'
            f'<td class="n">{money(i["price"])}</td><td>{season(i)}</td><td>{outlook(i)}</td></tr>' for i in rows)
        parts.append('<h2>All markets</h2><p class="note">USDA’s latest quote. Each market shows its own main pack and growing area.</p><table class="t markets"><thead><tr><th>Market</th>'
                     f'<th class="n">Case</th><th>For the season</th><th>Next 2 weeks</th></tr></thead><tbody>{body}</tbody></table>')
    qa = faq(commodity, rows)
    parts.append('<h2>Questions buyers ask</h2><div class="faq">'
                 + "".join(f"<h3>{esc(q)}</h3><p>{esc(a)}</p>" for q, a in qa) + "</div>")
    parts.append(f'<script type="application/ld+json">{json.dumps({"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [{"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in qa]})}</script>')
    if commodity in GROCERY:
        parts.append(f'<p class="fine">Shopping for home? <a href="@/grocery/{GROCERY[commodity]}/">See what supermarkets are '
                     f'charging for {esc(in_sentence(commodity))} this week</a>.</p>')
    others = "".join(f'<a href="@/{slug}/">{esc(name(c))}</a>' for c, (slug, _) in sorted(PAGES.items(), key=lambda cs: name(cs[0]))
                     if c != commodity)
    parts.append(f'<h2>Other items</h2><nav class="others">{others}</nav>')
    return "\n".join(parts) + "\n"


def apple_hub(items, as_of):
    """/apple-prices/: the trade prices apples by variety, so the page lists each with its New York price."""
    rows = [next((i for i in items if i["commodity"] == c and i["market"] == "New York"), None)
            for c in PAGES if c.startswith("Apples, ")]
    rows = [i for i in rows if i]
    if not rows:
        return ""
    body = "".join(
        f'<tr><td><a href="{item_link(i["commodity"])}">{esc(name(i["commodity"]))}</a><small>{esc(i["pack"])}'
        f'{esc(", " + i["quote"]["area"]) if i.get("quote") and i["quote"].get("area") else ""}</small></td>'
        f'<td class="n">{money(i["price"])}</td><td>{season(i)}</td><td>{outlook(i)}</td></tr>' for i in rows)
    low, high = min(i["price"] for i in rows), max(i["price"] for i in rows)
    names = lambda p: name_list([i for i in rows if i["price"] == p])  # noqa: E731  ties are named together
    return "\n".join([
        '<nav class="crumbs" aria-label="Breadcrumb"><a href="@/wholesale/">Wholesale prices</a><span>/</span>Apples</nav>',
        '<div class="pagehead"><h1>Apple prices today</h1>'
        f'<p class="date">Wholesale price per case by variety, updated {as_of:%A}, {as_of:%B} {as_of.day}, {as_of.year}</p>'
        f'<p class="answer">At Hunts Point (New York), {esc(names(low))} are the lowest-priced of the main varieties at '
        f'<strong>{money(low)} a case</strong> and {esc(names(high))} the highest at <strong>{money(high)}</strong>. '
        'The trade prices apples by variety, so each has its own page with all eight markets.</p></div>',
        '<section class="panel"><table class="t markets"><thead><tr><th>Variety, New York</th><th class="n">Case</th>'
        f'<th>For the season</th><th>Next 2 weeks</th></tr></thead><tbody>{body}</tbody></table>'
        '<p class="note">USDA’s latest quote for U.S. Extra Fancy tray packs. Premium “fine appearance” and lower Fancy grade '
        'lots are left out.</p></section>',
        f'<p class="fine">Shopping for home? <a href="@/grocery/apples/">See what supermarkets are charging for apples this '
        'week</a>.</p>']) + "\n"


# ---------- build ----------
def build():
    latest = brief._read("latest.csv")
    if not latest:
        raise SystemExit("no data/export/latest.csv; run pipeline.export first")
    series = {r["series_id"]: r for r in brief._read("series.csv")}
    forecasts = brief._json("forecasts.json", {}).get("series", {})
    card = {(r["commodity"], r["market"]): r for r in brief._read("forecast_report_card.csv")}
    alerts = brief._json("alerts.json", {}).get("alerts", [])
    record = brief._json("track_record.json", {})
    items = [i for i in brief.headline_items(latest, series, forecasts, card) if i["commodity"] in PAGES]
    for i in items:
        i["dir"] = i["dir"] or ("steady" if i["range"] else "")
    alerts = backed(alerts, items)
    hist = history(items)
    as_of, today = day_changes(items)
    quotes = latest_quotes(items)
    for i in items:
        i["quote"] = quotes.get(i["series_id"])
    as_of = as_of or max(dt.date.fromisoformat(r["week_start"]) for r in latest) + dt.timedelta(days=6)
    sizes = brief.size_options(latest, series)

    notes = supply_notes(as_of)
    out = {"home": home(items, hist, today, alerts, as_of, record, notes)}
    # imported here: the site deploy imports this module for page names only, without the fetch libraries
    from . import cpi, grocery, grocery_view, meat_view
    g_day, g_items = grocery.build(grocery.rows(), cpi.Deflator(cpi.load()))
    if g_items:
        out["grocery"] = grocery_view.page(g_day, g_items)
        for aisle in ("meat", "dairy"):
            body = grocery_view.page(g_day, g_items, aisle)
            if body:
                out[f"aisle-{aisle}"] = body
        for gi in g_items:
            out[f"grocery/{gi['slug']}"] = grocery_view.item_page(gi, g_day, g_items)
    for m in MARKETS:
        out[f"market-{MKEY[m]}"] = home(items, hist, today, alerts, as_of, record, notes, only=m)
    for commodity, (slug, _) in PAGES.items():
        rows = sorted((i for i in items if i["commodity"] == commodity), key=lambda i: MARKETS.index(i["market"]))
        if not rows:
            continue
        out[f"items/{slug}"] = item_page(commodity, rows, hist, today, sizes, alerts, as_of, notes)
        for i in rows if len(rows) > 1 else []:  # one market only: the item page already is that market's page
            out[f"items/{slug}--{MARKET_SLUG[i['market']]}"] = item_page(commodity, rows, hist, today, sizes, alerts,
                                                                       as_of, notes, only=i["market"])
    hub = apple_hub(items, as_of)
    if hub:
        out[f"items/{APPLE_HUB[0]}"] = hub
    meat_items = meat_view.load().get("items", [])
    if meat_items:
        out["meat"] = meat_view.page(meat_items)
        for mi in meat_items:
            out[f"meat/{mi['slug']}"] = meat_view.item_page(mi, meat_items)
    og = og_data(items, hist, as_of)
    for gi in g_items:
        word = grocery_view.STATUS[gi["status"]][0]
        og[f"g-{gi['slug']}"] = {"title": f"{gi['short']} prices this week", "price": f"${gi['price']:.2f}",
                                 "aisle": {"meat": "meat-prices/", "dairy": "dairy-and-egg-prices/"}.get(gi["aisle"], ""),
                                 "sub": f"U.S. supermarket prices · week of {g_day:%B} {g_day.day}, {g_day.year}",
                                 "out": word + (f", {abs(gi['vs_usual'])}% {'below' if gi['vs_usual'] < 0 else 'above'} usual"
                                                if gi.get("vs_usual") else ""),
                                 "tone": {"low": "down", "high": "up"}.get(gi["status"], "flat"), "unit": gi["unit"].strip()}
    if g_items:
        og["home"] = {"title": "This week’s best buys in the produce aisle",
                      "sub": f"Supermarket prices · week of {g_day:%B} {g_day.day}, {g_day.year}",
                      "rows": [{"name": i["short"], "word": f"{abs(i['vs_usual'])}% below usual" if i["vs_usual"] else "In season",
                                "tone": "down", "price": f"${i['price']:.2f}"} for i in grocery.best_buys(g_items, 4)]}
    out["og"] = json.dumps(og, separators=(",", ":"))
    if g_items:
        from . import grocery_forecast
        out["outlook_record"] = json.dumps(grocery_forecast.RECORD)
    return as_of, out


def og_data(items, hist, as_of):
    """What each page's link preview card shows (rendered by scripts/build_site.py + scripts/og_images.py)."""
    date = f"{as_of:%B} {as_of.day}, {as_of.year}"
    out = {}
    for m in MARKETS:
        rows = [i for i in items if i["market"] == m]
        moving = sorted((i for i in rows if i["dir"] in ("firming", "softening")), key=lambda i: -abs(i["change"] or 0))[:4]
        card = {"title": f"{'Hunts Point' if m == 'New York' else m} produce prices today", "sub": f"Wholesale, per case · {date}",
                "rows": [{"name": name(i["commodity"]), "word": " ".join(DIR[i["dir"]][:2]), "tone": DIR[i["dir"]][2],
                          "price": money(i["price"])} for i in moving]}
        out[f"market-{MKEY[m]}"] = card
        if m == "New York":
            out["wholesale"] = {**card, "title": "Wholesale produce prices today"}
    for i in items:
        if i["market"] != "New York":
            continue
        arrow, word, tone = DIR[i["dir"] or "steady"]
        rng = f", {expect_text(i, '')} in 2 weeks" if i["range"] else ""
        out[PAGES[i["commodity"]][0]] = {
            "title": f"{PAGES[i['commodity']][1]} prices today", "sub": f"Wholesale, Hunts Point (New York) · {date}",
            "price": money(i["price"]), "out": f"{arrow + ' ' if arrow else ''}{word}{rng}", "tone": tone,
            "spark": spark(hist.get(i["series_id"], []), i, 420, 150).replace('class="spark"', 'class="og-spark"')}
    return out


def main():
    as_of, pages = build()
    for sub in ("items", "grocery", "recipes", "meat"):
        (OUT / sub).mkdir(parents=True, exist_ok=True)
        for old in (OUT / sub).glob("*.html"):
            old.unlink()
    for key, body in pages.items():
        (OUT / (f"{key}.json" if key in ("og", "outlook_record") else f"{key}.html")).write_text(body, encoding="utf-8")
    (OUT / "as_of.txt").write_text(as_of.isoformat())
    if "grocery" in pages:
        g_day = re.search(r"Week of (\w+ \d+, \d{4})", pages["grocery"])
        if g_day:
            (OUT / "grocery_as_of.txt").write_text(dt.datetime.strptime(g_day.group(1), "%B %d, %Y").date().isoformat())
    print(f"board: {len(pages)} fragments for {as_of}")


if __name__ == "__main__":
    main()
