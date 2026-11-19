import datetime as dt
import io
import zipfile

from pipeline import board, downloads


def item(**kw):
    i = {"series_id": "s1", "commodity": "Avocados", "market": "New York", "pack": "Hass, cartons 2 layer, 48s",
         "price": 41.0, "status": "normal", "usual_low": 35.0, "usual_high": 55.0, "vs_norm": -12.3, "dir": "firming",
         "range": (40, 50), "change": 0.1,
         "quote": {"date": dt.date(2026, 11, 18), "area": "Mexico", "lot": "", "low": 40.0, "high": 42.0,
                   "mostly_low": None, "mostly_high": None, "other_lots": [], "areas": [("Mexico", 40.0, 42.0), ("California", 50.0, 50.0)]}}
    i.update(kw)
    return i


def test_csv_row_uses_the_page_numbers_and_words():
    text = board.download_tables([item()], {"s1": 0.05})["New York"]
    assert text.startswith("﻿")
    header, rows = downloads.read_csv(_tmp(text))
    row = dict(zip(header, rows[0]))
    assert row["Case price ($)"] == 41.0 and row["Low ($)"] == 40.0 and row["High ($)"] == 42.0
    assert row["Change from previous quote (%)"] == 5.0
    assert row["For the season"] == "Normal for the season" and row["Next 2 weeks"] == "Firming"
    assert row["Expected price in 2 weeks ($)"] == 45.1
    assert row["Other areas quoted that day"] == "California: 50.00"


def test_no_forecast_and_new_area():
    text = board.download_tables([item(range=None, change=None)], {"s1": board.NEW_AREA})["New York"]
    header, rows = downloads.read_csv(_tmp(text))
    row = dict(zip(header, rows[0]))
    assert row["Next 2 weeks"] == "No forecast" and row["Expected price in 2 weeks ($)"] == ""
    assert row["Change from previous quote (%)"] == "New growing area"


def test_workbook_has_a_tab_per_market_and_about(tmp_path):
    for m in ("New York", "Chicago"):
        (tmp_path / downloads.file_name(board.MARKET_SLUG[m])).write_text(
            board.download_tables([item(market=m)], {})[m], encoding="utf-8", newline="")
    book = downloads.workbook([(board.MARKET_LONG[m], board.MARKET_SLUG[m]) for m in board.MARKETS], tmp_path, dt.date(2026, 11, 18))
    z = zipfile.ZipFile(io.BytesIO(book))
    wb = z.read("xl/workbook.xml").decode()
    assert 'name="New York (Hunts Point)"' in wb and 'name="Chicago"' in wb and 'name="About this data"' in wb
    assert 'name="Miami"' not in wb  # no CSV, no tab
    sheet = z.read("xl/worksheets/sheet1.xml").decode()
    assert "<v>41</v>" in sheet and "Avocados" in sheet and 'state="frozen"' in sheet


def test_market_page_links_are_counted():
    html = board.download_links("Los Angeles")
    assert 'href="@/downloads/terminal-market-prices.xlsx"' in html
    assert 'href="@/downloads/terminal-market-prices-los-angeles.csv"' in html
    assert html.count("data-goatcounter-click=") == 2


_n = [0]


def _tmp(text):
    import tempfile
    from pathlib import Path
    _n[0] += 1
    p = Path(tempfile.mkdtemp()) / f"t{_n[0]}.csv"
    p.write_text(text, encoding="utf-8", newline="")
    return p
