"""News about supply shocks per grocery item, from the GDELT news database (free, worldwide, daily since 2017).

For each topic we count news articles a day that mention the item AND a supply-shock word (shortage, freeze,
bird flu, tariff, cartel, recall, ...), relative to all articles GDELT saw that day. A surge in that share is the
signal: the egg price spike of early 2025 was preceded by weeks of bird-flu coverage while stores had stopped
advertising eggs.

Raw counts live in data/raw/news/<topic>.csv (date, count, total). Run `python -m pipeline.news` to fetch the
missing days (GDELT asks for one request every 5 seconds, so a full backfill takes about an hour).
"""

import csv
import datetime as dt
import json
import math
import time
import urllib.parse
import urllib.request

from . import store

API = "https://api.gdeltproject.org/api/v2/doc/doc"
SHOCK = ('(shortage OR shortages OR "price spike" OR "prices soar" OR "prices surge" OR "prices jump" OR tariff '
         'OR tariffs OR ban OR cartel OR cartels OR freeze OR frost OR hurricane OR drought OR flood OR recall OR '
         'outbreak OR "bird flu" OR "avian flu" OR strike OR blockade OR disease)')
# topic -> (search terms, grocery items it covers)
TOPICS = {
    "eggs": ('(eggs OR "egg prices")', ["Eggs"]),
    "chicken": ("(chicken OR poultry)", ["Chicken breasts", "Chicken thighs", "Chicken drumsticks",
                                         "Boneless chicken thighs", "Whole chicken", "Rotisserie chicken"]),
    "turkey": ('(turkeys OR "turkey prices" OR "turkey farms" OR "turkey flocks")',
               ["Whole turkey", "Turkey breast", "Ground turkey"]),
    "beef": ("(beef OR cattle)", ["Ground beef", "Lean ground beef", "Chuck roast", "Ribeye steak", "Sirloin steak",
                                  "Strip steak", "T-bone steak", "London broil", "Stew beef"]),
    "pork": ("(pork OR hogs OR bacon)", ["Pork chops", "Pork loin roast", "Pork ribs", "Pork shoulder",
                                         "Pork tenderloin", "Bacon", "Breakfast sausage", "Italian sausage", "Spiral ham"]),
    "dairy": ("(milk OR dairy)", ["Milk", "Ice cream", "Yogurt", "Greek yogurt", "Cottage cheese", "Sour cream",
                                  "Cream cheese"]),
    "cheese": ("cheese", ["Block cheese", "Shredded cheese", "Sliced cheese"]),
    "butter": ("butter", ["Butter"]),
    "avocados": ("(avocado OR avocados)", ["Avocados"]),
    "limes": ("(limes OR lime)", ["Limes"]),
    "lemons": ("lemons", ["Lemons"]),
    "tomatoes": ("(tomato OR tomatoes)", ["Tomatoes"]),
    "lettuce": ("(lettuce OR romaine)", ["Lettuce", "Salad (Mixed Types)"]),
    "spinach": ("spinach", ["Spinach"]),
    "strawberries": ("strawberries", ["Strawberries"]),
    "blueberries": ("blueberries", ["Blueberries"]),
    "raspberries": ("(raspberries OR blackberries)", ["Raspberries", "Blackberries"]),
    "grapes": ("grapes", ["Grapes"]),
    "onions": ("onions", ["Onions, Dry", "Onions, Green"]),
    "potatoes": ("potatoes", ["Potatoes", "Sweet Potatoes"]),
    "bananas": ("bananas", ["Bananas"]),
    "oranges": ("(oranges OR citrus)", ["Oranges", "Tangerines/Mandarins", "Clementines", "Grapefruit", "Tangelos"]),
    "apples": ("apples", ["Apples"]),
    "pears": ("pears", ["Pears"]),
    "peppers": ('("bell peppers" OR jalapeno OR jalapenos OR "chile peppers")',
                ["Peppers, Bell Type", "Jalapeno Peppers", "Serrano Peppers", "Mixed Mini Sweet Peppers"]),
    "cucumbers": ("cucumbers", ["Cucumbers"]),
    "broccoli": ("(broccoli OR cauliflower)", ["Broccoli", "Cauliflower"]),
    "celery": ("celery", ["Celery"]),
    "carrots": ("carrots", ["Carrots"]),
    "corn": ('("sweet corn")', ["Corn-Sweet"]),
    "melons": ("(cantaloupe OR cantaloupes OR watermelon OR melons)", ["Cantaloupes", "Watermelons", "Honeydews"]),
    "stone fruit": ("(peaches OR nectarines OR cherries OR plums)", ["Peaches", "Nectarines", "Cherries", "Plums", "Apricots"]),
    "mangoes": ("mangoes", ["Mangoes"]),
    "pineapples": ("pineapples", ["Pineapples"]),
    "garlic": ("garlic", ["Garlic"]),
    "mushrooms": ("mushrooms", ["Mushrooms"]),
    "cabbage": ("cabbage", ["Cabbage", "Chinese Cabbage", "Bok Choy"]),
    "squash": ("(squash OR zucchini)", ["Squash"]),
}
ITEM_TOPIC = {item: t for t, (_, items) in TOPICS.items() for item in items}
DIR = store.DATA / "raw" / "news"
FIRST_YEAR = 2017


def _fetch(query, start, end, tries=12):
    params = {"query": query, "mode": "timelinevolraw", "format": "json",
              "startdatetime": start.strftime("%Y%m%d000000"), "enddatetime": end.strftime("%Y%m%d235959")}
    url = API + "?" + urllib.parse.urlencode(params)
    for n in range(tries):
        time.sleep(10)  # GDELT allows one request every 5 seconds; stay well under it
        try:
            with urllib.request.urlopen(url, timeout=120) as r:
                j = json.loads(r.read().decode("utf-8", "replace"))
            return [(dt.datetime.strptime(d["date"][:8], "%Y%m%d").date(), d["value"], d["norm"])
                    for d in j["timeline"][0]["data"]] if j.get("timeline") else []
        except (OSError, ValueError, KeyError, IndexError) as e:
            wait = 300 if "429" in str(e) else 30 * (n + 1)  # rate-limited: wait it out
            print(f"news: retry in {wait}s ({e})", flush=True)
            time.sleep(wait)
    raise RuntimeError(f"GDELT failed: {query} {start}..{end}")


def load(topic):
    path = DIR / f"{topic}.csv"
    if not path.exists():
        return {}
    with open(path, newline="", encoding="utf-8") as f:
        return {dt.date.fromisoformat(r["date"]): (int(r["count"]), int(r["total"])) for r in csv.DictReader(f)}


def update(today=None, topics=None):
    """Fetch the days each topic is missing, a year at a time; the current year is always refreshed."""
    today = today or dt.date.today()
    DIR.mkdir(parents=True, exist_ok=True)
    for topic in topics or TOPICS:
        have = load(topic)
        query = f"{TOPICS[topic][0]} {SHOCK}"
        for year in range(FIRST_YEAR, today.year + 1):
            start, end = dt.date(year, 1, 1), min(dt.date(year, 12, 31), today)
            if year < today.year and any(d.year == year for d in have):
                continue
            if year == today.year and have:
                start = max(start, max(have) - dt.timedelta(days=14))
            for d, c, n in _fetch(query, start, end):
                have[d] = (c, n)
        with open(DIR / f"{topic}.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["date", "count", "total"])
            for d in sorted(have):
                w.writerow([d.isoformat(), *have[d]])
        print(f"news: {topic} {len(have)} days")


def surge(item, day, recent=7, base=56):
    """log(share of shock news in the last `recent` days / share in the `base` days before), or None."""
    topic = ITEM_TOPIC.get(item)
    days = _cache.get(topic)
    if days is None:
        days = _cache[topic] = load(topic) if topic else {}
    if not days:
        return None

    def share(a, b):
        c = n = 0
        d = a
        while d < b:
            if d in days:
                c += days[d][0]
                n += days[d][1]
            d += dt.timedelta(days=1)
        return (c, n)

    c1, n1 = share(day - dt.timedelta(days=recent - 1), day + dt.timedelta(days=1))
    c0, n0 = share(day - dt.timedelta(days=recent + base - 1), day - dt.timedelta(days=recent - 1))
    if not n1 or not n0:
        return None
    return math.log((c1 / n1 + 1e-7) / (c0 / n0 + 1e-7))


_cache = {}

if __name__ == "__main__":
    update()
