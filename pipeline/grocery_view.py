"""HTML for the grocery view (the home page): this week's best buys at the supermarket.

Laid out per docs/design.md: the answer first (best buys with shelf tags), then what's in season, what's
pricey and what to buy instead, then every item. Data from pipeline/grocery.py.
"""

import html
import json

from . import grocery


def esc(s):
    return html.escape(str(s or ""), quote=True)


def money(v):
    return f"${v:,.2f}"


STATUS = {"low": ("Great price", "good"), "typical": ("Typical price", "flat"), "high": ("Pricey", "bad"),
          "new": ("New to the ads", "flat")}


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
    buys = grocery.best_buys(items)
    pricey = sorted((i for i in items if i["status"] == "high"), key=lambda i: -(i["vs_usual"] or 0))
    order = {"low": 0, "typical": 1, "new": 2, "high": 3}
    season = sorted((i for i in items if i["in_season"]), key=lambda i: (order[i["status"]], i["short"]))
    stores = max(i["stores"] for i in items) if items else 0
    parts = [f'<section class="intro"><h1>This week’s best buys in the produce aisle</h1>'
             f'<p class="date">Week of {today:%B} {today.day}, {today.year} · from supermarket ads across the U.S., '
             f'reported by USDA</p><p class="lede">{esc(lede(items, buys, pricey))}</p></section>']
    if buys:
        tiles = "".join(
            f'<li class="buy">{tag(i)}<div class="buy-body"><h3>{esc(i["name"])}</h3>'
            f'<p class="buy-why">{why_line(i, today)}</p>{price_bar(i, today)}</div></li>' for i in buys)
        parts.append(f'<section><h2>Best buys</h2><ul class="buys">{tiles}</ul></section>')
    if season:
        chips = "".join(f'<li><span class="sname">{esc(i["short"])}</span>'
                        f'<span class="sword {STATUS[i["status"]][1]}">{esc(STATUS[i["status"]][0])}</span></li>'
                        for i in season)
        parts.append(f'<section class="band"><h2>In season now</h2><p class="sub">Peak flavor and supply this '
                     f'{grocery.season_of(today)}, per USDA’s seasonal produce guide, and how each is priced this week.</p>'
                     f'<ul class="season-list">{chips}</ul></section>')
    if pricey:
        rows = "".join(
            f'<li><div><b>{esc(i["name"])}</b><span>{money(i["price"])}{esc(i["unit"])}, '
            f'<b class="bad">{i["vs_usual"]}% above usual</b></span></div>'
            + (f'<p class="swap">Try {esc(i["swap"].lower())} instead</p>' if i.get("swap") else "") + "</li>"
            for i in pricey[:8])
        parts.append(f'<section><h2>Pricey right now</h2><ul class="pricey">{rows}</ul></section>')
    rows = "".join(
        f'<tr data-name="{esc(i["name"].lower())}"><th scope="row">{esc(i["name"])}'
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
