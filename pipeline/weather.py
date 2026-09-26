"""Daily weather at the main growing regions, and weekly weather-stress signals per commodity.

    python -m pipeline.weather            # fetch/refresh (full history on first run, then last ~3 weeks)

Source: Open-Meteo (https://open-meteo.com) — ERA5-based historical archive plus recent days.
Free, no key, **non-commercial use**; data CC BY 4.0 (attribution: "Weather data by Open-Meteo.com").
A commercial product would need their paid plan (or NOAA for US-only regions).

Stored: data/raw/weather/<region>.csv  (date, tmax_c, tmin_c, precip_mm)
"""

import datetime as dt
import logging
import time

import numpy as np
import pandas as pd
import requests

from . import store

log = logging.getLogger(__name__)
ARCHIVE = "https://archive-api.open-meteo.com/v1/archive"
RECENT = "https://api.open-meteo.com/v1/forecast"
DAILY = "temperature_2m_max,temperature_2m_min,precipitation_sum"
FIRST_DATE = dt.date(2015, 1, 1)
WEATHER = store.DATA / "raw" / "weather"

# Growing regions (approximate center of production)
REGIONS = {
    "salinas": (36.68, -121.66), "santa_maria": (34.95, -120.43), "oxnard": (34.20, -119.18),
    "san_joaquin": (36.74, -119.79), "kern": (35.37, -119.02), "imperial": (32.79, -115.56),
    "yuma": (32.69, -114.63), "coachella": (33.68, -116.17), "michoacan": (19.41, -102.06),
    "sinaloa": (24.80, -107.39), "sonora": (29.07, -110.96), "veracruz": (20.07, -97.06),
    "jalisco": (20.66, -103.35), "baja": (30.55, -115.94), "immokalee_fl": (26.42, -81.42),
    "plant_city_fl": (28.02, -82.12), "south_georgia": (31.45, -83.51), "idaho_oregon": (43.79, -116.94),
    "columbia_basin": (46.30, -119.30), "leamington_on": (42.05, -82.60), "guatemala": (15.70, -88.60),
    "ecuador": (-1.80, -79.50), "central_chile": (-34.00, -71.00), "peru_north": (-8.10, -79.00),
    "michigan": (42.30, -86.20),
}

# Commodity -> [(region, months it's an important source)]. Industry-typical seasons; the
# weekly signal averages the regions active in that month.
ALL = set(range(1, 13))
SOURCES = {
    "Lettuce, Iceberg": [("salinas", {4, 5, 6, 7, 8, 9, 10, 11}), ("santa_maria", {4, 5, 6, 7, 8, 9, 10}),
                         ("yuma", {12, 1, 2, 3}), ("imperial", {12, 1, 2, 3})],
    "Lettuce, Romaine": [("salinas", {4, 5, 6, 7, 8, 9, 10, 11}), ("santa_maria", ALL), ("yuma", {12, 1, 2, 3}),
                         ("imperial", {12, 1, 2, 3})],
    "Celery": [("salinas", {5, 6, 7, 8, 9, 10, 11}), ("oxnard", {11, 12, 1, 2, 3, 4, 5}), ("michigan", {7, 8, 9})],
    "Broccoli": [("salinas", {4, 5, 6, 7, 8, 9, 10, 11}), ("santa_maria", ALL), ("yuma", {12, 1, 2, 3}),
                 ("imperial", {12, 1, 2, 3})],
    "Strawberries": [("oxnard", {1, 2, 3, 4, 5, 11, 12}), ("santa_maria", {3, 4, 5, 6, 7, 8, 9, 10}),
                     ("salinas", {5, 6, 7, 8, 9, 10}), ("plant_city_fl", {12, 1, 2, 3}), ("baja", {11, 12, 1, 2, 3, 4})],
    "Avocados": [("michoacan", ALL), ("jalisco", ALL), ("oxnard", {4, 5, 6, 7, 8})],
    "Limes": [("veracruz", ALL)],
    "Lemons": [("kern", {11, 12, 1, 2, 3, 4, 5}), ("oxnard", ALL), ("central_chile", {6, 7, 8, 9, 10})],
    "Tomatoes": [("sinaloa", {12, 1, 2, 3, 4}), ("baja", {6, 7, 8, 9, 10}), ("immokalee_fl", {11, 12, 1, 2, 3, 4, 5}),
                 ("san_joaquin", {6, 7, 8, 9, 10}), ("leamington_on", {4, 5, 6, 7, 8, 9, 10})],
    "Tomatoes, Plum Type": [("sinaloa", {11, 12, 1, 2, 3, 4, 5}), ("baja", {6, 7, 8, 9, 10}),
                            ("jalisco", ALL), ("san_joaquin", {6, 7, 8, 9, 10})],
    "Peppers, Bell Type": [("sinaloa", {12, 1, 2, 3, 4}), ("sonora", {5, 6, 10, 11}), ("immokalee_fl", {11, 12, 1, 2, 3, 4, 5}),
                           ("south_georgia", {5, 6, 10, 11}), ("san_joaquin", {6, 7, 8, 9, 10}),
                           ("leamington_on", {4, 5, 6, 7, 8, 9, 10})],
    "Cucumbers": [("sinaloa", {12, 1, 2, 3, 4}), ("sonora", {4, 5, 10, 11}), ("south_georgia", {5, 6, 10, 11}),
                  ("leamington_on", ALL), ("immokalee_fl", {11, 12, 1, 2, 3, 4})],
    "Onions, Dry": [("idaho_oregon", {8, 9, 10, 11, 12, 1, 2, 3, 4}), ("columbia_basin", {7, 8, 9, 10, 11, 12, 1, 2, 3}),
                    ("imperial", {4, 5}), ("san_joaquin", {6, 7, 8})],
    "Potatoes": [("idaho_oregon", ALL), ("columbia_basin", ALL)],
    "Carrots": [("kern", ALL), ("imperial", {12, 1, 2, 3})],
    "Grapes": [("san_joaquin", {6, 7, 8, 9, 10, 11}), ("central_chile", {12, 1, 2, 3, 4})],
    "Blueberries": [("peru_north", {8, 9, 10, 11, 12}), ("central_chile", {12, 1, 2, 3}), ("south_georgia", {5, 6}),
                    ("michigan", {7, 8}), ("jalisco", {1, 2, 3, 4})],
    "Bananas": [("guatemala", ALL), ("ecuador", ALL)],
}


def _get(url, params, tries=4):
    for attempt in range(tries):
        try:
            r = requests.get(url, params=params, timeout=120)
            if r.status_code == 200:
                return r.json()["daily"]
            log.warning("HTTP %s %s", r.status_code, r.text[:200])
        except requests.RequestException as e:
            log.warning("error %r", e)
        time.sleep(10 * (attempt + 1))
    raise RuntimeError(f"Open-Meteo failed: {url} {params}")


def fetch_region(name, lat, lon, start, end):
    """Archive for older days (it lags ~5 days), recent-days feed for the rest."""
    frames = []
    archive_end = min(end, dt.date.today() - dt.timedelta(days=6))
    if start <= archive_end:
        d = _get(ARCHIVE, {"latitude": lat, "longitude": lon, "start_date": start.isoformat(),
                           "end_date": archive_end.isoformat(), "daily": DAILY, "timezone": "UTC"})
        frames.append(pd.DataFrame(d))
    if end > archive_end:
        d = _get(RECENT, {"latitude": lat, "longitude": lon, "past_days": 14, "forecast_days": 1,
                          "daily": DAILY, "timezone": "UTC"})
        frames.append(pd.DataFrame(d))
    df = pd.concat(frames, ignore_index=True).rename(columns={
        "time": "date", "temperature_2m_max": "tmax_c", "temperature_2m_min": "tmin_c", "precipitation_sum": "precip_mm"})
    df = df[(df["date"] >= start.isoformat()) & (df["date"] <= end.isoformat())]
    return df.dropna(subset=["tmax_c", "tmin_c"])


def update(today=None):
    today = today or dt.date.today()
    WEATHER.mkdir(parents=True, exist_ok=True)
    for name, (lat, lon) in REGIONS.items():
        path = WEATHER / f"{name}.csv"
        old = pd.read_csv(path, dtype={"date": str}) if path.exists() else pd.DataFrame(columns=["date"])
        start = FIRST_DATE if old.empty else dt.date.fromisoformat(old["date"].max()) - dt.timedelta(days=21)
        try:
            new = fetch_region(name, lat, lon, start, today - dt.timedelta(days=1))
        except RuntimeError as e:
            log.error("%s: %s (keeping existing data)", name, e)
            continue
        merged = pd.concat([old[old["date"] < start.isoformat()], new]).drop_duplicates("date", keep="last")
        merged.sort_values("date").to_csv(path, index=False, lineterminator="\n")
        log.info("%-15s %d days (%s .. %s)", name, len(merged), merged["date"].min(), merged["date"].max())


def weekly_stress():
    """Per commodity-week weather signals, averaged over the regions active that month.

    freeze_days  nights at or below 0 C in the week
    heat_days    days at or above 35 C
    rain_days    days with >= 20 mm of rain
    precip_anom  log((week's rain + 5mm) / (typical for these weeks in prior years + 5mm))
    """
    rows = []
    for name in REGIONS:
        path = WEATHER / f"{name}.csv"
        if not path.exists():
            continue
        d = pd.read_csv(path)
        d["date"] = pd.to_datetime(d["date"])
        d["week"] = d["date"].dt.to_period("W-SUN").dt.start_time
        w = d.groupby("week").agg(freeze_days=("tmin_c", lambda s: (s <= 0).sum()),
                                  heat_days=("tmax_c", lambda s: (s >= 35).sum()),
                                  rain_days=("precip_mm", lambda s: (s >= 20).sum()),
                                  precip=("precip_mm", "sum")).reset_index()
        iso = w["week"].dt.isocalendar()
        w["year"], w["woy"] = iso["year"].to_numpy(), iso["week"].clip(upper=52).to_numpy()
        typical = np.full(len(w), np.nan)
        for i in range(len(w)):  # prior years only, same week +/-2
            dd = np.minimum(np.abs(w["woy"] - w["woy"].iat[i]), 52 - np.abs(w["woy"] - w["woy"].iat[i]))
            m = (w["year"] < w["year"].iat[i]) & (dd <= 2)
            if m.sum() >= 5:
                typical[i] = w.loc[m, "precip"].mean()
        w["precip_anom"] = np.log((w["precip"] + 5) / (typical + 5))
        w["region"] = name
        rows.append(w)
    if not rows:
        return pd.DataFrame(columns=["commodity", "week", "freeze_days", "heat_days", "rain_days", "precip_anom"])
    reg = pd.concat(rows, ignore_index=True)
    reg["month"] = reg["week"].dt.month
    out = []
    for commodity, srcs in SOURCES.items():
        parts = []
        for region, months in srcs:
            r = reg[(reg["region"] == region) & reg["month"].isin(months)]
            parts.append(r[["week", "freeze_days", "heat_days", "rain_days", "precip_anom"]])
        if parts:
            c = pd.concat(parts).groupby("week").mean().reset_index()
            c["commodity"] = commodity
            out.append(c)
    return pd.concat(out, ignore_index=True)


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    update()


if __name__ == "__main__":
    main()
