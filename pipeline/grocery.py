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

import csv

from . import conditions, config, cpi, staples, store
from .quality import LEVELS, quality
from .usual import with_usual

WINDOW_DAYS = 15     # same weeks in earlier years: +/- 2 weeks
MIN_YEARS = 3
LOW, HIGH = 25, 75   # percentile cut-offs, same as the wholesale view
MIN_STORES = 200     # fewer stores than this is often one chain's flyer: shown, but never headlined

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
    ["Chicken breasts", "Boneless chicken thighs", "Chicken thighs", "Whole chicken", "Chicken drumsticks"],
    ["Ground beef", "Lean ground beef", "Ground turkey"],
    ["Strip steak", "Ribeye steak", "Sirloin steak"],
    ["Chuck roast", "Pork shoulder", "Stew beef"],
    ["Pork chops", "Pork tenderloin", "Chicken breasts"],
    ["Shredded cheese", "Block cheese", "Sliced cheese"],
    ["Greek yogurt", "Yogurt"],
]


MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
          "November", "December"]


def slug(commodity):
    return re.sub(r"[^a-z0-9]+", "-", NAMES.get(commodity, commodity).lower()).strip("-")


def month_list(ms):
    """[4, 5, 6] -> 'April, May and June' (in calendar order)."""
    names = [MONTHS[m - 1] for m in sorted(ms)]
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def season_of(d):
    return {12: "winter", 1: "winter", 2: "winter", 3: "spring", 4: "spring", 5: "spring",
            6: "summer", 7: "summer", 8: "summer"}.get(d.month, "fall")


KEEP_CAPS = {"Brussels", "Swiss", "Roma", "Honeycrisp", "Gala", "Fuji", "Granny", "Smith", "Bartlett", "Anjou", "Bosc",
             "Hass", "Cara", "Navel", "Valencia", "Medjool", "Thompson", "Rainier", "Bing", "Persian", "Napa", "Italian", "Greek", "London", "T-bone"}


def sentence(n):
    """'Brussels Sprouts' -> 'Brussels sprouts', 'Swiss Chard' -> 'Swiss chard'."""
    words = n.split(" ")
    return " ".join([words[0]] + [w if w.strip("()") in KEEP_CAPS else w.lower() for w in words[1:]])


def display(commodity, variety=""):
    if commodity in staples.AISLE:
        return commodity
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
    if p == "12 count":
        return " a dozen"
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


STAPLE_IDS = set(config.STAPLE_REPORTS)


def load(rows):
    """item -> {(variety, pack): {date: [(price, stores)]}} for national, conventional sale prices.
    Meat, poultry, dairy and egg rows are mapped to shopper items (pipeline/staples.py)."""
    out = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
    for r in rows:
        if r["market"] != "National" or r["organic"] not in ("No", "N") or r["commodity"] in SKIP:
            continue
        if r.get("report_id") in STAPLE_IDS:
            item = staples.match(r)
            if not item:
                continue
            # USDA renamed products over the years ("WHITE LARGE" -> "Large White"), so staples are keyed by the
            # shopper item and pack, keeping value packs (cheaper per lb) as their own series
            value = "Value pack" if re.search(r"value", r["variety"] + " " + r.get("other_attributes", ""), re.I) else ""
            pack = "12 count" if item == "Eggs" and r["pack_size"] == "carton" else r["pack_size"]  # older reports: "per carton"
            r = dict(r, commodity=item, variety=value, pack_size=pack)
        price, stores = _num(r["unit_price"]), _num(r["store_count"])
        if price is None or not stores:
            continue
        v = (r["variety"] or "").strip()
        out[r["commodity"]][(v[:1].upper() + v[1:].lower(), r["pack_size"])][r["report_date"]].append((price, stores))
    return out


def main_pack(packs, since=None):
    """The item's main pack: most store-weeks of ads in the year before `since` (default: its last year)."""
    if since is None:
        since = (dt.date.fromisoformat(max(d for days in packs.values() for d in days)) - dt.timedelta(days=365)).isoformat()
    return max(packs, key=lambda k: sum(s for d, xs in packs[k].items() if d >= since for _, s in xs))


def build(rows, deflator=None, live=None):
    """live: this week's conditions per commodity (pipeline/conditions.py); computed from the reports when None."""
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
        key = main_pack(packs, year_ago)
        days = packs[key]
        if max(days) < year_ago:
            continue  # not advertised in the last year
        week = {}
        for d, xs in days.items():
            stores = sum(s for _, s in xs)
            week[d] = (sum(p * s for p, s in xs) / stores, stores)
        # reports close on different days (produce Friday, dairy Sunday): within the week counts as this week
        last = max(week)
        this_week = last >= (today - dt.timedelta(days=6)).isoformat()
        price, stores = week[last]
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
        # usual range for each week (same weeks, earlier years, today's dollars), for the item page chart
        dated = [(dt.date.fromisoformat(d), week[d][0], real[d]) for d in sorted(week)]
        band = {r[0]: (r[4], r[5]) for r in with_usual(dated)}
        # when it's usually cheapest (median price in today's dollars by month) and most advertised
        by_month, ads_month = defaultdict(list), defaultdict(list)
        for d, (p, st) in week.items():
            by_month[int(d[5:7])].append(real[d])
            ads_month[int(d[5:7])].append(st)
        med = {m: statistics.median(v) for m, v in by_month.items() if len(v) >= 3}
        cheapest = sorted(med, key=med.get)[:3] if len(med) >= 6 else []
        ads = {m: statistics.median(v) for m, v in ads_month.items()}
        peak = sorted(ads, key=ads.get, reverse=True)[:3] if len(ads) >= 6 else []
        item = {"commodity": commodity, "slug": slug(commodity), "name": display(commodity, key[0]),
                "aisle": staples.AISLE.get(commodity, "produce"),
                "short": sentence(NAMES.get(commodity, commodity)), "unit": unit(key[1]), "price": round(price, 2),
                "stores": int(stores), "this_week": this_week, "last_date": last,
                "in_season": commodity in SEASONS[season], "seasons": [k for k in SEASONS if commodity in SEASONS[k]],
                "cheapest_months": cheapest, "peak_months": peak,
                # typical ad price by month (median, today's dollars) and how many ad weeks back it up
                "month_price": {m: round(v, 2) for m, v in med.items()},
                "status": "new" if this_week else "absent", "vs_usual": None, "pctile": None,
                "low": None, "high": None, "featured": None,
                "chart": [(d, round(p, 2), band.get(d, (None, None)))
                          for d, (p, _) in sorted(week.items()) if d >= (today - dt.timedelta(days=371)).isoformat()]}
        item["quality"] = quality(commodity, today.month, item["in_season"] if item["seasons"] else None)
        if len(years) >= MIN_YEARS and this_week:
            pool.sort()
            now = real[last]
            usual = statistics.median(pool)
            pct = 100 * (sum(v < now for v in pool) + 0.5 * sum(v == now for v in pool)) / len(pool)
            q = lambda f: pool[min(len(pool) - 1, int(f * (len(pool) - 1) + 0.5))]  # noqa: E731
            item.update(vs_usual=round(100 * (now / usual - 1)), pctile=round(pct), low=round(q(0.25), 2),
                        high=round(q(0.75), 2), usual=round(usual, 2),
                        status="low" if pct <= LOW else "high" if pct >= HIGH else "typical")
            expected = statistics.mean(past_stores[y] for y in years) / 5  # stores per week, same weeks before
            item["featured"] = round(stores / expected, 2) if expected else None
        items.append(item)
    if live is None:
        path = store.DATA / "export" / "supply.csv"
        ship = {}
        if path.exists():
            with open(path, newline="", encoding="utf-8") as f:
                ship = {r["commodity"]: _num(r["vs_last_year_pct"]) for r in csv.DictReader(f)}
        live = conditions.build(today, ship)
    for i in items:  # real conditions this week, on top of the calendar
        c = live.get(i["commodity"])
        if not c or not c["notes"]:
            continue
        level, reason = i["quality"] or ("Good", "")
        if c["down"]:
            level = LEVELS[max(0, LEVELS.index(level) - 1)]
        i["quality"] = (level, f"{reason} {' '.join(c['notes'])}".strip())
        i["conditions"] = c["notes"]
    # two-week outlook (pipeline/grocery_forecast.py): only moves of 10%+ are shown
    from . import grocery_forecast
    ahead, _ = grocery_forecast.outlook(data, deflator, lambda p: main_pack(p, year_ago), today)
    for i in items:
        ch = ahead.get(i["commodity"]) if i["this_week"] else None
        i["outlook"] = round(ch, 3) if ch is not None and abs(ch) >= grocery_forecast.CALL else None
    by_c = {i["commodity"]: i for i in items if i["this_week"]}
    for i in items:
        if i["status"] == "high":
            fam = next((f for f in FAMILIES if i["commodity"] in f), [])
            alts = [by_c[c] for c in fam if c in by_c and c != i["commodity"] and by_c[c]["status"] == "low"
                    and (by_c[c]["in_season"] or by_c[c]["aisle"] != "produce") and by_c[c]["stores"] >= MIN_STORES
                    and q_rank(by_c[c]) >= 2]  # never suggest out-of-season fruit as the better buy
            i["swap"] = min(alts, key=lambda a: a["vs_usual"])["short"] if alts else None
    return today, sorted(items, key=lambda i: i["name"])


def q_rank(i):
    """0 Poor, 1 Fair, 2 Good, 3 Excellent; unknown counts as Good."""
    return LEVELS.index(i["quality"][0]) if i.get("quality") else 2


def best_buys(items, n=8, aisle="produce"):
    """Low for the time of year, good quality, in season and widely featured first. A cheap price on poor
    produce (August apples, winter peaches) is not a best buy."""
    items = [i for i in items if i["this_week"] and i["stores"] >= MIN_STORES and q_rank(i) >= 1 and i["aisle"] == aisle]
    good = [i for i in items if i["status"] == "low" or (i["status"] == "typical" and i["in_season"]
                                                           and (i["featured"] or 0) >= 1.3 and (i["vs_usual"] or 0) <= 0)]
    return sorted(good, key=lambda i: (i["status"] != "low", q_rank(i) < 2, -(i["in_season"]), i["vs_usual"] or 0))[:n]


def rows():
    """Every sale-price row the grocery view uses: produce (3324) and the staples reports."""
    yield from store.iter_all("retail")
    yield from store.iter_all("staples")


def main():
    today, items = build(rows(), cpi.Deflator(cpi.load()))
    print(f"grocery: {sum(i['this_week'] for i in items)} of {len(items)} items advertised the week of {today}")
    for i in best_buys(items):
        print(f"  {i['name']}: ${i['price']}{i['unit']}  {i['vs_usual']}% vs usual  in season={i['in_season']}")


if __name__ == "__main__":
    main()
