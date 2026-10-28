"""Daily buyer's brief, written after every nightly run (Mon-Sat, after the terminal reports).

    python -m pipeline.brief

Turns the export files (latest prices vs. usual, forecasts, alerts, shipments, track record)
into one short article for wholesale buyers: what moved today, what's cheap or expensive,
where prices are likely heading over the next two weeks, and what that means for pricing, inventory depth and specs.

Writes data/briefs/<market date>.html, an HTML fragment dated by the latest terminal-market
day in the data. scripts/build_site.py wraps each one into a page under /brief/ and an RSS feed
(for feed readers). Re-running the same day overwrites it.

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


# ---------- visual pieces ----------
# Set like a market sheet: ruled entries and tables, no boxes. Red and green carry one meaning each
# (red = costs the buyer more, green = costs less) and always come with an arrow and a word.
GROUP_HEAD = {  # market direction over the next two weeks
    "firming": ("▲", "Firming", "Expected to rise 5% or more within two weeks."),
    "softening": ("▼", "Softening", "Expected to ease 5% or more within two weeks."),
    "steady": ("", "Steady", "No big move expected."),
}
DIR_WORD = {"firming": "▲ Firming", "softening": "▼ Softening", "steady": "Steady"}
DIR_TONE = {"firming": "bad", "softening": "good"}


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


def tag(status):
    """Season status as a coloured word with an arrow: High for the season / Low for the season / Normal."""
    icon, word = {"cheap": ("▼", "Low for the season"), "expensive": ("▲", "High for the season")}.get(status, ("", "Normal"))
    cls = {"cheap": "good", "expensive": "bad"}.get(status, "neutral")
    return f'<span class="tag {cls}">{icon + " " if icon else ""}{word}</span>'


def plain_pctile(p, vs_norm=None):
    """Where today's price ranks among the same weeks in past years, in words."""
    if p is None:
        return "Not enough history to compare yet."
    # cut-offs match the cheap / normal / high status (pipeline/export.py: 25th and 75th percentile)
    if p <= 10:
        return "Cheaper than almost every past year at this time."
    if p <= 25:
        return "Cheaper than most past years at this time."
    if p < 75:
        if vs_norm is not None and abs(vs_norm) >= 15:
            return f"{'Above' if vs_norm > 0 else 'Below'} the usual price, but inside the normal range for the season."
        return "About the usual price for this time of year."
    if p < 90:
        return "Higher than most past years at this time."
    return "Higher than almost every past year at this time."


def meter(i):
    """Where today's price sits between the cheapest and highest past years (same weeks), with a mark at usual."""
    p = i["pctile"]
    if p is None:
        return ""
    cls = {"cheap": "good", "expensive": "bad"}.get(i["status"], "neutral")
    pos = min(max(p, 2), 98)
    return (f'<div class="meter" role="img" aria-label="{esc(plain_pctile(p, i['vs_norm']))}">'
            f'<div class="track"><span class="usual"></span><span class="needle {cls}" style="left:{pos:.0f}%"></span></div>'
            '<div class="ends"><span>Cheapest year</span><span>Usual</span><span>Highest year</span></div></div>')


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
    W, H, pad = 240, 56, 5
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
    out += f'<path class="line" d="{line}"/><circle class="now" cx="{x(k0):.1f}" cy="{y(v0):.1f}" r="3.5"/>'
    label = (f"{i['name']}, last 12 weeks: {money(hist[0][1])} to {money(v0)}"
             + (f"; likely {whole(fut[-1]['lo'])} to {whole(fut[-1]['hi'])} by {fut[-1]['week']}" if fut else ""))
    return (f'<svg class="spark" viewBox="0 0 {W} {H}" role="img" aria-label="{esc(label)}">'
            f"<title>{esc(label)}</title>{out}</svg>")


def outlook(i):
    if not i["range"]:
        return ""
    if i["stable"] or i["change"] is None or abs(i["change"]) < MOVE:
        word, cls = "Steady", "neutral"
    elif i["change"] > 0:
        word, cls = "▲ Firming", "bad"
    else:
        word, cls = "▼ Softening", "good"
    return (f'<div class="outlook">Next two weeks: <b class="arrow {cls}">{word}</b><br>'
            f'likely {whole(i["range"][0])} to {whole(i["range"][1])} a case</div>')


def sizes_line(opts):
    if not opts:
        return ""
    bits = ", ".join(f"{esc(o[1])} {money(o[2] * o[0])}" for o in opts)
    return f'<div class="sizes">Other counts today: {bits}.</div>'


def item_card(i, hist, opts=None, title=None):
    return (f'<div class="item">'
            f'<div class="item-head"><div><div class="item-name">{esc(title or i["name"])}</div>'
            f'<div class="item-pack">{esc(i["pack"])}</div></div>'
            f'<div class="item-price">{money(i["price"])}<small>a case</small></div></div>'
            f'<div class="item-status">{tag(i["status"])} {esc(plain_pctile(i["pctile"], i["vs_norm"]))}</div>'
            f'{meter(i)}'
            f'<div class="item-trend">{spark(hist, i)}{outlook(i)}</div>'
            + (f'<p class="action">{esc(i["action"])}</p>' if i["action"] else "") +
            f'{sizes_line(opts)}'
            f'</div>')


def moves_table(moves, with_item=True):
    """Today's 5%+ moves as a table: item, market, previous quote, today, change."""
    head = ("<th>Item</th>" if with_item else "") + '<th>Market</th><th class="num">Last quote</th><th class="num">Today</th><th class="num">Change</th>'
    rows = []
    for m in moves:
        up = m["day_change"] > 0
        chg = f'<b class="arrow {"bad" if up else "good"}">{"▲" if up else "▼"} {abs(round(100 * m["day_change"]))}%</b>'
        tone = f'<small>USDA: “{esc(m["tone"].capitalize())}”</small>' if m.get("tone") else ""
        rows.append("<tr>" + (f'<td>{esc(m["name"])}{tone}</td>' if with_item else "")
                    + f'<td data-label="Market">{esc(m["market"])}{"" if with_item else tone}</td>'
                    f'<td class="num" data-label="Last quote">{money(m["before"])}</td>'
                    f'<td class="num" data-label="Today"><b>{money(m["today"])}</b></td>'
                    f'<td class="num" data-label="Change">{chg}</td></tr>')
    return f'<table class="data stack"><thead><tr>{head}</tr></thead><tbody>{"".join(rows)}</tbody></table>'


def warnings_list(alerts, with_headline=True):
    return '<ul class="warnings">' + "".join(
        f'<li><b class="arrow {"bad" if a["direction"] == "up" else "good"}" aria-hidden="true">'
        f'{"▲" if a["direction"] == "up" else "▼"}</b><span><b>{esc(a["expect"])}</b>'
        + (f'<br>{esc(a["headline"].replace(a["commodity"], PRODUCE_NAMES.get(a["commodity"], a["commodity"]), 1))}'
           if with_headline else "")
        + f'<br><small>{esc(a["record"])}</small></span></li>' for a in alerts) + "</ul>"


def compact_rows(rows):
    """Other markets: one table row per item that is moving or out of the ordinary."""
    body = "".join(
        f'<tr><td>{esc(i["name"])}<small>{esc(i["pack"])}</small></td>'
        f'<td class="num" data-label="Case">{money(i["price"])}</td>'
        f'<td data-label="Season">{tag(i["status"])}</td>'
        f'<td data-label="Next 2 weeks">'
        + (f'<b class="arrow {DIR_TONE.get(i["dir"], "neutral")}">{esc(DIR_WORD.get(i["dir"], ""))}</b>' if i["dir"] else "")
        + (f'<small>{whole(i["range"][0])} to {whole(i["range"][1])}</small>' if i["range"] else "")
        + "</td></tr>" for i in rows)
    return ('<table class="data stack"><thead><tr><th>Item</th><th class="num">Case</th><th>For the season</th>'
            f'<th>Next 2 weeks</th></tr></thead><tbody>{body}</tbody></table>')


def name_list(rows):
    """'romaine, iceberg and cucumbers' (lower case inside a sentence, Roma kept capitalised)."""
    names = [i["name"].lower().replace("roma ", "Roma ") for i in rows]
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


MASS = {"Iceberg", "Romaine", "Broccoli", "Celery"}  # "romaine is", but "limes are"


def verb(rows):
    return "is" if len(rows) == 1 and rows[0]["name"] in MASS else "are"


def cap(s):
    return s[:1].upper() + s[1:]


def lede(groups, high, value):
    """One or two plain sentences on New York today, the way a market reporter opens."""
    bits = []
    firm, soft = groups["firming"][:3], groups["softening"][:3]
    if firm and soft:
        bits.append(f"{cap(name_list(firm))} {verb(firm)} firming at Hunts Point, "
                    f"while {name_list(soft)} {verb(soft)} softening.")
    elif firm:
        bits.append(f"{cap(name_list(firm))} {verb(firm)} firming at Hunts Point.")
    elif soft:
        bits.append(f"{cap(name_list(soft))} {verb(soft)} softening at Hunts Point.")
    else:
        bits.append("Hunts Point looks steady across the board for the next two weeks.")
    if high:
        bits.append(f"{cap(name_list(high[:3]))} {verb(high[:3])} high for the season.")
    elif value:
        bits.append(f"{cap(name_list(value[:3]))} {verb(value[:3])} good value for the season.")
    return " ".join(bits)


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
        f"<h1>Market report for {as_of.strftime('%A')}, {day(as_of)}, {as_of.year}</h1>",
        '<p class="dateline">Wholesale case prices, New York (Hunts Point), Los Angeles and Chicago</p>',
        f'<p class="lede">{esc(lede(groups, high, value))}</p>',
    ]

    # 1. Summary: four ruled lines a reader can act on without scrolling
    def line(head, sub, rows, tone=""):
        names = esc(", ".join(i["name"] for i in rows)) if rows else '<span class="none">None today</span>'
        return f'<div><dt class="{tone}"><span class="arrow">{head}</span><small>{sub}</small></dt><dd>{names}</dd></div>'
    parts.append(
        '<h2>New York summary</h2><dl class="summary">'
        + line("▲ Firming", "Likely higher in two weeks", groups["firming"], "bad")
        + line("▼ Softening", "Likely lower in two weeks", groups["softening"], "good")
        + line("High for the season", "Higher than most past years", high)
        + line("Good value", "Cheaper than most past years", value)
        + "</dl>")

    # 2. Today's moves
    parts.append("<h2>What moved today</h2>")
    parts.append(moves_table(today[:10]) if today else '<p class="quiet">A quiet day. Nothing moved 5% or more.</p>')

    # 3. Early warnings in full
    if alerts:
        parts += ["<h2>Early warnings</h2>",
                  '<p class="quiet">Only signals that have called the next move right at least 65% of the time over 10 years.</p>',
                  warnings_list(alerts[:6])]

    # 4. New York item by item, grouped by market direction
    parts.append("<h2>New York, item by item</h2>")
    for g, (icon, head, sub) in GROUP_HEAD.items():
        if groups[g]:
            arrow = f'<span class="arrow">{icon}</span> ' if icon else ""
            parts += [f'<h3 class="group {g}">{arrow}{head}<small>{sub}</small></h3>',
                      '<div class="items">' + "".join(item_card(i, hist.get(i["series_id"], []), sizes.get((i["commodity"], i["market"])))
                                                     for i in groups[g]) + "</div>"]

    # 5. Other markets: just what's moving or out of the ordinary
    for market in MARKETS[1:]:
        rows = sorted((i for i in items if i["market"] == market and (i["dir"] in ("firming", "softening")
                                                                       or i["status"] in ("cheap", "expensive"))),
                      key=lambda i: (i["dir"] != "firming", i["dir"] != "softening", i["name"]))
        if rows:
            parts += [f"<h2>{market}</h2>", '<p class="quiet">Items that are moving or out of the ordinary for the season.</p>',
                      compact_rows(rows)]

    # 6. Supply as simple bars (more or less shipped than this week last year)
    notes = [r for r in supply if _num(r["vs_last_year_pct"]) is not None and abs(_num(r["vs_last_year_pct"])) >= SUPPLY_NOTE]
    if notes:
        notes.sort(key=lambda r: _num(r["vs_last_year_pct"]))
        bars = "".join(
            f'<div class="sbar"><span class="sname">{esc(PRODUCE_NAMES.get(r["commodity"], r["commodity"]))}</span>'
            f'<span class="strack"><span class="sfill" style="width:{min(abs(v), 100):.0f}%"></span></span>'
            f'<span class="sval">{abs(round(v))}% {"less" if v < 0 else "more"}</span></div>'
            for r in notes for v in [_num(r["vs_last_year_pct"])])
        parts += ["<h2>Supply against a year ago</h2>",
                  f'<p class="quiet">USDA-reported shipments, week of {day(dt.date.fromisoformat(notes[0]["week"]))}. '
                  'Less supply usually means a firmer market.</p>', f'<div class="supply">{bars}</div>']

    # 7. Track record, in a sentence
    live, al_rec = record.get("forecasts_live", {}), record.get("alerts", {})
    said = []
    if live.get("scored"):
        said.append(f"{live['in_range_pct']:.0f}% of {live['scored']:,} price forecasts have landed inside their range "
                    "(the aim is 80%)")
    if al_rec.get("decided"):
        said.append(f"{al_rec['came_true']} of {al_rec['decided']} early warnings came true")
    if said:
        parts += ["<h2>Track record so far</h2>",
                  f'<p>Since going live, {" and ".join(said)}. <a href="../why/">The full record</a>.</p>']
    parts.append(
        '<p class="fine">How to read this: prices are the USDA “mostly” price per case for the main pack the trade buys '
        "in each market. High and low for the season compare with the same weeks in past years, adjusted for "
        "inflation. Each small chart shows the last 12 weeks; the shaded part is where the price is likely to be "
        "(80% of the time). Market prices, not your supplier's quote.</p>")
    return as_of, "\n".join(parts) + "\n"


def main():
    as_of, body = build()
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"{as_of.isoformat()}.html"
    path.write_text(body, encoding="utf-8")
    print(f"brief: {path.relative_to(store.DATA.parent)}")


if __name__ == "__main__":
    main()
