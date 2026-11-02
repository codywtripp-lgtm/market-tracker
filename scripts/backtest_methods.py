"""Do better-established forecasting methods beat the live wholesale model? Walk-forward test, same rows for every method.

Tried, and why:
  huber/lad       the site is judged on absolute error, whose best forecast is the median (Gneiting 2011), but the
                  live model minimizes squared error, so a few price spikes pull it around
  shrink          pull forecasts toward "no change"; the simplest forecast combination (Stock & Watson 2004)
  avg             plain averages of different models; simple averages are hard to beat (Timmermann 2006)
  median seasonal "usual" and the seasonal change from medians of past years, so one spike year counts less
  last            latest day's price vs the week's average: a weekly average hides a move late in the week (Working 1960)
  recent          weight recent years more
  gbm             gradient boosting on absolute error, the M5 winners' family (Makridakis et al. 2022)

Bar to adopt: at least a 1% smaller average miss (forecast.MIN_GAIN), no drop in call accuracy, steady across years.

Run: python scripts/backtest_methods.py [where to save predictions]
"""

import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pipeline import export, forecast as fc, store  # noqa: E402

CALL = np.log(1.05)


def late_week():
    """For each series and week: log(latest day's price / the week's average)."""
    grouped = export.load(r for r in store.iter_all() if r["market_type"] == "terminal")
    rows = []
    for key, days in grouped.items():
        weeks = defaultdict(list)
        for d, rs in sorted(days.items()):
            weeks[export.iso_week_start(pd.Timestamp(d).date())].append(export.daily_value(rs)["price"])
        sid = export.series_id(key)
        for w, ps in weeks.items():
            rows.append({"series_id": sid, "week": pd.Timestamp(w), "last": float(np.log(ps[-1] / np.mean(ps)))})
    return pd.DataFrame(rows)


def prior_year_medians(values, years, woy, window):
    ys = np.unique(years)
    idx = {y: i for i, y in enumerate(ys)}
    grid = np.full((len(ys), 52), np.nan)
    for v, y, w in zip(values, years, woy):
        if not np.isnan(v):
            grid[idx[y], w - 1] = v
    out = {}
    for i, y in enumerate(ys):
        for w in range(52):
            cols = [(w + k) % 52 for k in range(-window, window + 1)]
            past = grid[:i][:, cols].ravel()
            past = past[~np.isnan(past)]
            out[(y, w + 1)] = np.median(past) if len(past) else np.nan
    return np.array([out[(y, w)] for y, w in zip(years, woy)])


def add_median_seasonal(panel):
    parts = []
    for _, g in panel.groupby("series_id"):
        g = g.copy()
        years, woy = g["year"].to_numpy(), g["woy"].to_numpy()
        g["gap_med"] = g["lr"] - prior_year_medians(g["lr"].to_numpy(), years, woy, fc.NORM_WINDOW)
        for h in fc.HORIZONS:
            y = np.where(woy + h + fc.SEASON_WINDOW <= 52, g[f"y{h}"].to_numpy(), np.nan)
            g[f"seasonal_med{h}"] = prior_year_medians(y, years, woy, fc.SEASON_WINDOW)
        parts.append(g)
    return pd.concat(parts, ignore_index=True)


def robust(cols, kind, k=0.05, half_life=None, median_season=False, prior_rows=fc.PRIOR_ROWS, keys=("commodity", "market")):
    """The live per-item ridge-to-pooled fit, solved by reweighting for Huber / absolute-error loss, optionally by recency."""
    keys = list(keys)

    def X_of(df, h):
        names = []
        for c in cols:
            if c == "seasonal":
                names.append(f"seasonal_med{h}" if median_season else f"seasonal{h}")
            else:
                names.append("gap_med" if c == "gap" and median_season else c)
        return np.column_stack([np.ones(len(df)), df[names].fillna(0.0).to_numpy()])

    def group(df):
        return df[keys].astype(str).agg("|".join, axis=1).to_numpy()

    def solve(X, y, w0, lam=None, prior=None):
        lam = np.zeros((X.shape[1], X.shape[1])) if lam is None else lam
        prior = np.zeros(X.shape[1]) if prior is None else prior
        w = w0.copy()
        b = None
        for _ in range(1 if kind == "ols" else 12):
            XW = X * w[:, None]
            b = np.linalg.solve(XW.T @ X + lam + 1e-9 * np.eye(X.shape[1]), XW.T @ y + lam @ prior)
            r = np.abs(y - X @ b)
            w = w0 * (np.minimum(1.0, k / np.maximum(r, 1e-6)) if kind == "huber" else 1.0 / np.maximum(r, 1e-3))
            w = w / w.mean() * w0.mean()
        return b

    def fit(train, h):
        X, y = X_of(train, h), train[f"y{h}"].to_numpy()
        w0 = np.ones(len(y))
        if half_life:
            age = (train["week"].max() - train["week"]).dt.days.to_numpy() / 365.25
            w0 = 0.5 ** (age / half_life)
        pooled = solve(X, y, w0)
        lam = np.diag(np.diag(X.T @ X) / len(X) * prior_rows + 1e-9)
        gs = group(train)
        return pooled, {g: solve(X[gs == g], y[gs == g], w0[gs == g], lam, pooled) for g in np.unique(gs)}

    def predict(model, rows, h):
        pooled, per = model
        coefs = np.stack([per.get(g, pooled) for g in group(rows)])
        return np.einsum("ij,ij->i", X_of(rows, h), coefs)
    return fit, predict


def gbm_abs(cols):
    from sklearn.ensemble import HistGradientBoostingRegressor

    def frame(df, h, cats):
        X = df[[f"seasonal{h}" if c == "seasonal" else c for c in cols]].copy()
        X.columns = cols
        X["woy"] = df["woy"].to_numpy()
        X["commodity"] = pd.Categorical(df["commodity"].astype(str), categories=cats)
        X["market"] = pd.Categorical(df["market"].astype(str), categories=fc.TERMINALS)
        return X

    def fit(train, h):
        m = HistGradientBoostingRegressor(loss="absolute_error", max_iter=200, learning_rate=0.05, max_leaf_nodes=15,
                                          min_samples_leaf=100, categorical_features="from_dtype", random_state=0)
        cats = sorted(train["commodity"].astype(str).unique())
        m.fit(frame(train, h, cats), train[f"y{h}"].to_numpy())
        return m, cats

    def predict(model, rows, h):
        m, cats = model
        return m.predict(frame(rows, h, cats))
    return fit, predict


def report(name, t, p, headline):
    """t: test rows of all horizons. Scores a prediction column the same way for every method."""
    ape = np.abs(np.expm1(p) - np.expm1(t["y"].to_numpy())) * 100
    d = pd.DataFrame({"h": t["h"].to_numpy(), "year": t["year"].to_numpy(), "ape": ape, "p": p, "y": t["y"].to_numpy(),
                      "sid": t["series_id"].to_numpy(), "sp2": t["sp2"].to_numpy(),
                      "below8": t["below8"].fillna(False).to_numpy(dtype=bool)})
    two = d[d["h"] == 2]
    calls = two[two["p"].abs() >= CALL]
    kept = calls[~fc.held(calls["p"], calls["sp2"], calls["below8"])]

    def hit(c):
        return (np.sign(c["p"]) == np.sign(c["y"])).mean() * 100
    big = two[two["y"].abs() >= np.log(1.10)]
    caught = ((np.sign(big["p"]) == np.sign(big["y"])) & (big["p"].abs() >= CALL)).mean() * 100
    head = d[d["sid"].isin(headline)]
    print(f"{name:30s} miss {d.groupby('h')['ape'].mean().mean():6.3f}  2wk {two['ape'].mean():6.3f}  "
          f"main-pack {head.groupby('h')['ape'].mean().mean():6.3f}  calls {len(calls):5d} {hit(calls):5.1f}%  "
          f"guarded {len(kept):5d} {hit(kept):5.1f}%  caught {caught:4.1f}%", flush=True)
    return two.groupby("year")["ape"].mean()


def main():
    panel = fc.add_hold_inputs(fc.add_seasonal(fc.add_drivers(fc.weekly_panel())))
    panel = add_median_seasonal(panel)
    panel = panel.merge(late_week(), on=["series_id", "week"], how="left")
    print("weeks with latest-day value:", round(panel["last"].notna().mean(), 3), flush=True)
    series = pd.read_csv(fc.EXPORT / "series.csv", dtype=str)
    headline = set(series[(series["market_type"] == "terminal") & (series["headline"] == "Y")]["series_id"])
    usable = panel.dropna(subset=["lp"])
    base = fc.BASE
    methods = {
        "live": fc._by_group(base, keys=("commodity", "market")),
        "huber": robust(base, "huber"),
        "lad": robust(base, "lad"),
        "median seasonal": robust(base, "ols", median_season=True),
        "lad + median seasonal": robust(base, "lad", median_season=True),
        "+ last day": robust(base + ["last"], "ols"),
        "lad + last day": robust(base + ["last"], "lad"),
        "recent half-life 3y": robust(base, "ols", half_life=3),
        "pooled": fc._pooled(base),
        "gbm absolute": gbm_abs(base),
    }
    parts = []
    for h in fc.HORIZONS:
        for Y in range(fc.FIRST_TEST_YEAR, int(panel["year"].max()) + 1):
            train = usable[usable["week"] + pd.Timedelta(weeks=h) < pd.Timestamp(f"{Y}-01-01")].dropna(subset=[f"y{h}"])
            test = usable[usable["year"] == Y].dropna(subset=[f"y{h}"])
            if len(train) < 500 or test.empty:
                continue
            row = test[["series_id", "commodity", "market", "week", "year", "sp2", "below8"]].assign(h=h, y=test[f"y{h}"].to_numpy())
            for name, (f, p) in methods.items():
                row[name] = p(f(train, h), test, h)
            parts.append(row)
            print("done", h, Y, flush=True)
    t = pd.concat(parts, ignore_index=True)
    t.to_pickle(sys.argv[1] if len(sys.argv) > 1 else "backtest_methods.pkl")
    years = {}
    for name in methods:
        years[name] = report(name, t, t[name].to_numpy(), headline)
    report("no change", t, np.zeros(len(t)), headline)
    for s in (0.9, 0.8, 0.6):
        years[f"live x {s}"] = report(f"live x {s}", t, t["live"].to_numpy() * s, headline)
    for name, mix in {"avg live+lad": ["live", "lad"], "avg live+gbm": ["live", "gbm absolute"],
                      "avg lad+gbm": ["lad", "gbm absolute"], "avg live+lad+gbm": ["live", "lad", "gbm absolute"],
                      "avg live+pooled": ["live", "pooled"], "avg live+lad+pooled+gbm": ["live", "lad", "pooled", "gbm absolute"],
                      "avg ladlast+gbm": ["lad + last day", "gbm absolute"]}.items():
        years[name] = report(name, t, t[mix].mean(axis=1).to_numpy(), headline)
    print("\n2-week miss by test year")
    print(pd.DataFrame(years).T.round(2).to_string())


if __name__ == "__main__":
    main()
