"""Early-warning alerts, run after every daily fetch.

    python -m pipeline.alerts

Checks the last 7 days against the prior 7 days and fires an alert only when a signal
that has a strong 10-year track record for that commodity, market and direction is on
(rules in data/signals/rules.csv, produced by scripts/backtest_signals.py):

  sp_lead    shipping-point price index moved >= 10% but the terminal market hasn't
             moved 3% the same way yet -> terminal usually follows within 2 weeks
  usda_tone  USDA reporters at the terminal call the market higher/lower -> next week

Writes:
  data/export/alerts.json   current alerts (the website shows these)
  data/alerts/log.csv       every alert ever fired (for dedup and a public track record)
  new_alerts.md             only when new alerts fired today (the workflow opens a GitHub issue)

Details: docs/alerts.md
"""

import csv
import datetime as dt
import json
import math
import re
from pathlib import Path

import pandas as pd

from . import store

RULES = store.DATA / "signals" / "rules.csv"
LOG = store.DATA / "alerts" / "log.csv"
OUT_JSON = store.DATA / "export" / "alerts.json"
NEW_MD = store.DATA.parent / "new_alerts.md"

# Same thresholds as the backtest
MOVE = 0.10
NOT_YET = 0.03
# A rule must have this track record to alert
MIN_CASES = 15
MIN_HIT_RATE = 0.65
MIN_LIFT = 1.5

TERMINALS = ["New York", "Los Angeles", "Chicago"]
NON_STANDARD = re.compile(r"fair|poor|ordinary|holdover|decay|damage|scar|fine|mixed condition", re.I)
UP_WORDS = re.compile(r"\b(higher|firmer|stronger|advanc|increas)", re.I)
DOWN_WORDS = re.compile(r"\b(lower|weaker|declin|decreas)", re.I)
LOG_FIELDS = ["alert_id", "first_seen", "signal", "commodity", "market", "direction", "headline"]


def tone_score(text):
    if not text:
        return None
    up, down = bool(UP_WORDS.search(text)), bool(DOWN_WORDS.search(text))
    return 1 if up and not down else -1 if down and not up else 0


def load_recent(source, since):
    frames = []
    for path in sorted((store.DATA / "raw" / source).glob("*/*.csv")):
        if path.stem >= since[:7]:
            frames.append(pd.read_csv(path, dtype=str, keep_default_na=False))
    if not frames:
        return pd.DataFrame()
    df = pd.concat(frames, ignore_index=True)
    df = df[df["report_date"] >= since].copy()
    df["unit_price"] = pd.to_numeric(df["unit_price"], errors="coerce")
    df = df[df["unit_price"] > 0]
    std = ~(df["appearance"].str.contains(NON_STANDARD) | df["condition"].str.contains(NON_STANDARD)
            | df["quality"].str.contains(NON_STANDARD))
    df = df[std].copy()
    df["series"] = df[["market", "variety", "pack_size", "item_size", "properties", "organic"]].agg("|".join, axis=1)
    return df


def window_change(df, today):
    """(commodity, market) -> mean log change of series medians, last 7 days vs the 7 before."""
    cur_start = (today - dt.timedelta(days=6)).isoformat()
    prev_start = (today - dt.timedelta(days=13)).isoformat()
    df = df[df["report_date"] >= prev_start].copy()
    df["win"] = (df["report_date"] >= cur_start).map({True: "cur", False: "prev"})
    med = df.groupby(["commodity", "market", "series", "win"])["unit_price"].median().unstack("win")
    if "cur" not in med or "prev" not in med:
        return pd.Series(dtype=float)
    med = med.dropna(subset=["cur", "prev"])
    med["chg"] = (med["cur"] / med["prev"]).map(math.log)
    return med.groupby(["commodity", "market"])["chg"].mean()


def load_rules():
    if not RULES.exists():
        return {}
    rules = {}
    with open(RULES, newline="") as f:
        for r in csv.DictReader(f):
            cases, hit, base = int(r["cases"]), float(r["hit_rate"]), float(r["base_rate"] or 0)
            if cases >= MIN_CASES and hit >= MIN_HIT_RATE and base and hit / base >= MIN_LIFT:
                rules[(r["signal"], r["commodity"], r["market"], r["direction"])] = r
    return rules


def pct(x):
    return f"{(math.exp(x) - 1) * 100:+.0f}%"


def evaluate(term, ship, today, rules):
    alerts = []
    t_chg = window_change(term[term["market"].isin(TERMINALS)], today) if not term.empty else pd.Series(dtype=float)
    s_chg = window_change(ship.assign(market="Shipping point"), today) if not ship.empty else pd.Series(dtype=float)
    since = (today - dt.timedelta(days=6)).isoformat()

    for (commodity, market), tc in t_chg.items():
        # sp_lead
        sc = s_chg.get((commodity, "Shipping point"))
        if sc is not None and not math.isnan(sc):
            direction = "up" if sc >= math.log(1 + MOVE) else "down" if sc <= math.log(1 - MOVE) else None
            caught_up = direction and ((direction == "up" and tc >= math.log(1 + NOT_YET)) or
                                       (direction == "down" and tc <= math.log(1 - NOT_YET)))
            rule = rules.get(("sp_lead", commodity, market, direction)) if direction and not caught_up else None
            if rule:
                word = "up" if direction == "up" else "down"
                alerts.append({
                    "signal": "sp_lead", "commodity": commodity, "market": market, "direction": direction,
                    "headline": f"{commodity}: shipping point {word} {pct(sc).lstrip('+-')} this week; {market} hasn't followed yet ({pct(tc)} this week).",
                    "expect": f"Expect {market} prices to {'rise' if direction == 'up' else 'fall'} within ~2 weeks.",
                    "record": f"{market} followed {rule['hits']} of the last {rule['cases']} times (normally {float(rule['base_rate']):.0%}).",
                    "hit_rate": float(rule["hit_rate"]), "sp_change": round((math.exp(sc) - 1) * 100, 1),
                    "terminal_change": round((math.exp(tc) - 1) * 100, 1),
                })
        # usda_tone
        rows = term[(term["commodity"] == commodity) & (term["market"] == market) & (term["report_date"] >= since)]
        scores = [s for s in rows["market_tone"].map(tone_score) if s is not None]
        if scores:
            avg = sum(scores) / len(scores)
            direction = "up" if round(avg) >= 1 else "down" if round(avg) <= -1 else None
            rule = rules.get(("usda_tone", commodity, market, direction)) if direction else None
            if rule:
                # quote the comment that actually says "higher"/"lower", not a "steady" one from the same week
                want = 1 if direction == "up" else -1
                tones = rows.loc[rows["market_tone"].map(tone_score) == want, "market_tone"]
                tone = tones.mode().iat[0] if not tones.empty else ""
                alerts.append({
                    "signal": "usda_tone", "commodity": commodity, "market": market, "direction": direction,
                    "headline": f"{commodity}: USDA reporters in {market} call the market {'higher' if direction == 'up' else 'lower'} (“{tone.capitalize()}”).",
                    "expect": f"Expect {market} prices to {'rise' if direction == 'up' else 'fall'} next week.",
                    "record": f"That happened {rule['hits']} of the last {rule['cases']} times (normally {float(rule['base_rate']):.0%}).",
                    "hit_rate": float(rule["hit_rate"]),
                })
    alerts.sort(key=lambda a: -a["hit_rate"])
    return alerts


def week_of(today):
    return (today - dt.timedelta(days=today.weekday())).isoformat()


def main(today=None):
    today = today or dt.date.today()
    since = (today - dt.timedelta(days=20)).isoformat()
    rules = load_rules()
    alerts = evaluate(load_recent("terminal", since), load_recent("shipping_point", since), today, rules)

    for a in alerts:
        # One alert per signal/item/market/direction per week, so a running signal isn't re-sent daily.
        a["id"] = f"{a['signal']}|{a['commodity']}|{a['market']}|{a['direction']}|{week_of(today)}"

    LOG.parent.mkdir(parents=True, exist_ok=True)
    seen = set()
    if LOG.exists():
        with open(LOG, newline="") as f:
            seen = {r["alert_id"] for r in csv.DictReader(f)}
    new = [a for a in alerts if a["id"] not in seen]
    write_header = not LOG.exists()
    with open(LOG, "a", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        if write_header:
            w.writerow(LOG_FIELDS)
        for a in new:
            w.writerow([a["id"], today.isoformat(), a["signal"], a["commodity"], a["market"], a["direction"], a["headline"]])

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps({"asOf": today.isoformat(), "alerts": alerts}, indent=1))

    if new:
        lines = [f"**{len(new)} new price alert{'s' if len(new) > 1 else ''}** ({today.isoformat()})", ""]
        for a in new:
            lines += [f"- **{a['headline']}** {a['expect']} _{a['record']}_"]
        lines += ["", "See the dashboard: https://codywtripp-lgtm.github.io/market-tracker/", "",
                  "@codywtripp-lgtm"]
        NEW_MD.write_text("\n".join(lines))
    elif NEW_MD.exists():
        NEW_MD.unlink()
    print(f"alerts: {len(alerts)} active, {len(new)} new, {len(rules)} qualifying rules")


if __name__ == "__main__":
    main()
