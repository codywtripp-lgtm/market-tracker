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
    assert latest["compare_unit"] == "per each"
    assert float(latest["compare_price"]) == round(30 / 48, 4)
    assert float(latest["seasonal_norm"]) == round(40 / 48, 4)


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
