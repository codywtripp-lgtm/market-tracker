"""Second round after scripts/backtest_methods.py: the winners with the latest-day input, checked three harder ways.

  1. mid-week: the site forecasts every night, so re-score with only Monday-Wednesday prices known for the test week
  2. guard: does the "Unsettled" hold-back rule still earn its cost with the better model? (2024-2026 only)
  3. each model's 2-week calls with the live per-item choice vs "no change", scored as scripts/value_stats.py does

Run: python scripts/backtest_methods2.py
"""

import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from backtest_methods import gbm_abs, robust  # noqa: E402
from pipeline import export, forecast as fc, store  # noqa: E402

CALL = np.log(1.05)


def days():
    """Per series and week: full-week `last`, and the mean and latest price using only Monday-Wednesday."""
    grouped = export.load(r for r in store.iter_all() if r["market_type"] == "terminal")
    rows = []
    for key, by_day in grouped.items():
        weeks = defaultdict(list)
        for d, rs in sorted(by_day.items()):
            day = pd.Timestamp(d).date()
            weeks[export.iso_week_start(day)].append((day.weekday(), export.daily_value(rs)["price"]))
        sid = export.series_id(key)
        for w, ps in weeks.items():
            all_p = [p for _, p in ps]
            early = [p for wd, p in ps if wd <= 2]
            rows.append({"series_id": sid, "week": pd.Timestamp(w), "last": float(np.log(all_p[-1] / np.mean(all_p))),
                         "early_mean": float(np.mean(early)) if early else np.nan,
                         "early_last": float(early[-1]) if early else np.nan})
    return pd.DataFrame(rows)


def score(name, t, p):
    two = t.assign(p=p)
    ape = np.abs(np.expm1(two["p"]) - np.expm1(two["y"])) * 100
    miss = ape.groupby(two["h"]).mean()
    d = two[two["h"] == 2]
    calls = d[d["p"].abs() >= CALL]
    right = (np.sign(calls["p"]) == np.sign(calls["y"])).mean() * 100
    big = d[d["y"].abs() >= np.log(1.10)]
    caught = ((np.sign(big["p"]) == np.sign(big["y"])) & (big["p"].abs() >= CALL)).mean() * 100
    wrong = ((np.sign(big["p"]) != np.sign(big["y"])) & (big["p"].abs() >= CALL)).mean() * 100
    print(f"{name:34s} miss {miss.mean():6.3f}  2wk {miss[2]:6.3f}  calls {len(calls):5d} {right:5.1f}%  caught {caught:4.1f}%  wrong way {wrong:4.1f}%", flush=True)


def guarded(name, d, col):
    d = d[d["year"] >= 2024]
    p = d[col].to_numpy()
    called = np.abs(p) >= CALL
    keep = called & ~fc.held(p, d["sp2"], d["below8"].fillna(False))
    y = d["y"].to_numpy()
    big = np.abs(y) >= np.log(1.10)
    for label, c in (("no guard", called), ("guard", keep)):
        print(f"{name:26s} {label:9s} calls {c.sum():5d} right {(np.sign(p[c]) == np.sign(y[c])).mean() * 100:5.1f}%  "
              f"big called {(c & big & (np.sign(p) == np.sign(y))).sum() / big.sum() * 100:4.1f}%  "
              f"big wrong way {(c & big & (np.sign(p) != np.sign(y))).sum() / big.sum() * 100:4.1f}%", flush=True)


def per_item(r, col):
    """Live rule: use the model only for items where it beat no change, judged on earlier years."""
    d = r.assign(a=np.abs(np.expm1(r[col]) - np.expm1(r["y"])), n=np.abs(np.expm1(r["y"])))
    out = pd.Series(0.0, index=d.index)
    for (h, Y), cur in d.groupby(["h", "year"]):
        prior = d[(d["h"] == h) & (d["year"] < Y)].groupby(["commodity", "market"])[["a", "n"]].mean()
        ok = {k: v["a"] <= v["n"] for k, v in prior.iterrows()}
        use = np.array([ok.get(k, True) for k in zip(cur["commodity"], cur["market"])])
        out.loc[cur.index] = np.where(use, cur[col], 0.0)
    return out.to_numpy()


def main():
    panel = fc.add_hold_inputs(fc.add_seasonal(fc.add_drivers(fc.weekly_panel())))
    panel = panel.merge(days(), on=["series_id", "week"], how="left")
    usable = panel.dropna(subset=["lp"])
    base, plus = fc.BASE, fc.BASE + ["last"]
    methods = {"live": fc._by_group(base, keys=("commodity", "market")),
               "lad+last": robust(plus, "lad"), "huber+last": robust(plus, "huber"), "gbm+last": gbm_abs(plus), "gbm": gbm_abs(base)}
    full, mid = [], []
    for h in fc.HORIZONS:
        for Y in range(fc.FIRST_TEST_YEAR, int(panel["year"].max()) + 1):
            train = usable[usable["week"] + pd.Timedelta(weeks=h) < pd.Timestamp(f"{Y}-01-01")].dropna(subset=[f"y{h}"])
            test = usable[usable["year"] == Y].dropna(subset=[f"y{h}"])
            if len(train) < 500 or test.empty:
                continue
            early = test.dropna(subset=["early_mean"]).copy()
            delta = np.log(early["early_mean"]) - early["lp"]
            for c in ("lp", "mom1", "mom4", "gap"):
                early[c] = early[c] + delta
            early["last"] = np.log(early["early_last"] / early["early_mean"])
            keep = ["series_id", "commodity", "market", "week", "year", "sp2", "below8"]
            a = test[keep].assign(h=h, y=test[f"y{h}"].to_numpy())
            b = early[keep].assign(h=h, y=early[f"y{h}"].to_numpy() - delta.to_numpy())
            for name, (f, p) in methods.items():
                model = f(train, h)
                a[name], b[name] = p(model, test, h), p(model, early, h)
            full.append(a)
            mid.append(b)
            print("done", h, Y, flush=True)
    t, m = pd.concat(full, ignore_index=True), pd.concat(mid, ignore_index=True)
    mixes = {"avg lad+gbm (no last)": None, "avg lad+last, gbm": ["lad+last", "gbm"], "avg lad+last, gbm+last": ["lad+last", "gbm+last"],
             "avg huber+last, gbm+last": ["huber+last", "gbm+last"]}
    for frame in (t, m):
        for name, mix in mixes.items():
            if mix:
                frame[name] = frame[mix].mean(axis=1)
    cols = ["live", "lad+last", "huber+last", "gbm+last"] + [k for k, v in mixes.items() if v]
    print("\nFULL WEEK KNOWN")
    for c in cols:
        score(c, t, t[c].to_numpy())
    print("\nONLY MONDAY-WEDNESDAY KNOWN")
    score("no change", m, np.zeros(len(m)))
    for c in cols:
        score(c, m, m[c].to_numpy())
    print("\nWITH THE PER-ITEM CHOICE")
    for c in cols:
        t[c + " item"] = per_item(t, c)
        score(c, t, t[c + " item"].to_numpy())
    print("\nGUARD, 2-WEEK CALLS, 2024-2026")
    two = t[t["h"] == 2]
    for c in ["live", "avg lad+last, gbm+last", "avg huber+last, gbm+last", "avg lad+last, gbm"]:
        guarded(c, two, c + " item")
    print("\n2-week miss by year, per-item")
    print(pd.DataFrame({c: two.assign(a=np.abs(np.expm1(two[c + " item"]) - np.expm1(two["y"])) * 100).groupby("year")["a"].mean() for c in cols}).T.round(2).to_string())


if __name__ == "__main__":
    main()
