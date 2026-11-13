"""HTML for the grocery view (the home page): this week's best buys at the supermarket.

Laid out per docs/design.md: the answer first (best buys with shelf tags), then what's in season, what's
pricey and what to buy instead, then every item. Data from pipeline/grocery.py.
"""

import datetime as dt
import html
import json
import math
import re
import statistics

from . import grocery, quality, staples


def esc(s):
    return html.escape(str(s or ""), quote=True)


def money(v):
    return f"${v:,.2f}"


STATUS = {"low": ("Great price", "good"), "typical": ("Typical price", "flat"), "high": ("Pricey", "bad"),
          "new": ("New this year", "flat"), "absent": ("No price this week", "flat")}
# wholesale pages for the same item, when there is one
WHOLESALE = {"Avocados": "avocado-prices", "Strawberries": "strawberry-prices", "Tomatoes": "tomato-prices",
             "Peppers, Bell Type": "bell-pepper-prices", "Onions, Dry": "onion-prices", "Potatoes": "potato-prices",
             "Lemons": "lemon-prices", "Limes": "lime-prices", "Cucumbers": "cucumber-prices", "Broccoli": "broccoli-prices",
             "Celery": "celery-prices", "Carrots": "carrot-prices", "Bananas": "banana-prices",
             "Blueberries": "blueberry-prices", "Grapes": "grape-prices", "Apples": "apple-prices",
             "Watermelons": "watermelon-prices", "Pineapples": "pineapple-prices", "Cantaloupes": "cantaloupe-prices",
             "Mangoes": "mango-prices", "Pears": "pear-prices", "Cabbage": "cabbage-prices", "Oranges": "orange-prices",
             "Corn-Sweet": "sweet-corn-prices", "Cauliflower": "cauliflower-prices",
             "Sweet Potatoes": "sweet-potato-prices", "Mushrooms": "mushroom-prices"}


def qual(i):
    """One plain word for quality; the reason shows on hover or tap (site/tabs.js)."""
    if not i.get("quality"):
        return ""
    level, reason = i["quality"]
    return (f'<span class="ql"><button type="button" class="ql-btn q-{level.lower()}" aria-expanded="false">'
            f'{level} quality</button><span class="ql-tip" role="tooltip">{esc(reason)}</span></span>')


def link(i):
    return f'<a href="@/grocery/{i["slug"]}/">{esc(i["name"])}</a>'


def plural(i):
    return i["short"].endswith("s")


def verb(i):
    return "are" if plural(i) else "is"


IN_SEASON = ' <span class="insea">In season</span>'


def when(today):
    part = "early" if today.day <= 10 else "mid" if today.day <= 20 else "late"
    return f"{part} {today:%B}"


def price_bar(i, today):
    """Low / typical / high for the same weeks in past years, with this week's price marked (as Google Flights does)."""
    if i["pctile"] is None:
        return ""
    pos = min(max(i["pctile"], 3), 97)
    word, tone = STATUS[i["status"]]
    return (f'<div class="pbar" role="img" aria-label="{esc(word)}: {esc(money(i["price"]))}; usually '
            f'{esc(money(i["low"]))} to {esc(money(i["high"]))} in {esc(when(today))}">'
            f'<div class="pbar-track"><span class="z-low"></span><span class="z-typ"></span><span class="z-high"></span>'
            f'<span class="pbar-mark {tone}" style="left:{pos}%"></span></div>'
            '<div class="pbar-labels"><span>Low</span><span>Typical</span><span>High</span></div>'
            f'<p class="pbar-note">Usually {money(i["low"])}–{money(i["high"])} in {when(today)}</p></div>')


def vs_line(i, today):
    """Line 1: this week's price against the usual for the time of year."""
    v = i["vs_usual"]
    if v is None:
        return "New this year: no past prices to compare yet."
    if i["status"] == "typical" and i.get("low") and i.get("high"):  # inside the usual range: show the range, not a percent
        return f"Usually {money(i['low'])}–{money(i['high'])} in {when(today)}"
    if abs(v) >= 3:
        return (f'<b class="{"good" if v < 0 else "bad"}">{abs(v)}% {"below" if v < 0 else "above"} usual</b> '
                f"for {when(today)}")
    return f"About usual for {when(today)}" if i["status"] == "typical" else f'<b class="good">At the low end of usual</b> for {when(today)}'


def meta_line(i):
    """Line 2 (produce only): quality, with its reason on tap, and whether it's in season."""
    if i["aisle"] != "produce":
        return ""
    season = "in season" if i["in_season"] else ("out of season" if i["seasons"] else "")
    if season == "out of season" and "all year" in (i.get("quality") or ("", ""))[1]:  # beside "from Mexico all year" it contradicts
        season = ""
    q = qual(i)
    if not q and not season:
        return ""
    return f'<p class="meta">{q}{", " if q and season else ""}{season if q else season.capitalize()}</p>'


def next_line(i):
    """Line 3: the two-week outlook, for every item, so rows read the same."""
    o = i.get("outlook") if i["status"] in ("low", "typical", "high") else None
    word = "likely lower" if o and o < 0 else "likely higher" if o and o > 0 else "no clear change"
    tone = "good" if o and o < 0 else "bad" if o and o > 0 else ""
    return f'<p class="next">Next 2 weeks: <span class="{tone}">{word}</span></p>'


def row_lines(i, today):
    return f'<p class="vs">{vs_line(i, today)}</p>{meta_line(i)}{next_line(i)}'


def ahead(i):
    """The two-week outlook in plain words, or "" (pipeline/grocery_forecast.py; only for items with a usual price)."""
    if not i.get("outlook") or i["status"] not in ("low", "typical", "high"):
        return ""
    if i["outlook"] < 0:
        return "Likely to drop in the next 2 weeks."
    return ("This price likely won’t last: expect it higher in the next 2 weeks." if i["status"] == "low"
            else "Likely to rise in the next 2 weeks.")


def record_sentence():
    from .grocery_forecast import RECORD
    if not RECORD["calls"]:
        return ""
    return (f"In testing on {RECORD['since']} to {dt.date.today().year} prices, the price moved the way the outlook said "
            f"(by 5% or more) {round(100 * RECORD['right'] / RECORD['calls'])}% of the time.")


def tag(i):
    return (f'<div class="shelf"><span class="shelf-price">{money(i["price"])}</span>'
            f'<span class="shelf-unit">{esc(i["unit"].strip())}</span></div>')


def lede(items, buys, pricey):
    # name the standout deals (however many there are, up to four), not a fixed three
    standout = [b for b in buys if (b["vs_usual"] or 0) <= -12][:4] or buys[:1]
    names = [b["short"].lower() for b in standout]
    if not names:
        return "Prices at the store are close to normal for the time of year."
    s = (names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1])
    s = s[:1].upper() + s[1:] + (" is" if len(names) == 1 else " are") + " the best buys this week."
    high = [p["short"].lower() for p in pricey[:2]]
    if high:
        h = high[0] if len(high) == 1 else " and ".join(high)
        s += f" {h[:1].upper() + h[1:]} {'are' if len(high) > 1 or high[0].endswith('s') else 'is'} pricey."
    return s


AISLE_HEAD = {
    "produce": "This week’s best buys in the produce aisle",
    "meat": "This week’s best buys on meat and poultry",
    "dairy": "This week’s best buys on dairy and eggs",
}
AISLE_FIND = {"produce": "Apples, berries, lettuce…", "meat": "Chicken, ground beef, bacon…", "dairy": "Eggs, milk, butter…"}


def page(today, items, aisle="produce"):
    items = [i for i in items if i["this_week"] and i["aisle"] == aisle]
    if not items:
        return None
    buys = grocery.best_buys(items, aisle=aisle)
    pricey = sorted((i for i in items if i["status"] == "high" and i["stores"] >= grocery.MIN_STORES),
                    key=lambda i: -(i["vs_usual"] or 0))
    order = {"low": 0, "typical": 1, "new": 2, "high": 3}
    season = sorted((i for i in items if i["in_season"]), key=lambda i: (order[i["status"]], i["short"]))
    stores = max(i["stores"] for i in items) if items else 0
    parts = [f'<section class="intro"><h1>{AISLE_HEAD[aisle]}</h1>'
             f'<p class="date">Week of {today:%B} {today.day}, {today.year}</p><p class="value">Each price is compared with the same '
             f'weeks in past years, adjusted for inflation. Quality comes from USDA crop reports, and every item gets a '
             f'two-week forecast.</p><p class="lede">{esc(lede(items, buys, pricey))}</p></section>']
    if buys:
        tiles = "".join(
            f'<li class="buy">{tag(i)}<div class="buy-body"><h3>{link(i)}</h3>{row_lines(i, today)}</div></li>'
            for i in buys)
        parts.append(f'<section><h2>Best buys</h2><ul class="buys">{tiles}</ul></section>')
    if season and aisle == "produce":
        chips = "".join(f'<li><span><a class="sname" href="@/grocery/{i["slug"]}/">{esc(i["short"])}</a>{qual(i)}</span>'
                        f'<span class="sword {STATUS[i["status"]][1]}">{esc(STATUS[i["status"]][0])}</span></li>'
                        for i in season)
        parts.append(f'<section class="band"><h2>In season now</h2><p class="sub">Peak flavor and supply this '
                     f'{grocery.season_of(today)}, per USDA’s seasonal produce guide, and how each is priced this week.</p>'
                     f'<ul class="season-list">{chips}</ul><p class="more"><a href="@/whats-in-season/">'
                     f'See what’s in season in {today:%B}</a>, with what’s coming next month.</p></section>')
    if pricey:
        rows = "".join(
            f'<li><h3>{link(i)}<span class="pprice">{money(i["price"])}{esc(i["unit"])}</span></h3>{row_lines(i, today)}</li>'
            for i in pricey[:8])
        parts.append(f'<section><h2>Pricey right now</h2><ul class="pricey">{rows}</ul></section>')
    rows = "".join(
        f'<tr data-name="{esc(i["name"].lower())}" data-v="{"" if i["vs_usual"] is None else i["vs_usual"]}" '
        f'data-q="{grocery.q_rank(i) if i.get("quality") else -1}"><th scope="row">{link(i)}'
        f'{IN_SEASON if i["in_season"] else ""}</th>'
        f'<td class="n">{money(i["price"])}<small>{esc(i["unit"].strip())}</small></td>'
        f'<td><span class="word {STATUS[i["status"]][1]}">{esc(STATUS[i["status"]][0])}</span>'
        + (f'<small>Usually {money(i["low"])}–{money(i["high"])}</small>' if i["status"] == "typical" and i.get("low") else
           f'<small>{abs(i["vs_usual"])}% {"below" if i["vs_usual"] < 0 else "above"} usual</small>'
           if i["vs_usual"] is not None and abs(i["vs_usual"]) >= 3 else "") + f"</td><td>{qual(i)}</td></tr>"
        for i in items)
    parts.append('<section><h2>All prices this week</h2>'
                 '<label class="find"><span>Find an item</span><input type="search" id="find" '
                 f'placeholder="{AISLE_FIND[aisle]}" autocomplete="off"></label>'
                 '<table class="all sortable"><thead><tr>'
                 '<th scope="col" aria-sort="ascending"><button type="button" data-sort="name">Item</button></th>'
                 '<th scope="col" class="n">Price</th>'
                 '<th scope="col"><button type="button" data-sort="v">Vs. usual</button></th>'
                 '<th scope="col"><button type="button" data-sort="q">Quality</button></th></tr></thead>'
                 f'<tbody>{rows}</tbody></table></section>')
    what = {"produce": "produce", "meat": "meat and poultry", "dairy": "dairy and eggs"}[aisle]
    quality = ('<p>Quality is what to expect this time of year: new crop and peak harvest rate excellent; storage, '
               'imports, end-of-season and growing-area changeovers rate fair or poor. Tap or hover over a rating for the '
               'reason. A low price on poor-quality produce is never listed as a best buy.</p>' if aisle == "produce" else "")
    years = "five to ten years" if aisle == "produce" else "five years"
    season = " “In season” is from USDA’s seasonal produce guide." if aisle == "produce" else ""
    parts.append(f'<section class="how"><h2>How this works</h2>{quality}<p>Every week USDA records the {what} prices '
                 f'U.S. supermarkets advertise, from about {round(stores, -2):,} stores for the most common items. We compare '
                 f'this week’s average price with the same weeks in the last {years}, adjusted for inflation: the cheapest '
                 f'quarter of those weeks is a great price, the highest quarter is pricey. The two-week outlook comes from a model of each item’s seasonal pattern and how '
                 f'far it is from its usual price. {record_sentence()}{season} These are advertised '
                 'prices; your store’s everyday shelf price may differ.</p><p>Buy for a restaurant, store or distributor? '
                 '<a href="@/wholesale/">See wholesale produce prices and two-week forecasts</a>.</p></section>')
    data = {"@context": "https://schema.org", "@type": "Dataset", "name": f"Supermarket {what} prices this week",
            "description": f"Average advertised supermarket prices for {what} in the U.S., compared with the same "
                           "weeks in past years.", "isBasedOn": "https://www.ams.usda.gov/market-news/retail",
            "creator": {"@type": "Organization", "name": "Produce Price Tracker"},
            "license": "https://creativecommons.org/licenses/by/4.0/"}  # same terms as the About page
    parts.append(f'<script type="application/ld+json">{json.dumps(data)}</script>')
    return "\n".join(parts) + "\n"


# ---------- one page per item ----------
def chart(i, today):
    """The past year of weekly ad prices, over the usual range for each week (earlier years, today's dollars)."""
    pts = [(dt.date.fromisoformat(d), p, lo, hi) for d, p, (lo, hi) in i["chart"]]
    if len(pts) < 6:
        return ""
    W, H, L, R, T, B = 720, 260, 92, 16, 14, 34
    t0 = today - dt.timedelta(days=371)
    vals = [p for _, p, _, _ in pts] + [v for _, _, lo, hi in pts for v in (lo, hi) if v is not None]
    lo_v, hi_v = min(vals), max(vals)
    raw = (hi_v - lo_v) / 4 or 0.25
    step = next(x for x in (0.1, 0.2, 0.25, 0.5, 1, 2, 2.5, 5, 10, 20) if x >= raw)
    y0, y1 = step * int(lo_v // step), step * (int(hi_v // step) + 1)
    x = lambda d: L + (d - t0).days / 371 * (W - L - R)  # noqa: E731
    y = lambda v: T + (y1 - v) / (y1 - y0) * (H - T - B)  # noqa: E731
    g, v = [], y0
    while v <= y1 + 1e-9:
        g.append(f'<line class="grid" x1="{L}" x2="{W - R}" y1="{y(v):.1f}" y2="{y(v):.1f}"/>'
                 f'<text class="ylab" x="{L - 8}" y="{y(v) + 4:.1f}">${v:,.2f}</text>')
        v += step
    m = dt.date(t0.year, t0.month, 1)
    while m <= today:
        if m >= t0:
            odd = " odd" if m.month % 2 else ""
            g.append(f'<text class="xlab{odd}" x="{x(m):.1f}" y="{H - 8}">{m:%b}</text>')
        m = dt.date(m.year + (m.month == 12), m.month % 12 + 1, 1)
    band = [(d, lo, hi) for d, _, lo, hi in pts if lo is not None]
    if len(band) > 1:
        top = "L".join(f"{x(d):.1f},{y(hi):.1f}" for d, _, hi in band)
        bot = "L".join(f"{x(d):.1f},{y(lo):.1f}" for d, lo, _ in reversed(band))
        g.append(f'<path class="usual" d="M{top}L{bot}Z"/>')
    # a line between weekly ads; a gap where stores didn't advertise it for over two weeks
    seg, prev = [], None
    for d, p, _, _ in pts:
        cmd = "L" if prev and (d - prev).days <= 15 else "M"
        seg.append(f"{cmd}{x(d):.1f},{y(p):.1f}")
        prev = d
    g.append(f'<path class="price" d="{"".join(seg)}"/>')
    d, p = pts[-1][0], pts[-1][1]
    g.append(f'<circle class="now" cx="{x(d):.1f}" cy="{y(p):.1f}" r="4.5"/>')
    label = f"{i['short']}, average supermarket price over the past year"
    return (f'<figure class="chart"><svg viewBox="0 0 {W} {H}" role="img" aria-label="{esc(label)}"><title>{esc(label)}</title>'
            f'{"".join(g)}</svg><div class="legend"><span><i class="k-price"></i>Average price{esc(i["unit"])}</span>'
            '<span><i class="k-usual"></i>Usual range for the time of year</span></div></figure>')


def calendar(i, today):
    """A 12-month strip: quality to expect each month, and how the typical ad price runs, with this month marked."""
    def in_season(m):
        if not i["seasons"]:
            return None
        return i["commodity"] in grocery.SEASONS[grocery.season_of(dt.date(2026, m, 15))]
    q = {m: quality.quality(i["commodity"], m, in_season(m)) for m in range(1, 13)}
    prices = i.get("month_price") or {}
    show_price = len(prices) >= 6
    if not any(q.values()) and not show_price:
        return ""
    now = today.month
    head = "".join(f'<th scope="col"{" class=now" if m == now else ""}><span class="mfull">{grocery.MONTHS[m - 1][:3]}</span>'
                   f'<span class="mone" aria-hidden="true">{grocery.MONTHS[m - 1][0]}</span></th>' for m in range(1, 13))
    rows = ""
    if any(q.values()):
        cells = "".join(
            f'<td class="cq{" q-" + q[m][0].lower() if q[m] else ""}" '
            f'title="{grocery.MONTHS[m - 1]}: {esc(q[m][0] + " quality. " + q[m][1]) if q[m] else "no rating"}">'
            f'<span class="vh">{q[m][0] if q[m] else "No rating"}</span></td>' for m in range(1, 13))
        rows += f'<tr><th scope="row">Quality</th>{cells}</tr>'
    if show_price:
        rows += price_line(prices, now)
    legend = ""
    if any(q.values()):
        legend = '<figcaption class="legend">' + "".join(
            f'<span><i class="sw q-{lv.lower()}"></i>{lv} quality</span>' for lv in reversed(quality.LEVELS)
            if any(v and v[0] == lv for v in q.values())) + "</figcaption>"
    note, all_months = "", ""
    if show_price:
        note = f'<p class="cal-note">{price_note(prices, now, esc(i["unit"]))}</p>'
        all_months = ('<details class="cal-all"><summary>Typical price by month</summary><ul>' + "".join(
            f'<li><span>{grocery.MONTHS[m - 1]}</span><span>{money(prices[m])}{esc(i["unit"])}</span></li>' for m in sorted(prices))
            + "</ul></details>")
    return (f'<figure class="cal"><table><caption class="vh">{esc(i["short"])}: quality and typical supermarket price '
            f'by month</caption><thead><tr><td></td>{head}</tr></thead><tbody>{rows}</tbody></table>{legend}</figure>'
            f'{note}{all_months}')


def _ticks(lo, hi):
    """Round price labels for the axis: a step that gives 2 to 4 of them inside the range."""
    for step in (0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 20, 50):
        first = math.ceil(lo / step)
        values = [n * step for n in range(first, math.floor(hi / step) + 1)]
        if len(values) <= 4:
            return values
    return [lo, hi]


def price_line(prices, now):
    """Typical price by month as a line: a line can use a narrower axis than a bar, which needs zero, as long as the
    axis is labeled. The axis spans at least 25% of the typical price, so differences of pennies stay small."""
    lo, hi = min(prices.values()), max(prices.values())
    mid = statistics.median(prices.values())
    span = max((hi - lo) * 1.3, 0.25 * mid)
    bottom = max(0.0, (lo + hi) / 2 - span / 2)
    top = bottom + span

    def y(v):
        return 100 * (top - v) / (top - bottom)

    def x(m):
        return 100 * (m - 0.5) / 12

    ticks = _ticks(bottom, top)
    grid = "".join(f'<i class="lc-grid" style="top:{y(t):.1f}%"></i>' for t in ticks)
    labels = "".join(f'<span class="lc-tick" style="top:{y(t):.1f}%">{money(t)}</span>' for t in ticks)
    runs, run = [], []  # no line across months with no price
    for m in range(1, 13):
        if m in prices:
            run.append(f"{x(m) * 12:.1f},{y(prices[m]):.1f}")
        elif run:
            runs.append(run)
            run = []
    if run:
        runs.append(run)
    lines = "".join(f'<polyline points="{" ".join(r)}" vector-effect="non-scaling-stroke"/>' for r in runs)
    low = min(prices, key=prices.get)
    dots, tags = "", ""
    for m, v in sorted(prices.items()):
        kind = " now" if m == now else " low" if m == low else ""
        dots += (f'<i class="lc-dot{kind}" style="left:{x(m):.2f}%;top:{y(v):.1f}%" '
                 f'title="{grocery.MONTHS[m - 1]}: usually {money(v)}"></i>')
    for m, place in ((now, "above"), (low, "below")):
        if m in prices and not (place == "below" and low == now):
            edge = " start" if m <= 1 else " end" if m >= 12 else ""
            tags += (f'<span class="lc-val {place}{edge}" style="left:{x(m):.2f}%;top:{y(prices[m]):.1f}%">'
                     f"{'Low' if m == low else grocery.MONTHS[m - 1][:3]}: {money(prices[m])}</span>")
    return (f'<tr class="lc-row"><th scope="row"><span class="vh">Typical price</span><span class="lc-axis" aria-hidden="true">{labels}'
            f'</span></th><td colspan="12"><div class="lc" aria-hidden="true">{grid}<svg viewBox="0 0 1200 100" '
            f'preserveAspectRatio="none">{lines}</svg>{dots}{tags}</div></td></tr>')


def price_note(prices, now, unit):
    """The chart in words."""
    lo, hi = min(prices, key=prices.get), max(prices, key=prices.get)
    if (prices[hi] - prices[lo]) / statistics.median(prices.values()) < 0.10:
        return (f"The price barely changes through the year: usually {money(prices[lo])} to "
                f"{money(prices[hi])}{unit}.")
    text = (f"Usually cheapest in {grocery.MONTHS[lo - 1]}, at {money(prices[lo])}{unit}, and highest in "
            f"{grocery.MONTHS[hi - 1]}, at {money(prices[hi])}.")
    if now in prices and now not in (lo, hi):
        text += f" {grocery.MONTHS[now - 1]} usually runs {money(prices[now])}."
    return text


def answer(i, today):
    return price_sentence(i, today) + " " + season_sentence(i, today)


def price_sentence(i, today):
    name = i["short"].lower()
    if i["this_week"]:
        s = (f"{i['short']} {'average' if plural(i) else 'averages'} <strong>{money(i['price'])}{esc(i['unit'])}"
             "</strong> at U.S. supermarkets this week")
        if i["vs_usual"] is not None:
            s += (", about the usual price" if abs(i["vs_usual"]) < 3 else
                  f", {abs(i['vs_usual'])}% {'below' if i['vs_usual'] < 0 else 'above'} usual") + f" for {when(today)}"
        s += "."
    else:
        last = dt.date.fromisoformat(i["last_date"])
        s = (f"There’s no U.S. supermarket price for {name} this week. The last one, the week of {last:%B} {last.day}, "
             f"was <strong>{money(i['price'])}{esc(i['unit'])}</strong>.")
    return s


def as_modifier(name):
    """'Eggs' -> 'Egg', 'Pork chops' -> 'Pork chop', for 'egg prices'; mass nouns stay ('Pork shoulder')."""
    *head, last = name.split(" ")
    if last.endswith("ies"):
        last = last[:-3] + "y"
    elif last.endswith(("oes", "ches", "shes")):
        last = last[:-2]
    elif last.endswith("s") and not last.endswith(("ss", "us")):
        last = last[:-1]
    return " ".join(head + [last])


def season_sentence(i, today):
    when_in = ", ".join(i["seasons"][:-1]) + (" and " if len(i["seasons"]) > 1 else "") + i["seasons"][-1] if i["seasons"] else ""
    if i["in_season"]:
        s = f"{i['short']} {verb(i)} in season now."
    elif when_in:
        s = f"{i['short']} {verb(i)} out of season now; {'they’re' if plural(i) else 'it’s'} in season in {when_in}."
    else:
        s = ""
    best = quality.best_months(i["commodity"])
    if i["cheapest_months"] and best and not set(i["cheapest_months"]) & set(best):
        s += (f" Prices are lowest in {grocery.month_list(i['cheapest_months'])}, but that’s out-of-season produce; "
              f"for the best quality, buy in {grocery.month_list(best)}.")
    elif i["cheapest_months"] and s:
        s += f" {'They’re' if plural(i) else 'It’s'} usually cheapest in {grocery.month_list(i['cheapest_months'])}."
    elif i["cheapest_months"]:  # no season to speak of (meat, dairy, some produce): say it on its own
        s = f"{as_modifier(i['short'])} prices are usually lowest in {grocery.month_list(i['cheapest_months'])}."
    return s.strip()


def organic_sentence(i):
    o = i["organic"]
    gap = (f"{o['more']}% more than regular" if o["more"] > 0 else f"{-o['more']}% less than regular" if o["more"] < 0
           else "the same as regular")
    return (f"Organic: ${o['price']:.2f}{i['unit']} in this week’s store flyers, {gap} "
            f"({o['stores']:,} stores advertised it).")


def faq(i, today):
    name = i["short"].lower()
    qa = [(f"How much {'do' if plural(i) else 'does'} {name} cost at the grocery store?",
           html.unescape(re.sub(r"<[^>]+>", "", price_sentence(i, today))))]
    if i["aisle"] == "produce":  # "in season" only means something for fruit and vegetables
        ans = "" if not i["seasons"] else season_sentence(i, today).split(" They’re usually")[0].split(" It’s usually")[0]
        qa.append((f"{'Are' if plural(i) else 'Is'} {name} in season right now?",
                   ans or "USDA’s seasonal guide doesn’t list it; stores carry it most of the year."))
    if i.get("why") and i["status"] in ("low", "high"):
        cause = i["why"].removeprefix("Why: ")
        qa.append((f"Why {verb(i)} {name} so {'cheap' if i['status'] == 'low' else 'expensive'} right now?",
                   cause[:1].upper() + cause[1:].rstrip(".") + ", according to this week’s USDA reports."))
    if ahead(i):
        qa.append((f"Will {name} get {'cheaper' if i['outlook'] < 0 else 'more expensive'} soon?",
                   f"{ahead(i)} {record_sentence()}".strip()))
    if i.get("organic"):
        qa.append((f"How much more {'do' if plural(i) else 'does'} organic {name} cost?", organic_sentence(i)
                   .replace("Organic: ", "Organic " + name + " averaged ", 1)))
    if i["cheapest_months"]:
        qa.append((f"When {verb(i)} {name} cheapest?",
                   f"In past years, supermarket prices for {name} were lowest in "
                   f"{grocery.month_list(i['cheapest_months'])}"
                   + "."))
    return qa


def priced(i):
    """' for boneless strip steak (value packs)': names the cut when the item name could mean several."""
    cut = staples.CUT.get(i["commodity"])
    if not cut and not i.get("value_pack"):
        return ""
    return f" for {cut or i['short'].lower()}" + (" (value packs)" if i.get("value_pack") else "")


def item_page(i, today, all_items):
    h1 = f"How much {verb(i)} {i['short'].lower()} this week?"
    up, label = {"meat": ("@/meat-prices/", "Meat & poultry"), "dairy": ("@/dairy-and-egg-prices/", "Dairy & eggs")}.get(
        i["aisle"], ("@/", "Produce"))
    parts = [f'<nav class="crumbs" aria-label="Breadcrumb"><a href="{up}">{label}</a><span>/</span>{esc(i["short"])}</nav>',
             f'<section class="intro"><h1>{esc(h1)}</h1>'
             f'<p class="date">Week of {today:%B} {today.day}, {today.year}. Average advertised price{priced(i)} at U.S. '
             'supermarkets, checked against the same week in past years.</p>'
             f'<p class="answer">{answer(i, today)}</p></section>']
    if i["this_week"]:
        word, tone = STATUS[i["status"]]
        parts.append(f'<section class="gquote">{tag(i)}<div><p class="gword {tone}">{esc(word)}</p>{row_lines(i, today)}'
                     + (f'<p class="cause">{esc(i["why"])}</p>' if i.get("why") else "")
                     + f'{price_bar(i, today)}</div></section>')
        if i.get("organic"):
            parts.append(f'<p class="organic">{esc(organic_sentence(i))}</p>')
        if i["stores"] < grocery.MIN_STORES:
            parts.append(f'<p class="fine">Only {i["stores"]:,} stores listed {"them" if plural(i) else "it"} this '
                         "week, often a single chain, so treat the comparison loosely.</p>")
    when_bits = []
    if i.get("quality"):
        when_bits.append(f"<li><b>Quality now</b><span><b class=\"q-{i['quality'][0].lower()}\">{i['quality'][0]}.</b> "
                         f"{esc(i['quality'][1])}</span></li>")
    if i["seasons"] and i["commodity"] not in quality.CALENDAR:  # the calendar above says it better
        when_bits.append(f"<li><b>In season</b><span>{esc(', '.join(s.capitalize() for s in i['seasons']))} "
                         "(USDA seasonal produce guide)</span></li>")
    if quality.best_months(i["commodity"]):
        when_bits.append(f"<li><b>Best quality</b><span>{grocery.month_list(quality.best_months(i['commodity']))}</span></li>")
    cal = calendar(i, today)
    if when_bits or cal:
        parts.append(f'<section><h2>When to buy</h2>{cal}' + (f'<ul class="facts">{"".join(when_bits)}</ul>' if when_bits else "") + "</section>")
    c = chart(i, today)
    if c:
        parts.append(f"<section><h2>The past year</h2>{c}</section>")
    qa = faq(i, today)
    parts.append('<section class="faq"><h2>Questions shoppers ask</h2>'
                 + "".join(f"<h3>{esc(q)}</h3><p>{esc(a)}</p>" for q, a in qa) + "</section>")
    parts.append(f'<script type="application/ld+json">{json.dumps({"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [{"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in qa]})}</script>')
    if i["commodity"] in WHOLESALE:
        parts.append(f'<p class="fine">Buy for a restaurant, store or distributor? <a href="@/{WHOLESALE[i["commodity"]]}/">'
                     f'See wholesale {esc(i["short"].lower())} prices and the two-week outlook</a>.</p>')
    # more from the same aisle, then the way to the other aisles
    others = "".join(f'<a href="@/grocery/{o["slug"]}/">{esc(o["short"])}</a>'
                     for o in sorted(all_items, key=lambda o: o["short"])
                     if o["slug"] != i["slug"] and o["aisle"] == i["aisle"])
    aisles = {"produce": ("@/", "Produce"), "meat": ("@/meat-prices/", "Meat & poultry"),
              "dairy": ("@/dairy-and-egg-prices/", "Dairy & eggs")}
    rest = " and ".join(f'<a href="{u}">{n}</a>' for a, (u, n) in aisles.items() if a != i["aisle"])
    parts.append(f'<section><h2>More {aisles[i["aisle"]][1].lower()}</h2><nav class="others">{others}</nav>'
                 f'<p class="fine">Other aisles: {rest}</p></section>')
    return "\n".join(parts) + "\n"


# ---------- what's in season this month (/whats-in-season/) ----------
# One page at one address, updated as the months change (Google's John Mueller: reuse one URL for recurring
# seasonal content so it keeps its links). Fruit vs vegetable follows USDA MyPlate's food groups
# (avocados, tomatoes and plantains are vegetables there).
FRUITS = {"Apple Pears", "Apples", "Apricots", "Bananas", "Blackberries", "Blueberries", "Cactus Pears", "Cantaloupes",
          "Cherries", "Clementines", "Coconut", "Cranberries", "Dekopon (Shiranui)", "Dragon Fruit (Pitaya)", "Grapefruit",
          "Grapes", "Honeydews", "Kiwifruit", "Lemons", "Limes", "Mangoes", "Nectarines", "Oranges", "Papaya", "Peaches",
          "Pears", "Persimmons", "Pineapples", "Plums", "Pomegranates", "Raspberries", "Satsumas", "Strawberries",
          "Tangelos", "Tangerines/Mandarins", "Watermelons"}
NOT_PRODUCE = {"Honey"}
KEEP_NAME = ("Brussels sprouts", "Swiss chard")


def names_list(ns):
    ns = list(ns)
    return ns[0] if len(ns) == 1 else ", ".join(ns[:-1]) + " and " + ns[-1]


def in_text(rows):
    """Names as they read mid-sentence: 'apples', 'Brussels sprouts'."""
    return [i["short"] if i["short"] in KEEP_NAME else i["short"].lower() for i in rows]


def season_rows(rows):
    def right(i):
        if not i["this_week"]:
            return '<span class="sword flat">No price this week</span>'
        return (f'<span class="sprice">{money(i["price"])}<small>{esc(i["unit"])}</small>'
                f'<span class="sword {STATUS[i["status"]][1]}">{esc(STATUS[i["status"]][0])}</span></span>')
    return "".join(f'<li><span><a class="sname" href="@/grocery/{i["slug"]}/">{esc(i["short"])}</a>{qual(i)}</span>'
                   f'{right(i)}</li>' for i in rows)


def season_page(today, items):
    """Fruits and vegetables in season this month, each with this week's supermarket price and the quality to expect.
    In season = USDA SNAP-Ed Seasonal Produce Guide (as everywhere on the site); "also at their best" = rated
    excellent this month in the quality calendar without being on USDA's list (clementines in November)."""
    produce = [i for i in items if i["aisle"] == "produce" and i["commodity"] not in NOT_PRODUCE]
    if not produce:
        return None
    month = grocery.MONTHS[today.month - 1]
    nxt = dt.date(today.year + (today.month == 12), today.month % 12 + 1, 15)
    next_month = grocery.MONTHS[nxt.month - 1]
    order = {"low": 0, "typical": 1, "new": 2, "high": 3, "absent": 4}

    def level(i):
        return (i.get("quality") or ("", ""))[0]

    def key(i):
        return (not i["this_week"], order.get(i["status"], 4), -grocery.q_rank(i) if i.get("quality") else 0, i["short"])

    def by_name(rows):
        return sorted(rows, key=lambda i: i["short"])
    season = [i for i in produce if i["in_season"]]
    best = [i for i in produce if not i["in_season"] and level(i) == "Excellent"]
    fruits = sorted((i for i in season if i["commodity"] in FRUITS), key=key)
    veg = sorted((i for i in season if i["commodity"] not in FRUITS), key=key)
    value = sorted((i for i in season + best if i["this_week"] and i["status"] == "low" and level(i) not in ("Poor", "Fair")),
                   key=lambda i: i["vs_usual"] or 0)[:6]
    # coming next month: on USDA's list next month or rated excellent next month, and neither now
    coming = by_name(i for i in produce if not i["in_season"] and level(i) != "Excellent" and (
        i["commodity"] in grocery.SEASONS[grocery.season_of(nxt)]
        or (quality.quality(i["commodity"], nxt.month) or ("",))[0] == "Excellent"))
    soon = {i["commodity"] for i in coming}  # before their season is not "past their best" (leeks in November)
    past = sorted((i for i in produce if i["this_week"] and not i["in_season"] and level(i) in ("Poor", "Fair")
                   and i["commodity"] not in soon),
                  key=lambda i: (level(i) != "Poor", i["short"]))

    lede = ""
    peak = [i for i in fruits + veg if level(i) == "Excellent"][:8]  # name the answer first (it is also the search snippet)
    if peak:
        names = names_list(in_text(peak))
        lede = f"{names[:1].upper() + names[1:]} are at their best in {month}. "
    if fruits and veg:
        lede += f"In all, {len(fruits)} fruits and {len(veg)} vegetables are in season, per USDA’s seasonal produce guide. "
    if value:
        lede += f"The best value this week: {names_list(in_text(value))}, all priced below usual at U.S. supermarkets."
    parts = [f'<section class="intro"><h1>What’s in season in {month}</h1>'
             f'<p class="date">Prices for the week of {today:%B} {today.day}, {today.year}</p>'
             f'<p class="lede">{esc(lede.strip())}</p>'
             '<p class="value">Each item shows the quality to expect this month and its average price at U.S. '
             'supermarkets this week, compared with the same weeks in past years.</p></section>']
    for head, rows in (("Fruits", fruits), ("Vegetables", veg)):
        if rows:
            parts.append(f'<section><h2>{head} in season in {month}</h2>'
                         f'<ul class="season-list in-month">{season_rows(rows)}</ul></section>')
    if best:
        parts.append(f'<section><h2>Also at their best in {month}</h2><p class="sub">Not on USDA’s list for '
                     f'{grocery.season_of(today)}, but this is their peak harvest.</p>'
                     f'<ul class="season-list in-month">{season_rows(sorted(best, key=key))}</ul></section>')
    if coming:
        links = names_list([f'<a href="@/grocery/{i["slug"]}/">{esc(i["short"])}</a>' for i in coming])
        parts.append(f'<section><h2>Coming into season in {next_month}</h2><p>{links}.</p></section>')
    if past:
        parts.append(f'<section><h2>Past their best in {month}</h2><p class="sub">Still in stores, but out of season, '
                     'so most likely imported or from storage. Tap a rating for the reason.</p>'
                     f'<ul class="season-list in-month">{season_rows(past)}</ul></section>')
    qa = []
    for head, rows in (("fruits", fruits), ("vegetables", veg)):
        if rows:
            qa.append((f"What {head} are in season in {month}?",
                       f"Per USDA’s seasonal produce guide: {names_list(in_text(by_name(rows)))}."))
    if value:
        qa.append(("Which in-season produce is the best value this week?",
                   names_list([f"{n[:1].upper() + n[1:] if k == 0 else n} ({money(i['price'])}{i['unit']}, "
                               f"{abs(i['vs_usual'])}% below usual)" for k, (n, i) in enumerate(zip(in_text(value), value))])
                   + ", at U.S. supermarkets this week."))
    if coming:
        names = names_list(in_text(coming))
        qa.append((f"What comes into season in {next_month}?", names[:1].upper() + names[1:] + "."))
    if qa:
        parts.append('<section class="faq"><h2>Questions shoppers ask</h2>'
                     + "".join(f"<h3>{esc(q)}</h3><p>{esc(a)}</p>" for q, a in qa) + "</section>")
        ld = {"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [
            {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in qa]}
        parts.append(f'<script type="application/ld+json">{json.dumps(ld)}</script>')
    parts.append('<section class="how"><h2>How this works</h2><p>“In season” follows USDA’s SNAP-Ed Seasonal Produce '
                 'Guide. Quality is what to expect this month: new crop and peak harvest rate excellent; storage, imports '
                 'and the end of a season rate fair or poor. Prices are the average U.S. supermarkets advertised this week, '
                 'reported by USDA; your store’s price may differ. Fruits and vegetables are grouped the way USDA’s MyPlate '
                 'groups them, so avocados and tomatoes count as vegetables.</p></section>')
    return "\n".join(parts) + "\n"
