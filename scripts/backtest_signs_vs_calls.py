"""When a Sign of a move fires, how does it do by what the two-week forecast says for the headline pack? 2021-2026.

Run: python scripts/backtest_signs_vs_calls.py
"""
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "scripts")]
from backtest_hold_rule import replay  # noqa: E402
from pipeline import alerts, signals  # noqa: E402
from pipeline import forecast as fc  # noqa: E402

CALL, FOLLOW = np.log(1.05), np.log(1.05)

panel = fc.add_hold_inputs(fc.add_seasonal(fc.add_drivers(fc.weekly_panel())))
print("panel cols", [c for c in panel.columns if c in ("headline", "series_id", "y1", "y2", "sp", "tone")], flush=True)
r = replay()
print("replay rows", len(r), flush=True)

series = pd.read_csv(ROOT / "data/export/series.csv")
hl = series[series["headline"].astype(str).str.upper().isin(["Y", "TRUE", "1"])]
print("headlines", len(hl), flush=True)

# replay keeps no series id, so rebuild the frame in the same row order
usable = panel.dropna(subset=["lp"])
keys = []
for Y in range(fc.FIRST_TEST_YEAR, int(panel["year"].max()) + 1):
    test = usable[usable["year"] == Y].dropna(subset=["y2"])
    keys.append(test[["series_id", "sp", "y1"]])
k = pd.concat(keys, ignore_index=True)
assert len(k) == len(r)
r = pd.concat([r, k], axis=1)
r = r[r["series_id"].isin(set(hl["series_id"]))].copy()
print("headline rows", len(r), flush=True)

term = signals.load("terminal")
t_chg = signals.index_changes(term[term["market"].isin(alerts.TERMINALS)]).rename("tc").reset_index()
r = r.merge(t_chg, on=["commodity", "market", "week"], how="left")
rules = alerts.load_rules()
print("rules", len(rules), flush=True)

rows = []
for x in r.itertuples():
    sp_dir = "up" if x.sp >= math.log(1.10) else "down" if x.sp <= math.log(0.90) else None
    if sp_dir and pd.notna(x.tc):
        caught = (sp_dir == "up" and x.tc >= math.log(1.03)) or (sp_dir == "down" and x.tc <= math.log(0.97))
        if not caught and ("sp_lead", x.commodity, x.market, sp_dir) in rules:
            rows.append(("sp_lead", sp_dir, x))
    if pd.notna(x.tone):
        td = "up" if round(x.tone) >= 1 else "down" if round(x.tone) <= -1 else None
        if td and ("usda_tone", x.commodity, x.market, td) in rules:
            rows.append(("usda_tone", td, x))

out = []
for sig, d, x in rows:
    s = 1 if d == "up" else -1
    held = bool(fc.held(np.array([x.p]), np.array([x.sp2]), np.array([bool(x.below8) if pd.notna(x.below8) else False]),
                        np.array([0 if pd.isna(x.tone) else x.tone]))[0])
    fcall = 0 if abs(x.p) < CALL else int(np.sign(x.p))
    view = "held" if fcall and held else "steady" if not fcall else "agrees" if fcall == s else "opposite"
    y = x.y1 if sig == "usda_tone" else x.y
    out.append({"sig": sig, "view": view, "year": x.year, "hit": s * y >= FOLLOW if pd.notna(y) else np.nan,
                "same": s * y > 0 if pd.notna(y) else np.nan, "rev": s * y <= -FOLLOW if pd.notna(y) else np.nan,
                "flat": abs(y) < FOLLOW if pd.notna(y) else np.nan, "item": x.commodity})
o = pd.DataFrame(out).dropna(subset=["hit"])
for c in ("hit", "same", "rev", "flat"):
    o[c] = o[c].astype(float)
print("\nAll sign firings, 2021-2026, headline pack (scored on its own horizon)")
print((o.groupby(["sig", "view"])[["hit", "same", "rev", "flat"]].mean() * 100).round(1).join(o.groupby(["sig", "view"]).size().rename("n")).to_string())
print("\nSplit by period, hit% (n)")
o["part"] = np.where(o["year"] <= 2023, "2021-23", "2024-26")
print(o.groupby(["sig", "view", "part"])["hit"].agg(["mean", "size"]).round(3).to_string())
print("\nBase: any headline week moved 5%+ one way in 2 weeks", round((np.abs(r["y"]) >= FOLLOW).mean() * 100, 1))
