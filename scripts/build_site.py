"""Assemble the static website into _site/ (deployed to GitHub Pages).

    python scripts/build_site.py

Copies site/, wraps the pages pipeline/board.py writes (home, market pages, item pages) and the
track record page in the shared frame, and writes the JSON the price-history page loads:
  data/latest.json          every headline series: this week's price, status, blurb inputs
  data/s/<series_id>.json   weekly history for one series, loaded when it's shown in the chart:
                            [week_start, price, real_price, pct_vs_usual, usual_lo, usual_hi]
"""

import csv
import datetime as dt
import html
import json
import re
import shutil
from collections import defaultdict
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from pipeline import board  # noqa: E402
from pipeline.usual import with_usual  # noqa: E402
EXPORT = ROOT / "data" / "export"
OUT = ROOT / "_site"

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
            "coverage": num(s.get("coverage_last_year")), "main": s.get("headline") == "Y",
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
    urls = board_pages() + why_page() + charts_page()
    redirect("brief", "../")
    seo_files(urls)
    print(f"site: {len(latest)} items, {len(weekly)} series histories, {len(urls)} pages")


# ---------- page frame shared by every page ----------
SITE_URL = "https://producepricetracker.com/"
SITE_NAME = "Produce Price Tracker"
FONTS = ('<link rel="preconnect" href="https://fonts.googleapis.com">'
         '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
         '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Source+Sans+3:wght@400;600;700&display=swap">')
# the mark: a price line over a crate slat, in the brand green
MARK = ('<svg viewBox="0 0 28 28" aria-hidden="true"><rect width="28" height="28" rx="7" fill="#2f8a57"/>'
        '<path d="M6 18.5l5-5.5 4 3 7-8" stroke="#fff" stroke-width="2.6" fill="none" stroke-linecap="round" '
        'stroke-linejoin="round"/><path d="M6 22h16" stroke="#fff" stroke-opacity=".55" stroke-width="2" stroke-linecap="round"/></svg>')
ICON = ("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 28 28'%3E"
        "%3Crect width='28' height='28' rx='7' fill='%232f8a57'/%3E%3Cpath d='M6 18.5l5-5.5 4 3 7-8' stroke='%23fff' "
        "stroke-width='2.6' fill='none' stroke-linecap='round' stroke-linejoin='round'/%3E%3Cpath d='M6 22h16' "
        "stroke='%23fff' stroke-opacity='.55' stroke-width='2' stroke-linecap='round'/%3E%3C/svg%3E")
NAV = (("", "Today's prices"), ("charts/", "Price history"), ("why/", "Track record"))


def _esc(s):
    return html.escape(str(s or ""), quote=True)


def topbar(up, active=None):
    cur = ' aria-current="page"'
    links = "".join(f'<a href="{up}{href}"{cur if href == active else ""}>{label}</a>' for href, label in NAV)
    return (f'<header class="top"><div class="wrap"><a class="logo" href="{up}">{MARK}{SITE_NAME}</a>'
            f'<nav class="nav" aria-label="Site">{links}</nav></div></header>')


def footer(up):
    items = "".join(f'<a href="{up}{slug}/">{_esc(board.name(c))} prices</a>' for c, (slug, _) in board.PAGES.items())
    markets = "".join(f'<a href="{up}{slug}/">{"Hunts Point" if m == "New York" else m} produce prices</a>'
                      for m, slug in board.MARKET_PAGES.items())
    return ('<footer class="foot"><div class="wrap"><p>Prices are the USDA “mostly” price per case at the terminal '
            "markets, from USDA AMS Market News, for the main pack the trade buys in each market. “Usual” means the "
            "same weeks of the year over the past 10 years, adjusted for food inflation. Forecast ranges hold about "
            "80% of the time. These are market prices, not a supplier's quote.</p>"
            f"<nav>{markets}</nav><nav>{items}</nav></div></footer>")


def page(title, desc, canonical, up, body, active=None, head="", og=None, main_class="wrap"):
    image = (f'<meta property="og:image" content="{SITE_URL}og/{og}.png">'
             '<meta property="og:image:width" content="1200"><meta property="og:image:height" content="630">'
             '<meta name="twitter:card" content="summary_large_image">') if og else ""
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_esc(title)}</title>
<meta name="description" content="{_esc(desc[:300])}">
<link rel="canonical" href="{canonical}">
<meta property="og:type" content="website"><meta property="og:site_name" content="{SITE_NAME}">
<meta property="og:title" content="{_esc(title)}"><meta property="og:description" content="{_esc(desc[:300])}">
<meta property="og:url" content="{canonical}">{image}
<link rel="icon" href="{ICON}">
{FONTS}
<link rel="stylesheet" href="{up}style.css">{head}
<script src="{up}tabs.js" defer></script></head>
<body>
{topbar(up, active)}
<main class="{main_class}">
{body}
</main>
{footer(up)}
</body></html>
"""


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def redirect(path, to):
    write(OUT / path / "index.html", f'<!doctype html><meta charset="utf-8"><meta http-equiv="refresh" content="0; url={to}">'
                                     f'<link rel="canonical" href="{SITE_URL}"><title>{SITE_NAME}</title><a href="{to}">{SITE_NAME}</a>')


# ---------- home, market pages, item pages (fragments from pipeline/board.py) ----------
BOARD = ROOT / "data" / "board"


def _text(fragment, cls):
    m = re.search(rf'<p class="{cls}">(.*?)</p>', fragment, re.S)
    return html.unescape(re.sub(r"<[^>]+>", "", m.group(1))) if m else ""


def board_pages():
    if not (BOARD / "home.html").exists():
        return []
    as_of = dt.date.fromisoformat((BOARD / "as_of.txt").read_text().strip())
    og = json.loads((BOARD / "og.json").read_text(encoding="utf-8")) if (BOARD / "og.json").exists() else {}
    cards = {}
    urls = []

    def emit(rel, frag_name, title, depth, active=None, og_key=None, head=""):
        frag = (BOARD / f"{frag_name}.html").read_text(encoding="utf-8")
        up = "../" * depth
        desc = _text(frag, "answer") or _text(frag, "lede")
        if og_key and og_key in og:
            cards[og_key] = og[og_key]
        write(OUT / rel / "index.html", page(title, desc, SITE_URL + rel, up, frag.replace('href="@/', f'href="{up}'),
                                             active=active, og=og_key if og_key in og else None, head=head))
        urls.append(SITE_URL + rel)

    dataset = json.dumps({
        "@context": "https://schema.org", "@type": "Dataset", "name": "Wholesale produce terminal market prices",
        "description": "Daily wholesale case prices for 18 produce items at the New York (Hunts Point), Los Angeles "
                       "and Chicago terminal markets, compared with the usual price for the time of year, with a "
                       "two-week outlook.",
        "url": SITE_URL, "creator": {"@type": "Organization", "name": SITE_NAME},
        "isBasedOn": "https://www.ams.usda.gov/market-news", "temporalCoverage": f"2016-01-01/{as_of.isoformat()}",
        "spatialCoverage": ["New York, NY", "Los Angeles, CA", "Chicago, IL"]})
    emit("", "home", f"Wholesale Produce Prices Today: Hunts Point, Los Angeles, Chicago | {SITE_NAME}", 0, active="",
         og_key="home", head=f'<script type="application/ld+json">{dataset}</script>')
    for m, slug in board.MARKET_PAGES.items():
        place = "Hunts Point (New York)" if m == "New York" else m
        emit(f"{slug}/", f"market-{board.MKEY[m]}", f"{place} Wholesale Produce Prices Today | {SITE_NAME}", 1,
             og_key=f"market-{board.MKEY[m]}")
    for c, (slug, _) in board.PAGES.items():
        if not (BOARD / "items" / f"{slug}.html").exists():
            continue
        n = board.PAGES[c][1].title()
        emit(f"{slug}/", f"items/{slug}", f"{n} Prices Today, Wholesale per Case | {SITE_NAME}", 1, og_key=slug)
        for m, ms in board.MARKET_SLUG.items():
            if (BOARD / "items" / f"{slug}--{ms}.html").exists():
                place = "Hunts Point" if m == "New York" else m
                emit(f"{slug}/{ms}/", f"items/{slug}--{ms}", f"{n} Prices Today in {place}, Wholesale per Case | {SITE_NAME}",
                     2, og_key=slug)
    # link preview cards, rendered to PNG by scripts/og_images.py
    for key, c in cards.items():
        write(OUT / "og" / f"{key}.html", og_card(c))
    return urls


def og_card(c):
    """A 1200x630 preview card: what a shared link shows in texts, LinkedIn, Slack."""
    rows = "".join(f'<div class="og-row"><span>{_esc(r["name"])}</span><b class="{r["tone"]}">{_esc(r["word"])}</b>'
                   f'<span class="og-n">{_esc(r["price"])}</span></div>' for r in c.get("rows", []))
    main = (f'<div class="og-price">{_esc(c["price"])}<span>a case</span></div>'
            f'<div class="og-out {c["tone"]}">{_esc(c["out"])}</div>{c.get("spark", "")}' if c.get("price") else rows)
    return f"""<!doctype html><html><head><meta charset="utf-8"><meta name="robots" content="noindex">{FONTS}
<style>
html,body{{margin:0;width:1200px;height:630px;overflow:hidden}}
body{{background:#f5f4f0;color:#15171c;font-family:"Source Sans 3",Arial,sans-serif;font-variant-numeric:tabular-nums}}
.og{{box-sizing:border-box;height:630px;padding:56px 72px;display:flex;flex-direction:column}}
.og-top{{display:flex;align-items:center;gap:14px;font-weight:700;font-size:30px}}
.og-top svg{{width:44px;height:44px}}
.og-title{{font-size:72px;font-weight:700;letter-spacing:-0.02em;line-height:1.05;margin-top:44px}}
.og-sub{{font-size:28px;color:#5c626c;margin-top:10px}}
.og-price{{font-size:96px;font-weight:700;letter-spacing:-0.02em;margin-top:22px;line-height:1}}
.og-price span{{font-size:30px;font-weight:600;color:#5c626c;margin-left:14px;letter-spacing:0}}
.og-out{{font-size:34px;font-weight:700;margin-top:18px}}
.up{{color:#c0352b}}.down{{color:#17793c}}.flat{{color:#5c626c}}
.og-row{{display:grid;grid-template-columns:1fr 260px 160px;font-size:32px;padding:12px 0;border-top:2px solid #e4e2db}}
.og-row:first-of-type{{margin-top:30px}}
.og-n{{text-align:right;font-weight:700}}
.og-spark{{position:absolute;right:72px;bottom:72px;width:420px;height:150px}}
.og-spark .ln{{fill:none;stroke:#15171c;stroke-width:3;stroke-linejoin:round;stroke-linecap:round}}
.og-spark .fc{{fill:rgba(21,23,28,.08)}}
.og-spark .fc.up{{fill:#fcefed;stroke:#f1c9c4}}.og-spark .fc.down{{fill:#ecf6ef;stroke:#bfdfca}}
.og-spark .dot{{fill:#15171c}}
</style></head><body><div class="og"><div class="og-top">{MARK}{SITE_NAME}</div>
<div class="og-title">{_esc(c["title"])}</div><div class="og-sub">{_esc(c["sub"])}</div>{main}</div></body></html>"""


def charts_page():
    """The 10-year price history explorer (site/charts/ template + app.js)."""
    tpl = OUT / "charts" / "index.html"
    if not tpl.exists():
        return []
    text = tpl.read_text(encoding="utf-8")
    text = text.replace("<!--TOP-->", topbar("../", "charts/")).replace("<!--FOOT-->", footer("../"))
    text = text.replace("<!--HEAD-->", f'<link rel="icon" href="{ICON}">{FONTS}')
    write(tpl, text)
    return [f"{SITE_URL}charts/"]


def seo_files(urls):
    today = dt.date.today().isoformat()
    write(OUT / "sitemap.xml", '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
          + "".join(f"  <url><loc>{u}</loc><lastmod>{today}</lastmod><changefreq>daily</changefreq></url>\n" for u in urls)
          + "</urlset>\n")
    write(OUT / "robots.txt", f"User-agent: *\nAllow: /\nDisallow: /og/\nSitemap: {SITE_URL}sitemap.xml\n")
    # plain-text guide for AI search tools (llmstxt.org)
    items = "\n".join(f"- [{board.name(c)} prices]({SITE_URL}{slug}/): today's wholesale case price in New York, "
                      "Los Angeles and Chicago, against the usual for the season, with a two-week outlook"
                      for c, (slug, _) in board.PAGES.items())
    write(OUT / "llms.txt", f"""# {SITE_NAME}

> Free daily wholesale produce prices at the New York (Hunts Point), Los Angeles and Chicago terminal markets, from
> USDA AMS Market News. Each item shows today's case price for the main pack the trade buys, how it compares with
> the same weeks in the last 10 years (adjusted for inflation), and a tested two-week forecast range.

Updated every market evening (Monday to Saturday). Prices are USDA "mostly" prices per case, not supplier quotes.

## Pages
- [Today's prices]({SITE_URL}): every item, all three markets, and what's firming or softening
- [Track record]({SITE_URL}why/): how accurate the forecasts have been, 2021 to 2026, misses included
- [Price history]({SITE_URL}charts/): 10 years of weekly prices per item

## Items
{items}
""")


# ---------- "why buyers read it" (the pitch) ----------
# Every number comes from data/export/value.json (scripts/value_stats.py: the brief's calls replayed
# walk-forward on 2021-2026 data, plus the alert rules) and track_record.json (live results).
NICE = {"Lettuce, Romaine": "Romaine", "Lettuce, Iceberg": "Iceberg", "Tomatoes, Plum Type": "Roma tomatoes",
        "Peppers, Bell Type": "Bell peppers", "Onions, Dry": "Onions"}


def why_page():
    path = EXPORT / "value.json"
    if not path.exists():
        return []
    v = json.loads(path.read_text(encoding="utf-8"))
    rec = json.loads((EXPORT / "track_record.json").read_text()) if (EXPORT / "track_record.json").exists() else {}
    live = rec.get("forecasts_live", {})
    best = [c for c in v["by_commodity"] if c["right_pct"] >= 65][:8]
    rows = "".join(f"<tr><td>{_esc(NICE.get(c['commodity'], c['commodity']))}</td><td class=\"num\">{c['right_pct']:.0f}%</td>"
                   f"<td class=\"num\">{c['calls']:,}</td><td class=\"num\">${c['avg_dollars']:.2f}</td></tr>" for c in best)
    live_line = (f"<p>Live since {_esc(live['since'])}: {live['in_range_pct']:.0f}% of {live['scored']:,} scored "
                 f"forecasts have landed inside their range. The running score is on the "
                 f"<a href=\"../charts/\">price history page</a>, misses included.</p>") if live.get("scored") else ""

    def hit(e):
        return e["call"] == ("firming" if e["move_pct"] > 0 else "softening")

    def ex_row(e):
        said = {"firming": "▲ Firming", "softening": "▼ Softening"}.get(e["call"], "Steady")
        verdict = (f'<b class="tag good">Called it</b><small>Said {said.lower()}</small>' if hit(e)
                   else f'<b class="tag bad">Missed</b><small>Said {said.lower()}</small>')
        d = dt.date.fromisoformat(e["week"])
        return (f'<tr><td>{_esc(NICE.get(e["commodity"], e["commodity"]))}<small>Week of {d:%b} {d.day}, {d.year}</small></td>'
                f'<td class="num" data-label="Before">${e["price"]:,.2f}</td>'
                f'<td class="num" data-label="Two weeks later"><b>${e["price_after"]:,.2f}</b>'
                f'<small>{"+" if e["move_pct"] > 0 else ""}{e["move_pct"]:.0f}%</small></td>'
                f'<td data-label="Forecast">{verdict}</td></tr>')
    examples = v.get("examples", [])
    hits = [e for e in examples if hit(e)]
    ex_html = (f"""<h2>The biggest New York moves of the past year</h2>
<p>Each item's largest two-week move at Hunts Point in the last 12 months, and what the forecast said two weeks
before, using only data available at the time. It called {len(hits)} of these {len(examples)}. The miss is listed too.</p>
<table class="data stack"><thead><tr><th>Item</th><th class="num">Before</th><th class="num">Two weeks later</th><th>Forecast</th></tr></thead>
<tbody>{"".join(ex_row(e) for e in examples)}</tbody></table>""" if examples else "")
    if hits:
        top = max(hits, key=lambda e: abs(e["move_pct"]))
        d = dt.date.fromisoformat(top["week"])
        opener = (f"In {d:%B} {d.year}, {NICE.get(top['commodity'], top['commodity']).lower().replace('roma ', 'Roma ')} "
                  f"at Hunts Point went from ${top['price']:,.2f} to ${top['price_after']:,.2f} a case in two weeks. "
                  f"The forecast here had it {'firming' if top['move_pct'] > 0 else 'softening'} before it happened. ")
    else:
        opener = ""
    body = f"""<h1>How accurate are the forecasts?</h1>
<p class="lede">{_esc(opener)}This page is the full record, misses included, from a test that only ever used the
data a buyer would have had at the time.</p>

<h2>The record, 2021 to 2026</h2>
<table class="data"><thead><tr><th>What was measured</th><th class="num">Result</th></tr></thead><tbody>
<tr><td>Firming and softening calls that got the direction right<small>{v['calls']:,} calls, {_esc(v['years'])}</small></td><td class="num"><b>{v['calls_right_pct']:.0f}%</b></td></tr>
<tr><td>Price swings of 10% or more flagged two weeks ahead<small>Called the wrong way {v['big_moves_called_wrong_way_pct']:.0f}% of the time; the rest had no call</small></td><td class="num"><b>{v['big_moves_called_ahead_pct']:.0f}%</b></td></tr>
<tr><td>Average move in the direction called, within two weeks</td><td class="num"><b>${v['avg_dollars_per_case']:.2f}</b><small>a case</small></td></tr>
<tr><td>Early warnings that came true<small>Against {v['alert_base_pct']:.0f}% by chance, over {v['alert_cases']:,} past cases</small></td><td class="num"><b>{v['alert_hit_pct']:.0f}%</b></td></tr>
</tbody></table>

{ex_html}

<h2>What the USDA reports leave out</h2>
<p>Every price here comes from USDA Market News, and those reports are the right place to see what traded today.
What they don't tell you is what it means for your next order.</p>
<table class="data stack"><thead><tr><th></th><th>USDA market reports</th><th>This report</th></tr></thead><tbody>
<tr><td>Coverage</td><td data-label="USDA">One report per market per day, often hundreds of lines</td><td data-label="Here">Three terminals and the shipping points on one page</td></tr>
<tr><td>Is the price high?</td><td data-label="USDA">Today's price only</td><td data-label="Here">Against the same weeks of the last 10 years, adjusted for inflation</td></tr>
<tr><td>Where is it going?</td><td data-label="USDA">Not covered</td><td data-label="Here">A two-week price range for each item, tested on five years of data</td></tr>
<tr><td>Early warning</td><td data-label="USDA">You spot shipping-point moves yourself, if you have time</td><td data-label="Here">Flagged when a signal has called the next move at least 65% of the time</td></tr>
<tr><td>What to do about it</td><td data-label="USDA">Up to you</td><td data-label="Here">Firming, softening or steady for each item, with what it means for pricing, inventory and specs</td></tr>
</tbody></table>

<h2>How buyers use it</h2>
<ul>
<li><b>Lock price or stay open.</b> On a firming market, lock price with your supplier before it moves. On a softening one, stay on the open market.</li>
<li><b>Decide how deep to buy.</b> Items that keep a month or more (onions, potatoes, carrots, celery, lemons, limes) can go a few days deeper ahead of a rise. Perishables stay bought to need.</li>
<li><b>Get quotes out on time.</b> Update customer pricing before the market moves, not after the margin is gone.</li>
<li><b>Check your specs.</b> Compare case prices across counts (48s against 60s, 175s against 200s) and see what's good value to put on special.</li>
<li><b>Check the supplier's story.</b> See whether “the market's up” matches what the terminals and shipping points show.</li>
</ul>

<h2>Where it's strongest</h2>
<table class="data"><caption>Share of two-week calls that got the direction right, 2021 to 2026, and the average move per case in the direction called.</caption>
<thead><tr><th>Item</th><th class="num">Right</th><th class="num">Calls</th><th class="num">Avg move</th></tr></thead>
<tbody>{rows}</tbody></table>
<p class="fine">Items that hold steady, such as onions and potatoes, rarely move enough to call. When there's no signal the report says steady rather than guess.</p>

<h2>The limits</h2>
<p>These are USDA-reported terminal prices, not your supplier's quote. A forecast is a range, not a promise: about
one price in five lands outside it, and about half of big swings come with no call at all. Every number on this
page comes from a walk-forward test. Each year was predicted only with data from before it, the same way it runs live.</p>
{live_line}
<p>Put together by a former New York produce buyer.</p>
<p><a class="cta" href="../">See today's prices</a></p>"""
    desc = ("How often the wholesale produce price forecasts were right: direction calls, big swings flagged two weeks "
            "ahead and early warnings, tested on USDA terminal market data 2021 to 2026, misses included.")
    (OUT / "why").mkdir(parents=True, exist_ok=True)
    (OUT / "why" / "index.html").write_text(
        page(f"How accurate are the forecasts? | {SITE_NAME}", desc, f"{SITE_URL}why/", "../", body, active="why/",
             main_class="wrap landing"),
        encoding="utf-8")
    return [f"{SITE_URL}why/"]


if __name__ == "__main__":
    main()
