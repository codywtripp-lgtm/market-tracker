"""Every wholesale price on the site has to trace back to USDA's own rows. These read the real data files."""

import csv
import glob
import statistics

import pytest

from pipeline import board, brief, export, store


def _latest():
    rows = brief._read("latest.csv")
    if not rows or "last_price" not in rows[0]:
        pytest.skip("export has no latest-quote columns yet")
    return rows


def _recent_rows():
    for path in sorted(glob.glob(str(store.DATA / "raw" / "terminal" / "*" / "*.csv")))[-3:]:
        with open(path, newline="", encoding="utf-8") as f:
            yield from csv.DictReader(f)


def _headlines(latest):
    series = {r["series_id"]: r for r in brief._read("series.csv")}
    return [r for r in latest if r["market_type"] == "terminal" and series.get(r["series_id"], {}).get("headline") == "Y"]


def test_each_headline_price_is_the_median_usda_row_from_its_main_area():
    latest = _headlines(_latest())
    grouped = export.load(_recent_rows())
    by_id = {export.series_id(k): v for k, v in grouped.items()}
    checked = 0
    for r in latest:
        days = by_id.get(r["series_id"])
        if not days or r["last_date"] not in days:
            continue
        rows = [x for x in days[r["last_date"]] if x["origin"] == r["area"]]
        assert rows, (r["series_id"], r["area"], r["last_date"])
        assert float(r["last_price"]) == pytest.approx(statistics.median(float(x["unit_price"]) for x in rows))
        checked += 1
    assert checked >= 40


def test_the_price_shown_sits_inside_usdas_range_for_that_day():
    wanted = {r["series_id"] for r in _headlines(_latest())}
    last = {}
    for r in brief._read("prices_daily_365.csv"):
        if r["series_id"] in wanted:
            last[r["series_id"]] = r
    for r in last.values():
        price, low, high = (brief._num(r[k]) for k in ("compare_price", "low", "high"))
        if low and high:
            assert low <= price <= high, r["series_id"]


def test_pages_show_the_latest_quote_and_measure_the_forecast_from_it():
    latest = {r["series_id"]: r for r in _headlines(_latest())}
    series = {r["series_id"]: r for r in brief._read("series.csv")}
    forecasts = brief._json("forecasts.json", {}).get("series", {})
    card = {(r["commodity"], r["market"]): r for r in brief._read("forecast_report_card.csv")}
    items = [i for i in brief.headline_items(list(latest.values()), series, forecasts, card) if i["commodity"] in board.PAGES]
    _, out = board.build()
    for i in items:
        assert i["price"] == float(latest[i["series_id"]]["last_price"])
        assert board.money(i["price"]) in out[f"market-{board.MKEY[i['market']]}"], (i["commodity"], i["market"])
        if i["range"] and i["change"] and not i["stable"]:
            two = next(p for p in i["points"] if p["h"] == 2)
            assert i["price"] * (1 + i["change"]) == pytest.approx(two["mid"], abs=0.01)
