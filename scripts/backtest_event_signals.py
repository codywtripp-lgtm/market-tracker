"""Do government event records improve the wholesale forecast? Walk-forward test against the live model.

Per commodity and week (data/raw/events, from scripts/fetch_events.py):
  recall    FDA recalls of the item reported in the last 4 weeks (log count; report_date, when it became public)
  serious   the same, Class I only
  trade     Federal Register tariff, antidumping or quarantine documents naming the item, last 4 weeks (log count)
  storm     NOAA crop damage in the item's main growing states, last 4 weeks (log dollars). NOAA publishes months late, so
            this is an upper bound: it uses information the live site would not have yet.

Bar to adopt: at least a 1% smaller average miss (forecast.MIN_GAIN), or clearly better calls in event weeks.

Run: python scripts/backtest_event_signals.py
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path[:0] = [str(Path(__file__).resolve().parents[1]), str(Path(__file__).resolve().parent)]
from backtest_wholesale_signals import score  # noqa: E402
from pipeline import forecast as fc, store  # noqa: E402

EV = store.DATA / "raw" / "events"
# main U.S. growing states (Mexico and other imports aren't in NOAA's records)
STATES = {"Avocados": ["California"], "Blueberries": ["Georgia", "Michigan", "New Jersey", "Washington", "Oregon", "Florida"],
          "Broccoli": ["California", "Arizona"], "Carrots": ["California", "Georgia", "Michigan"],
          "Celery": ["California", "Michigan", "Florida"], "Cucumbers": ["Florida", "Georgia", "Michigan", "North Carolina"],
          "Grapes": ["California"], "Lemons": ["California", "Arizona"], "Lettuce, Iceberg": ["California", "Arizona"],
          "Lettuce, Romaine": ["California", "Arizona"], "Onions, Dry": ["Idaho", "Oregon", "Washington", "California", "Texas"],
          "Peppers, Bell Type": ["California", "Florida", "Georgia"], "Potatoes": ["Idaho", "Washington", "Wisconsin", "Colorado", "North Dakota"],
          "Strawberries": ["California", "Florida"], "Tomatoes": ["Florida", "California", "Georgia", "Virginia", "Tennessee"],
          "Tomatoes, Plum Type": ["Florida", "California"]}


def weekly(df, date_col, value=None):
    """commodity x week totals, then the sum of the last 4 weeks."""
    df = df.copy()
    df["week"] = pd.to_datetime(df[date_col], errors="coerce").dt.to_period("W-SUN").dt.start_time
    df = df.dropna(subset=["week"])
    v = df.groupby(["commodity", "week"])[value].sum() if value else df.groupby(["commodity", "week"]).size()
    out = []
    for c, s in v.groupby(level=0):
        s = s.droplevel(0).asfreq("7D", fill_value=0)
        out.append(pd.DataFrame({"commodity": c, "week": s.index, "v": s.rolling(4, min_periods=1).sum().to_numpy()}))
    return pd.concat(out, ignore_index=True)


def events():
    fda = pd.read_csv(EV / "fda_recalls.csv", dtype=str, keep_default_na=False)
    fda["report_date"] = pd.to_datetime(fda["report_date"], format="%Y%m%d", errors="coerce")
    fda = fda.drop_duplicates()
    fr = pd.read_csv(EV / "federal_register.csv", dtype=str, keep_default_na=False)
    fr = fr[fr["commodity"] != "All imports"]
    no = pd.read_csv(EV / "noaa_crop_damage.csv")
    st = pd.DataFrame([(c, s) for c, ss in STATES.items() for s in ss], columns=["commodity", "state"])
    no = no.merge(st, on="state")
    parts = {"recall": weekly(fda, "report_date"), "serious": weekly(fda[fda["class"] == "Class I"], "report_date"),
             "trade": weekly(fr, "date"), "storm": weekly(no, "date", "crop_damage")}
    return {k: v.rename(columns={"v": k}) for k, v in parts.items()}


def main():
    panel = fc.add_hold_inputs(fc.add_seasonal(fc.add_drivers(fc.weekly_panel())))
    for name, d in events().items():
        panel = panel.merge(d, on=["commodity", "week"], how="left")
        panel[name] = np.log1p(panel[name].fillna(0))
    last = int(panel["year"].max())
    print("share of item-weeks with an event:", {k: round(float((panel[k] > 0).mean()), 3) for k in ("recall", "serious", "trade", "storm")})
    results = {"live model": score(panel, fc.BASE, "live model", last)}
    for name, extra in [("+ recalls", ["recall"]), ("+ serious recalls", ["serious"]), ("+ trade actions", ["trade"]),
                        ("+ storm crop damage (upper bound)", ["storm"]), ("+ all", ["recall", "serious", "trade", "storm"])]:
        score(panel, fc.BASE + extra, name, last)
    # what actually happens to prices after an event, compared with other weeks
    d = panel.dropna(subset=["y2"])
    for k in ("recall", "serious", "trade", "storm"):
        on, off = d[d[k] > 0]["y2"], d[d[k] == 0]["y2"]
        big = d[d[k] >= d.loc[d[k] > 0, k].quantile(0.9)]["y2"]
        print(f"{k:8s} 2-week change: with event {100 * on.mean():+.2f}% (n={len(on)}), biggest 10% {100 * big.mean():+.2f}% "
              f"(n={len(big)}), without {100 * off.mean():+.2f}% (n={len(off)})")


if __name__ == "__main__":
    main()
