"""Backtest early-warning signals against the stored history.

    python scripts/backtest_signals.py          # writes backtest_output/

Question for each signal: when it fires, how often does the terminal price actually move
the way it says over the next 1-2 weeks, compared with the base rate (how often prices
move that way anyway)? A signal is only useful if its hit rate clearly beats the base rate.

Signals tested:
  1. Shipping-point lead: the shipping-point price index for a commodity jumps/drops >= 10%
     in a week -> terminal (NY/LA/CHI) follows within 2 weeks?
  2. USDA market tone: the reporters' own words ("higher", "firmer" / "lower", "weaker")
     this week -> terminal price up/down next week?
  3. Terminal momentum (baseline to beat): terminal already moved >= 10% this week ->
     keeps going next week?

Price index per commodity x market = mean weekly log change across all standard-grade
series (every pack/size) quoted in both weeks. Using changes, not levels, means packs with
different prices can be combined.
"""

import csv
import math
import re
from collections import defaultdict
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
OUT = ROOT / "backtest_output"

MOVE = 0.10          # signal threshold: 10% weekly move
FOLLOW = 0.05        # "followed" = terminal moved >= 5% the same way within the horizon
HORIZON = 2          # weeks
NON_STANDARD = re.compile(r"fair|poor|ordinary|holdover|decay|damage|scar|fine|mixed condition", re.I)
TERMINALS = ["New York", "Los Angeles", "Chicago"]

UP_WORDS = re.compile(r"\b(higher|firmer|stronger|advanc|increas)", re.I)
DOWN_WORDS = re.compile(r"\b(lower|weaker|declin|decreas)", re.I)


def tone_score(text):
    """+1 higher, -1 lower, 0 steady/mixed, None if no tone."""
    if not text:
        return None
    up, down = bool(UP_WORDS.search(text)), bool(DOWN_WORDS.search(text))
    if up and not down:
        return 1
    if down and not up:
        return -1
    return 0


def load(source):
    frames = []
    cols = ["report_date", "commodity", "variety", "pack_size", "item_size", "properties", "organic",
            "appearance", "condition", "quality", "unit_price", "market", "market_tone"]
    for path in sorted((RAW / source).glob("*/*.csv")):
        frames.append(pd.read_csv(path, usecols=cols, dtype=str, keep_default_na=False))
    df = pd.concat(frames, ignore_index=True)
    df["unit_price"] = pd.to_numeric(df["unit_price"], errors="coerce")
    df = df[df["unit_price"] > 0]
    std = ~(df["appearance"].str.contains(NON_STANDARD) | df["condition"].str.contains(NON_STANDARD)
            | df["quality"].str.contains(NON_STANDARD))
    df = df[std].copy()
    df["week"] = pd.to_datetime(df["report_date"]).dt.to_period("W-SUN").dt.start_time
    df["series"] = df[["market", "variety", "pack_size", "item_size", "properties", "organic"]].agg("|".join, axis=1)
    df["tone"] = df["market_tone"].map(tone_score)
    return df


def index_changes(df):
    """(commodity, market) -> Series of weekly mean log price change, indexed by week."""
    wk = df.groupby(["commodity", "market", "series", "week"])["unit_price"].median().reset_index()
    wk = wk.sort_values("week")
    wk["prev_week"] = wk.groupby(["commodity", "market", "series"])["week"].shift()
    wk["prev_price"] = wk.groupby(["commodity", "market", "series"])["unit_price"].shift()
    consecutive = (wk["week"] - wk["prev_week"]).dt.days == 7
    wk = wk[consecutive].copy()
    wk["chg"] = (wk["unit_price"] / wk["prev_price"]).map(math.log)
    return wk.groupby(["commodity", "market", "week"])["chg"].mean()


def forward(changes, weeks):
    """Sum of the next `weeks` weekly changes (log), aligned to the current week."""
    s = changes.copy()
    total = 0
    for k in range(1, weeks + 1):
        total = total + s.shift(-k, freq="7D").reindex(s.index)
    return total


def evaluate(signal, fwd, direction):
    """Hit rate when the signal fires vs. base rate over all weeks with a forward value."""
    both = pd.concat([signal, fwd], axis=1, keys=["sig", "fwd"]).dropna()
    if both.empty:
        return None
    moved = both["fwd"] >= math.log(1 + FOLLOW) if direction > 0 else both["fwd"] <= math.log(1 - FOLLOW)
    fired = both["sig"] == direction
    n = int(fired.sum())
    if n == 0:
        return None
    hit = moved[fired].mean()
    base = moved.mean()
    return {"fired": n, "hit_rate": round(hit, 3), "base_rate": round(base, 3), "lift": round(hit / base, 2) if base else None}


def main():
    OUT.mkdir(exist_ok=True)
    term = load("terminal")
    ship = load("shipping_point")
    term_chg = index_changes(term[term["market"].isin(TERMINALS)])
    # shipping point: combine all districts into one index per commodity
    ship = ship.assign(market="Shipping point")
    ship_chg = index_changes(ship)

    results = []
    for (commodity, mkt), _ in term_chg.groupby(level=[0, 1]):
        t = term_chg.loc[(commodity, mkt)]
        t.index = pd.DatetimeIndex(t.index)
        t = t.asfreq("7D")
        fwd = forward(t, HORIZON)
        fwd1 = forward(t, 1)

        # 1. shipping-point lead
        if (commodity, "Shipping point") in ship_chg.index.droplevel(2):
            sp = ship_chg.loc[(commodity, "Shipping point")]
            sp.index = pd.DatetimeIndex(sp.index)
            sp = sp.asfreq("7D")
            sig = pd.Series(0.0, index=sp.index)
            sig[sp >= math.log(1 + MOVE)] = 1
            sig[sp <= math.log(1 - MOVE)] = -1
            sig[sp.isna()] = float("nan")
            for d in (1, -1):
                r = evaluate(sig, fwd, d)
                if r:
                    results.append({"signal": "shipping point lead", "direction": "up" if d > 0 else "down",
                                    "commodity": commodity, "market": mkt, "horizon_weeks": HORIZON, **r})
            # 1b. the actionable case: shipping point moved, the terminal hasn't caught up yet
            #     (terminal moved < 3% the same way this week)
            same_week = t.reindex(sig.index)
            lagging = sig.copy()
            lagging[(sig == 1) & (same_week >= math.log(1.03))] = 0
            lagging[(sig == -1) & (same_week <= math.log(0.97))] = 0
            lagging[same_week.isna()] = float("nan")
            for d in (1, -1):
                r = evaluate(lagging, fwd, d)
                if r:
                    results.append({"signal": "shipping point lead, terminal not yet moved", "direction": "up" if d > 0 else "down",
                                    "commodity": commodity, "market": mkt, "horizon_weeks": HORIZON, **r})
            # correlation of this week's shipping-point change with terminal change k weeks later
            for k in range(0, 4):
                pair = pd.concat([sp, t.shift(-k)], axis=1).dropna()
                if len(pair) > 30:
                    results.append({"signal": f"corr sp->terminal lag {k}w", "direction": "",
                                    "commodity": commodity, "market": mkt, "horizon_weeks": k,
                                    "fired": len(pair), "hit_rate": round(pair.corr().iloc[0, 1], 3),
                                    "base_rate": "", "lift": ""})

        # 2. USDA tone at this terminal market (weekly average, rounded to -1/0/+1)
        tn = term[(term["commodity"] == commodity) & (term["market"] == mkt)].groupby("week")["tone"].mean()
        tn.index = pd.DatetimeIndex(tn.index)
        tsig = tn.round().clip(-1, 1)
        for d in (1, -1):
            r = evaluate(tsig, fwd1, d)
            if r:
                results.append({"signal": "USDA tone (terminal)", "direction": "up" if d > 0 else "down",
                                "commodity": commodity, "market": mkt, "horizon_weeks": 1, **r})

        # 3. momentum baseline
        msig = pd.Series(0.0, index=t.index)
        msig[t >= math.log(1 + MOVE)] = 1
        msig[t <= math.log(1 - MOVE)] = -1
        msig[t.isna()] = float("nan")
        for d in (1, -1):
            r = evaluate(msig, fwd1, d)
            if r:
                results.append({"signal": "terminal momentum", "direction": "up" if d > 0 else "down",
                                "commodity": commodity, "market": mkt, "horizon_weeks": 1, **r})

    fields = ["signal", "direction", "commodity", "market", "horizon_weeks", "fired", "hit_rate", "base_rate", "lift"]
    with open(OUT / "signals.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(results)

    # Summary: pooled across commodities, per signal / direction / market
    df = pd.DataFrame([r for r in results if not r["signal"].startswith("corr")])
    lines = ["# Signal backtest summary", "",
             f"Move threshold {MOVE:.0%}/week; 'followed' = terminal moved >= {FOLLOW:.0%} the same way.", ""]
    if not df.empty:
        df["hits"] = df["hit_rate"] * df["fired"]
        pooled = df.groupby(["signal", "direction", "market"]).agg(fired=("fired", "sum"), hits=("hits", "sum")).reset_index()
        base = df.assign(bw=df["base_rate"] * df["fired"]).groupby(["signal", "direction", "market"])["bw"].sum().values
        pooled["hit_rate"] = (pooled["hits"] / pooled["fired"]).round(3)
        pooled["base_rate"] = (base / pooled["fired"]).round(3)
        pooled["lift"] = (pooled["hit_rate"] / pooled["base_rate"]).round(2)
        lines.append(pooled.drop(columns="hits").to_markdown(index=False))
    corr = pd.DataFrame([r for r in results if r["signal"].startswith("corr")])
    if not corr.empty:
        lines += ["", "## Correlation: shipping-point weekly change vs terminal change k weeks later (median across commodities)", ""]
        lines.append(corr.groupby(["signal", "market"])["hit_rate"].median().round(3).reset_index()
                     .rename(columns={"hit_rate": "median_corr"}).to_markdown(index=False))
    (OUT / "summary.md").write_text("\n".join(lines))
    print("\n".join(lines))


if __name__ == "__main__":
    main()
