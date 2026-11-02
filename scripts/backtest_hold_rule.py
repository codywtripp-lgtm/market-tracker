"""With the blended forecast, which version of the "Unsettled" hold-back rule earns its cost? Two-week calls, per-item
choice as live. Rules are compared on 2021-2023 and checked on 2024-2026.

Run: python scripts/backtest_hold_rule.py
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pipeline import forecast as fc  # noqa: E402

H, CALL = 2, np.log(1.05)


def replay():
    panel = fc.add_hold_inputs(fc.add_seasonal(fc.add_drivers(fc.weekly_panel())))
    usable = panel.dropna(subset=["lp"])
    fit, pred = fc.METHODS[fc.MODEL]
    out = []
    for Y in range(fc.FIRST_TEST_YEAR, int(panel["year"].max()) + 1):
        train = usable[usable["week"] + pd.Timedelta(weeks=H) < pd.Timestamp(f"{Y}-01-01")].dropna(subset=[f"y{H}"])
        test = usable[usable["year"] == Y].dropna(subset=[f"y{H}"])
        out.append(test[["commodity", "market", "week", "year", "sp2", "below8", "gap", "tone"]].assign(
            y=test[f"y{H}"].to_numpy(), p=pred(fit(train, H), test, H)))
    r = pd.concat(out, ignore_index=True)
    r["a"], r["n"] = np.abs(np.expm1(r["p"]) - np.expm1(r["y"])), np.abs(np.expm1(r["y"]))
    use = pd.Series(True, index=r.index)
    for Y, cur in r.groupby("year"):
        prior = r[r["year"] < Y].groupby(["commodity", "market"])[["a", "n"]].mean()
        ok = {k: v["a"] <= v["n"] for k, v in prior.iterrows()}
        use.loc[cur.index] = [ok.get(k, True) for k in zip(cur["commodity"], cur["market"])]
    r["p"] = np.where(use, r["p"], 0.0)
    return r


def rules(r):
    sp, below, p = r["sp2"].to_numpy(dtype=float), r["below8"].fillna(False).to_numpy(dtype=bool), r["p"].to_numpy()
    tone = r["tone"].fillna(0).to_numpy()
    against = lambda x: ((p < 0) & (sp > x)) | ((p > 0) & (sp < -x))  # noqa: E731
    return {"no rule": np.zeros(len(r), bool), "live: sp 5% or long low": against(0.05) | ((p > 0) & below),
            "sp 5% only": against(0.05), "sp 10% only": against(0.10), "sp 15% only": against(0.15),
            "long low only": (p > 0) & below, "sp 10% or long low": against(0.10) | ((p > 0) & below),
            "long low unless USDA says firm": (p > 0) & below & (tone <= 0),
            "sp 10%, or long low unless firm": against(0.10) | ((p > 0) & below & (tone <= 0))}


def show(name, r, hold):
    called = (np.abs(r["p"].to_numpy()) >= CALL) & ~hold
    y, p = r["y"].to_numpy(), r["p"].to_numpy()
    good = np.sign(p) == np.sign(y)
    big = np.abs(y) >= np.log(1.10)
    up = called & (p > 0)
    print(f"{name:34s} calls {called.sum():5d} right {good[called].mean() * 100:5.1f}%  firming {up.sum():5d} right "
          f"{good[up].mean() * 100:5.1f}%  big called {(called & big & good).sum() / big.sum() * 100:4.1f}%  "
          f"wrong way {(called & big & ~good).sum() / big.sum() * 100:4.1f}%", flush=True)


def main():
    r = replay()
    for label, part in (("2021-2023", r["year"] <= 2023), ("2024-2026", r["year"] >= 2024)):
        print(label)
        sub = r[part].reset_index(drop=True)
        for name, hold in rules(sub).items():
            show(name, sub, hold)


if __name__ == "__main__":
    main()
