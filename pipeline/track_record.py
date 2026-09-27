"""Public track record: how our live forecasts and alerts actually turned out.

    python -m pipeline.track_record      # run nightly after forecast + alerts

1. Logs tonight's forecasts to data/forecasts/log.csv (one row per series, starting week and
   horizon; a later run in the same week replaces the earlier one, since the week's price
   was still filling in).
2. Scores every logged forecast whose target week is complete: was the actual price inside
   the 80% range, how far off was the middle, and how far off would "no change" have been.
3. Scores every alert in data/alerts/log.csv whose window has passed: did the terminal price
   move >= 5% the called way (2 weeks for shipping-point alerts, 1 week for USDA-call alerts)?
4. Writes data/export/track_record.json for the website, alongside the 2021-2026 backtest
   figures (clearly labelled as backtest, not live).
"""

import datetime as dt
import json
import math

import pandas as pd

from . import signals, store

EXPORT = store.DATA / "export"
FC_LOG = store.DATA / "forecasts" / "log.csv"
ALERT_LOG = store.DATA / "alerts" / "log.csv"
FOLLOW = 0.05
ALERT_WEEKS = {"sp_lead": 2, "usda_tone": 1}
FC_COLS = ["made_on", "series_id", "commodity", "market", "from_week", "from_price", "h", "target_week", "lo", "mid", "hi"]


def week_start(d):
    return d - dt.timedelta(days=d.weekday())


def log_forecasts(today):
    path = EXPORT / "forecasts.json"
    if not path.exists():
        return
    fc = json.loads(path.read_text())
    series = pd.read_csv(EXPORT / "series.csv", dtype=str).set_index("series_id")
    rows = []
    for sid, s in fc["series"].items():
        meta = series.loc[sid] if sid in series.index else {}
        for p in s["points"]:
            rows.append({"made_on": today.isoformat(), "series_id": sid, "commodity": meta.get("commodity", ""),
                         "market": meta.get("market", ""), "from_week": s["from_week"], "from_price": s["from_price"],
                         "h": p["h"], "target_week": p["week"], "lo": p["lo"], "mid": p["mid"], "hi": p["hi"]})
    new = pd.DataFrame(rows, columns=FC_COLS)
    old = pd.read_csv(FC_LOG, dtype={"series_id": str}) if FC_LOG.exists() else pd.DataFrame(columns=FC_COLS)
    log = pd.concat([old, new]).drop_duplicates(["series_id", "from_week", "h"], keep="last")
    FC_LOG.parent.mkdir(parents=True, exist_ok=True)
    log.sort_values(["from_week", "series_id", "h"]).to_csv(FC_LOG, index=False, lineterminator="\n")


def score_forecasts(today):
    if not FC_LOG.exists():
        return pd.DataFrame()
    log = pd.read_csv(FC_LOG, dtype={"series_id": str})
    actual = pd.read_csv(EXPORT / "prices_weekly.csv", dtype={"series_id": str})[["series_id", "week_start", "compare_price"]]
    done = log[log["target_week"] < week_start(today).isoformat()]  # target week complete
    s = done.merge(actual, left_on=["series_id", "target_week"], right_on=["series_id", "week_start"], how="inner")
    if s.empty:
        return s
    s["in_range"] = (s["compare_price"] >= s["lo"]) & (s["compare_price"] <= s["hi"])
    s["miss_pct"] = (s["mid"] / s["compare_price"] - 1).abs() * 100
    s["no_change_miss_pct"] = (s["from_price"] / s["compare_price"] - 1).abs() * 100
    return s


def score_alerts(today):
    if not ALERT_LOG.exists():
        return pd.DataFrame()
    alerts = pd.read_csv(ALERT_LOG, dtype=str, keep_default_na=False)
    if alerts.empty:
        return alerts
    since = (pd.to_datetime(alerts["first_seen"]).min() - pd.Timedelta(days=14)).date().isoformat()
    term = signals.load("terminal", since=since)
    chg = signals.index_changes(term)  # (commodity, market, week) -> weekly log change
    this_week = pd.Timestamp(week_start(today))
    out = []
    for a in alerts.itertuples():
        weeks = ALERT_WEEKS.get(a.signal, 1)
        w0 = pd.Timestamp(week_start(dt.date.fromisoformat(a.first_seen)))
        after = [w0 + pd.Timedelta(weeks=k) for k in range(1, weeks + 1)]
        status, moved = "pending", None
        if after[-1] < this_week:  # window complete
            vals = [chg.get((a.commodity, a.market, w)) for w in after]
            vals = [v for v in vals if v is not None and not math.isnan(v)]
            # "came true" if at any point in the window the cumulative move reached 5% the called way
            path, total = [], 0.0
            for v in vals:
                total += v
                path.append(total)
            if path:
                best = max(path) if a.direction == "up" else min(path)
                moved = round((math.exp(best) - 1) * 100, 1)
                hit = best >= math.log(1 + FOLLOW) if a.direction == "up" else best <= math.log(1 - FOLLOW)
                status = "came true" if hit else "did not happen"
            else:
                status = "no data"
        out.append({"first_seen": a.first_seen, "commodity": a.commodity, "market": a.market,
                    "direction": a.direction, "signal": a.signal, "headline": a.headline,
                    "status": status, "moved_pct": moved})
    return pd.DataFrame(out)


def backtest_summary():
    path = EXPORT / "forecast_backtest.csv"
    if not path.exists():
        return {}
    b = pd.read_csv(path)
    fc = json.loads((EXPORT / "forecasts.json").read_text()) if (EXPORT / "forecasts.json").exists() else {}
    rows = {}
    for h in (1, 2, 3, 4):
        g = b[b["horizon"] == h].set_index("method")["mae_pct"]
        if "per_item" in g and "naive" in g:
            rows[str(h)] = {"miss_pct": round(g["per_item"], 1), "no_change_miss_pct": round(g["naive"], 1)}
    return {"years": "2021-2026", "by_horizon": rows, "range_coverage_pct": round(100 * fc.get("coverage_backtest", float("nan")), 1)}


def main(today=None):
    today = today or dt.date.today()
    log_forecasts(today)
    f = score_forecasts(today)
    a = score_alerts(today)
    live = {}
    if not f.empty:
        live = {"scored": int(len(f)), "since": f["from_week"].min(),
                "in_range_pct": round(100 * f["in_range"].mean(), 1),
                "miss_pct": round(f["miss_pct"].mean(), 1),
                "no_change_miss_pct": round(f["no_change_miss_pct"].mean(), 1)}
    alerts = {}
    if not a.empty:
        decided = a[a["status"].isin(["came true", "did not happen"])]
        alerts = {"issued": int(len(a)), "decided": int(len(decided)),
                  "came_true": int((decided["status"] == "came true").sum()),
                  "pending": int((a["status"] == "pending").sum()),
                  "recent": a.sort_values("first_seen", ascending=False).head(20).to_dict("records")}
    out = {"asOf": today.isoformat(), "forecasts_live": live, "forecasts_backtest": backtest_summary(), "alerts": alerts}
    (EXPORT / "track_record.json").write_text(json.dumps(out, indent=1, default=str))
    print(json.dumps({k: v for k, v in out.items() if k != "alerts"} | {"alerts": {k: v for k, v in alerts.items() if k != "recent"}}, default=str))


if __name__ == "__main__":
    main()
