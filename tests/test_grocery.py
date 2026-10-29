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
    today, items = grocery.build(live={}, rows=history("Apples", 1.2))
    [a] = items
    assert a["status"] == "low" and a["vs_usual"] < 0 and a["in_season"]  # apples: fall, per USDA guide
    assert grocery.best_buys(items) == [a]


def test_pricey_item_gets_an_in_season_swap_only():
    rows = history("Blueberries", 5.0) + history("Raspberries", 1.0) + history("Strawberries", 1.0)
    _, items = grocery.build(live={}, rows=rows)
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
    today, items = grocery.build(live={}, rows=rows)
    [s] = items
    assert s["slug"] == "strawberries" and s["cheapest_months"] == [5, 6, 7]
    page = grocery_view.item_page(s, today, items)
    assert "How much are strawberries this week?" in page
    assert "out of season now" in page and "May, June and July" in page
    assert '"@type": "FAQPage"' in page
    assert dt.date.fromisoformat(s["last_date"]) == today


def test_one_chains_flyer_never_headlines():
    rows = [r | {"store_count": "40"} for r in history("Collards", 0.5)]
    _, items = grocery.build(live={}, rows=rows)
    assert items[0]["status"] == "low" and grocery.best_buys(items) == []


def test_quality_calendar_and_cheap_poor_produce_is_not_a_best_buy():
    from pipeline import quality
    assert quality.quality("Apples", 8)[0] == "Poor" and quality.quality("Apples", 10)[0] == "Excellent"
    assert quality.quality("Avocados", 10)[0] == "Good"  # year-round, despite the USDA guide's season lists
    assert quality.quality("Jicama", 10) is None  # nothing reliable to say
    rows = history("Peaches", 1.0, today="2026-10-23")  # cheap, but imported winter peaches
    _, items = grocery.build(live={}, rows=rows)
    assert items[0]["status"] == "low" and items[0]["quality"][0] == "Poor" and grocery.best_buys(items) == []


def test_real_conditions_lower_the_rating():
    rows = history("Strawberries", 1.0, today="2026-04-10")
    _, items = grocery.build(live={"Strawberries": {"down": True, "notes": ["Rain damage reported."]}}, rows=rows)
    assert items[0]["quality"][0] == "Good" and "Rain damage" in items[0]["quality"][1]  # Excellent, one level down


def test_staples_match_shopper_items_across_usda_renames():
    from pipeline import staples
    row = lambda c, v, pack="per lb", cond="Fresh": {"commodity": c, "variety": v, "pack_size": pack, "properties": cond}  # noqa: E731
    assert staples.match(row("Chicken", "Breast, Boneless/Skinless")) == "Chicken breasts"
    assert staples.match(row("Egg", "WHITE LARGE", "carton")) == staples.match(row("Egg", "Large White", "12 count")) == "Eggs"
    assert staples.match(row("Pork", "BKFST SAUSAGE, LINK/PATTY")) == "Breakfast sausage"
    assert staples.match(row("Turkey", "Whole Turkey < 16 Lbs", cond="Frozen")) == "Whole turkey"
    assert staples.match(row("Chicken", "Self-Service Deli Chicken Tub/Pouch", cond="Prepared")) is None
    assert staples.match({"commodity": "Milk", "variety": "All Fat Tests", "pack_size": "Gallon"}) == "Milk"


def test_meat_and_dairy_pages_dont_talk_about_seasons():
    from pipeline import grocery_view
    assert grocery_view.as_modifier("Eggs") == "Egg" and grocery_view.as_modifier("Pork chops") == "Pork chop"
    assert grocery_view.as_modifier("Pork shoulder") == "Pork shoulder" and grocery_view.as_modifier("Asparagus") == "Asparagus"
    i = {"short": "Pork shoulder", "commodity": "Pork shoulder", "aisle": "meat", "seasons": [], "in_season": False,
         "cheapest_months": [2, 3, 4]}
    assert grocery_view.season_sentence(i, None) == "Pork shoulder prices are usually lowest in February, March and April."


def test_item_page_lists_more_from_its_own_aisle():
    from pipeline import grocery_view
    today, items = grocery.build(live={}, rows=history("Apples", 1.2) + history("Pears", 1.5))
    page = grocery_view.item_page(items[0], today, items)
    assert "<h2>More produce</h2>" in page and "Other aisles" in page


def test_every_aisle_links_the_same_guides_and_holiday_calls_need_agreeing_years():
    import datetime as dt
    from pipeline import grocery_view, holiday
    g = grocery_view.guides(dt.date(2026, 11, 1))
    assert "thanksgiving-produce-prices" in g
    assert grocery_view.guides(dt.date(2026, 7, 1)) == ""
    flip = {"short": "Eggs", "commodity": "Eggs"}
    o = {"change": 0.26, "steady": False, "stores_x": 1}
    assert holiday.advice(flip, o).startswith("No reliable pattern")
