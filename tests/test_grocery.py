from pipeline import grocery


def row(date, commodity, price, stores=100, pack="per lb", variety=""):
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
