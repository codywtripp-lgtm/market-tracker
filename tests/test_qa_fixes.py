from pipeline import export, staples


def row(variety, pack="per lb", cond="Fresh", commodity="Beef"):
    return {"commodity": commodity, "variety": variety, "pack_size": pack, "properties": cond}


def test_each_meat_item_is_one_cut_under_old_and_new_usda_names():
    assert staples.match(row("Strip Steak, Boneless")) == "Strip steak"
    assert staples.match(row("BNLS NEW YORK STRIP STEAK")) == "Strip steak"
    assert staples.match(row("Strip Steak, Bone-In")) is None
    assert staples.match(row("Ribeye Steak, Bone-In")) is None
    assert staples.match(row("Top Sirloin Steak, Boneless")) == "Sirloin steak"
    assert staples.match(row("Sirloin Steak, Bone-In")) is None
    assert staples.match(row("CC Loin Chops, Boneless", commodity="Pork")) == "Pork chops"
    assert staples.match(row("CC CHOPS BNLS", commodity="Pork")) == "Pork chops"
    assert staples.match(row("Assorted Chops, Bone-In", commodity="Pork")) is None
    assert staples.match(row("CC Loin Chops, Boneless, Thick Cut", commodity="Pork")) is None
    assert staples.match(row("Spareribs", commodity="Pork")) is None
    assert staples.match(row("Breast, Boneless/Skinless", commodity="Chicken")) == "Chicken breasts"
    assert staples.match(row("Breast, Boneless/Skinless, Thin-Sliced", commodity="Chicken")) is None


def q(price, low, high):
    return {"unit_price": str(price), "normalized_price": "", "low_price": str(low), "high_price": str(high),
            "mostly_low_price": "", "mostly_high_price": "", "origin": "Pennsylvania", "market_tone": ""}


def test_range_shown_is_one_real_quote():
    # New York mushrooms, Nov 6 2026: three same-label quotes; the page showed "$16 to $21", which nobody quoted
    out = export.daily_value([q(17, 16, 18), q(20.5, 20, 21), q(17, 16, 18)])
    assert out["price"] == 17 and (out["low"], out["high"]) == (16, 18)


def test_main_area_stays_while_still_close():
    days = {}
    for d in range(1, 20):  # two areas quoted every day; yesterday's area keeps the price
        days[f"2026-10-{d:02d}"] = [{"origin": "Canada", "unit_price": "21"}, {"origin": "California", "unit_price": "60"}]
    picks = export.main_areas(days)
    assert len(set(picks.values())) == 1
