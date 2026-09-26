import datetime as dt
import json

from pipeline import alerts, store
from pipeline import normalize as n

TS = "2026-09-26T00:00:00+00:00"
TODAY = dt.date(2026, 9, 25)
RULES = """signal,commodity,market,direction,horizon_weeks,cases,hits,hit_rate,base_rate
sp_lead,Celery,New York,up,2,30,26,0.867,0.32
sp_lead,Cucumbers,New York,up,2,70,33,0.471,0.311
usda_tone,Romaine,New York,up,1,10,9,0.9,0.3
"""


def celery(d, price, sp=False, tone=""):
    raw = {"report_date": d.strftime("%m/%d/%Y"), "slug_id": "2403" if sp else "2315", "commodity": "Celery",
           "package": "cartons", "item_size": "2 dozen", "low_price": str(price), "high_price": str(price),
           "market_tone_comments": tone}
    if sp:
        return n.shipping_point({**raw, "pkg": "cartons", "district": "SALINAS-WATSONVILLE CALIFORNIA"}, TS)
    return n.terminal({**raw, "origin": "California"}, "New York", TS)


def setup(tmp_path, monkeypatch, sp_now, ny_now, tone=""):
    monkeypatch.setattr(store, "DATA", tmp_path / "data")
    monkeypatch.setattr(alerts, "RULES", tmp_path / "data" / "signals" / "rules.csv")
    monkeypatch.setattr(alerts, "LOG", tmp_path / "data" / "alerts" / "log.csv")
    monkeypatch.setattr(alerts, "OUT_JSON", tmp_path / "data" / "export" / "alerts.json")
    monkeypatch.setattr(alerts, "NEW_MD", tmp_path / "new_alerts.md")
    (tmp_path / "data" / "signals").mkdir(parents=True)
    (tmp_path / "data" / "signals" / "rules.csv").write_text(RULES)
    term, ship = [], []
    for back in range(14):
        d = TODAY - dt.timedelta(days=back)
        recent = back < 7
        ship.append(celery(d, sp_now if recent else 20, sp=True))
        term.append(celery(d, ny_now if recent else 30, tone=tone if recent else ""))
    store.write_rows("terminal", term)
    store.write_rows("shipping_point", ship)


def test_fires_when_shipping_point_moved_and_ny_has_not(tmp_path, monkeypatch):
    setup(tmp_path, monkeypatch, sp_now=25, ny_now=30.3)
    alerts.main(today=TODAY)
    out = json.loads((tmp_path / "data" / "export" / "alerts.json").read_text())
    [a] = out["alerts"]
    assert a["commodity"] == "Celery" and a["market"] == "New York" and a["direction"] == "up"
    assert "26 of the last 30" in a["record"]
    assert (tmp_path / "new_alerts.md").exists()

    # Same signal the next day: still shown, but not re-sent.
    alerts.main(today=TODAY + dt.timedelta(days=1))
    assert not (tmp_path / "new_alerts.md").exists()


def test_no_alert_when_ny_already_moved(tmp_path, monkeypatch):
    setup(tmp_path, monkeypatch, sp_now=25, ny_now=34)
    alerts.main(today=TODAY)
    assert json.loads((tmp_path / "data" / "export" / "alerts.json").read_text())["alerts"] == []


def test_no_alert_for_small_move(tmp_path, monkeypatch):
    setup(tmp_path, monkeypatch, sp_now=21, ny_now=30)
    alerts.main(today=TODAY)
    assert json.loads((tmp_path / "data" / "export" / "alerts.json").read_text())["alerts"] == []


def test_weak_or_thin_rules_never_alert(tmp_path, monkeypatch):
    monkeypatch.setattr(alerts, "RULES", tmp_path / "rules.csv")
    (tmp_path / "rules.csv").write_text(RULES)
    rules = alerts.load_rules()
    assert ("sp_lead", "Celery", "New York", "up") in rules
    assert ("sp_lead", "Cucumbers", "New York", "up") not in rules   # 47% hit rate: too weak
    assert ("usda_tone", "Romaine", "New York", "up") not in rules   # only 10 cases: too thin


def test_tone_alert_quotes_a_matching_comment(tmp_path, monkeypatch):
    setup(tmp_path, monkeypatch, sp_now=20, ny_now=30)
    (tmp_path / "data" / "signals" / "rules.csv").write_text(RULES + "usda_tone,Celery,New York,down,1,40,30,0.75,0.3\n")
    days = [TODAY - dt.timedelta(days=b) for b in range(4)]
    tones = ["MARKET LOWER", "MARKET LOWER", "MARKET SLIGHTLY LOWER", "MARKET ABOUT STEADY"]
    store.write_rows("terminal", [celery(d, 30, tone=t) for d, t in zip(days, tones)])
    alerts.main(today=TODAY)
    [a] = json.loads((tmp_path / "data" / "export" / "alerts.json").read_text())["alerts"]
    assert a["signal"] == "usda_tone" and a["direction"] == "down"
    assert "Steady" not in a["headline"] and "Market lower" in a["headline"]


def test_tone_scoring():
    assert alerts.tone_score("MARKET SLIGHTLY HIGHER") == 1
    assert alerts.tone_score("Lower") == -1
    assert alerts.tone_score("MARKET ABOUT STEADY") == 0
    assert alerts.tone_score("Red Lower, others slightly higher") == 0
    assert alerts.tone_score("") is None
