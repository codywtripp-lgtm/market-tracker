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
import re
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
    brief_urls = briefs() + why_page()
    pages = landing_pages(latest, as_of, brief_urls)
    print(f"site: {len(latest)} items, {len(weekly)} series histories, {pages} landing pages, {len(brief_urls)} briefs")


# ---------- page frame shared by every generated page ----------
SITE_NAME = "Produce Price Tracker"
FONTS = ('<link rel="preconnect" href="https://fonts.googleapis.com">'
         '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
         '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Public+Sans:wght@400;600;700'
         '&family=Source+Serif+4:opsz,wght@8..60,400;8..60,700&display=swap">')
ICON = ("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E"
        "%3Crect width='32' height='32' fill='%231c1b19'/%3E"
        "%3Cpath d='M5 23l7-8 5 4 10-11' stroke='%23fbfaf6' stroke-width='3' fill='none'/%3E%3C/svg%3E")
NAV = (("brief/", "Today's report"), ("", "Price charts"), ("why/", "Track record"))


def masthead(up, active=None):
    links = []
    for href, label in NAV:
        cur = ' aria-current="page"' if href == active else ""
        links.append(f'<a href="{up}{href}"{cur}>{label}</a>')
    return (f'<header class="mast"><div class="mast-in"><div class="mast-row">'
            f'<a class="mast-name" href="{up}">{SITE_NAME}</a>'
            f'<nav class="mast-nav" aria-label="Site">{"".join(links)}</nav></div>'
            '<p class="mast-tag">Wholesale produce prices at the New York, Los Angeles and Chicago terminal markets, '
            'from USDA Market News. Updated every market evening.</p></div></header>')


def item_links(up):
    return " · ".join(f'<a href="{up}{slug}/">{_esc(name)} prices</a>' for slug, name in PAGE_NAMES.values())


def footer(up):
    return ('<footer class="foot">Prices are the USDA “mostly” price per case at the terminal markets, from USDA AMS '
            "Market News. “Usual” means the same weeks of the year over the past 10 years, adjusted for food "
            "inflation. These are market prices, not a supplier's quote."
            f'<p class="foot-links">{item_links(up)}</p></footer>')


def page(title, desc, canonical, up, body, active=None, head=""):
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_esc(title)}</title>
<meta name="description" content="{_esc(desc)}">
<link rel="canonical" href="{canonical}">
<meta property="og:title" content="{_esc(title)}">
<meta property="og:description" content="{_esc(desc)}">
<meta property="og:url" content="{canonical}">
<meta property="og:site_name" content="{SITE_NAME}">
<link rel="icon" href="{ICON}">
{FONTS}
<link rel="stylesheet" href="{up}style.css">{head}</head>
<body class="page">
{masthead(up, active)}
<main class="landing">
{body}
</main>
{footer(up)}
</body></html>
"""


# ---------- daily market report ----------
# pipeline/brief.py writes one HTML fragment per market day to data/briefs/; here each becomes a page,
# /brief/ shows the latest, and feed.xml carries full issues.
BRIEFS = ROOT / "data" / "briefs"
BRIEF_TITLE = "Produce market report"


def _brief_page(body, depth, canonical, extra=""):
    up = "../" * depth
    title = re.search(r"<h1>(.*?)</h1>", body)
    title = html.unescape(title.group(1)) if title else BRIEF_TITLE
    desc = re.search(r'<p class="lede">(.*?)</p>', body)
    body = body.replace('href="../why/"', f'href="{up}why/"')
    feed = f'\n<link rel="alternate" type="application/rss+xml" title="{SITE_NAME}" href="{SITE_URL}brief/feed.xml">'
    return page(f"{title} | {SITE_NAME}", html.unescape(desc.group(1)) if desc else "", canonical, up,
                f"<article>\n{body}</article>\n{extra}", active="brief/" if depth == 1 else None, head=feed)


def briefs():
    files = sorted(BRIEFS.glob("*.html"), reverse=True) if BRIEFS.exists() else []
    if not files:
        return []
    urls, items = [], []
    for f in files:
        week, body = f.stem, f.read_text(encoding="utf-8")
        url = f"{SITE_URL}brief/{week}/"
        (OUT / "brief" / week).mkdir(parents=True, exist_ok=True)
        (OUT / "brief" / week / "index.html").write_text(_brief_page(body, 2, url), encoding="utf-8")
        urls.append(url)
        title = re.search(r"<h1>(.*?)</h1>", body)
        title = html.unescape(title.group(1)) if title else f"{BRIEF_TITLE}: {week}"
        pub = dt.datetime.combine(dt.date.fromisoformat(week), dt.time(6), dt.timezone.utc)
        items.append(f"<item><title>{_esc(title)}</title><link>{url}</link><guid>{url}</guid>"
                     f"<pubDate>{pub.strftime('%a, %d %b %Y %H:%M:%S +0000')}</pubDate>"
                     f"<description>{_esc(re.sub(r'<h1>.*?</h1>', '', body))}</description></item>")
    past = "".join(f'<li><a href="{f.stem}/">{dt.date.fromisoformat(f.stem):%A, %B} {dt.date.fromisoformat(f.stem).day}</a></li>'
                   for f in files[1:60])
    latest = files[0].read_text(encoding="utf-8")
    extra = (f'<h2>Earlier reports</h2><ul class="issues">{past}</ul>' if past else "") + (
        f'<p class="fine">Published every market evening, Monday to Saturday. '
        f'Feed readers can follow <a href="{SITE_URL}brief/feed.xml">the RSS feed</a>.</p>')
    (OUT / "brief" / "index.html").write_text(_brief_page(latest, 1, f"{SITE_URL}brief/", extra), encoding="utf-8")
    (OUT / "brief" / "feed.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n<rss version="2.0"><channel>'
        f"<title>{SITE_NAME}</title><link>{SITE_URL}brief/</link>"
        "<description>Daily wholesale produce market report for New York, Los Angeles and Chicago: case prices "
        "against the season and a two-week outlook. From USDA Market News data.</description><language>en-us</language>"
        + "".join(items[:20]) + "</channel></rss>\n", encoding="utf-8")
    return [f"{SITE_URL}brief/"] + urls


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
                 f"<a href=\"../\">price charts</a>, misses included.</p>") if live.get("scored") else ""

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
<p><a class="cta" href="../brief/">Read today's market report</a></p>"""
    desc = ("How often the wholesale produce price forecasts were right: direction calls, big swings flagged two weeks "
            "ahead and early warnings, tested on USDA terminal market data 2021 to 2026, misses included.")
    (OUT / "why").mkdir(parents=True, exist_ok=True)
    (OUT / "why" / "index.html").write_text(
        page(f"How accurate are the forecasts? | {SITE_NAME}", desc, f"{SITE_URL}why/", "../", body, active="why/"),
        encoding="utf-8")
    return [f"{SITE_URL}why/"]


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
    bits = [f"<strong>{_esc(i['market'])}</strong> {_money(i['price'])} a case",
            _esc(" · ".join(x for x in (i["variety"] if i["variety"] not in ("", "N/A") else "", i["pack"],
                                           i["size"] if i["size"] not in ("", "N/A") else "") if x))]
    if i["vsNorm"] is not None:
        bits.append(f"{abs(round(i['vsNorm']))}% {'above' if i['vsNorm'] > 0 else 'below'} usual for this time of year"
                    + (f" ({_status(i)})" if _status(i) else ""))
    f2 = (i.get("forecast") or {}).get(2)
    if f2 and not i.get("fcStable"):
        whole = lambda v: f"${v:,.0f}" if v >= 10 else f"${v:,.2f}"  # ranges: no false precision  # noqa: E731
        bits.append(f"next two weeks likely {whole(f2[0])} to {whole(f2[2])}")
    return ", ".join(b for b in bits if b)


PAGES_DIR = ROOT / "data" / "pages"  # rich fragments from pipeline/pages.py (nightly)


def rich_page(slug, name, body, dash):
    """Wrap a pipeline/pages.py fragment: search title and description from today's numbers, links to every item."""
    answer = re.search(r'<p class="answer">(.*?)</p>', body, re.S)
    desc = html.unescape(re.sub(r"<[^>]+>", "", answer.group(1))) if answer else ""
    title = f"{name.title()} Prices Today, Wholesale per Case | {SITE_NAME}"
    extra = (f'<p><a class="cta" href="{_esc(dash)}">See the 10-year price chart</a></p>'
             '<p class="fine">Prices are the USDA “mostly” price per case for the main pack the trade buys in each '
             "market, updated every market evening. Forecast ranges hold about 80% of the time.</p>")
    return page(title, desc[:300], f"{SITE_URL}{slug}/", "../", body + extra)


def landing_pages(latest, as_of, extra_urls=()):
    by_c = defaultdict(list)
    for i in latest:
        if i["type"] == "terminal" and i["commodity"] in PAGE_NAMES:
            by_c[i["commodity"]].append(i)
    d = dt.date.fromisoformat(as_of) if as_of else None
    week = f"{d:%B} {d.day}, {d.year}" if d else ""
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
        rich = PAGES_DIR / f"{slug}.html"
        if rich.exists():
            (OUT / slug).mkdir(parents=True, exist_ok=True)
            (OUT / slug / "index.html").write_text(rich_page(slug, name, rich.read_text(encoding="utf-8"), dash),
                                                   encoding="utf-8")
            urls.append(f"{SITE_URL}{slug}/")
            links.append(f'<a href="{slug}/">{_esc(name)} prices</a>')
            continue
        title = f"{name} Wholesale Prices This Week | {SITE_NAME}"
        desc = (f"{name} wholesale case prices from USDA terminal markets (Hunts Point NY, LA, Chicago), updated every "
                f"evening: this week against the usual for the season, and a two-week outlook.")
        body = (f"<h1>{_esc(name)} wholesale prices{(', week of ' + week) if week else ''}</h1>"
                "<p>USDA terminal market case prices, compared with what's usual for this time of year.</p>"
                f"<ul>{''.join(lines) or '<li>No current quotes.</li>'}</ul>"
                f'<p><a class="cta" href="{_esc(dash)}">Open {_esc(name.lower())} on the price charts</a></p>')
        page_html = page(title, desc, f"{SITE_URL}{slug}/", "../", body)
        (OUT / slug).mkdir(parents=True, exist_ok=True)
        (OUT / slug / "index.html").write_text(page_html, encoding="utf-8")
        urls.append(f"{SITE_URL}{slug}/")
        links.append(f'<a href="{slug}/">{_esc(name)} prices</a>')
    urls += list(extra_urls)
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
