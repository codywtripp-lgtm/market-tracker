"""Assemble the static website into _site/ (deployed to GitHub Pages).

    python scripts/build_site.py

Copies site/ and writes the JSON the page loads:
  data/latest.json          every headline series: this week's price, status, blurb inputs
  data/s/<series_id>.json   weekly history for one series, loaded when it's shown in the chart:
                            [week_start, price, real_price, pct_vs_usual, usual_lo, usual_hi]
"""

import csv
import datetime as dt
import html
import json
import shutil
import statistics
from collections import defaultdict
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parent.parent
EXPORT = ROOT / "data" / "export"
OUT = ROOT / "_site"

# Same rule as pipeline/export.py: same ISO week +/-2, prior years only, at least 3 years.
WEEK_WINDOW = 2
MIN_YEARS = 3


def read(name):
    path = EXPORT / name
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def num(s):
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def quantile(sorted_vals, q):
    pos = (len(sorted_vals) - 1) * q
    lo, hi = int(pos), min(int(pos) + 1, len(sorted_vals) - 1)
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (pos - lo)


def with_usual(weeks):
    """weeks: sorted [(date, price, real)] -> rows with % vs usual and the usual (25th-75th pct) range."""
    by_isoweek = defaultdict(list)  # iso week -> [(iso year, real)]
    for d, _, real in weeks:
        y, w = d.isocalendar()[:2]
        if real is not None:
            by_isoweek[w].append((y, real))
    out = []
    for d, price, real in weeks:
        y, w = d.isocalendar()[:2]
        pool, years = [], set()
        for o in range(-WEEK_WINDOW, WEEK_WINDOW + 1):
            for yy, v in by_isoweek.get((w - 1 + o) % 53 + 1, ()):
                if yy < y:
                    pool.append(v)
                    years.add(yy)
        if len(years) >= MIN_YEARS and real is not None:
            pool.sort()
            usual = statistics.median(pool)
            pct = round((real / usual - 1) * 100, 1) if usual else None
            lo, hi = round(quantile(pool, 0.25), 3), round(quantile(pool, 0.75), 3)
        else:
            pct = lo = hi = None
        out.append([d.isoformat(), price, real, pct, lo, hi])
    return out


def main():
    if OUT.exists():
        shutil.rmtree(OUT)
    shutil.copytree(ROOT / "site", OUT)
    (OUT / "data" / "s").mkdir(parents=True)

    series = {r["series_id"]: r for r in read("series.csv")}
    forecasts = EXPORT / "forecasts.json"
    fc = json.loads(forecasts.read_text())["series"] if forecasts.exists() else {}
    # typical 2-week forecast miss per commodity x market (walk-forward), shown next to forecasts
    card = {(r["commodity"], r["market"]): r for r in read("forecast_report_card.csv")}
    # last complete week's shipments vs. the same weeks last year, per commodity (all origins)
    supply = {r["commodity"]: num(r.get("vs_last_year_pct")) for r in read("supply.csv")}
    # Chicken is quoted in cents/lb; show it in dollars like everything else.
    scale = {sid: 0.01 if s["compare_unit"] == "cents/lb" else 1 for sid, s in series.items()}

    def price(sid, v):
        v = num(v)
        return None if v is None else round(v * scale.get(sid, 1), 4)

    # Latest day's USDA tone and origins per series (for the "what's going on" lines)
    last_day = {}
    for r in read("prices_daily_365.csv"):
        if r["date"] >= last_day.get(r["series_id"], {}).get("date", ""):
            last_day[r["series_id"]] = r

    latest = []
    for r in read("latest.csv"):
        sid = r["series_id"]
        s, day = series.get(sid, {}), last_day.get(sid, {})
        latest.append({
            "id": sid, "commodity": r["commodity"], "market": r["market"], "type": r["market_type"],
            "week": r["week_start"], "price": price(sid, r["compare_price"]),
            "unit": "per lb" if scale.get(sid) == 0.01 else r["compare_unit"],
            "norm": price(sid, r["seasonal_norm"]), "vsNorm": num(r["pct_vs_norm"]),
            "pctile": num(r["percentile"]), "status": r["status"], "years": num(r["years_of_history"]),
            "vs4w": num(r["pct_vs_4_weeks_ago"]), "vsYear": num(r["pct_vs_last_year"]),
            "variety": s.get("variety", ""), "pack": s.get("pack_size", ""), "size": s.get("item_size", ""),
            "props": s.get("properties", ""), "organic": s.get("organic", ""),
            "coverage": num(s.get("coverage_last_year")),
            "tone": day.get("market_tone", ""), "origins": day.get("origins", ""),
            "forecast": {p["h"]: [p["lo"], p["mid"], p["hi"]] for p in fc.get(sid, {}).get("points", [])},
            "fcMiss": num(card.get((r["commodity"], r["market"]), {}).get("forecast_miss_pct")),
            "fcStable": card.get((r["commodity"], r["market"]), {}).get("uses") == "no change",
            "supplyVsLastYear": supply.get(r["commodity"]) if r["market_type"] in ("terminal", "shipping point") else None,
        })
    record = EXPORT / "track_record.json"
    (OUT / "data" / "track_record.json").write_text(record.read_text() if record.exists() else "{}")
    alerts = EXPORT / "alerts.json"
    if alerts.exists():
        shutil.copy(alerts, OUT / "data" / "alerts.json")
    else:
        (OUT / "data" / "alerts.json").write_text('{"alerts":[]}')
    as_of = max((x["week"] for x in latest), default="")
    (OUT / "data" / "latest.json").write_text(json.dumps({"asOf": as_of, "items": latest}, separators=(",", ":")))

    weekly = defaultdict(list)
    for r in read("prices_weekly.csv"):
        sid = r["series_id"]
        weekly[sid].append((dt.date.fromisoformat(r["week_start"]), price(sid, r["compare_price"]),
                            price(sid, r["real_compare_price"])))
    for sid, rows in weekly.items():
        rows.sort()
        (OUT / "data" / "s" / f"{sid}.json").write_text(json.dumps(with_usual(rows), separators=(",", ":")))
    pages = landing_pages(latest, as_of)
    print(f"site: {len(latest)} items, {len(weekly)} series histories, {pages} landing pages")


# ---------- search landing pages ----------
# Owner's rule: the one-page dashboard is the product; there is no per-commodity navigation.
# These pages exist only so search engines can find "romaine prices" etc. They summarise this
# week and send people into the dashboard with that commodity selected.
SITE_URL = "https://codywtripp-lgtm.github.io/market-tracker/"
PAGE_NAMES = {  # commodity -> (url slug, plain name used in titles)
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
MARKET_KEYS = {"New York": "ny", "Los Angeles": "la", "Chicago": "chi"}


def _esc(s):
    return html.escape(str(s or ""), quote=True)


def _money(v):
    return "—" if v is None else (f"${v:,.0f}" if v >= 100 else f"${v:,.2f}")


def _status(i):
    return {"cheap": "cheap", "expensive": "expensive", "normal": "about normal"}.get(i["status"], "")


def _line(i):
    bits = [f"<strong>{_esc(i['market'])}</strong>: {_money(i['price'])} per case",
            _esc(" · ".join(x for x in (i["variety"] if i["variety"] not in ("", "N/A") else "", i["pack"],
                                           i["size"] if i["size"] not in ("", "N/A") else "") if x))]
    if i["vsNorm"] is not None:
        bits.append(f"{abs(round(i['vsNorm']))}% {'above' if i['vsNorm'] > 0 else 'below'} usual for this time of year"
                    + (f" ({_status(i)})" if _status(i) else ""))
    f2 = (i.get("forecast") or {}).get(2)
    if f2 and not i.get("fcStable"):
        whole = lambda v: f"${v:,.0f}" if v >= 10 else f"${v:,.2f}"  # ranges: no false precision  # noqa: E731
        bits.append(f"next 2 weeks likely {whole(f2[0])}–{whole(f2[2])}")
    return " — ".join(b for b in bits if b)


def landing_pages(latest, as_of):
    by_c = defaultdict(list)
    for i in latest:
        if i["type"] == "terminal" and i["commodity"] in PAGE_NAMES:
            by_c[i["commodity"]].append(i)
    week = dt.date.fromisoformat(as_of).strftime("%B %-d, %Y") if as_of else ""
    urls, links = [SITE_URL], []
    for commodity, (slug, name) in PAGE_NAMES.items():
        items = sorted(by_c.get(commodity, []), key=lambda i: ({"New York": 0, "Los Angeles": 1, "Chicago": 2}.get(i["market"], 9),
                                                               -(i.get("coverage") or 0)))
        # one line per market: its best-covered series
        seen, lines = set(), []
        for i in items:
            if i["market"] not in seen:
                seen.add(i["market"])
                lines.append(f"<li>{_line(i)}</li>")
        dash = f"../?m=ny&c={quote(commodity)}"
        title = f"{name} wholesale prices this week — New York, Los Angeles, Chicago"
        desc = (f"{name} wholesale case prices from USDA terminal markets (Hunts Point NY, LA, Chicago), updated every "
                f"evening: this week vs. usual for the season, 1–4 week forecast and early-warning alerts.")
        page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_esc(title)} | Produce Price Check</title>
<meta name="description" content="{_esc(desc)}">
<link rel="canonical" href="{SITE_URL}{slug}/">
<link rel="stylesheet" href="../style.css"></head>
<body><main class="landing">
<p class="sub"><a href="../">Produce Price Check</a></p>
<h1>{_esc(name)} wholesale prices{(' — week of ' + week) if week else ''}</h1>
<p>USDA terminal-market case prices, compared with what's usual for this time of year.</p>
<ul class="landing-list">{''.join(lines) or '<li>No current quotes.</li>'}</ul>
<p><a class="btn cta" href="{_esc(dash)}">Open {_esc(name.lower())} in the live dashboard →</a></p>
<p class="hint">Charts, forecasts with ranges, shipping-point prices and alerts are in the dashboard.
Data: USDA AMS Market News, updated every evening.</p>
</main></body></html>
"""
        (OUT / slug).mkdir(parents=True, exist_ok=True)
        (OUT / slug / "index.html").write_text(page, encoding="utf-8")
        urls.append(f"{SITE_URL}{slug}/")
        links.append(f'<a href="{slug}/">{_esc(name)} prices</a>')
    today = dt.date.today().isoformat()
    (OUT / "sitemap.xml").write_text('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
                                     + "".join(f"  <url><loc>{u}</loc><lastmod>{today}</lastmod><changefreq>daily</changefreq></url>\n" for u in urls)
                                     + "</urlset>\n")
    (OUT / "robots.txt").write_text(f"User-agent: *\nAllow: /\nSitemap: {SITE_URL}sitemap.xml\n")
    # crawlable links from the dashboard footer
    index = OUT / "index.html"
    index.write_text(index.read_text(encoding="utf-8").replace("<!--COMMODITY_LINKS-->", " · ".join(links)), encoding="utf-8")
    return len(PAGE_NAMES)


if __name__ == "__main__":
    main()
