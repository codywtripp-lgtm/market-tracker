"""The grocery view: what's a good buy at the supermarket this week.

Source: USDA National Retail Report (3324), the prices supermarkets advertise each week and how many
stores ran the ad, national level, every produce item. For each item's most-advertised pack:

- this week's average advertised price (weighted by stores),
- how it compares with the same weeks in earlier years (in today's dollars): low / typical / high,
- whether it's in season (USDA SNAP-Ed Seasonal Produce Guide) and whether stores are featuring it more than
  usual for the time of year,
- for pricey items, a cheaper swap from the same family that's a good price this week.

Wholesale prices are not used here: weekly ad prices barely follow them (correlation about 0.1 at 0-8 week
lags, 2016-2026), so nothing on the grocery view claims they do.
"""

import datetime as dt
import re
import statistics
from collections import defaultdict

from . import cpi, store

WINDOW_DAYS = 15     # same weeks in earlier years: +/- 2 weeks
MIN_YEARS = 3
LOW, HIGH = 25, 75   # percentile cut-offs, same as the wholesale view

SKIP = {"Hemp Seeds Shelled", "Hemp Protein", "Hemp (Seed) Oil", "Ornamentals", "Apples, Processed", "Prunes"}
NAMES = {
    "Corn-Sweet": "Sweet corn", "Onions, Dry": "Onions", "Onions, Green": "Green onions",
    "Peppers, Bell Type": "Bell peppers", "Salad (Mixed Types)": "Bagged salad", "Tangerines/Mandarins": "Mandarins",
    "Cactus Leaf (Nopales)": "Nopales", "Mixed Mini Sweet Peppers": "Mini sweet peppers", "Turnip Tops": "Turnip greens",
    "Mustard": "Mustard greens", "Collards": "Collard greens", "Beans": "Green beans", "Corn": "Sweet corn",
    "Lettuce, Iceberg": "Iceberg lettuce", "Lettuce, Romaine": "Romaine lettuce", "Tomatoes, Plum Type": "Roma tomatoes",
}

# USDA SNAP-Ed Seasonal Produce Guide, mapped to the retail report's names.
SEASONS = {
    "spring": "Apples Apricots Asparagus Avocados Bananas Broccoli Cabbage Carrots Celery Collards Garlic Cilantro Kale "
              "Kiwifruit Lemons Lettuce Limes Mushrooms Onions,_Dry Peas Pineapples Radishes Spinach Strawberries "
              "Swiss_Chard",
    "summer": "Apples Apricots Avocados Bananas Beets Peppers,_Bell_Type Blackberries Blueberries Cantaloupes Carrots "
              "Celery Cherries Corn-Sweet Cucumbers Eggplant Garlic Beans Cilantro Honeydews Lemons Limes Mangoes Okra "
              "Peaches Plums Raspberries Strawberries Squash Tomatillos Tomatoes Watermelons Nectarines",
    "fall": "Apples Bananas Beets Peppers,_Bell_Type Broccoli Brussels_Sprouts Cabbage Carrots Cauliflower Celery Collards "
            "Cranberries Garlic Ginger Grapes Beans Cilantro Kale Kiwifruit Lemons Lettuce Limes Mangoes Mushrooms "
            "Onions,_Dry Parsnips Pears Peas Pineapples Potatoes Pumpkins Radishes Raspberries Spinach Sweet_Potatoes "
            "Swiss_Chard Squash",
    "winter": "Apples Avocados Bananas Beets Brussels_Sprouts Cabbage Carrots Celery Collards Grapefruit Cilantro Kale "
              "Kiwifruit Lemons Limes Onions,_Dry Oranges Parsnips Pears Pineapples Potatoes Pumpkins Sweet_Potatoes "
              "Swiss_Chard Squash",
}
SEASONS = {k: {w.replace("_", " ") for w in v.split()} for k, v in SEASONS.items()}

# families for "pricey? try this instead"
FAMILIES = [
    ["Strawberries", "Blueberries", "Raspberries", "Blackberries"],
    ["Oranges", "Tangerines/Mandarins", "Clementines", "Grapefruit"],
    ["Watermelons", "Cantaloupes", "Honeydews"],
    ["Peaches", "Nectarines", "Plums", "Apricots", "Cherries"],
    ["Apples", "Pears", "Grapes"],
    ["Lettuce", "Salad (Mixed Types)", "Spinach"],
    ["Kale", "Collards", "Swiss Chard", "Turnip Tops", "Mustard"],
    ["Broccoli", "Cauliflower", "Brussels Sprouts", "Beans", "Asparagus"],
    ["Peppers, Bell Type", "Mixed Mini Sweet Peppers"],
    ["Squash", "Eggplant", "Cucumbers"],
    ["Mangoes", "Pineapples", "Papaya", "Kiwifruit"],
    ["Potatoes", "Sweet Potatoes"],
]


def season_of(d):
    return {12: "winter", 1: "winter", 2: "winter", 3: "spring", 4: "spring", 5: "spring",
            6: "summer", 7: "summer", 8: "summer"}.get(d.month, "fall")


KEEP_CAPS = {"Brussels", "Swiss", "Roma", "Honeycrisp", "Gala", "Fuji", "Granny", "Smith", "Bartlett", "Anjou", "Bosc",
             "Hass", "Cara", "Navel", "Valencia", "Medjool", "Thompson", "Rainier", "Bing", "Persian", "Napa"}


def sentence(n):
    """'Brussels Sprouts' -> 'Brussels sprouts', 'Swiss Chard' -> 'Swiss chard'."""
    words = n.split(" ")
    return " ".join([words[0]] + [w if w.strip("()") in KEEP_CAPS else w.lower() for w in words[1:]])


def display(commodity, variety=""):
    n = sentence(NAMES.get(commodity, commodity))
    v = variety.strip()
    if v and v.lower() not in n.lower() and not re.search(r"mixed|various|n/a", v, re.I):
        v = re.sub(r"\s+type$", "", v, flags=re.I).replace("(", "").replace(")", "")
        v = re.sub(r"^vine ripes? - ", "", v, flags=re.I)
        n += f" ({v[:1].upper() + v[1:].lower()})"
    return n


def unit(pack):
    """'per lb' -> '/lb', '3 count' -> ' for 3', '6 oz package' -> ' for 6 oz', 'per bunch' -> ' a bunch'."""
    p = pack.strip().lower()
    if p in ("per lb", "lb"):
        return "/lb"
    if p == "each":
        return " each"
    if p.startswith("per "):
        return " a " + p[4:]
    m = re.match(r"(\d+) count", p)
    if m:
        return f" for {m.group(1)}"
    m = re.match(r"([0-9./-]+ (?:oz|lb|pint|quart|pt|qt))", p)
    if m:
        return f" for {m.group(1)}"
    return f" for a {p}"


def _num(s):
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def load(rows):
    """commodity -> {(variety, pack): {date: [(price, stores)]}} for national, conventional ads."""
    out = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
    for r in rows:
        if r["market"] != "National" or r["organic"] not in ("No", "N") or r["commodity"] in SKIP:
            continue
        price, stores = _num(r["unit_price"]), _num(r["store_count"])
        if price is None or not stores:
            continue
        v = (r["variety"] or "").strip()
        out[r["commodity"]][(v[:1].upper() + v[1:].lower(), r["pack_size"])][r["report_date"]].append((price, stores))
    return out


def build(rows, deflator=None):
    deflator = deflator or cpi.Deflator({})
    data = load(rows)
    if not data:
        return None, []
    latest = max(d for packs in data.values() for days in packs.values() for d in days)
    today = dt.date.fromisoformat(latest)
    year_ago = (today - dt.timedelta(days=365)).isoformat()
    season = season_of(today)
    items = []
    for commodity, packs in data.items():
        # the item's main pack: most store-weeks of ads in the last year
        key = max(packs, key=lambda k: sum(s for d, xs in packs[k].items() if d >= year_ago for _, s in xs))
        days = packs[key]
        if latest not in days:
            continue  # not advertised this week
        week = {}
        for d, xs in days.items():
            stores = sum(s for _, s in xs)
            week[d] = (sum(p * s for p, s in xs) / stores, stores)
        price, stores = week[latest]
        real = {d: p * deflator.factor(d) for d, (p, _) in week.items()}
        pool, years, past_stores = [], set(), defaultdict(float)
        for d in week:
            dd = dt.date.fromisoformat(d)
            for back in range(1, 11):
                try:
                    same = today.replace(year=today.year - back)
                except ValueError:
                    same = today.replace(year=today.year - back, day=28)
                if abs((dd - same).days) <= WINDOW_DAYS:
                    pool.append(real[d])
                    years.add(back)
                    past_stores[back] += week[d][1]
        item = {"commodity": commodity, "name": display(commodity, key[0]), "short": sentence(NAMES.get(commodity, commodity)),
                "unit": unit(key[1]), "price": round(price, 2), "stores": int(stores),
                "in_season": commodity in SEASONS[season], "status": "new", "vs_usual": None, "pctile": None,
                "low": None, "high": None, "featured": None,
                "history": [(d, round(week[d][0], 2)) for d in sorted(week) if d >= year_ago]}
        if len(years) >= MIN_YEARS:
            pool.sort()
            now = real[latest]
            usual = statistics.median(pool)
            pct = 100 * (sum(v < now for v in pool) + 0.5 * sum(v == now for v in pool)) / len(pool)
            q = lambda f: pool[min(len(pool) - 1, int(f * (len(pool) - 1) + 0.5))]  # noqa: E731
            item.update(vs_usual=round(100 * (now / usual - 1)), pctile=round(pct), low=round(q(0.25), 2),
                        high=round(q(0.75), 2), usual=round(usual, 2),
                        status="low" if pct <= LOW else "high" if pct >= HIGH else "typical")
            expected = statistics.mean(past_stores[y] for y in years) / 5  # stores per week, same weeks before
            item["featured"] = round(stores / expected, 2) if expected else None
        items.append(item)
    by_c = {i["commodity"]: i for i in items}
    for i in items:
        if i["status"] == "high":
            fam = next((f for f in FAMILIES if i["commodity"] in f), [])
            alts = [by_c[c] for c in fam if c in by_c and c != i["commodity"] and by_c[c]["status"] == "low"
                    and by_c[c]["in_season"]]  # never suggest out-of-season fruit as the better buy
            i["swap"] = min(alts, key=lambda a: a["vs_usual"])["short"] if alts else None
    return today, sorted(items, key=lambda i: i["name"])


def best_buys(items, n=8):
    """Low for the time of year, in-season and widely featured first."""
    good = [i for i in items if i["status"] == "low" or (i["status"] == "typical" and i["in_season"]
                                                           and (i["featured"] or 0) >= 1.3 and (i["vs_usual"] or 0) <= 0)]
    return sorted(good, key=lambda i: (i["status"] != "low", -(i["in_season"]), i["vs_usual"] or 0))[:n]


def main():
    today, items = build(store.iter_all("retail"), cpi.Deflator(cpi.load()))
    print(f"grocery: {len(items)} items advertised the week of {today}")
    for i in best_buys(items):
        print(f"  {i['name']}: ${i['price']}{i['unit']}  {i['vs_usual']}% vs usual  in season={i['in_season']}")


if __name__ == "__main__":
    main()
