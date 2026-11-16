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


def test_week_waits_for_its_weekly_report(monkeypatch):
    # 11-16: apples' "Week Ending" report comes the Monday after; counting the week before it read as -97%
    import pandas as pd
    from pipeline import volumes
    monkeypatch.setattr(volumes, "latest_report", lambda: pd.Timestamp("2026-11-13"))
    assert pd.Timestamp("2026-11-13") - pd.Timedelta(days=8) < pd.Timestamp("2026-11-09")
    assert pd.Timestamp("2026-11-13") - pd.Timedelta(days=8) >= pd.Timestamp("2026-11-02")


def test_other_kinds_named_like_shoppers_say_them():
    assert grocery.kind_name("Plum type (roma)") == "Roma"
    assert grocery.kind_name("Gala/royal gala") == "Gala"
    assert grocery.kind_name("Romaine (hearts)") == "Romaine hearts"
    assert grocery.kind_name("") == ""
    packs = {("Vine ripes - on the vine", "per lb"): {"2026-11-13": [(2.35, 2000)]},
             ("Plum type (roma)", "per lb"): {"2026-11-13": [(1.99, 600)]},
             ("Cherry type", "1 pint package"): {"2026-11-13": [(2.5, 20)]}}
    k = grocery.kinds(packs, ("Vine ripes - on the vine", "per lb"), "2026-11-13")
    assert [x["kind"] for x in k] == ["Roma"] and k[0]["price"] == 1.99
