from pipeline import normalize as n

TS = "2026-09-26T00:00:00+00:00"

NY_AVOCADO = {
    "report_date": "09/24/2026", "slug_id": "2314", "report_title": "New York Terminal Market Fruit Prices (NX_FV010)",
    "commodity": "Avocados", "variety": "HASS", "package": "cartons 2 layer", "item_size": "48s",
    "appearance": "N/A", "origin": "Mexico", "district": "N/A", "organic": "N", "properties": None,
    "low_price": "32.00", "high_price": "33.00", "mostly_low_price": None, "mostly_high_price": None,
    "market_tone_comments": "MARKET ABOUT STEADY",
}


def test_terminal_row():
    r = n.terminal(NY_AVOCADO, "New York", TS)
    assert r["report_date"] == "2026-09-24"
    assert r["market"] == "New York" and r["market_type"] == "terminal"
    assert r["count_size"] == 48
    assert r["unit_price"] == 32.5
    assert r["normalized_price"] == round(32.5 / 48, 4) and r["normalized_unit"] == "per each"
    assert r["origin"] == "Mexico" and r["origin_detail"] == ""
    assert r["appearance"] == ""


def test_appearance_changes_row_id():
    a = n.terminal(NY_AVOCADO, "New York", TS)
    b = n.terminal({**NY_AVOCADO, "appearance": "Fine Appearance", "low_price": "34.00"}, "New York", TS)
    assert a["row_id"] != b["row_id"]


def test_row_id_ignores_price_and_fetch_time():
    a = n.terminal(NY_AVOCADO, "New York", TS)
    b = n.terminal({**NY_AVOCADO, "low_price": "30.00"}, "New York", "2027-01-01T00:00:00+00:00")
    assert a["row_id"] == b["row_id"]


def test_mostly_price_preferred():
    assert n.representative_price(20, 24, 22, None) == 22
    assert n.representative_price(20, 24, None, None) == 22
    assert n.representative_price(None, None, None, None) is None


def test_package_weights():
    assert n.package_lb("Strawberries", "flats 8 1-lb containers with lids") == 8
    assert n.package_lb("Tomatoes, Plum Type", "25 lb cartons loose") == 25
    assert n.package_lb("Peppers, Bell Type", "5 kg/11 lb cartons") == 11
    assert n.package_lb("Onions, Dry", "master container 16 3-lb mesh sacks") == 48
    assert n.package_lb("Peppers, Habanero", "4 kg cartons") == 8.818
    assert n.package_lb("Strawberries", "flats 12 1-pint baskets") == 9
    assert n.package_lb("Peppers, Bell Type", "1 1/9 bushel cartons") == 25
    assert n.package_lb("Lettuce, Iceberg", "cartons") is None


def test_counts():
    assert n.count_size("24s film wrapped", "cartons") == 24
    assert n.count_size("film lined 24s", "cartons") == 24
    assert n.count_size("N/A", "cartons 12 3-count packages") == 36
    assert n.count_size("4x5s", "cartons 2 layer") is None
    assert n.count_size("extra large", "25 lb cartons loose") is None
    assert n.count_size("2 dozen", "cartons") == 24
    assert n.count_size("2 1/2 dozen", "cartons") == 30


def test_single_package_ounces():
    assert n.package_lb("Blueberries", "18 oz package") == 1.125
    assert n.package_lb("Cucumbers", "1 1/9 bushel cartons") == 55


def test_lettuce_per_head():
    raw = {**NY_AVOCADO, "commodity": "Lettuce, Iceberg", "variety": "N/A", "package": "cartons",
           "item_size": "24s film wrapped", "low_price": "45.00", "high_price": "48.00",
           "mostly_low_price": "46.00", "mostly_high_price": "47.00"}
    r = n.terminal(raw, "New York", TS)
    assert r["unit_price"] == 46.5
    assert r["normalized_price"] == round(46.5 / 24, 4) and r["normalized_unit"] == "per each"


def test_shipping_point_uses_district_and_short_fields():
    raw = {"report_date": "09/24/2026", "slug_id": "2390", "commodity": "Avocados", "var": "HASS",
           "pkg": "cartons 2 layer", "item_size": "60s", "district": "MEXICO CROSSINGS THROUGH TEXAS",
           "low_price": "24.25", "high_price": "28.25", "mostly_low_price": "24.25", "mostly_high_price": "26.25"}
    r = n.shipping_point(raw, TS)
    assert r["variety"] == "HASS" and r["pack_size"] == "cartons 2 layer"
    assert r["origin"] == r["market"] == "MEXICO CROSSINGS THROUGH TEXAS"
    assert r["market_type"] == "shipping point"
    assert r["unit_price"] == 25.25


def test_retail():
    raw = {"report_end_date": "09/25/2026", "slug_id": "3324", "commodity": "Onions, Dry", "variety": "YELLOW",
           "region": "National", "size": "3 lb bag", "organic": "No", "store_count": "2727", "wtd_avg_price": "3.14"}
    r = n.retail(raw, TS)
    assert r["report_date"] == "2026-09-25" and r["market_type"] == "retail"
    assert r["normalized_price"] == round(3.14 / 3, 4) and r["normalized_unit"] == "per lb"
    each = n.retail({**raw, "size": "each", "wtd_avg_price": "0.88"}, TS)
    assert each["normalized_price"] == 0.88 and each["normalized_unit"] == "per each"


def test_beef_cutout_and_cuts():
    cut = {"report_date": "09/25/2026", "slug_id": "2453", "item_description": "Rib, ribeye, bnls, heavy (112A  3)",
           "price_range_low": "1,541.00", "price_range_high": "1,636.86", "weighted_average": "1,562.72",
           "total_pounds": "81,997"}
    [r] = n.beef(cut, "Choice Cuts", TS)
    assert r["grade"] == "Choice" and r["unit_price"] == 1562.72
    assert r["normalized_price"] == 15.6272 and r["price_unit"] == "$/cwt"
    assert n.beef({**cut, "weighted_average": ".00"}, "Choice Cuts", TS) == []
    rows = n.beef({"report_date": "09/25/2026", "slug_id": "2453", "choice_600_900_current": "378.83",
                   "select_600_900_current": "355.76"}, "Current Cutout Values", TS)
    assert [x["grade"] for x in rows] == ["Choice", "Select"]


def test_other_attributes_distinguish_rows():
    a = n.terminal({**NY_AVOCADO, "crop": "NEW CROP"}, "New York", TS)
    b = n.terminal({**NY_AVOCADO, "crop": "OLD CROP"}, "New York", TS)
    assert a["other_attributes"] == "crop=NEW CROP"
    assert a["row_id"] != b["row_id"]
    assert n.terminal(NY_AVOCADO, "New York", TS)["other_attributes"] == ""


def test_reporter_comment_distinguishes_rows():
    base = {**NY_AVOCADO, "commodity": "Carrots", "package": "cartons 10 5-lb film bags"}
    a = n.terminal({**base, "reporter_comment": "5lb. film bag orange"}, "New York", TS)
    b = n.terminal({**base, "reporter_comment": "5lb. film bag mixed color"}, "New York", TS)
    assert a["row_id"] != b["row_id"] and a["reporter_comment"] == "5lb. film bag orange"
    sp = n.shipping_point({"report_date": "09/25/2026", "commodity": "Carrots", "rep_cmt": "orange"}, TS)
    assert sp["reporter_comment"] == "orange"


def test_retail_names_and_greenhouse():
    raw = {"report_end_date": "09/25/2026", "slug_id": "3324", "commodity": "Peppers (Bell Type)",
           "variety": "Red", "region": "National", "size": "each", "wtd_avg_price": "1.33"}
    field = n.retail({**raw, "environment": "N/A"}, TS)
    house = n.retail({**raw, "environment": "Greenhouse", "wtd_avg_price": "1.00"}, TS)
    assert field["commodity"] == "Peppers, Bell Type"
    assert house["other_attributes"] == "environment=Greenhouse"
    assert field["row_id"] != house["row_id"]


def test_ground_beef_uses_trim_description():
    raw = {"report_date": "09/25/2026", "slug_id": "2453", "trim_description": "Ground Beef 81%",
           "price_range_low": "317.00", "price_range_high": "378.03", "weighted_average": "330.01"}
    [r] = n.beef(raw, "Ground Beef", TS)
    assert r["variety"] == "Ground Beef 81%"
    [r73] = n.beef({**raw, "trim_description": "Ground Beef 73%"}, "Ground Beef", TS)
    assert r73["row_id"] != r["row_id"]


def test_stored_row_id_is_stable():
    # This exact ID is in data/raw/terminal/2026/2026-09.csv. If a code change alters it, every
    # stored row would be re-keyed and the next fetch would duplicate them.
    assert n.terminal(NY_AVOCADO, "New York", TS)["row_id"] == "b4e70220a467564d"


def test_movement():
    raw = {"report_date": "09/25/2026", "slug_id": 3283, "commodity": "Avocados", "variety": "HASS",
           "district": "MEXICO CROSSINGS THROUGH PHARR TEXAS", "origin": "Mexico", "trans_Mode": "Truck",
           "import/Export": "I (import)", "organic": "No", "1 lb units": 2807816, "package": None}
    r = n.movement(raw, TS)
    assert r["volume"] == 2807816 and r["volume_unit"] == "lb" and r["market_type"] == "movement"
    assert r["market"] == "MEXICO CROSSINGS THROUGH PHARR TEXAS" and r["origin"] == "Mexico"
    assert "trans_Mode=Truck" in r["other_attributes"]
    boat = n.movement({**raw, "trans_Mode": "Boat"}, TS)
    assert boat["row_id"] != r["row_id"]
    assert n.movement({**raw, "1 lb units": None}, TS) is None


def test_chicken():
    raw = {"report_date": "09/21/2026", "slug_id": 3646, "item": "Breast - B/S", "region": "National",
           "trade_status": "Domestic", "condition": "Fresh", "low_price": "98.00", "high_price": "142.00",
           "wtd_avg_price": 122.14, "volume": 1790, "volume_traded_unit": "Pounds"}
    r = n.chicken(raw, TS)
    assert r["normalized_price"] == 1.2214 and r["price_unit"] == "cents/lb"
    assert r["variety"] == "Breast - B/S"
