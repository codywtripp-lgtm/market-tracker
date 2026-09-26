"""Week-by-week price forecasts (next 1-4 weeks) with an 80% range, for terminal-market headline series.

    python -m pipeline.forecast

What it predicts: the change in a series' weekly price from this week to h weeks ahead
(h = 1..4), as a log change. Ranges come from the model's own out-of-sample errors.

Features (all known at the time of the forecast; nothing from the future):
  seasonal   average change from this week-of-year to h weeks later, in prior years only
  gap        how far this week's price (today's dollars) sits from the usual for this
             week-of-year in prior years (extremes tend to come back)
  mom1/mom4  change over the last 1 and 4 weeks
  sp         this week's shipping-point price change for the commodity
  tone       USDA reporters' market call at this terminal this week (-1..1)

Models compared by walk-forward testing (train on years before Y, test on year Y):
  naive      no change
  seasonal   the seasonal change only
  model      linear regression on all features (one per horizon, pooled across series)
The live forecast uses the model only for horizons where it beat both baselines; otherwise
the better baseline.

Writes data/export/forecasts.json (live) and data/export/forecast_backtest.csv (scores).
Details: docs/forecast.md
"""

import datetime as dt
import json

import numpy as np
import pandas as pd

from . import signals, store

EXPORT = store.DATA / "export"
HORIZONS = [1, 2, 3, 4]
FEATURES = ["seasonal", "gap", "mom1", "mom4", "sp", "tone"]
TERMINALS = ["New York", "Los Angeles", "Chicago"]
FIRST_TEST_YEAR = 2021
# 80% range. Plain 10th/90th error percentiles covered only 77% out of sample (errors in a
# new year run a bit bigger than in past years), so the quantiles are set slightly wider.
LO_Q, HI_Q = 0.085, 0.915
SEASON_WINDOW = 1        # weeks either side when averaging seasonal changes
NORM_WINDOW = 2          # weeks either side for the usual price


def weekly_panel():
    """One row per terminal headline series per week, on a regular weekly grid."""
    series = pd.read_csv(EXPORT / "series.csv", dtype=str)
    series = series[series["market_type"] == "terminal"]
    wk = pd.read_csv(EXPORT / "prices_weekly.csv", dtype={"series_id": str})
    wk = wk[wk["series_id"].isin(series["series_id"])]
    wk["week"] = pd.to_datetime(wk["week_start"])
    frames = []
    for sid, g in wk.groupby("series_id"):
        g = g.set_index("week").sort_index()[["compare_price", "real_compare_price"]]
        g = g.asfreq("7D")
        g["series_id"] = sid
        frames.append(g.reset_index())
    panel = pd.concat(frames, ignore_index=True)
    panel = panel.merge(series[["series_id", "commodity", "market"]], on="series_id")
    panel["lp"] = np.log(panel["compare_price"])
    panel["lr"] = np.log(panel["real_compare_price"].fillna(panel["compare_price"]))
    iso = panel["week"].dt.isocalendar()
    panel["year"], panel["woy"] = iso["year"].astype(int), iso["week"].clip(upper=52).astype(int)
    g = panel.groupby("series_id")["lp"]
    panel["mom1"] = panel["lp"] - g.shift(1)
    panel["mom4"] = panel["lp"] - g.shift(4)
    for h in HORIZONS:
        panel[f"y{h}"] = g.shift(-h) - panel["lp"]
    return panel


def add_drivers(panel):
    """Shipping-point change (commodity-wide) and USDA tone (per terminal) for each week."""
    ship = signals.load("shipping_point").assign(market="Shipping point")
    sp = signals.index_changes(ship).droplevel("market").rename("sp").reset_index()
    term = signals.load("terminal")
    tone = signals.weekly_tone(term[term["market"].isin(TERMINALS)]).rename("tone").reset_index()
    panel = panel.merge(sp, on=["commodity", "week"], how="left")
    panel = panel.merge(tone, on=["commodity", "market", "week"], how="left")
    return panel


def _prior_year_means(values, years, woy, window):
    """For each row: mean of `values` in the same series' prior years, same week-of-year +/- window.

    values/years/woy are arrays for ONE series. Only strictly earlier years are used, so a
    row never sees its own year (or the future)."""
    ys = np.unique(years)
    idx = {y: i for i, y in enumerate(ys)}
    s = np.zeros((len(ys), 52))
    n = np.zeros((len(ys), 52))
    ok = ~np.isnan(values)
    np.add.at(s, (np.vectorize(idx.get)(years[ok]), woy[ok] - 1), values[ok])
    np.add.at(n, (np.vectorize(idx.get)(years[ok]), woy[ok] - 1), 1)
    # widen to +/- window weeks (circular)
    sw = sum(np.roll(s, k, axis=1) for k in range(-window, window + 1))
    nw = sum(np.roll(n, k, axis=1) for k in range(-window, window + 1))
    # cumulative over years, excluding the current year
    cs = np.cumsum(sw, axis=0) - sw
    cn = np.cumsum(nw, axis=0) - nw
    with np.errstate(invalid="ignore", divide="ignore"):
        mean = cs / cn
    return mean[np.vectorize(idx.get)(years), woy - 1]


def add_seasonal(panel):
    out = []
    for sid, g in panel.groupby("series_id"):
        g = g.copy()
        years, woy = g["year"].to_numpy(), g["woy"].to_numpy()
        g["norm"] = _prior_year_means(g["lr"].to_numpy(), years, woy, NORM_WINDOW)
        g["gap"] = g["lr"] - g["norm"]
        for h in HORIZONS:
            # Only use changes that stay inside one year, so late-December rows can't carry
            # next January's prices into a test year.
            y = np.where(woy + h + SEASON_WINDOW <= 52, g[f"y{h}"].to_numpy(), np.nan)
            g[f"seasonal{h}"] = _prior_year_means(y, years, woy, SEASON_WINDOW)
        out.append(g)
    return pd.concat(out, ignore_index=True)


def design(df, h):
    X = df[["gap", "mom1", "mom4", "sp", "tone"]].copy()
    X.insert(0, "seasonal", df[f"seasonal{h}"])
    X = X.fillna(0.0)  # missing driver = no information = 0 change
    X.insert(0, "const", 1.0)
    return X.to_numpy()


def fit(df, h):
    X, y = design(df, h), df[f"y{h}"].to_numpy()
    coef, *_ = np.linalg.lstsq(X, y, rcond=None)
    return coef


def predict(df, h, method, coef=None):
    if method == "naive":
        return np.zeros(len(df))
    if method == "seasonal":
        return df[f"seasonal{h}"].fillna(0.0).to_numpy()
    return design(df, h) @ coef


def backtest(panel, last_year):
    """Walk-forward: for each test year Y, fit on rows whose target is fully before Y."""
    rows, residuals = [], []
    usable = panel.dropna(subset=["lp"])
    for h in HORIZONS:
        for Y in range(FIRST_TEST_YEAR, last_year + 1):
            start = pd.Timestamp(f"{Y}-01-01")
            train = usable[(usable["week"] + pd.Timedelta(weeks=h) < start)].dropna(subset=[f"y{h}"])
            test = usable[(usable["year"] == Y)].dropna(subset=[f"y{h}"])
            if len(train) < 500 or test.empty:
                continue
            coef = fit(train, h)
            for m in ("naive", "seasonal", "model"):
                pred = predict(test, h, m, coef)
                err = test[f"y{h}"].to_numpy() - pred
                rows.append({"horizon": h, "year": Y, "method": m, "n": len(test),
                             "mae_pct": float(np.mean(np.abs(np.expm1(pred + 0) - np.expm1(test[f"y{h}"].to_numpy()))) * 100),
                             "mae_log": float(np.mean(np.abs(err))),
                             "direction_hit": float(np.mean(np.sign(pred) == np.sign(test[f"y{h}"].to_numpy())))
                             if m != "naive" else float("nan")})
                residuals.append(pd.DataFrame({"horizon": h, "year": Y, "method": m,
                                               "commodity": test["commodity"].to_numpy(), "resid": err}))
    return pd.DataFrame(rows), pd.concat(residuals, ignore_index=True) if residuals else pd.DataFrame()


def interval_table(resid):
    """(commodity, horizon) -> (lo, hi) residual quantiles; falls back to all commodities."""
    table = {}
    pooled = resid.groupby("horizon")["resid"].quantile([LO_Q, HI_Q]).unstack()
    for (c, h), g in resid.groupby(["commodity", "horizon"]):
        if len(g) >= 60:
            table[(c, h)] = (g["resid"].quantile(LO_Q), g["resid"].quantile(HI_Q))
    return table, {h: (pooled.loc[h, LO_Q], pooled.loc[h, HI_Q]) for h in pooled.index}


def coverage(resid):
    """Honest coverage: for each test year, ranges built only from earlier years' residuals."""
    hits = total = 0
    for Y in sorted(resid["year"].unique()):
        prior = resid[resid["year"] < Y]
        if len(prior) < 200:
            continue
        table, pooled = interval_table(prior)
        cur = resid[resid["year"] == Y]
        for (c, h), g in cur.groupby(["commodity", "horizon"]):
            lo, hi = table.get((c, h), pooled[h])
            hits += int(((g["resid"] >= lo) & (g["resid"] <= hi)).sum())
            total += len(g)
    return hits / total if total else float("nan")


def main():
    panel = add_seasonal(add_drivers(weekly_panel()))
    last_year = int(panel["year"].max())
    scores, resid = backtest(panel, last_year)
    summary = scores.groupby(["horizon", "method"]).apply(
        lambda g: pd.Series({"mae_pct": np.average(g["mae_pct"], weights=g["n"]),
                             "direction_hit": np.average(g["direction_hit"].fillna(0), weights=g["n"])}),
        include_groups=False).reset_index()
    # choose per horizon: the model only if it beats both baselines on average error
    best = {}
    for h in HORIZONS:
        s = summary[summary["horizon"] == h].set_index("method")["mae_pct"]
        best[h] = s.idxmin() if not s.empty else "seasonal"
    # ranges come from the out-of-sample errors of the method actually used
    used = pd.concat([resid[(resid["horizon"] == h) & (resid["method"] == best[h])] for h in HORIZONS])
    cov = coverage(used) if not used.empty else float("nan")

    # live forecast: train on everything available
    usable = panel.dropna(subset=["lp"])
    table, pooled = interval_table(used)
    latest = usable.sort_values("week").groupby("series_id").tail(1)
    today = pd.Timestamp(dt.date.today())
    latest = latest[(today - latest["week"]).dt.days <= 14]  # skip series that stopped reporting
    out = {}
    for h in HORIZONS:
        coef = fit(usable.dropna(subset=[f"y{h}"]), h)
        pred = predict(latest, h, best[h], coef)
        for (_, r), p in zip(latest.iterrows(), pred):
            lo, hi = table.get((r["commodity"], h), pooled[h])
            wk = (r["week"] + pd.Timedelta(weeks=h)).date().isoformat()
            out.setdefault(r["series_id"], {"from_week": r["week"].date().isoformat(),
                                             "from_price": round(float(r["compare_price"]), 2), "points": []})
            out[r["series_id"]]["points"].append({
                "week": wk, "h": h, "mid": round(float(np.exp(r["lp"] + p)), 2),
                "lo": round(float(np.exp(r["lp"] + p + lo)), 2), "hi": round(float(np.exp(r["lp"] + p + hi)), 2)})

    EXPORT.mkdir(parents=True, exist_ok=True)
    (EXPORT / "forecasts.json").write_text(json.dumps({
        "asOf": dt.date.today().isoformat(), "method": {str(h): best[h] for h in HORIZONS},
        "range": "80%", "coverage_backtest": round(cov, 3), "series": out}, separators=(",", ":")))
    summary.round(4).to_csv(EXPORT / "forecast_backtest.csv", index=False)
    print(summary.round(3).to_string(index=False))
    print(f"80% range coverage (walk-forward): {cov:.1%}; methods used: {best}; series forecast: {len(out)}")


if __name__ == "__main__":
    main()
