"""Weekly buyer's brief, written every Saturday after the nightly run.

    python -m pipeline.brief

Turns the export files (latest prices vs. usual, forecasts, alerts, shipments, track record)
into one short article for wholesale buyers: what's cheap or expensive, where prices are
likely heading over the next two weeks, and a plain buy-ahead / hold-off call per item.

Writes data/briefs/<monday>.html, an HTML fragment dated by the Monday of the week it is
for. scripts/build_site.py wraps each one into a page under /brief/ and an RSS feed (which
an email newsletter service can send automatically). Re-running the same week overwrites it.

Rules for the calls: docs/brief.md
"""

import csv
import datetime as dt
import html
import json
import math

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


def call(status, change, stable):
    """Plain-language buying call from where the price is vs. usual and where it's heading."""
    if stable or change is None or abs(change) < MOVE:
        return {"cheap": "Good value, holding steady", "expensive": "High, no relief expected yet"}.get(status, "Steady")
    if change > 0:
        return "Buy ahead: cheap now, expected to rise" if status == "cheap" else "Book ahead if you can: expected to rise"
    return "Buy as needed: high now, expected to ease" if status == "expensive" else "Hold off where you can: expected to ease"


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
            "commodity": commodity, "name": PRODUCE_NAMES[commodity], "market": market, "pack": pack(s),
            "price": price, "vs_norm": _num(r["pct_vs_norm"]), "status": r["status"],
            "vs_4w": _num(r["pct_vs_4_weeks_ago"]), "range": (point["lo"], point["hi"]) if point else None,
            "change": 0.0 if stable and point else change, "stable": stable,
            "call": call(r["status"], change, stable) if point else "",
        })
    return items


def vs_usual(v):
    if v is None:
        return "—"
    if abs(v) < 5:
        return "about usual"
    return f"{abs(round(v))}% {'above' if v > 0 else 'below'}"


def table(rows):
    body = "".join(
        f"<tr><td><strong>{esc(i['name'])}</strong><br><small>{esc(i['pack'])}</small></td>"
        f"<td data-label=\"Last week\">{money(i['price'])}</td><td data-label=\"vs. usual\">{vs_usual(i['vs_norm'])}</td>"
        f"<td data-label=\"In 2 weeks\">{(whole(i['range'][0]) + '–' + whole(i['range'][1])) if i['range'] else '—'}</td>"
        f"<td class=\"call\">{esc(i['call'])}</td></tr>"
        for i in rows)
    return ("<table class=\"brief-table\"><thead><tr><th>Item</th><th>Last week, per case</th><th>vs. usual</th>"
            f"<th>Likely in 2 weeks</th><th>Call</th></tr></thead><tbody>{body}</tbody></table>")


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
    data_week = max(dt.date.fromisoformat(r["week_start"]) for r in latest)
    for_week = data_week + dt.timedelta(weeks=1)
    ny = sorted((i for i in items if i["market"] == "New York"), key=lambda i: i["name"])

    # Top lines: biggest expected moves, then most unusual prices (New York first, the deepest market)
    moves = sorted((i for i in ny if i["change"] is not None and not i["stable"] and abs(i["change"]) >= MOVE),
                   key=lambda i: -abs(i["change"]))[:2]
    unusual = sorted((i for i in ny if i["vs_norm"] is not None and abs(i["vs_norm"]) >= 15 and i not in moves),
                     key=lambda i: -abs(i["vs_norm"]))[:3 - len(moves)]
    tops = [f"<li><strong>{esc(i['name'])}</strong> ({money(i['price'])} last week) is expected to "
            f"{'rise' if i['change'] > 0 else 'ease'} to about {whole(i['range'][0])}–{whole(i['range'][1])} a case "
            f"within two weeks. {esc(i['call'].split(':')[0])}.</li>" for i in moves]
    tops += [f"<li><strong>{esc(i['name'])}</strong>: {money(i['price'])} a case, {abs(round(i['vs_norm']))}% "
             f"{'above' if i['vs_norm'] > 0 else 'below'} the usual price for this time of year.</li>" for i in unusual]

    parts = [
        f"<h1>Produce Buyer's Brief: week of {day(for_week)}, {for_week.year}</h1>",
        f"<p class=\"lede\">Wholesale case prices at the New York (Hunts Point), Los Angeles and Chicago terminal "
        f"markets, compared with the same weeks of the last 10 years, and where they are likely heading. "
        f"USDA Market News data through {day(data_week + dt.timedelta(days=6))}.</p>",
    ]
    if tops:
        parts += ["<h2>What matters this week</h2>", f"<ul>{''.join(tops)}</ul>"]
    if alerts:
        al = "".join(f"<li>{esc(a['headline'])} {esc(a['expect'])} <small>{esc(a['record'])}</small></li>"
                     for a in alerts[:6])
        parts += ["<h2>Early warnings</h2>",
                  "<p>Signals that have called the next move correctly at least 65% of the time over 10 years.</p>",
                  f"<ul>{al}</ul>"]
    parts += ["<h2>New York</h2>", table(ny)]
    for market in MARKETS[1:]:
        rows = sorted((i for i in items if i["market"] == market and i["call"] not in ("Steady", "")),
                      key=lambda i: i["name"])
        if rows:
            parts += [f"<h2>{market}: items to watch</h2>", table(rows)]
    notes = [r for r in supply if (_num(r["vs_last_year_pct"]) is not None and abs(_num(r["vs_last_year_pct"])) >= SUPPLY_NOTE)]
    if notes:
        notes.sort(key=lambda r: _num(r["vs_last_year_pct"]))
        line = "; ".join(f"{esc(PRODUCE_NAMES.get(r['commodity'], r['commodity']))} "
                         f"{abs(round(_num(r['vs_last_year_pct'])))}% {'below' if _num(r['vs_last_year_pct']) < 0 else 'above'}"
                         for r in notes)
        parts += ["<h2>Supply</h2>", f"<p>USDA-reported shipments for the week of {day(dt.date.fromisoformat(notes[0]['week']))} vs. the same "
                  f"week last year: {line}.</p>"]
    live, al_rec = record.get("forecasts_live", {}), record.get("alerts", {})
    rec = []
    if live.get("scored"):
        rec.append(f"{live['in_range_pct']:.0f}% of {live['scored']} forecasts scored since "
                   f"{live['since']} landed inside their stated range (the range is built to hold 80%).")
    if al_rec.get("decided"):
        rec.append(f"Early warnings: {al_rec['came_true']} of {al_rec['decided']} decided so far came true.")
    if rec:
        parts += ["<h2>Our track record</h2>", f"<p>{' '.join(rec)}</p>"]
    parts.append(
        "<p class=\"fine\">How to read this: “per case” is the USDA-reported mostly price for the pack shown, "
        "for the most consistently reported pack per market. “Usual” is the median for the same weeks of the "
        "year over past years, inflation-adjusted. “Likely in 2 weeks” is an 80% range from a model tested on "
        "2021–2026 data; items marked “Steady” have historically been forecast best by assuming no change. "
        "Market prices, not your supplier's quote; a guide, not a guarantee.</p>")
    return for_week, "\n".join(parts) + "\n"


def main():
    for_week, body = build()
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"{for_week.isoformat()}.html"
    path.write_text(body, encoding="utf-8")
    print(f"brief: {path.relative_to(store.DATA.parent)}")


if __name__ == "__main__":
    main()
