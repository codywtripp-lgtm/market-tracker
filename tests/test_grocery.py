from pipeline import grocery


def row(date, commodity, price, stores=1000, pack="per lb", variety=""):
    return {"report_date": date, "commodity": commodity, "market": "National", "organic": "No", "unit_price": str(price),
            "store_count": str(stores), "variety": variety, "pack_size": pack}


def history(commodity, now_price, years=4, usual=2.0, today="2026-10-23"):
    rows = []
    for y in range(2026 - years, 2026):
        rows.append(row(f"{y}-10-23", commodity, usual))
    rows.append(row(today, commodity, now_price))
    return rows


def test_cheap_this_week_is_a_great_price_and_a_best_buy():
    today, items = grocery.build(history("Apples", 1.2))
    [a] = items
    assert a["status"] == "low" and a["vs_usual"] < 0 and a["in_season"]  # apples: fall, per USDA guide
    assert grocery.best_buys(items) == [a]


def test_pricey_item_gets_an_in_season_swap_only():
    rows = history("Blueberries", 5.0) + history("Raspberries", 1.0) + history("Strawberries", 1.0)
    _, items = grocery.build(rows)
    blue = next(i for i in items if i["commodity"] == "Blueberries")
    assert blue["status"] == "high" and blue["swap"] == "Raspberries"  # strawberries are out of season in fall


def test_units_and_names_read_naturally():
    assert grocery.unit("per lb") == "/lb" and grocery.unit("3 count") == " for 3" and grocery.unit("6 oz package") == " for 6 oz"
    assert grocery.display("Brussels Sprouts") == "Brussels sprouts"
    assert grocery.display("Lettuce", "Romaine (hearts)") == "Lettuce (Romaine hearts)"


def test_item_page_answers_price_season_and_when_cheapest():
    import datetime as dt
    from pipeline import grocery_view
    rows = []
    for y in range(2021, 2026):
        for m, p in ((5, 2.0), (6, 2.1), (7, 2.2), (10, 4.0), (11, 4.2), (12, 4.4), (1, 4.5), (2, 3.5), (3, 3.0)):
            rows.append(row(f"{y}-{m:02d}-15", "Strawberries", p, pack="1 lb package"))
    rows.append(row("2026-10-23", "Strawberries", 3.2, pack="1 lb package"))
    today, items = grocery.build(rows)
    [s] = items
    assert s["slug"] == "strawberries" and s["cheapest_months"] == [5, 6, 7]
    page = grocery_view.item_page(s, today, items)
    assert "How much are strawberries this week?" in page
    assert "out of season now" in page and "May, June and July" in page
    assert '"@type": "FAQPage"' in page
    assert dt.date.fromisoformat(s["last_date"]) == today


def test_one_chains_flyer_never_headlines():
    rows = [r | {"store_count": "40"} for r in history("Collards", 0.5)]
    _, items = grocery.build(rows)
    assert items[0]["status"] == "low" and grocery.best_buys(items) == []
