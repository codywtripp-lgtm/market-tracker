import csv

from pipeline import normalize as n
from pipeline import store

TS1 = "2026-09-26T00:00:00+00:00"
TS2 = "2026-09-27T00:00:00+00:00"
RAW = {"report_date": "09/24/2026", "slug_id": "2314", "commodity": "Avocados", "variety": "HASS",
       "package": "cartons 2 layer", "item_size": "48s", "origin": "Mexico",
       "low_price": "32.00", "high_price": "33.00"}


def read(path):
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def test_upsert_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DATA", tmp_path)
    row = n.terminal(RAW, "New York", TS1)
    assert store.write_rows("terminal", [row]) == (1, 0)
    path = tmp_path / "raw" / "terminal" / "2026" / "2026-09.csv"
    before = path.read_text()

    # Same data fetched again the next day: no change, file untouched.
    assert store.write_rows("terminal", [n.terminal(RAW, "New York", TS2)]) == (0, 0)
    assert path.read_text() == before

    # USDA correction: same row, new price -> updated in place, no duplicate.
    assert store.write_rows("terminal", [n.terminal({**RAW, "low_price": "31.00"}, "New York", TS2)]) == (0, 1)
    rows = read(path)
    assert len(rows) == 1 and rows[0]["low_price"] == "31.0"


def test_partitions_by_month(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DATA", tmp_path)
    a = n.terminal(RAW, "New York", TS1)
    b = n.terminal({**RAW, "report_date": "10/01/2026"}, "New York", TS1)
    store.write_rows("terminal", [a, b])
    assert (tmp_path / "raw" / "terminal" / "2026" / "2026-09.csv").exists()
    assert (tmp_path / "raw" / "terminal" / "2026" / "2026-10.csv").exists()
