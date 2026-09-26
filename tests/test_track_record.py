import datetime as dt
import json

import pandas as pd

from pipeline import track_record as tr


def setup(tmp_path, monkeypatch):
    exp = tmp_path / "export"
    exp.mkdir()
    monkeypatch.setattr(tr, "EXPORT", exp)
    monkeypatch.setattr(tr, "FC_LOG", tmp_path / "forecasts" / "log.csv")
    monkeypatch.setattr(tr, "ALERT_LOG", tmp_path / "alerts" / "log.csv")
    pd.DataFrame([{"series_id": "s1", "commodity": "Celery", "market": "New York"}]).to_csv(exp / "series.csv", index=False)
    (exp / "forecasts.json").write_text(json.dumps({"coverage_backtest": 0.801, "series": {"s1": {
        "from_week": "2026-09-21", "from_price": 30.0,
        "points": [{"h": 1, "week": "2026-09-28", "lo": 28, "mid": 33, "hi": 38},
                   {"h": 2, "week": "2026-10-05", "lo": 27, "mid": 34, "hi": 41}]}}}))
    return exp


def test_forecasts_logged_then_scored(tmp_path, monkeypatch):
    exp = setup(tmp_path, monkeypatch)
    tr.log_forecasts(dt.date(2026, 9, 26))
    tr.log_forecasts(dt.date(2026, 9, 26))  # same week again: no duplicates
    assert len(pd.read_csv(tr.FC_LOG)) == 2

    pd.DataFrame([{"series_id": "s1", "week_start": "2026-09-28", "compare_price": 35.0},
                  {"series_id": "s1", "week_start": "2026-10-05", "compare_price": 50.0}]).to_csv(exp / "prices_weekly.csv", index=False)
    # On Oct 7 only the Sep 28 week is complete
    s = tr.score_forecasts(dt.date(2026, 10, 7))
    assert len(s) == 1
    row = s.iloc[0]
    assert bool(row["in_range"]) is True
    assert round(row["miss_pct"], 1) == round(abs(33 / 35 - 1) * 100, 1)
    assert round(row["no_change_miss_pct"], 1) == round(abs(30 / 35 - 1) * 100, 1)
    # Later both are scored; the $50 week fell outside the $27-41 range
    s = tr.score_forecasts(dt.date(2026, 10, 14))
    assert list(s.sort_values("h")["in_range"]) == [True, False]
