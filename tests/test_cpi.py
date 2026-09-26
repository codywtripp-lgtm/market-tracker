import csv
import datetime as dt

from pipeline import cpi, export
from tests.test_export import TODAY, avocado


def test_deflator_factors():
    d = cpi.Deflator({"2020-01": 100.0, "2020-02": 110.0, "2026-08": 200.0})
    assert d.base_month == "2026-08"
    assert d.factor("2020-01-15") == 2.0
    assert d.factor("2026-09-25") == 1.0      # newer than latest CPI release
    assert d.factor("2020-03-01") == 200 / 110  # gap: use latest earlier month
    assert d.factor("2019-12-01") == 2.0      # before series: earliest month
    assert cpi.Deflator({}).factor("2020-01-01") == 1.0


def test_price_that_only_kept_up_with_inflation_is_normal(tmp_path, monkeypatch):
    monkeypatch.setattr(export, "EXPORT", tmp_path)
    # CPI rises ~5%/year (monthly steps); the avocado price moves exactly with it.
    values, rows = {}, []
    start = TODAY - dt.timedelta(days=4 * 365)
    d = start
    while d <= TODAY:
        month = d.strftime("%Y-%m")
        if month not in values:
            values[month] = 100 * 1.05 ** ((d - start).days / 365)
        if d.weekday() < 5:
            rows.append(avocado(d, 40 * values[month] / 100))
        d += dt.timedelta(days=1)
    export.build(rows, today=TODAY, deflator=cpi.Deflator(values))
    with open(tmp_path / "latest.csv", newline="") as f:
        [latest] = list(csv.DictReader(f))
    assert latest["status"] == "normal"
    assert abs(float(latest["pct_vs_norm"])) < 5
    # Without adjustment the same data looks expensive.
    export.build(rows, today=TODAY)
    with open(tmp_path / "latest.csv", newline="") as f:
        [nominal] = list(csv.DictReader(f))
    assert nominal["status"] == "expensive"
