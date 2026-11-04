"""Should a wholesale price follow one growing area instead of blending every area quoted that day? 2021-2026.

Main area, chosen with no look-ahead as export.main_areas does it: quoted most over the previous 28 days, ties to the most
pounds shipped in the four weeks before. Compared with the live blend (median of all quotes that day):
  1. how much the price jumps week to week
  2. two-week forecast miss and calls, each scored on its own series
  3. both sets of calls scored on the main-area price, the one a buyer would be quoted
  4. forecast change measured from the week's average or from the latest day

Run: python scripts/backtest_main_area.py
"""

import csv
import statistics
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

sys.path[:0] = [str(Path(__file__).resolve().parents[1]), str(Path(__file__).resolve().parent)]
from backtest_hold_rule import replay  # noqa: E402
from pipeline import cpi, export, store  # noqa: E402
from pipeline import forecast as fc  # noqa: E402

CALL, H = np.log(1.05), 2
DAYS = 28


def main_area_prices(by_day, shipped):
    """{date: price} following the main area, as live."""
    leads = export.main_areas(by_day, shipped)
    return {d: export.daily_value(rs, leads[d])["price"] for d, rs in by_day.items()}


def rebuild(tmp):
    """prices_weekly.csv on main-area prices, same columns and series as the live file."""
    deflator = cpi.Deflator(cpi.load())
    grouped = export.load(r for r in store.iter_all() if r["market_type"] == "terminal")
    shipments = export.load_shipments()
    rows = list(csv.DictReader(open(fc.EXPORT / "prices_weekly.csv", encoding="utf-8")))
    base = {}
    for r in rows:
        base.setdefault(r["series_id"], r)
    new = []
    for key, by_day in grouped.items():
        sid = export.series_id(key)
        if sid not in base:
            continue
        weeks = defaultdict(list)
        for d, p in sorted(main_area_prices(by_day, lambda a, d, c=key[2]: export.shipped_before(shipments, c, a, d)).items()):
            weeks[export.iso_week_start(pd.Timestamp(d).date())].append(p)
        for w, ps in sorted(weeks.items()):
            v = round(statistics.mean(ps), 4)
            new.append({**base[sid], "week_start": w.isoformat(), "compare_price": v, "last_price": ps[-1],
                        "real_compare_price": round(v * deflator.factor(w.isoformat()), 4), "days": len(ps)})
    with open(tmp / "prices_weekly.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(new)
    (tmp / "series.csv").write_bytes((fc.EXPORT / "series.csv").read_bytes())
    return pd.DataFrame(new)


def keyed():
    """replay() with the series id it leaves out, in the same row order, plus each series' price and latest price."""
    panel = fc.add_hold_inputs(fc.add_seasonal(fc.add_drivers(fc.weekly_panel())))
    r = replay()
    usable = panel.dropna(subset=["lp"])
    k = []
    for Y in range(fc.FIRST_TEST_YEAR, int(panel["year"].max()) + 1):
        t = usable[usable["year"] == Y].dropna(subset=[f"y{H}"])
        k.append(t[["series_id", "compare_price", "last_price"]])
    return pd.concat([r, pd.concat(k, ignore_index=True)], axis=1)


def held(d, p):
    return fc.held(p, d["sp2"].to_numpy(dtype=float), d["below8"].fillna(False).to_numpy(dtype=bool), d["tone"].fillna(0).to_numpy())


def score(name, d, p, y, hold=True):
    called = np.abs(p) >= CALL
    if hold:
        called &= ~held(d, p)
    right = np.sign(p) == np.sign(y)
    big = np.abs(y) >= np.log(1.10)
    miss = np.abs(np.expm1(p) - np.expm1(y)) * 100
    print(f"{name:44s} miss {miss.mean():6.2f}%  calls {called.sum():5d} right {right[called].mean() * 100:5.1f}%  "
          f"big called {(called & big & right).sum() / big.sum() * 100:4.1f}%  wrong way {(called & big & ~right).sum() / big.sum() * 100:4.1f}%", flush=True)


def main():
    head = {r["series_id"] for r in csv.DictReader(open(fc.EXPORT / "series.csv", encoding="utf-8"))
            if r["headline"] == "Y" and r["market_type"] == "terminal"}
    live = keyed()
    print("live done", len(live), flush=True)
    real_export = fc.EXPORT
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        rebuild(tmp)
        fc.EXPORT = tmp
        area = keyed()
    fc.EXPORT = real_export
    print("main area done", len(area), flush=True)
    key = ["series_id", "week"]
    d = live.merge(area[key + ["p", "y", "compare_price", "last_price"]], on=key, suffixes=("", "_a"))
    d = d[d["series_id"].isin(head)].reset_index(drop=True)
    print("rows, headline series", len(d), d["series_id"].nunique())

    for name, col in (("blend", "compare_price"), ("main area", "compare_price_a")):
        w = d.sort_values(key)
        c = np.log(w[col]).groupby(w["series_id"]).diff().abs().dropna()
        print(f"{name:10s} weekly change: median {c.median() * 100:5.2f}%  mean {c.mean() * 100:5.2f}%  weeks 20%+ {(c >= np.log(1.2)).mean() * 100:5.2f}%")

    print("\nEach on its own series")
    score("blend", d, d["p"].to_numpy(), d["y"].to_numpy())
    score("main area", d, d["p_a"].to_numpy(), d["y_a"].to_numpy())
    print("\nBoth scored on the main-area price")
    score("calls from the blend model", d, d["p"].to_numpy(), d["y_a"].to_numpy())
    score("calls from the main-area model", d, d["p_a"].to_numpy(), d["y_a"].to_numpy())
    print("\nMeasured from the latest day (main-area model; target: week average two weeks on vs latest day)")
    y_last = np.log(d["compare_price_a"] * np.exp(d["y_a"]) / d["last_price_a"]).to_numpy()
    from_avg = d["p_a"].to_numpy()
    from_last = np.log(d["compare_price_a"] * np.exp(d["p_a"]) / d["last_price_a"]).to_numpy()
    score("change from the week's average", d, from_avg, y_last)
    score("change from the latest day", d, from_last, y_last)
    print("\nBy period, main-area model vs blend model, both on main-area price: miss")
    for part, m in (("2021-23", d["year"] <= 2023), ("2024-26", d["year"] >= 2024)):
        s = d[m].reset_index(drop=True)
        score(f"{part} blend model", s, s["p"].to_numpy(), s["y_a"].to_numpy())
        score(f"{part} main-area model", s, s["p_a"].to_numpy(), s["y_a"].to_numpy())


if __name__ == "__main__":
    main()
