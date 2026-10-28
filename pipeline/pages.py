"""Commodity pages for search ("romaine lettuce prices today"), rebuilt after every nightly run.

    python -m pipeline.pages

One page per commodity: a plain-sentence answer up top (what it costs today, high or low for the
season, firming or softening), then a card per terminal market with the same visuals as the daily
brief, today's moves, early warnings, shipments, and short questions-and-answers in the words
people search with. Every number comes from the export files, so the page changes every evening.

Writes data/pages/<slug>.html fragments; scripts/build_site.py wraps them at /<slug>/.
"""

import datetime as dt

from . import brief, store

OUT = store.DATA / "pages"

# commodity -> (url slug, name used in titles); same slugs as scripts/build_site.py (tested)
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
}
MARKET_LONG = {"New York": "New York (Hunts Point)", "Los Angeles": "Los Angeles", "Chicago": "Chicago"}


def plural(name):
    """Name as used in a sentence: 'tomatoes', 'iceberg lettuce'."""
    n = name.lower()
    n = "Roma" + n[4:] if n.startswith("roma ") else n
    if n.endswith(("lettuce", "broccoli", "celery")):
        return n
    if n.endswith("y"):
        return n[:-1] + "ies"
    return n + ("es" if n.endswith("o") else "s")


def season_phrase(i):
    """'19% below the usual price for this time of year, still within its normal range' etc."""
    if i["vs_norm"] is None:
        return ""
    base = f"{brief.vs_usual(i['vs_norm'])} the usual price for this time of year"
    if base.startswith("about usual"):
        return "about the usual price for this time of year"
    return base + {"cheap": ", low for the season", "expensive": ", high for the season"}.get(
        i["status"], ", still within its normal range")


def answer(name, i, as_of):
    """The one-paragraph answer a searcher wants, from the New York (or first available) card."""
    s = (f"On {as_of:%B} {as_of.day}, {as_of.year}, wholesale {plural(name)} ({i['pack']}) traded at "
         f"<strong>{brief.money(i['price'])} a case</strong> in {MARKET_LONG[i['market']]}")
    if i["vs_norm"] is not None:
        s += f", {season_phrase(i)}"
    s += "."
    if i["range"]:
        lo, hi = brief.whole(i["range"][0]), brief.whole(i["range"][1])
        s += {"firming": f" The market is <strong>firming</strong>: likely {lo} to {hi} a case within two weeks.",
              "softening": f" The market is <strong>softening</strong>: likely {lo} to {hi} a case within two weeks.",
              }.get(i["dir"], f" The market looks <strong>steady</strong>: likely {lo} to {hi} a case over the next two weeks.")
    return s


def faq(name, rows, supply_pct):
    """Short Q&A in search words, answered only with today's numbers."""
    ny = rows[0]
    lower = plural(name)
    single = name.lower().replace("roma ", "Roma ")  # "onion prices", "Roma tomato prices"
    verb = "is" if lower == single else "are"  # "romaine is", "onions are"
    qa = [(f"How much does a case of {lower} cost wholesale right now?",
           " ".join(f"{brief.money(i['price'])} in {i['market']} ({i['pack']})." for i in rows))]
    if ny["vs_norm"] is not None:
        why = (f" USDA-reported shipments are {abs(round(supply_pct))}% {'below' if supply_pct < 0 else 'above'} "
               f"the same week last year." if supply_pct is not None and abs(supply_pct) >= 10 else "")
        qa.append((f"Are {single} prices high right now?",
                   f"In New York, {lower} {verb} {season_phrase(ny)}.{why}"))
    if ny["range"]:
        word = {"firming": "go up", "softening": "come down"}.get(ny["dir"], "stay about the same")
        qa.append((f"Will {single} prices go up or down?",
                   f"The two-week forecast for New York says prices should {word}, likely {brief.whole(ny['range'][0])} to "
                   f"{brief.whole(ny['range'][1])} a case. Forecasts like this landed inside their range about 80% "
                   "of the time in testing (2021–2026)."))
    return ("<h2>Questions buyers ask</h2>" + "".join(f'<h3 class="q">{brief.esc(q)}</h3><p>{brief.esc(a)}</p>' for q, a in qa))


def build_all():
    latest = brief._read("latest.csv")
    if not latest:
        raise SystemExit("no data/export/latest.csv; run pipeline.export first")
    series = {r["series_id"]: r for r in brief._read("series.csv")}
    forecasts = brief._json("forecasts.json", {}).get("series", {})
    card = {(r["commodity"], r["market"]): r for r in brief._read("forecast_report_card.csv")}
    alerts = brief._json("alerts.json", {}).get("alerts", [])
    supply = {r["commodity"]: brief._num(r["vs_last_year_pct"]) for r in brief._read("supply.csv")}

    items = brief.headline_items(latest, series, forecasts, card)
    hist = brief.weekly_history(items)
    sizes = brief.size_options(latest, series)
    as_of, today = brief.daily_moves(items)
    as_of = as_of or max(dt.date.fromisoformat(r["week_start"]) for r in latest) + dt.timedelta(days=6)
    out = {}
    for commodity, (slug, name) in PAGES.items():
        rows = sorted((i for i in items if i["commodity"] == commodity), key=lambda i: brief.MARKETS.index(i["market"]))
        if not rows:
            continue
        parts = [f"<h1>Wholesale {brief.esc(name.lower()).replace('roma ', 'Roma ')} prices today</h1>",
                 f'<p class="dateline">Updated {as_of:%A}, {as_of:%B} {as_of.day}, {as_of.year}, from USDA terminal market reports</p>',
                 f'<p class="answer">{answer(name, rows[0], as_of)}</p>']
        moved = [m for m in today if m["commodity"] == commodity]
        if moved:
            parts += ["<h2>Moved today</h2>", brief.moves_table(moved, with_item=False)]
        warn = [a for a in alerts if a["commodity"] == commodity]
        if warn:
            parts += ["<h2>Early warning</h2>", brief.warnings_list(warn, with_headline=False)]
        parts.append("<h2>By market</h2><div class=\"items\">" + "".join(
            brief.item_card(i, hist.get(i["series_id"], []), sizes.get((i["commodity"], i["market"])),
                            title=MARKET_LONG[i["market"]]) for i in rows) + "</div>")
        parts.append(faq(name, rows, supply.get(commodity)))
        out[slug] = "\n".join(parts) + "\n"
    return as_of, out


def main():
    as_of, pages = build_all()
    OUT.mkdir(parents=True, exist_ok=True)
    for slug, body in pages.items():
        (OUT / f"{slug}.html").write_text(body, encoding="utf-8")
    print(f"pages: {len(pages)} commodity pages for {as_of}")


if __name__ == "__main__":
    main()
