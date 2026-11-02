"""Do the methods that improved the wholesale forecast also improve the grocery one? Walk-forward test, 2022-2026.

Same reasons as scripts/backtest_methods.py: fit for absolute error (Gneiting 2011), plain averages of forecasts
(Timmermann 2006), gradient boosting (Makridakis et al. 2022), per-item coefficients shrunk toward the shared ones.

Bar to adopt: at least a 1% smaller miss, no drop in the share of calls that come true, steady across years.

Run: python scripts/backtest_grocery_methods.py
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pipeline import cpi, grocery  # noqa: E402
from pipeline import grocery_forecast as gf  # noqa: E402

FEATS = list(gf.FEATS)
YEARS = (2022, 2023, 2024, 2025, 2026)


def X_of(d):
    return np.column_stack([np.ones(len(d)), d[FEATS].to_numpy()])


def irls(X, y, lam, prior, k):
    """k=None: absolute error. Otherwise Huber: errors beyond k count linearly."""
    w = np.ones(len(y))
    for _ in range(12):
        XW = X * w[:, None]
        b = np.linalg.solve(XW.T @ X + lam + 1e-9 * np.eye(X.shape[1]), XW.T @ y + lam @ prior)
        r = np.abs(y - X @ b)
        w = 1 / np.maximum(r, 1e-3) if k is None else np.minimum(1.0, k / np.maximum(r, 1e-6))
        w = w / w.mean()
    return b


def shared(train, test, k):
    X = X_of(train)
    b = irls(X, train["y"].to_numpy(), np.zeros((X.shape[1], X.shape[1])), np.zeros(X.shape[1]), k)
    return X_of(test) @ b


def per_group(train, test, key, k, prior_rows):
    X, y = X_of(train), train["y"].to_numpy()
    zero = np.zeros((X.shape[1], X.shape[1]))
    pooled = irls(X, y, zero, np.zeros(X.shape[1]), k)
    lam = np.diag(np.diag(X.T @ X) / len(X) * prior_rows + 1e-9)
    gs = train[key].to_numpy()
    per = {g: irls(X[gs == g], y[gs == g], lam, pooled, k) for g in np.unique(gs)}
    return np.einsum("ij,ij->i", X_of(test), np.stack([per.get(g, pooled) for g in test[key]]))


def gbm(train, test):
    from sklearn.ensemble import HistGradientBoostingRegressor
    cats = sorted(train["item"].unique())

    def frame(d):
        X = d[FEATS].copy()
        X["woy"] = d["date"].dt.isocalendar().week.astype(int).to_numpy()
        X["item"] = pd.Categorical(d["item"].where(d["item"].isin(cats)), categories=cats)
        return X
    m = HistGradientBoostingRegressor(loss="absolute_error", max_iter=200, learning_rate=0.05, max_leaf_nodes=15,
                                      min_samples_leaf=100, categorical_features="from_dtype", random_state=0)
    m.fit(frame(train), train["y"].to_numpy())
    return m.predict(frame(test))


def score(name, t, p):
    y, run = t["y"].to_numpy(), t["run"].to_numpy()
    called = (np.abs(p) >= gf.CALL) & ~((p < 0) & (run == 1)) & ~((p > 0) & (run == -1))
    right = ((p > 0) & (y >= gf.HIT)) | ((p < 0) & (y <= -gf.HIT))
    move = np.abs(y) >= 0.10
    miss = np.abs(y - p)
    by_year = pd.Series(miss).groupby(t["date"].dt.year.to_numpy()).mean() * 100
    by_rec = pd.Series(right[called]).groupby(t["date"].dt.year.to_numpy()[called]).mean() * 100
    print(f"{name:28s} miss {miss.mean() * 100:6.3f}%  calls {called.sum():5d} right {right[called].mean() * 100:5.1f}%  "
          f"10%+ moves called {(called & move & right).sum() / move.sum() * 100:4.1f}%  "
          f"years {' '.join(f'{v:5.2f}' for v in by_year)}  record {' '.join(f'{v:3.0f}' for v in by_rec)}", flush=True)


def main():
    pts = gf.series(grocery.load(grocery.rows()), cpi.Deflator(cpi.load()), grocery.main_pack)
    rows = [dict(r, item=c) for c, p in pts.items() for r in gf.training_rows(p)]
    d = pd.DataFrame(rows)
    d["date"] = pd.to_datetime(d["date"])
    parts = []
    for Y in YEARS:
        train, test = d[d["date"].dt.year < Y], d[d["date"].dt.year == Y]
        if len(train) < 500 or test.empty:
            continue
        w = gf.fit(train.to_dict("records"))
        out = test.copy()
        out["live"] = [gf.predict(w, r) for r in test.to_dict("records")]
        out["lad"] = shared(train, test, None)
        out["huber 5%"] = shared(train, test, 0.05)
        out["huber 10%"] = shared(train, test, 0.10)
        out["per item"] = per_group(train, test, "item", 0.0 + 1e9, 500)  # k huge: plain squared error
        out["per item huber"] = per_group(train, test, "item", 0.10, 500)
        out["gbm"] = gbm(train, test)
        parts.append(out)
        print("done", Y, flush=True)
    t = pd.concat(parts, ignore_index=True)
    score("no change", t, np.zeros(len(t)))
    for c in ["live", "lad", "huber 5%", "huber 10%", "per item", "per item huber", "gbm"]:
        score(c, t, t[c].to_numpy())
    for name, mix in {"avg live+gbm": ["live", "gbm"], "avg huber10+gbm": ["huber 10%", "gbm"],
                      "avg per item huber+gbm": ["per item huber", "gbm"], "avg per item+gbm": ["per item", "gbm"]}.items():
        score(name, t, t[mix].mean(axis=1).to_numpy())
    for s in (0.9, 0.8):
        score(f"live x {s}", t, t["live"].to_numpy() * s)


if __name__ == "__main__":
    main()
