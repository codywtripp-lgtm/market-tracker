"""Thanksgiving produce prices: what the holiday items cost now, and how their sale prices usually move by
Thanksgiving week.

Supermarkets put Thanksgiving staples on sale the week before the holiday. From USDA's weekly retail report
(2016-2026), for each item: the median change in its sale price from this point in the fall to Thanksgiving
week, how many more stores put it on sale that week, and what it cost last Thanksgiving week.
"""

import datetime as dt
import statistics

ITEMS = ["Whole turkey", "Sweet Potatoes", "Cranberries", "Celery", "Brussels Sprouts", "Beans", "Potatoes", "Onions, Dry", "Carrots",
         "Mushrooms", "Apples", "Pears", "Oranges", "Tangerines/Mandarins", "Pumpkins", "Garlic", "Salad (Mixed Types)"]
KEEPS = {"Whole turkey", "Potatoes", "Onions, Dry", "Sweet Potatoes", "Garlic", "Carrots", "Apples", "Pumpkins", "Oranges"}  # fine to buy ahead
WINDOW = 12  # days before Thanksgiving: the weekly report dated in this window carries the holiday sales


def thanksgiving(year):
    d = dt.date(year, 11, 1)
    d += dt.timedelta(days=(3 - d.weekday()) % 7)  # first Thursday
    return d + dt.timedelta(weeks=3)


def _mean(xs):
    return statistics.mean(xs) if xs else None


def item_outlook(i, today):
    """{change, stores_x, years, last_tg} for one grocery item (pipeline/grocery.py, with its 'weeks')."""
    week = {dt.date.fromisoformat(d): v for d, v in i["weeks"].items()}
    target = thanksgiving(today.year) if today <= thanksgiving(today.year) else thanksgiving(today.year + 1)
    lead = (target - today).days
    ratios, stores = [], []
    for y in range(target.year - 10, target.year):
        tg = thanksgiving(y)
        now = tg - dt.timedelta(days=lead)
        at = [v for d, v in week.items() if 0 < (tg - d).days <= WINDOW]
        before = [v for d, v in week.items() if abs((d - now).days) <= 7]
        if at and before:
            ratios.append(_mean([p for p, _ in at]) / _mean([p for p, _ in before]))
            stores.append(_mean([s for _, s in at]) / _mean([s for _, s in before]))
    last = [p for d, (p, _) in week.items() if 0 < (thanksgiving(target.year - 1) - d).days <= WINDOW]
    return {"target": target, "years": len(ratios),
            "change": statistics.median(ratios) - 1 if len(ratios) >= 3 else None,
            "stores_x": statistics.median(stores) if len(stores) >= 3 else None,
            "last_tg": _mean(last)}


def advice(i, o):
    c = o["change"]
    if c is None:
        return "Not enough past years to say how it moves into Thanksgiving week."
    if c <= -0.10:
        more = f", when {o['stores_x']:.0f} times as many stores feature it" if (o["stores_x"] or 0) >= 2 else ""
        return f"Wait for the holiday specials: usually {abs(round(100 * c))}% cheaper Thanksgiving week{more}."
    if c >= 0.05:
        if i["commodity"] in KEEPS:
            return f"Buy ahead if you see a good price: it usually costs {round(100 * c)}% more by Thanksgiving week, and it keeps."
        return f"Usually {round(100 * c)}% more by Thanksgiving week. Buy when you see a good sale, a few days ahead."
    return "Usually little change by Thanksgiving week. Buy whenever it suits you."
