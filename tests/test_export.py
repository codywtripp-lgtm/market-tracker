import csv
import datetime as dt

from pipeline import export
from pipeline import normalize as n

TS = "2026-09-26T00:00:00+00:00"
TODAY = dt.date(2026, 9, 25)


def avocado(d, price, appearance="N/A", size="48s"):
    return n.terminal({
        "report_date": d.strftime("%m/%d/%Y"), "slug_id": "2314", "commodity": "Avocados", "variety": "HASS",
        "package": "cartons 2 layer", "item_size": size, "origin": "Mexico", "appearance": appearance,
        "low_price": str(price), "high_price": str(price)}, "New York", TS)


def history(last_price):
    """Four years of weekday quotes at $40, then a final week at last_price."""
    rows = []
    d = TODAY - dt.timedelta(days=4 * 365)
    while d <= TODAY:
        if d.weekday() < 5:
            price = last_price if (TODAY - d).days < 5 else 40
            rows.append(avocado(d, price))
            rows.append(avocado(d, 5, appearance="Fair Appearance"))  # distressed: must be ignored
        d += dt.timedelta(days=1)
    return rows


def read(path):
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def test_cheap_week_is_flagged(tmp_path, monkeypatch):
    monkeypatch.setattr(export, "EXPORT", tmp_path)
    counts = export.build(history(last_price=30), today=TODAY)
    assert counts["series"] == 1
    [latest] = read(tmp_path / "latest.csv")
    assert latest["status"] == "cheap"
    # quoted per case, like the trade does (not per avocado)
    assert latest["compare_unit"] == "$/package"
    assert float(latest["compare_price"]) == 30
    assert float(latest["seasonal_norm"]) == 40


def test_distressed_rows_excluded(tmp_path, monkeypatch):
    monkeypatch.setattr(export, "EXPORT", tmp_path)
    export.build(history(last_price=40), today=TODAY)
    daily = read(tmp_path / "prices_daily_365.csv")
    assert {float(r["price"]) for r in daily} == {40.0}
    [latest] = read(tmp_path / "latest.csv")
    assert latest["status"] == "normal"


def test_short_history_has_no_norm(tmp_path, monkeypatch):
    monkeypatch.setattr(export, "EXPORT", tmp_path)
    rows = [r for r in history(40) if r["report_date"] >= "2025-10-01"]
    export.build(rows, today=TODAY)
    [latest] = read(tmp_path / "latest.csv")
    assert latest["status"] == "not enough history"


def test_rarely_reported_series_dropped(tmp_path, monkeypatch):
    monkeypatch.setattr(export, "EXPORT", tmp_path)
    rows = history(40) + [avocado(TODAY - dt.timedelta(days=3), 50, size="84s")]
    export.build(rows, today=TODAY)
    assert [r["item_size"] for r in read(tmp_path / "series.csv")] == ["48s"]


def test_main_trade_pack_beats_better_covered_specialty():
    """Yellow jumbo 50 lb onions are the headline even though pearl onions are quoted more often,
    and the onion types USDA splits them into are merged into one series."""
    pearl = ("terminal", "New York", "Onions, Dry", "PEARL TYPE", "cartons 12 10-oz packages", "small", "YELLOW", "N")
    assert not export.is_main_pack(pearl)
    row = {"market_type": "terminal", "market": "New York", "commodity": "Onions, Dry", "variety": "YELLOW",
           "pack_size": "50 lb sacks", "item_size": "jumbo", "organic": "N"}
    keys = {export.series_key({**row, "properties": p}) for p in ("HYBRID", "SPANISH HYBRID", "GRANO")}
    [key] = keys
    assert export.is_main_pack(key)
    dates = [f"2026-09-{d:02d}" for d in range(1, 26)]
    grouped = {pearl: {d: [{}] for d in dates}, key: {d: [{}] for d in dates[::2]}}
    chosen = export.select(grouped, TODAY)
    assert next(iter(chosen)) == key


def test_organic_is_not_the_headline():
    org = ("terminal", "Chicago", "Lettuce, Iceberg", "", "cartons", "24s film wrapped", "", "Y")
    conv = org[:7] + ("N",)
    assert export.is_main_pack(conv) and not export.is_main_pack(org)


def test_market_can_have_its_own_main_pack():
    la = ("terminal", "Los Angeles", "Tomatoes", "VINE RIPES", "cartons 2 layer", "5x5s", "Light Red-red", "No")
    ny = ("terminal", "New York", "Tomatoes", "VINE RIPES", "cartons 2 layer", "5x5s", "Light Red-red", "No")
    assert export.is_main_pack(la) and not export.is_main_pack(ny)


def test_a_pack_usda_stopped_quoting_is_not_the_headline():
    today = dt.date(2026, 11, 1)
    days = [(today - dt.timedelta(days=d)).isoformat() for d in range(1, 300)]
    old = ("terminal", "Los Angeles", "Bananas", "", "40 lb cartons containerized", "", "", "No")
    new = ("terminal", "Los Angeles", "Bananas", "", "40 lb cartons", "", "", "No")
    baby = ("terminal", "Los Angeles", "Bananas", "BABY", "15 lb cartons", "", "", "No")
    grouped = {old: {d: [{}] for d in days[100:]}, new: {d: [{}] for d in days[:120]}, baby: {d: [{}] for d in days}}
    assert next(iter(export.select(grouped, today))) == new


def _quote(area, price):
    return {"origin": area, "unit_price": str(price), "low_price": str(price), "high_price": str(price),
            "normalized_price": "", "mostly_low_price": "", "mostly_high_price": "", "market_tone": ""}


def test_price_follows_the_main_growing_area_not_a_median_across_areas():
    days = {f"2026-10-{d:02d}": [_quote("California", 60)] for d in range(20, 31)}
    days["2026-11-03"] = [_quote("California", 60), _quote("New Jersey", 41), _quote("Canada", 41)]
    assert export.main_areas(days)["2026-11-03"] == "California"
    v = export.daily_value(days["2026-11-03"], "California")
    assert v["price"] == 60 and v["area"] == "California"
    assert v["areas"] == "California:60.0:60.0;Canada:41.0:41.0;New Jersey:41.0:41.0"
    assert export.daily_value(days["2026-11-03"])["price"] == 41  # what the blend used to say


def test_a_new_area_takes_over_once_the_old_one_stops_quoting():
    days = {"2026-10-01": [_quote("California", 60)], "2026-10-02": [_quote("Mexico", 40)]}
    assert export.main_areas(days)["2026-10-02"] == "Mexico"


def test_a_one_price_quote_with_no_high_still_counts_in_the_range():
    one = dict(_quote("California", 36), high_price="")
    v = export.daily_value([one, dict(_quote("California", 25.5), low_price="25", high_price="26")], "California")
    assert (v["low"], v["high"], v["price"]) == (25, 36, 30.75)


def test_areas_quoted_equally_go_to_the_most_pounds_shipped():
    day = "2026-11-03"
    days = {day: [_quote("California", 25), _quote("Idaho-Oregon", 24), _quote("Washington", 23)]}
    shipments = {("Onions", dt.date(2026, 10, 26), "Washington"): 900, ("Onions", dt.date(2026, 10, 26), "Idaho"): 600,
                 ("Onions", dt.date(2026, 10, 26), "Oregon"): 500, ("Onions", dt.date(2026, 11, 2), "California"): 9999}
    shipped = lambda area, d: export.shipped_before(shipments, "Onions", area, d)  # noqa: E731
    assert export.main_areas(days, shipped)[day] == "Idaho-Oregon"  # this week's California pounds aren't known yet


def test_tied_area_missing_from_movement_reports_wins_when_quoted_most_over_the_year():
    days = {f"2026-01-{d:02d}": [_quote("California", 22)] for d in range(1, 11)}
    days.update({f"2026-10-{d:02d}": [_quote("California", 22), _quote("Canada", 13)] for d in range(1, 11)})
    shipped = lambda area, d: {"Canada": 900}.get(area, 0)  # noqa: E731
    assert export.main_areas(days, shipped)["2026-10-10"] == "California"


def test_tied_area_with_no_pounds_stays_out_when_not_quoted_most_over_the_year():
    days = {f"2026-01-{d:02d}": [_quote("Idaho", 24)] for d in range(1, 11)}
    days.update({f"2026-10-{d:02d}": [_quote("Idaho", 24), _quote("Nevada", 19)] for d in range(1, 11)})
    shipped = lambda area, d: {"Idaho": 900}.get(area, 0)  # noqa: E731
    assert export.main_areas(days, shipped)["2026-10-10"] == "Idaho"


def test_18_and_19_lb_grape_containers_are_one_series():
    row = {"market_type": "terminal", "market": "New York", "commodity": "Grapes", "variety": "WHITE SEEDLESS TYPE",
           "item_size": "extra large", "properties": "", "organic": "N"}
    keys = {export.series_key({**row, "pack_size": f"{n} lb containers bagged"}) for n in (18, 19)}
    assert len(keys) == 1 and export.is_main_pack(next(iter(keys)))
    assert export.series_key({**row, "pack_size": "19 lb lugs bagged"}) not in keys


def _terminal(**kw):
    row = {"market_type": "terminal", "market": "New York", "commodity": "Corn, Sweet", "variety": "", "pack_size": "wirebound crates",
           "item_size": "4 dozen", "properties": "", "organic": "N"}
    return {**row, **kw}


def test_usda_label_changes_stay_one_series():
    old = _terminal(variety="YELLOW", item_size="4 dozen minimum")
    new = _terminal(properties="YELLOW", pack_size="cartons/crates")
    assert export.series_key(old) == export.series_key(new)
    assert export.is_main_pack(export.series_key(new))


def test_cauliflower_with_no_color_stated_is_white_but_colors_stay_apart():
    white = dict(commodity="Cauliflower", pack_size="flat cartons film wrapped", item_size="12s film wrapped")
    assert export.series_key(_terminal(**white)) == export.series_key(_terminal(**white, properties="White"))
    assert export.series_key(_terminal(**white, properties="Purple")) != export.series_key(_terminal(**white))


def _graded(grade, price, day="2026-11-03"):
    return {"origin": "California", "grade": grade, "properties": "", "origin_detail": "", "unit_price": str(price), "report_date": day}


def test_two_grades_the_same_day_price_the_main_one_not_the_midpoint():
    by_day = {"2026-10-30": [_graded("Shippers First Grade", 39)], "2026-11-02": [_graded("Shippers First Grade", 39)],
              "2026-11-03": [_graded("Shippers First Grade", 39), _graded("Shippers Choice", 32)]}
    lots = export.main_lots(by_day, dict.fromkeys(by_day, "California"))
    assert lots["2026-11-03"][0] == "Shippers First Grade"


def test_the_standard_grade_wins_even_when_the_lower_one_is_quoted_more():
    by_day = {"2026-10-30": [_graded("Shippers Choice", 32)], "2026-11-02": [_graded("Shippers Choice", 32)],
              "2026-11-03": [_graded("Shippers Choice", 32), _graded("Shippers First Grade", 39)]}
    lots = export.main_lots(by_day, dict.fromkeys(by_day, "California"))
    assert lots["2026-11-02"][0] == "Shippers Choice" and lots["2026-11-03"][0] == "Shippers First Grade"
