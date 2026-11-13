import datetime as dt

from pipeline import grocery, grocery_view


def item(commodity, short, in_season, quality=None, status="typical", this_week=True, vs=0):
    return {"commodity": commodity, "short": short, "slug": short.lower().replace(" ", "-"), "aisle": "produce",
            "in_season": in_season, "quality": quality, "status": status, "this_week": this_week,
            "price": 1.5, "unit": "/lb", "vs_usual": vs}


def test_fruits_and_vegetables_follow_myplate_and_usda_season():
    items = [item("Apples", "Apples", True, ("Excellent", "New crop.")),
             item("Avocados", "Avocados", False, ("Good", "All year.")),
             item("Tomatoes", "Tomatoes", True, ("Good", "")),
             item("Clementines", "Clementines", False, ("Excellent", "Peak."), status="low", vs=-16),
             item("Peaches", "Peaches", False, ("Poor", "Imported.")),
             item("Honey", "Honey", True)]
    h = grocery_view.season_page(dt.date(2026, 11, 6), items)
    fruits = h.split("<h2>Fruits in season in November</h2>")[1].split("</section>")[0]
    veg = h.split("<h2>Vegetables in season in November</h2>")[1].split("</section>")[0]
    assert "Apples" in fruits and "Tomatoes" in veg and "Tomatoes" not in fruits
    assert "Honey" not in h
    assert "Clementines" in h.split("Also at their best in November")[1].split("</section>")[0]
    assert "Peaches" in h.split("Past their best in November")[1].split("</section>")[0]
    assert "Clementines ($1.50/lb, 16% below usual)" in h


def test_pack_with_hyphen_reads_as_a_size():
    assert grocery.unit("1-lb containers with lids") == " for 1 lb"
    assert grocery.unit("2 pound bags") == " for 2 lb"
    assert grocery.unit("8-10 oz package") == " for 8-10 oz"


def test_beef_datamart_fails_fast(monkeypatch):
    import requests
    from pipeline import usda
    calls = []

    class Hung:
        def get(self, url, params=None, auth=None, timeout=None):
            calls.append(timeout)
            raise requests.Timeout("hung")
    monkeypatch.setattr(usda.time, "sleep", lambda s: None)
    c = usda.Client(api_key="x", session=Hung())
    try:
        c.datamart("2453", "Ground Beef", dt.date(2026, 11, 2), dt.date(2026, 11, 12))
    except usda.USDAError:
        pass
    assert calls == [90, 90]
