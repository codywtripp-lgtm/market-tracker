"""Wholesale meat pages, from data/export/meat.json (pipeline/meat.py). Same board parts as the produce pages."""

import datetime as dt
import json

from . import board, brief
from .brief import esc

PAGE = "wholesale-meat-prices"
UNIT = {"Beef": "per cwt", "Chicken": "per lb"}
BASIS = {
    "Beef": "USDA's national boxed beef report: negotiated sales, FOB plant, for delivery within 21 days. Packers' formula "
            "and forward sales aren't in these prices. USDA reports no city prices for boxed beef.",
    "Chicken": "USDA's weekly national chicken report, fresh domestic. Whole birds are priced delivered and parts FOB. "
               "USDA publishes it at the end of each week.",
}
GROUPS = (("Boxed beef, Choice cuts and cutout", lambda i: i["kind"] == "Beef" and not i["slug"].startswith("ground")),
          ("Ground beef", lambda i: i["slug"].startswith("ground")),
          ("Chicken", lambda i: i["kind"] == "Chicken"))
ACTIONS = (
    ("firming", "Firming", "Likely higher in two weeks. Cover your needs and update customer quotes.", "up"),
    ("softening", "Softening", "Likely lower in two weeks. Buy to need; don't lock price at today's level.", "down"),
    ("high", "High for the season, no relief yet", "Look at other cuts or grades, and price quotes to cover it.", "up"),
    ("value", "Good value for the season", "Worth featuring on specials and promotions.", "down"),
)


def load():
    return brief._json("meat.json", {})


def money(v):
    return "—" if v is None else f"${v:,.2f}"


def short(v):
    """Board rows: cents would push a four-figure price off a phone screen."""
    return f"${v:,.0f}" if v >= 1000 else money(v)


def link(i):
    return f"@/{PAGE}/{i['slug']}/"


def shown_date(i):
    d = dt.date.fromisoformat(i["date"])
    return f"week of {d:%B} {d.day}" if i["kind"] == "Chicken" else f"{d:%B} {d.day}"


def change(i):
    if i["prev"] is None or not i["prev"]:
        return ""
    return board.change(i["price"] / i["prev"] - 1)


def since(i):
    return "From last week" if i["kind"] == "Chicken" else "Latest day"


def season(i):
    word, tone = board.SEASON.get(i["status"], ("Not enough history", "flat"))
    if i["status"] == "normal" and i["usual_low"] is not None:
        sub = f"usually {money(i['usual_low'])} to {money(i['usual_high'])}"
    else:
        sub = "" if i["vs_norm"] is None else brief.vs_usual(i["vs_norm"]) + " usual"
    return f'<span class="season {tone}"><b>{word}</b>{f"<small>{esc(sub)}</small>" if sub else ""}</span>'


def expected(i):
    return i["points"][1]["mid"]


def about(i):
    """A forecast isn't good to the cent on a $1,400 price."""
    v = expected(i)
    return f"${v:,.0f}" if v >= 100 else money(v)


def outlook(i):
    arrow, word, tone = board.DIR[i["dir"]]
    return f'<span class="out {tone}"><b>{arrow + " " if arrow else ""}{word}</b><small>about {about(i)}</small></span>'


def history(i):
    return [(dt.date.fromisoformat(d), p, lo, hi) for d, p, lo, hi in i["hist"]]


def row(i):
    return (f'<a class="brow" href="{link(i)}"><span class="b-item"><b>{esc(i["name"])}</b><small>{UNIT[i["kind"]]}</small></span>'
            f'<span class="b-season">{season(i)}</span><span class="b-spark">{board.spark(history(i), i)}</span>'
            f'<span class="b-price"><b>{short(i["price"])}</b>{change(i)}</span><span class="b-out">{outlook(i)}</span></a>')


def rows(items):
    head = ('<div class="bhead" aria-hidden="true"><span>Item</span><span>For the season</span><span>12 weeks</span>'
            '<span class="r">Price</span><span>Next 2 weeks</span></div>')
    return f'<div class="board">{head}{"".join(row(i) for i in items)}</div>'


def actions(items):
    groups = {
        "firming": sorted((i for i in items if i["dir"] in ("firming", "bottoming")), key=lambda i: -i["change"]),
        "softening": sorted((i for i in items if i["dir"] in ("softening", "topping")), key=lambda i: i["change"]),
        "high": [i for i in items if i["status"] == "expensive" and i["dir"] == "steady"],
        "value": [i for i in items if i["status"] == "cheap" and i["dir"] == "steady"],
    }
    cards = []
    for key, title, todo, tone in ACTIONS:
        lis = "".join(f'<li><a href="{link(i)}"><span>{esc(i["name"])}</span><span class="num">{money(i["price"])}'
                      + (f' <span class="to">to about {about(i)}</span>' if key in ("firming", "softening") else "")
                      + "</span></a></li>" for i in groups[key]) or '<li class="none">Nothing today</li>'
        cards.append(f'<section class="act {tone}"><h3>{title}</h3><p>{todo}</p><ul>{lis}</ul></section>')
    return '<div class="acts">' + "".join(cards) + "</div>"


def page(items):
    beef = max(i["date"] for i in items if i["kind"] == "Beef")
    chicken = max(i["date"] for i in items if i["kind"] == "Chicken")
    b, c = dt.date.fromisoformat(beef), dt.date.fromisoformat(chicken)
    cutout = next(i for i in items if i["slug"] == "choice-cutout")
    word = board.SEASON.get(cutout["status"], ("", ""))[0].lower()
    parts = ['<div class="pagehead"><h1>Wholesale meat prices today</h1>'
             f'<p class="date">Boxed beef as of {b:%B} {b.day}, {b.year}. Chicken for the week of {c:%B} {c.day}. USDA national prices.</p>'
             f'<p class="lede">The Choice beef cutout is {money(cutout["price"])} per hundredweight, {esc(word)}.</p></div>',
             '<section class="panel"><h2>What to do today</h2>', actions(items)]
    for title, keep in GROUPS:
        group = [i for i in items if keep(i)]
        parts.append(f'<h2>{esc(title)}</h2>{rows(group)}')
    parts.append("</section>")
    for kind, text in BASIS.items():
        parts.append(f'<p class="fine"><b>{kind}:</b> {esc(text)}</p>')
    return "\n".join(parts) + "\n"


def faq(i):
    unit = UNIT[i["kind"]]
    arrow, word, _ = board.DIR[i["dir"]]
    season_word = board.SEASON.get(i["status"], ("Not enough history", ""))[0]
    way = (f"Steady: about {about(i)} {unit} in two weeks." if i["dir"] == "steady" else
           f"{word}: about {about(i)} {unit} in two weeks, from {money(i['price'])} now.")
    pound = f" ({money(i['per_lb'])} a pound)" if i["kind"] == "Beef" else ""
    item = i["name"][0].lower() + i["name"][1:]
    usual = (f" Usually {money(i['usual_low'])} to {money(i['usual_high'])} at this time of year, in today's dollars."
             if i["usual_low"] is not None else "")
    return [(f"What is the wholesale price of {item} today?",
             f"{money(i['price'])} {unit}{pound} on USDA's latest report, {shown_date(i)}."),
            ("Is that high for the time of year?", f"{season_word}.{usual}"),
            ("Will the price go up or down?", way),
            ("Where does this price come from?", BASIS[i["kind"]])]


def item_page(i, items):
    unit = UNIT[i["kind"]]
    arrow, word, tone = board.DIR[i["dir"]]
    rng = f"USDA range {money(i['low'])} to {money(i['high'])}" if i["low"] and i["high"] else ""
    extra = f"{money(i['per_lb'])} a pound" if i["kind"] == "Beef" else ""
    qa = faq(i)
    chart = board.chart(history(i), {**i, "commodity": i["name"], "market": "the U.S.", "range": True},
                        noun="price", money_fn=money, label=f"{i['name']}, U.S. wholesale, weekly price {unit} over the last year")
    others = "".join(f'<a href="{link(o)}">{esc(o["name"])}</a>' for o in items if o["slug"] != i["slug"])
    return "\n".join([
        f'<nav class="crumbs" aria-label="Breadcrumb"><a href="@/wholesale/">Wholesale prices</a><span>/</span>'
        f'<a href="@/{PAGE}/">Meat</a><span>/</span>{esc(i["name"])}</nav>',
        f'<div class="pagehead"><h1>{esc(i["name"])} wholesale price today</h1>'
        f'<p class="date">U.S. wholesale price {unit}, USDA report for {shown_date(i)}</p>'
        f'<p class="answer">{esc(qa[0][1])} {esc(qa[2][1])}</p></div>',
        '<section class="panel"><div class="quote"><div class="q-main">'
        f'<span class="q-price">{money(i["price"])}</span><span class="q-unit">{unit}</span>'
        f'<span class="q-pack">{esc(extra)}</span>' + (f'<span class="q-range">{esc(rng)}</span>' if rng else "") + "</div>"
        f'<dl class="q-facts"><div><dt>{since(i)}</dt><dd>{change(i)}</dd></div>'
        f'<div><dt>For the season</dt><dd>{season(i)}</dd></div>'
        f'<div><dt>Next 2 weeks</dt><dd><span class="out {tone}"><b>{arrow + " " if arrow else ""}{word}</b>'
        f'<small>about {about(i)}</small></span></dd></div></dl></div>'
        + (f'<div class="todo {tone}"><h2>What to do</h2><p>{esc(i["action"])}</p></div>' if i["action"] else "")
        + chart + "</section>",
        '<h2>Questions buyers ask</h2><div class="faq">' + "".join(f"<h3>{esc(q)}</h3><p>{esc(a)}</p>" for q, a in qa) + "</div>",
        '<script type="application/ld+json">' + json.dumps({"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [
            {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in qa]}) + "</script>",
        f'<h2>Other items</h2><nav class="others">{others}</nav>']) + "\n"
