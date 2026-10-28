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


# ---------- daily buyer's brief ----------
# pipeline/brief.py writes one HTML fragment per market day to data/briefs/; here each becomes a page,
# /brief/ shows the latest, and feed.xml carries full issues.
BRIEFS = ROOT / "data" / "briefs"
BRIEF_TITLE = "Produce Buyer's Brief"


def _brief_page(body, depth, canonical, extra=""):
    up = "../" * depth
    title = re.search(r"<h1>(.*?)</h1>", body)
    title = html.unescape(title.group(1)) if title else BRIEF_TITLE
    desc = re.search(r'<p class="lede">(.*?)</p>', body)
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_esc(title)} | Produce Price Check</title>
<meta name="description" content="{_esc(html.unescape(desc.group(1)) if desc else '')}">
<link rel="canonical" href="{canonical}">
<link rel="alternate" type="application/rss+xml" title="{BRIEF_TITLE}" href="{SITE_URL}brief/feed.xml">
<link rel="stylesheet" href="{up}style.css"></head>
<body><main class="landing brief">
<p class="sub"><a href="{up}">Produce Price Check</a> · <a href="{up}brief/">Buyer's brief</a> · <a href="{up}why/">Why buyers read it</a></p>
<!--SIGNUP-->
<article>
{body}</article>
<p class="hint">Free, every market evening (Monday–Saturday). Follow by RSS: <a href="{SITE_URL}brief/feed.xml">{SITE_URL}brief/feed.xml</a>.
Charts and daily updates are in the <a href="{up}">live dashboard</a>.</p>
{extra}
</main></body></html>
"""


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
    extra = f"<h2>Past issues</h2><ul>{past}</ul>" if past else ""
    (OUT / "brief" / "index.html").write_text(_brief_page(latest, 1, f"{SITE_URL}brief/", extra), encoding="utf-8")
    (OUT / "brief" / "feed.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n<rss version="2.0"><channel>'
        f"<title>{BRIEF_TITLE}</title><link>{SITE_URL}brief/</link>"
        "<description>Daily wholesale produce prices vs. usual, 2-week outlook and buy-ahead calls for "
        "New York, Los Angeles and Chicago. From USDA Market News data.</description><language>en-us</language>"
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
    rows = "".join(f"<tr><td>{_esc(NICE.get(c['commodity'], c['commodity']))}</td><td>{c['right_pct']:.0f}%</td>"
                   f"<td>{c['calls']:,}</td><td>${c['avg_dollars']:.2f}</td></tr>" for c in best)
    live_line = (f"<p>Since going live on {_esc(live['since'])}, {live['in_range_pct']:.0f}% of {live['scored']:,} scored "
                 f"forecasts landed inside their range. The running score is on the "
                 f"<a href=\"../\">dashboard</a>, misses included.</p>") if live.get("scored") else ""
    def ex_row(e):
        hit = e["call"] == ("firming" if e["move_pct"] > 0 else "softening")
        said = {"firming": "▲ Firming", "softening": "▼ Softening"}.get(e["call"], "Steady (missed it)")
        d = dt.date.fromisoformat(e["week"])
        return (f'<tr><td><strong>{_esc(NICE.get(e["commodity"], e["commodity"]))}</strong><br><small>week of {d:%b} {d.day}, {d.year}</small></td>'
                f'<td>${e["price"]:,.2f} → <strong>${e["price_after"]:,.2f}</strong><br><small>{"+" if e["move_pct"] > 0 else ""}{e["move_pct"]:.0f}% in 2 weeks</small></td>'
                f'<td><span class="pill {"good" if hit else "bad"}">{"✓" if hit else "✕"} {said}</span></td></tr>')
    examples = v.get("examples", [])
    hits = sum(e["call"] == ("firming" if e["move_pct"] > 0 else "softening") for e in examples)
    ex_html = (f"""<h2>The biggest New York spikes of the past year</h2>
<p>Every item's largest 2-week move at Hunts Point in the last 12 months, and what the model said two weeks before,
using only data available at the time. It saw {hits} of these {len(examples)} coming. The miss is shown too.</p>
<table class="brief-table ex"><thead><tr><th>Item</th><th>Case price</th><th>Two weeks before, the model said</th></tr></thead>
<tbody>{"".join(ex_row(e) for e in examples)}</tbody></table>""" if examples else "")
    body = f"""<p class="eyebrow">For wholesale produce buyers</p>
<h1>See produce price moves coming, two weeks out.</h1>
<p class="lede">USDA reports tell you what traded yesterday. This free daily brief tells you which way Hunts Point,
Los Angeles and Chicago prices are likely to go next, item by item, tested on five years of market data. Then
it tells you what that means for your contract pricing, customer quotes, inventory and specs.</p>
<p><a class="btn cta" href="../brief/">Read today's brief →</a></p>

<div class="stats">
  <div><strong>{v['calls_right_pct']:.0f}%</strong><span>of firming / softening calls got the direction right ({v['calls']:,} calls, {_esc(v['years'])})</span></div>
  <div><strong>{v['big_moves_called_ahead_pct']:.0f}%</strong><span>of all 10%+ price swings flagged two weeks ahead; called the wrong way only {v['big_moves_called_wrong_way_pct']:.0f}%</span></div>
  <div><strong>${v['avg_dollars_per_case']:.2f}</strong><span>average move per case, in the direction called, within two weeks</span></div>
  <div><strong>{v['alert_hit_pct']:.0f}%</strong><span>early warnings that came true, vs. {v['alert_base_pct']:.0f}% by chance ({v['alert_cases']:,} past cases)</span></div>
</div>

{ex_html}

<h2>Why not just read the USDA reports?</h2>
<p>The reports are where the numbers come from, and they are good at saying what traded today. They don't tell you
what that means for your next order.</p>
<table class="brief-table vs"><thead><tr><th></th><th>USDA market reports</th><th>The brief</th></tr></thead><tbody>
<tr><td>Coverage</td><td>One report per market, per day, often hundreds of lines</td><td>Three terminals and the shipping points on one page</td></tr>
<tr><td>Is this price high?</td><td>Today's price only</td><td>Compared with the same weeks of the last 10 years, adjusted for inflation</td></tr>
<tr><td>Where is it going?</td><td>Not covered</td><td>A 2-week price range per item, tested on five years of data</td></tr>
<tr><td>Early warning</td><td>You spot shipping-point moves yourself, if you have time</td><td>Flagged when a signal has called the next move at least 65% of the time</td></tr>
<tr><td>What it means for you</td><td>Up to you</td><td>Firming, softening or steady per item, with what to do about pricing, inventory depth and specs</td></tr>
</tbody></table>

<h2>How buyers use it</h2>
<ul>
<li><strong>Lock price or stay open.</strong> On a firming market, lock price with your supplier before it moves; on a softening one, stay on the open market.</li>
<li><strong>Set how deep to buy.</strong> Items that store for a month or more (onions, potatoes, carrots, celery, lemons, limes) can go a few days deeper ahead of a rise; perishables stay bought to need.</li>
<li><strong>Get quotes out right.</strong> Update customer pricing before the market moves, not after your margin is gone.</li>
<li><strong>Check your specs.</strong> See case prices across counts (48s vs. 60s, 175s vs. 200s) and what's good value to feature on specials.</li>
<li><strong>Check the supplier's story.</strong> Know whether "the market's up" matches what the terminals and shipping points show.</li>
</ul>

<h2>Where it's strongest</h2>
<p>Share of 2-week calls that got the direction right, 2021–2026, and the average move per case in the direction called.</p>
<table class="brief-table"><thead><tr><th>Item</th><th>Right</th><th>Calls</th><th>Avg move / case</th></tr></thead>
<tbody>{rows}</tbody></table>
<p class="fine">Steady items such as onions and potatoes rarely move enough to call; the brief says "Steady" rather than guess.</p>

<h2>Honest about the limits</h2>
<p>These are USDA-reported terminal prices, not your supplier's quote, and a forecast is a range, not a promise: about
one in five prices lands outside it. About half of big swings come with no call at all; when the brief has no
signal it says "Steady" rather than guess. Every number here comes from a walk-forward test: each year was
predicted only with data from before it, the way it works live.</p>
{live_line}
<p class="fine">Built by a former New York produce buyer. Data: USDA AMS Market News, updated every market evening.</p>
<p><a class="btn cta" href="../brief/">Read today's brief →</a></p>"""
    title = "See produce price moves coming two weeks out"
    desc = ("Free daily brief for produce buyers: Hunts Point, LA and Chicago terminal prices vs. usual for the "
            "season, a tested 2-week outlook and early warnings.")
    page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_esc(title)} | Produce Price Check</title>
<meta name="description" content="{_esc(desc)}">
<meta property="og:title" content="See produce price moves coming, two weeks out">
<meta property="og:description" content="{_esc(desc)}">
<link rel="canonical" href="{SITE_URL}why/">
<link rel="stylesheet" href="../style.css"></head>
<body><main class="landing brief why">
<p class="sub"><a href="../">Produce Price Check</a> · <a href="../brief/">Buyer's brief</a></p>
<!--SIGNUP-->
{body}
</main></body></html>
"""
    (OUT / "why").mkdir(parents=True, exist_ok=True)
    (OUT / "why" / "index.html").write_text(page, encoding="utf-8")
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


PAGES_DIR = ROOT / "data" / "pages"  # rich fragments from pipeline/pages.py (nightly)


def rich_page(slug, name, body, dash):
    """Wrap a pipeline/pages.py fragment: search title and description from today's numbers, links to every item."""
    answer = re.search(r'<p class="answer">(.*?)</p>', body, re.S)
    desc = html.unescape(re.sub(r"<[^>]+>", "", answer.group(1))) if answer else ""
    title = f"{name.title()} Prices Today: Wholesale Case Price & 2-Week Outlook"
    others = " · ".join(f'<a href="../{sl}/">{_esc(nm)}</a>' for c, (sl, nm) in PAGE_NAMES.items() if sl != slug)
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_esc(title)} | Produce Price Check</title>
<meta name="description" content="{_esc(desc[:300])}">
<link rel="canonical" href="{SITE_URL}{slug}/">
<meta property="og:title" content="{_esc(title)}">
<meta property="og:description" content="{_esc(desc[:300])}">
<meta property="og:url" content="{SITE_URL}{slug}/">
<link rel="stylesheet" href="../style.css"></head>
<body><main class="landing brief">
<p class="sub"><a href="../">Produce Price Check</a> · <a href="../brief/">Today's brief</a> · <a href="../why/">How accurate is it?</a></p>
{body}
<p><a class="btn cta" href="{_esc(dash)}">See the 10-year price chart →</a></p>
<h2>Other wholesale produce prices</h2>
<p class="others">{others}</p>
<p class="fine">Prices are the USDA “mostly” price per case at the terminal markets (USDA AMS Market News), for the
most consistently reported pack in each market, updated every market evening. “Usual” = the same weeks of the year
over the past 10 years, adjusted for inflation. Forecast ranges hold about 80% of the time. Market prices, not a
supplier's quote.</p>
</main></body></html>
"""


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
            page = rich_page(slug, name, rich.read_text(encoding="utf-8"), dash)
            (OUT / slug).mkdir(parents=True, exist_ok=True)
            (OUT / slug / "index.html").write_text(page, encoding="utf-8")
            urls.append(f"{SITE_URL}{slug}/")
            links.append(f'<a href="{slug}/">{_esc(name)} prices</a>')
            continue
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
