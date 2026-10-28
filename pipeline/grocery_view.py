"""HTML for the grocery view (the home page): this week's best buys at the supermarket.

Laid out per docs/design.md: the answer first (best buys with shelf tags), then what's in season, what's
pricey and what to buy instead, then every item. Data from pipeline/grocery.py.
"""

import datetime as dt
import html
import json
import re

from . import grocery


def esc(s):
    return html.escape(str(s or ""), quote=True)


def money(v):
    return f"${v:,.2f}"


STATUS = {"low": ("Great price", "good"), "typical": ("Typical price", "flat"), "high": ("Pricey", "bad"),
          "new": ("New to the ads", "flat"), "absent": ("Not in this week’s ads", "flat")}
# wholesale pages for the same item, when there is one
WHOLESALE = {"Avocados": "avocado-prices", "Strawberries": "strawberry-prices", "Tomatoes": "tomato-prices",
             "Peppers, Bell Type": "bell-pepper-prices", "Onions, Dry": "onion-prices", "Potatoes": "potato-prices",
             "Lemons": "lemon-prices", "Limes": "lime-prices", "Cucumbers": "cucumber-prices", "Broccoli": "broccoli-prices",
             "Celery": "celery-prices", "Carrots": "carrot-prices", "Bananas": "banana-prices",
             "Blueberries": "blueberry-prices", "Grapes": "grape-prices"}


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


def why_line(i, today):
    bits = []
    if i["vs_usual"] is not None and abs(i["vs_usual"]) >= 3:
        bits.append(f'<b class="{"good" if i["vs_usual"] < 0 else "bad"}">{abs(i["vs_usual"])}% '
                    f'{"below" if i["vs_usual"] < 0 else "above"} usual</b> for {when(today)}.')
    if i["in_season"]:
        bits.append("In season.")
    if i["featured"] and i["featured"] >= 1.3:
        bits.append(f"On special in {i['stores']:,} stores, more than usual.")
    return " ".join(bits)


def tag(i):
    return (f'<div class="shelf"><span class="shelf-price">{money(i["price"])}</span>'
            f'<span class="shelf-unit">{esc(i["unit"].strip())}</span></div>')


def lede(items, buys, pricey):
    names = [b["short"].lower() for b in buys[:3]]
    if not names:
        return "Prices at the store are close to normal for the time of year."
    s = (names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1])
    s = s[:1].upper() + s[1:] + (" is" if len(names) == 1 else " are") + " the best buys this week."
    swaps = [p for p in pricey if p.get("swap")]
    if swaps:
        p = swaps[0]
        s += f" {p['short']} {'is' if not p['short'].endswith('s') else 'are'} pricey; {p['swap'].lower()} " \
             f"{'is' if not p['swap'].endswith('s') else 'are'} the better buy."
    return s


def page(today, items):
    items = [i for i in items if i["this_week"]]
    buys = grocery.best_buys(items)
    pricey = sorted((i for i in items if i["status"] == "high" and i["stores"] >= grocery.MIN_STORES),
                    key=lambda i: -(i["vs_usual"] or 0))
    order = {"low": 0, "typical": 1, "new": 2, "high": 3}
    season = sorted((i for i in items if i["in_season"]), key=lambda i: (order[i["status"]], i["short"]))
    stores = max(i["stores"] for i in items) if items else 0
    parts = [f'<section class="intro"><h1>This week’s best buys in the produce aisle</h1>'
             f'<p class="date">Week of {today:%B} {today.day}, {today.year} · from supermarket ads across the U.S., '
             f'reported by USDA</p><p class="lede">{esc(lede(items, buys, pricey))}</p></section>']
    if buys:
        tiles = "".join(
            f'<li class="buy">{tag(i)}<div class="buy-body"><h3>{link(i)}</h3>'
            f'<p class="buy-why">{why_line(i, today)}</p>{price_bar(i, today)}</div></li>' for i in buys)
        parts.append(f'<section><h2>Best buys</h2><ul class="buys">{tiles}</ul></section>')
    if season:
        chips = "".join(f'<li><a class="sname" href="@/grocery/{i["slug"]}/">{esc(i["short"])}</a>'
                        f'<span class="sword {STATUS[i["status"]][1]}">{esc(STATUS[i["status"]][0])}</span></li>'
                        for i in season)
        parts.append(f'<section class="band"><h2>In season now</h2><p class="sub">Peak flavor and supply this '
                     f'{grocery.season_of(today)}, per USDA’s seasonal produce guide, and how each is priced this week.</p>'
                     f'<ul class="season-list">{chips}</ul></section>')
    if pricey:
        rows = "".join(
            f'<li><div><b>{link(i)}</b><span>{money(i["price"])}{esc(i["unit"])}, '
            f'<b class="bad">{i["vs_usual"]}% above usual</b></span></div>'
            + (f'<p class="swap">Try {esc(i["swap"].lower())} instead</p>' if i.get("swap") else "") + "</li>"
            for i in pricey[:8])
        parts.append(f'<section><h2>Pricey right now</h2><ul class="pricey">{rows}</ul></section>')
    rows = "".join(
        f'<tr data-name="{esc(i["name"].lower())}"><th scope="row">{link(i)}'
        f'{IN_SEASON if i["in_season"] else ""}</th>'
        f'<td class="n">{money(i["price"])}<small>{esc(i["unit"].strip())}</small></td>'
        f'<td><span class="word {STATUS[i["status"]][1]}">{esc(STATUS[i["status"]][0])}</span>'
        + (f'<small>{abs(i["vs_usual"])}% {"below" if i["vs_usual"] < 0 else "above"} usual</small>'
           if i["vs_usual"] is not None and abs(i["vs_usual"]) >= 3 else "") + "</td></tr>"
        for i in items)
    parts.append('<section><h2>Every item in this week’s ads</h2>'
                 '<label class="find"><span>Find an item</span><input type="search" id="find" '
                 'placeholder="Apples, berries, lettuce…" autocomplete="off"></label>'
                 '<table class="all"><thead><tr><th scope="col">Item</th><th scope="col" class="n">Ad price</th>'
                 f'<th scope="col">For the time of year</th></tr></thead><tbody>{rows}</tbody></table></section>')
    parts.append(f'<section class="how"><h2>How this works</h2><p>Every week USDA records the produce prices '
                 f'supermarkets advertise, about {stores:,} stores for the most-advertised items. We compare this '
                 'week’s average ad price with the same weeks in the last five to ten years, adjusted for inflation: '
                 'the cheapest quarter of those weeks is a great price, the highest quarter is pricey. “In season” is '
                 'from USDA’s seasonal produce guide. These are advertised sale prices; your store’s shelf price may '
                 'differ.</p><p>Buy for a restaurant, store or distributor? <a href="@/wholesale/">See wholesale '
                 'market prices and two-week forecasts</a>.</p></section>')
    data = {"@context": "https://schema.org", "@type": "Dataset", "name": "Supermarket produce ad prices this week",
            "description": "Average advertised supermarket prices for produce in the U.S., compared with the same "
                           "weeks in past years.", "isBasedOn": "https://www.ams.usda.gov/market-news/retail"}
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
    label = f"{i['short']}, average supermarket ad price over the past year"
    return (f'<figure class="chart"><svg viewBox="0 0 {W} {H}" role="img" aria-label="{esc(label)}"><title>{esc(label)}</title>'
            f'{"".join(g)}</svg><div class="legend"><span><i class="k-price"></i>Average ad price{esc(i["unit"])}</span>'
            '<span><i class="k-usual"></i>Usual range for the time of year</span></div></figure>')


def answer(i, today):
    return price_sentence(i, today) + " " + season_sentence(i, today)


def price_sentence(i, today):
    name = i["short"].lower()
    if i["this_week"]:
        s = (f"This week, U.S. supermarkets are advertising {name} at <strong>{money(i['price'])}{esc(i['unit'])}"
             "</strong> on average")
        if i["vs_usual"] is not None:
            s += (", about the usual price" if abs(i["vs_usual"]) < 3 else
                  f", {abs(i['vs_usual'])}% {'below' if i['vs_usual'] < 0 else 'above'} usual") + f" for {when(today)}"
        s += "."
    else:
        last = dt.date.fromisoformat(i["last_date"])
        s = (f"{i['short']} {verb(i)} not in this week’s supermarket ads. Stores last advertised {'them' if plural(i) else 'it'} "
             f"the week of {last:%B} {last.day} at <strong>{money(i['price'])}{esc(i['unit'])}</strong>.")
    return s


def season_sentence(i, today):
    when_in = ", ".join(i["seasons"][:-1]) + (" and " if len(i["seasons"]) > 1 else "") + i["seasons"][-1] if i["seasons"] else ""
    if i["in_season"]:
        s = f"{i['short']} {verb(i)} in season now."
    elif when_in:
        s = f"{i['short']} {verb(i)} out of season now; {'they’re' if plural(i) else 'it’s'} in season in {when_in}."
    else:
        s = ""
    if i["cheapest_months"]:
        s += f" {'They’re' if plural(i) else 'It’s'} usually cheapest in {grocery.month_list(i['cheapest_months'])}."
    return s.strip()


def faq(i, today):
    name = i["short"].lower()
    qa = [(f"How much {'do' if plural(i) else 'does'} {name} cost at the grocery store?",
           html.unescape(re.sub(r"<[^>]+>", "", price_sentence(i, today))))]
    qa.append((f"{'Are' if plural(i) else 'Is'} {name} in season right now?",
               season_sentence(i, today).split(" They’re usually")[0].split(" It’s usually")[0] or
               "USDA’s seasonal guide doesn’t list it; stores carry it most of the year."))
    if i["cheapest_months"]:
        qa.append((f"When {verb(i)} {name} cheapest?",
                   f"In past years, supermarket ads for {name} were lowest in "
                   f"{grocery.month_list(i['cheapest_months'])}"
                   + (f", and stores featured {'them' if plural(i) else 'it'} most in {grocery.month_list(i['peak_months'])}."
                      if i["peak_months"] else ".")))
    return qa


def item_page(i, today, all_items):
    h1 = f"How much {verb(i)} {i['short'].lower()} this week?"
    parts = [f'<nav class="crumbs"><a href="@/">Grocery prices</a><span>/</span>{esc(i["short"])}</nav>',
             f'<section class="intro"><h1>{esc(h1)}</h1>'
             f'<p class="date">Supermarket ads across the U.S., week of {today:%B} {today.day}, {today.year}, from USDA</p>'
             f'<p class="answer">{answer(i, today)}</p></section>']
    if i["this_week"]:
        word, tone = STATUS[i["status"]]
        parts.append(f'<section class="gquote">{tag(i)}<div><p class="gword {tone}">{esc(word)}</p>'
                     f'<p class="buy-why">{why_line(i, today) or esc(i["name"])}</p>{price_bar(i, today)}</div></section>')
        if i.get("swap"):
            parts.append(f'<p class="swap big">Pricey this week. Try {esc(i["swap"].lower())} instead.</p>')
        if i["stores"] < grocery.MIN_STORES:
            parts.append(f'<p class="fine">Only {i["stores"]:,} stores advertised {"them" if plural(i) else "it"} this '
                         "week, often a single chain, so treat the comparison loosely.</p>")
    when_bits = []
    if i["seasons"]:
        when_bits.append(f"<li><b>In season</b><span>{esc(', '.join(s.capitalize() for s in i['seasons']))} "
                         "(USDA seasonal produce guide)</span></li>")
    if i["cheapest_months"]:
        when_bits.append(f"<li><b>Usually cheapest</b><span>{grocery.month_list(i['cheapest_months'])}</span></li>")
    if i["peak_months"]:
        when_bits.append(f"<li><b>Most stores feature it</b><span>{grocery.month_list(i['peak_months'])}</span></li>")
    if when_bits:
        parts.append(f'<section><h2>When to buy</h2><ul class="facts">{"".join(when_bits)}</ul></section>')
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
    others = "".join(f'<a href="@/grocery/{o["slug"]}/">{esc(o["short"])}</a>'
                     for o in sorted(all_items, key=lambda o: o["short"]) if o["slug"] != i["slug"])
    parts.append(f'<section><h2>Other produce</h2><nav class="others">{others}</nav></section>')
    return "\n".join(parts) + "\n"
