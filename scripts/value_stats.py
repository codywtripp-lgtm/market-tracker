"""Evidence for the "why buyers use it" page: how the brief's calls would have done, 2021-2026.

    python scripts/value_stats.py

Replays the 2-week forecast walk-forward (same model, same honest per-item choice of model vs.
"no change" using only earlier years) and scores the calls the brief makes: when it says a price
will rise or ease by 5%+ within two weeks, how often did it move that way, and by how much per case.
Also summarises the alert rules. Writes data/export/value.json (read by scripts/build_site.py).
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pipeline import forecast as fc  # noqa: E402
from pipeline import store  # noqa: E402

H = 2
CALL = 0.05


def replay():
    panel = fc.add_seasonal(fc.add_drivers(fc.weekly_panel()))
    usable = panel.dropna(subset=["lp"])
    fit_fn, pred_fn = fc.METHODS[fc.MODEL]
    out = []
    for Y in range(fc.FIRST_TEST_YEAR, int(panel["year"].max()) + 1):
        start = pd.Timestamp(f"{Y}-01-01")
        train = usable[(usable["week"] + pd.Timedelta(weeks=H) < start)].dropna(subset=[f"y{H}"])
        test = usable[usable["year"] == Y].dropna(subset=[f"y{H}"])
        if len(train) < 500 or test.empty:
            continue
        out.append(test[["commodity", "market", "week", "year", "compare_price", f"y{H}"]]
                   .assign(pred=pred_fn(fit_fn(train, H), test, H)))
    r = pd.concat(out, ignore_index=True).rename(columns={f"y{H}": "y"})
    r["ape_model"] = np.abs(np.expm1(r["pred"]) - np.expm1(r["y"]))
    r["ape_naive"] = np.abs(np.expm1(r["y"]))
    # per-item choice from earlier years only (as the live forecast does)
    use = []
    for Y, cur in r.groupby("year", sort=True):
        prior = r[r["year"] < Y].groupby(["commodity", "market"])[["ape_model", "ape_naive"]].mean()
        ok = {k: row["ape_model"] <= row["ape_naive"] for k, row in prior.iterrows()}
        use.append(pd.Series([ok.get(k, True) for k in zip(cur["commodity"], cur["market"])], index=cur.index))
    r["final"] = np.where(pd.concat(use).sort_index(), r["pred"], 0.0)
    return r


def main():
    r = replay()
    calls = r[np.abs(np.expm1(r["final"])) >= CALL].copy()
    calls["move"] = np.expm1(calls["y"])
    calls["right"] = np.sign(calls["final"]) == np.sign(calls["move"])
    calls["dollars"] = np.sign(calls["final"]) * calls["move"] * calls["compare_price"]  # $/case in the called direction
    big = calls[calls["move"].abs() >= 0.10]
    by_c = (calls.groupby("commodity").agg(calls=("right", "size"), right=("right", "mean"),
                                           avg_dollars=("dollars", "mean"))
            .query("calls >= 30").sort_values("right", ascending=False))
    rules = pd.read_csv(store.DATA / "signals" / "rules.csv")
    good = rules[(rules["cases"] >= 15) & (rules["hit_rate"] >= 0.65) & (rules["hit_rate"] >= 1.5 * rules["base_rate"])]
    value = {
        "years": f"{fc.FIRST_TEST_YEAR}-{int(r['year'].max())}",
        "weeks_scored": int(len(r)),
        "calls": int(len(calls)),
        "calls_right_pct": round(100 * calls["right"].mean(), 1),
        "big_moves": int(len(big)),
        "big_moves_right_pct": round(100 * big["right"].mean(), 1),
        "avg_dollars_per_case": round(float(calls["dollars"].mean()), 2),
        "avg_dollars_when_right": round(float(calls.loc[calls["right"], "dollars"].mean()), 2),
        "by_commodity": [{"commodity": c, "calls": int(x["calls"]), "right_pct": round(100 * x["right"], 1),
                          "avg_dollars": round(float(x["avg_dollars"]), 2)} for c, x in by_c.iterrows()],
        "alert_rules": int(len(good)),
        "alert_cases": int(good["cases"].sum()),
        "alert_hit_pct": round(100 * good["hits"].sum() / good["cases"].sum(), 1),
        "alert_base_pct": round(100 * (good["base_rate"] * good["cases"]).sum() / good["cases"].sum(), 1),
    }
    (fc.EXPORT / "value.json").write_text(json.dumps(value, indent=1))
    print(json.dumps(value, indent=1))


if __name__ == "__main__":
    main()
