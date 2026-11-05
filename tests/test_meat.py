"""Meat prices have to trace back to USDA's rows, and the pages have to say what the price is."""

import csv
import glob

import pytest

from pipeline import brief, meat, meat_view, store


def _items():
    items = brief._json("meat.json", {}).get("items", [])
    if not items:
        pytest.skip("no data/export/meat.json yet")
    return items


def _usda(source):
    out = []
    for path in sorted(glob.glob(str(store.DATA / "raw" / source / "*" / "*.csv")))[-3:]:
        with open(path, newline="", encoding="utf-8") as f:
            out.extend(csv.DictReader(f))
    return out


def test_beef_prices_are_usda_rows_in_dollars_per_hundredweight():
    rows = _usda("beef")
    spec = {s: (v, sec) for s, _, v, sec in meat.BEEF}
    for i in (x for x in _items() if x["kind"] == "Beef"):
        variety, section = spec[i["slug"]]
        hit = [float(r["unit_price"]) for r in rows if r["report_date"] == i["date"] and r["variety"] == variety
               and (r["grade"] == section if section in ("Choice", "Select") else r["pack_size"] == section)]
        assert hit and i["price"] == pytest.approx(hit[-1], abs=0.01), i["slug"]


def test_chicken_prices_are_usda_rows_in_dollars_per_pound():
    rows = [r for r in _usda("chicken") if r["market"] == "National" and r["pack_size"] == "Fresh Domestic"]
    spec = {s: (v, size) for s, _, v, size in meat.CHICKEN}
    for i in (x for x in _items() if x["kind"] == "Chicken"):
        item, size = spec[i["slug"]]
        hit = [float(r["unit_price"]) for r in rows if r["report_date"] == i["date"] and r["variety"] == item and r["item_size"] == size]
        assert hit and i["price"] == pytest.approx(hit[-1] / 100, abs=0.01), i["slug"]
        assert i["price"] < 10  # dollars a pound, never cents


def test_every_listed_item_has_a_current_price_and_a_forecast():
    items = _items()
    assert {i["slug"] for i in items} == set(meat.NAMES)
    for i in items:
        assert i["points"][1]["lo"] <= i["points"][1]["mid"] <= i["points"][1]["hi"], i["slug"]
        assert i["low"] is None or i["low"] <= i["price"] <= i["high"], i["slug"]
        assert i["dir"] in ("firming", "softening", "steady", "topping", "bottoming")


def test_pages_name_the_unit_and_where_the_price_comes_from():
    items = _items()
    page = meat_view.page(items)
    assert "Wholesale meat prices today" in page and "negotiated sales" in page and "per cwt" in page and "per lb" in page
    assert page.count('class="brow"') == len(items)
    one = next(i for i in items if i["slug"] == "boneless-skinless-breast")
    body = meat_view.item_page(one, items)
    assert "per lb" in body and "a case" not in body and "Weekly price" in body and '"@type": "FAQPage"' in body
    assert meat_view.money(one["price"]) in body
    for banned in ("Wait if you can", "Hold off", "Good time to buy", " — "):
        assert banned not in page and banned not in body
