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

  sp_prev    last week's shipping-point change

Methods compared by walk-forward testing (train on years before Y, test on year Y):
  naive           no change
  seasonal        the seasonal change only
  pooled          linear regression, one per horizon, pooled across series (v1)
  pooled+sp_prev  the same plus last week's shipping-point change
  by_commodity    per-commodity regression, shrunk toward the pooled one
  gbm             gradient boosting (learns interactions; also sees week-of-year, commodity, market)
The live forecast uses whichever method had the smallest average miss for each horizon.

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
    # last week's shipping-point move too (terminals often lag by about a week)
    panel = panel.sort_values(["series_id", "week"]).reset_index(drop=True)
    panel["sp_prev"] = panel.groupby("series_id")["sp"].shift(1)
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


BASE = ["seasonal", "gap", "mom1", "mom4", "sp", "tone"]
EXTENDED = BASE + ["sp_prev"]
# Pull toward the pooled coefficients, expressed as "worth this many rows of data": a commodity
# with far more rows than this mostly follows its own data; a thin one stays near the pooled fit.
PRIOR_ROWS = 1000


def design(df, h, cols):
    X = df[[f"seasonal{h}" if c == "seasonal" else c for c in cols]].fillna(0.0)  # missing driver = no info
    return np.column_stack([np.ones(len(X)), X.to_numpy()])


def ols(X, y):
    return np.linalg.lstsq(X, y, rcond=None)[0]


# Each method: fit(train, h) -> model; predict(model, rows, h) -> predicted log change.
def _naive():
    return (lambda train, h: None), (lambda model, rows, h: np.zeros(len(rows)))


def _seasonal():
    return (lambda train, h: None), (lambda model, rows, h: rows[f"seasonal{h}"].fillna(0.0).to_numpy())


def _pooled(cols):
    def fit(train, h):
        return ols(design(train, h, cols), train[f"y{h}"].to_numpy())
    return fit, (lambda coef, rows, h: design(rows, h, cols) @ coef)


def _by_group(cols, keys=("commodity",), prior_rows=PRIOR_ROWS):
    """Per-group regression (e.g. per commodity), shrunk toward the pooled fit (thin groups stay near pooled)."""
    keys = list(keys)

    def group(df):
        return df[keys].astype(str).agg("|".join, axis=1) if len(keys) > 1 else df[keys[0]]

    def fit(train, h):
        X, y = design(train, h, cols), train[f"y{h}"].to_numpy()
        pooled = ols(X, y)
        per = {}
        lam = np.diag(np.diag(X.T @ X) / len(X) * prior_rows)  # scale-aware penalty per feature
        for g, idx in pd.Series(np.arange(len(train))).groupby(group(train).to_numpy()).groups.items():
            idx = np.asarray(idx)
            Xg, yg = X[idx], y[idx]
            per[g] = np.linalg.solve(Xg.T @ Xg + lam, Xg.T @ yg + lam @ pooled)
        return pooled, per

    def predict(model, rows, h):
        pooled, per = model
        X = design(rows, h, cols)
        coefs = np.stack([per.get(g, pooled) for g in group(rows)])
        return np.einsum("ij,ij->i", X, coefs)
    return fit, predict


def _gbm(cols):
    """Gradient boosting: can learn interactions (e.g. a gap matters more in some seasons/commodities)."""
    from sklearn.ensemble import HistGradientBoostingRegressor

    def frame(df, h):
        X = df[[f"seasonal{h}" if c == "seasonal" else c for c in cols]].copy()
        X.columns = cols
        X["woy"] = df["woy"].to_numpy()
        X["commodity"] = df["commodity"].astype("category")
        X["market"] = df["market"].astype("category")
        return X

    def fit(train, h):
        X = frame(train, h)
        cats = {c: X[c].cat.categories for c in ("commodity", "market")}
        m = HistGradientBoostingRegressor(max_iter=300, learning_rate=0.05, max_leaf_nodes=31,
                                          min_samples_leaf=100, l2_regularization=1.0,
                                          categorical_features="from_dtype", random_state=0)
        m.fit(X, train[f"y{h}"].to_numpy())
        return m, cats

    def predict(model, rows, h):
        m, cats = model
        X = frame(rows, h)
        for c, levels in cats.items():  # same category codes as in training
            X[c] = pd.Categorical(X[c].astype(str), categories=levels)
        return m.predict(X)
    return fit, predict


# Kept in the nightly run: baselines, v1, and the v2 winner. Variants tried on 2026-09-26 and
# dropped for not helping (see docs/forecast.md): last week's shipping-point move (sp_prev),
# gradient boosting (_gbm), shrinkage strengths of 250 and 4000 rows. Re-enable to re-test.
METHODS = {
    "naive": _naive(),
    "seasonal": _seasonal(),
    "pooled": _pooled(BASE),                                              # v1
    "by_commodity": _by_group(BASE),
    "by_commodity_market": _by_group(BASE, keys=("commodity", "market")),  # v2
}


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
            for m, (fit_fn, pred_fn) in METHODS.items():
                pred = pred_fn(fit_fn(train, h), test, h)
                err = test[f"y{h}"].to_numpy() - pred
                rows.append({"horizon": h, "year": Y, "method": m, "n": len(test),
                             "mae_pct": float(np.mean(np.abs(np.expm1(pred + 0) - np.expm1(test[f"y{h}"].to_numpy()))) * 100),
                             "mae_log": float(np.mean(np.abs(err))),
                             "direction_hit": float(np.mean(np.sign(pred) == np.sign(test[f"y{h}"].to_numpy())))
                             if m != "naive" else float("nan")})
                residuals.append(pd.DataFrame({
                    "horizon": h, "year": Y, "method": m, "commodity": test["commodity"].to_numpy(),
                    "market": test["market"].to_numpy(), "resid": err,
                    "ape": np.abs(np.expm1(pred) - np.expm1(test[f"y{h}"].to_numpy())) * 100}))
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
        fit_fn, pred_fn = METHODS[best[h]]
        pred = pred_fn(fit_fn(usable.dropna(subset=[f"y{h}"]), h), latest, h)
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

    # Report card: typical 2-week miss per commodity x market, ours vs. "no change"
    two = resid[resid["horizon"] == 2]
    card = (two[two["method"].isin([best[2], "naive"])]
            .groupby(["commodity", "market", "method"])["ape"].mean().unstack("method").round(1)
            .rename(columns={best[2]: "forecast_miss_pct", "naive": "no_change_miss_pct"}).reset_index())
    card["better_by_pct"] = (100 * (1 - card["forecast_miss_pct"] / card["no_change_miss_pct"])).round(0)
    card.sort_values(["market", "forecast_miss_pct"]).to_csv(EXPORT / "forecast_report_card.csv", index=False)
    print("2-week report card, New York:")
    print(card[card["market"] == "New York"].sort_values("forecast_miss_pct").to_string(index=False))
    print(summary.round(3).to_string(index=False))
    print(f"80% range coverage (walk-forward): {cov:.1%}; methods used: {best}; series forecast: {len(out)}")


if __name__ == "__main__":
    main()
