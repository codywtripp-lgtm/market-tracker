"""Weekly shipment volumes per commodity, from the movement reports (data/raw/movement).

Several reports can carry the same crossing/port (USDA moved Mexico and Miami numbers into
the national report around 2024), so rows are de-duplicated on
(date, commodity, district, origin, variety, attributes) keeping the largest figure before summing.
"""

import numpy as np
import pandas as pd

from . import store

COLS = ["report_date", "commodity", "variety", "organic", "market", "origin", "other_attributes", "volume"]


def weekly():
    """DataFrame: commodity, week (Monday), volume_lb."""
    frames = [pd.read_csv(p, usecols=COLS, dtype=str, keep_default_na=False)
              for p in sorted((store.DATA / "raw" / "movement").glob("*/*.csv"))]
    if not frames:
        return pd.DataFrame(columns=["commodity", "week", "volume_lb"])
    df = pd.concat(frames, ignore_index=True)
    df["volume"] = pd.to_numeric(df["volume"], errors="coerce").fillna(0)
    key = ["report_date", "commodity", "variety", "organic", "market", "origin", "other_attributes"]
    df = df.groupby(key, as_index=False)["volume"].max()  # same shipment in two reports -> count once
    # late additions count toward the date they belong to ("asw=Add:09/18/2026")
    asw = df["other_attributes"].str.extract(r"asw=[^:;]*:(\d\d/\d\d/\d{4})")[0]
    effective = pd.to_datetime(asw, format="%m/%d/%Y", errors="coerce").fillna(pd.to_datetime(df["report_date"]))
    df["week"] = effective.dt.to_period("W-SUN").dt.start_time
    return df.groupby(["commodity", "week"], as_index=False)["volume"].sum().rename(columns={"volume": "volume_lb"})


def supply_features(vol):
    """Per commodity-week: supply vs the usual for this time of year (prior years), and recent change.

    supply_gap  log(this week's volume / average for the same weeks +/-2 in prior years)
    supply_chg  log(this week's volume / average of the previous 2 weeks)
    """
    out = []
    for c, g in vol.groupby("commodity"):
        g = g.set_index("week").sort_index().asfreq("7D").reset_index()
        g["commodity"] = c
        lv = np.log(g["volume_lb"].where(g["volume_lb"] > 0))
        iso = g["week"].dt.isocalendar()
        years, woy = iso["year"].to_numpy(), iso["week"].clip(upper=52).to_numpy()
        prior = np.full(len(g), np.nan)
        for i in range(len(g)):
            d = np.minimum(np.abs(woy - woy[i]), 52 - np.abs(woy - woy[i]))
            m = (years < years[i]) & (d <= 2) & lv.notna().to_numpy()
            if m.sum() >= 6:  # need a few prior-year weeks
                prior[i] = lv.to_numpy()[m].mean()
        g["supply_gap"] = lv - prior
        g["supply_chg"] = lv - np.log(g["volume_lb"].shift(1).add(g["volume_lb"].shift(2)).div(2).where(lambda s: s > 0))
        out.append(g[["commodity", "week", "supply_gap", "supply_chg"]])
    return pd.concat(out, ignore_index=True) if out else pd.DataFrame(columns=["commodity", "week", "supply_gap", "supply_chg"])
