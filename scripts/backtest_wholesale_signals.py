"""Do USDA reporters' notes, or the peso, improve the wholesale forecast? Walk-forward test against the live model.

Signals per commodity and week, from every shipping-point row (priced or not, since a short market often has no price):
  short     share of district-days where the reporter says supplies are short (insufficient, too few hands, very light)
  short_chg change in `short` from 2 weeks earlier
  disrupt   share of district-days mentioning a disruption (rain, freeze, hurricane, crossings, strike, ...)
  note_tone reporters' comments: share saying higher minus share saying lower
  areas     log(growing areas reporting / their average over the prior 8 weeks): an area finishing or starting
  peso      4-week change in pesos per dollar (FRED DEXMXUS)

Bar to adopt: at least a 1% smaller average miss (forecast.MIN_GAIN), with no drop in call accuracy.

Run: python scripts/backtest_wholesale_signals.py
"""

import io
import re
import sys
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pipeline import forecast as fc, store  # noqa: E402

SHORT = re.compile(r"insufficient|too few|few hands|very light|very limited|short suppl", re.I)
DISRUPT = re.compile(r"rain|wet field|freeze|frost|cold|heat|hurricane|storm|flood|weather|crossing|border|strike|smoke|fire", re.I)
HIGHER, LOWER = re.compile(r"higher|firm", re.I), re.compile(r"lower|weak", re.I)


def notes():
    frames = []
    for p in sorted((store.DATA / "raw" / "shipping_point").glob("*/*.csv")):
        frames.append(pd.read_csv(p, usecols=["report_date", "commodity", "market", "reporter_comment", "market_tone"],
                                  dtype=str, keep_default_na=False))
    df = pd.concat(frames, ignore_index=True)
    df["text"] = df["reporter_comment"] + " " + df["market_tone"]
    day = df.groupby(["report_date", "commodity", "market"])["text"].agg(" ".join).reset_index()
    day["week"] = pd.to_datetime(day["report_date"]).dt.to_period("W-SUN").dt.start_time
    day["short"] = day["text"].str.contains(SHORT).astype(float)
    day["disrupt"] = day["text"].str.contains(DISRUPT).astype(float)
    day["note_tone"] = day["text"].str.contains(HIGHER).astype(float) - day["text"].str.contains(LOWER).astype(float)
    wk = day.groupby(["commodity", "week"]).agg(short=("short", "mean"), disrupt=("disrupt", "mean"),
                                                note_tone=("note_tone", "mean"), n=("market", "nunique")).reset_index()
    wk = wk.sort_values(["commodity", "week"])
    g = wk.groupby("commodity")
    wk["short_chg"] = wk["short"] - g["short"].shift(2)
    wk["areas"] = np.log(wk["n"] / g["n"].transform(lambda s: s.shift(1).rolling(8, min_periods=4).mean()))
    return wk.drop(columns="n")


def peso():
    url = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DEXMXUS"
    with urllib.request.urlopen(url, timeout=60) as r:
        d = pd.read_csv(io.BytesIO(r.read()), na_values=".")
    d.columns = ["date", "rate"]
    d["week"] = pd.to_datetime(d["date"]).dt.to_period("W-SUN").dt.start_time
    w = d.dropna().groupby("week")["rate"].mean().rename("rate").reset_index()
    w["peso"] = np.log(w["rate"] / w["rate"].shift(4))
    return w[["week", "peso"]]


def score(panel, cols, name, last_year):
    fit, pred = fc._by_group(cols, keys=("commodity", "market"))
    usable = panel.dropna(subset=["lp"])
    out = []
    for h in fc.HORIZONS:
        for Y in range(fc.FIRST_TEST_YEAR, last_year + 1):
            train = usable[usable["week"] + pd.Timedelta(weeks=h) < pd.Timestamp(f"{Y}-01-01")].dropna(subset=[f"y{h}"])
            test = usable[usable["year"] == Y].dropna(subset=[f"y{h}"])
            if len(train) >= 500 and len(test):
                out.append(pd.DataFrame({"h": h, "year": Y, "commodity": test["commodity"].to_numpy(),
                                         "p": pred(fit(train, h), test, h), "y": test[f"y{h}"].to_numpy()}))
    r = pd.concat(out)
    r["ape"] = np.abs(np.expm1(r["p"]) - np.expm1(r["y"])) * 100
    two = r[r["h"] == 2]
    calls = two[two["p"].abs() >= np.log(1.05)]
    right = (np.sign(calls["p"]) == np.sign(calls["y"])).mean() * 100
    big = two[two["y"].abs() >= np.log(1.10)]
    caught = ((np.sign(big["p"]) == np.sign(big["y"])) & (big["p"].abs() >= np.log(1.05))).mean() * 100
    wrong = ((np.sign(big["p"]) != np.sign(big["y"])) & (big["p"].abs() >= np.log(1.05))).mean() * 100
    print(f"{name:34s} avg miss {r.groupby('h')['ape'].mean().mean():6.3f}%  2wk {two['ape'].mean():6.3f}%  "
          f"calls {len(calls):5d} right {right:5.1f}%  big moves caught {caught:5.1f}%  wrong way {wrong:4.1f}%")
    return r


def main():
    panel = fc.add_seasonal(fc.add_drivers(fc.weekly_panel()))
    panel = panel.merge(notes(), on=["commodity", "week"], how="left").merge(peso(), on="week", how="left")
    last_year = int(panel["year"].max())
    base = fc.BASE
    print("weeks with notes:", panel["short"].notna().mean().round(3), " with peso:", panel["peso"].notna().mean().round(3))
    score(panel, base, "live model", last_year)
    for name, extra in [("+ short supply", ["short"]), ("+ short + its change", ["short", "short_chg"]),
                        ("+ disruption mentions", ["disrupt"]), ("+ reporters' note tone", ["note_tone"]),
                        ("+ areas starting/finishing", ["areas"]), ("+ peso", ["peso"]),
                        ("+ all", ["short", "short_chg", "disrupt", "note_tone", "areas", "peso"])]:
        score(panel, base + extra, name, last_year)


if __name__ == "__main__":
    main()
