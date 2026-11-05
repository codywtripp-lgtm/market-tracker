"""Wholesale meat: USDA boxed beef (daily, $/cwt, FOB plant, negotiated sales) and chicken (weekly, cents/lb).

    python -m pipeline.meat

Only national prices: USDA's boxed beef report has no city prices, and its chicken report splits by city only for
whole birds. Reads the raw rows directly, so nothing here touches the produce series or their forecast.

Whole chicken is priced delivered and chicken parts FOB (USDA report 3646). The beef number after the IMPS code is
USDA's fat limitation. Test and rules: scripts/backtest_meat.py, docs/forecast.md.

Writes data/export/meat.json (read by pipeline/meat_view.py) and logs each night's calls to data/forecasts/meat_log.csv.
"""

import csv
import datetime as dt
import json

import numpy as np
import pandas as pd

from . import brief, cpi, export, forecast as fc, store

# slug, name, USDA variety, USDA section
BEEF = [
    ("choice-cutout", "Choice cutout", "Cutout 600-900 lb", "Choice"),
    ("select-cutout", "Select cutout", "Cutout 600-900 lb", "Select"),
    ("ribeye-lip-on-109e", "Ribeye, lip-on, bone-in (109E)", "Rib, ribeye, lip-on, bn-in (109E  1)", "Choice Cuts"),
    ("strip-loin-180", "Strip loin, boneless (180)", "Loin, strip, bnls, 0x1 (180  3)", "Choice Cuts"),
    ("tenderloin-189a", "Tenderloin, trimmed, heavy (189A)", "Loin, tndrloin, trmd, heavy (189A  4)", "Choice Cuts"),
    ("top-butt-184", "Top butt, boneless (184)", "Loin, top butt, boneless (184  3)", "Choice Cuts"),
    ("flap-185a", "Bottom sirloin flap (185A)", "Loin, bottom sirloin, flap (185A  4)", "Choice Cuts"),
    ("tri-tip-185c", "Tri-tip (185C)", "Loin, sirloin, tri-tip (185C  1)", "Choice Cuts"),
    ("chuck-roll-116a", "Chuck roll, neck-off (116A)", "Chuck, roll, lxl, neck/off (116A  3)", "Choice Cuts"),
    ("shoulder-clod-114a", "Shoulder clod, trimmed (114A)", "Chuck, shoulder clod, trmd (114A  3)", "Choice Cuts"),
    ("chuck-short-rib-130", "Chuck short rib (130)", "Chuck, short rib (130  4)", "Choice Cuts"),
    ("plate-short-rib-123a", "Plate short rib (123A)", "Short Plate, short rib (123A  3)", "Choice Cuts"),
    ("brisket-120", "Brisket, deckle-off (120)", "Brisket, deckle-off, bnls (120  1)", "Choice Cuts"),
    ("flank-steak-193", "Flank steak (193)", "Flank, flank steak (193  4)", "Choice Cuts"),
    ("top-round-168", "Top inside round (168)", "Round, top inside round (168  3)", "Choice Cuts"),
    ("outside-round-171b", "Outside round (171B)", "Round, outside round (171B  3)", "Choice Cuts"),
    ("eye-of-round-171c", "Eye of round (171C)", "Round, eye of round (171C  3)", "Choice Cuts"),
    ("knuckle-167a", "Knuckle, peeled (167A)", "Round, knuckle, peeled (167A  4)", "Choice Cuts"),
    ("ground-beef-73", "Ground beef, 73% lean", "Ground Beef 73%", "Ground Beef"),
    ("ground-beef-81", "Ground beef, 81% lean", "Ground Beef 81%", "Ground Beef"),
    ("ground-beef-85", "Ground beef, 85% lean", "Ground Beef 85%", "Ground Beef"),
    ("ground-beef-93", "Ground beef, 93% lean", "Ground Beef 93%", "Ground Beef"),
]
# slug, name, USDA item, USDA size
CHICKEN = [
    ("whole-chicken-wog", "Whole chicken, without giblets (WOG)", "WOG", "All Sizes"),
    ("boneless-skinless-breast", "Boneless skinless breast", "Breast - B/S", ""),
    ("boneless-skinless-thighs", "Boneless skinless thighs", "Thighs - B/S", ""),
    ("chicken-tenders", "Tenderloins", "Tenderloins", ""),
    ("chicken-wings", "Whole wings", "Wings - Whole", ""),
    ("leg-quarters", "Leg quarters, bulk", "Leg quarters - Bulk", ""),
    ("drumsticks", "Drumsticks", "Drumsticks", ""),
    ("bone-in-legs", "Bone-in legs", "Legs - Bone-in", ""),
]
NAMES = {slug: name for slug, name, *_ in BEEF + CHICKEN}
OUT = store.DATA / "export" / "meat.json"
LOG = store.DATA / "forecasts" / "meat_log.csv"
H = 2
HORIZONS = [1, 2]
TREND_WEEKS = 56
FIRST_TEST = {"Beef": 2021, "Chicken": 2025}  # chicken starts in August 2022, and a seasonal needs two past years
COLS = ["seasonal", "gap", "mom1", "mom4", "last"]
ACTION = {
    "firming": "Cover your needs now, lock price with your supplier where you can, and update customer quotes before it moves.",
    "softening": "Buy to need and stay on the open market; don't lock price at today's level.",
    "topping": "Still firm this week, then easing. Buy to need, don't lock price at the top, and expect relief in two to four weeks.",
    "bottoming": "Still easing this week, then firming. Use the dip to lock price with your supplier for the next few weeks.",
    "expensive": "High for the season with no relief in sight. Look at other cuts or grades, and price quotes to cover it.",
    "cheap": "Good value for the season: a good item to feature on specials and promotions.",
}


def rows():
    """One row per item per report date, in dollars per lb: slug, kind, date, price, low, high."""
    out = []
    b = pd.DataFrame(store.iter_all("beef"))
    for slug, _, variety, section in BEEF:
        m = (b["variety"] == variety) & (b["grade"] == section if section in ("Choice", "Select") else b["pack_size"] == section)
        out.append(b[m].assign(slug=slug, kind="Beef"))
    c = pd.DataFrame(store.iter_all("chicken"))
    c = c[(c["market"] == "National") & (c["pack_size"] == "Fresh Domestic")]
    for slug, _, item, size in CHICKEN:
        out.append(c[(c["variety"] == item) & (c["item_size"] == size)].assign(slug=slug, kind="Chicken"))
    d = pd.concat(out, ignore_index=True)
    d["date"] = pd.to_datetime(d["report_date"])
    for col in ("normalized_price", "unit_price", "low_price", "high_price"):
        d[col] = pd.to_numeric(d[col], errors="coerce")
    d = d.dropna(subset=["normalized_price"]).sort_values(["slug", "date", "fetched_at"]).groupby(["slug", "date"]).tail(1)
    per_lb = d["normalized_price"] / d["unit_price"]
    return pd.DataFrame({"slug": d["slug"], "kind": d["kind"], "date": d["date"], "price": d["normalized_price"],
                         "low": d["low_price"] * per_lb, "high": d["high_price"] * per_lb})


def panel(daily, deflator):
    """Weekly panel in the shape forecast.py's fitting functions expect; each item is its own "commodity"."""
    d = daily.assign(week=daily["date"] - pd.to_timedelta(daily["date"].dt.weekday, unit="D")).sort_values("date")
    w = d.groupby(["slug", "kind", "week"]).agg(price=("price", "mean"), last_price=("price", "last")).reset_index()
    frames = []
    for slug, g in w.groupby("slug"):
        kind = g["kind"].iloc[0]
        g = g.set_index("week").sort_index()[["price", "last_price"]].asfreq("7D")
        g["series_id"], g["commodity"], g["kind"], g["market"] = slug, slug, kind, "National"
        frames.append(g.reset_index())
    p = pd.concat(frames, ignore_index=True)
    factor = p["week"].dt.strftime("%Y-%m-%d").map(deflator.factor)
    p["lp"], p["lr"] = np.log(p["price"]), np.log(p["price"] * factor)
    iso = p["week"].dt.isocalendar()
    p["year"], p["woy"] = iso["year"].astype(int), iso["week"].clip(upper=52).astype(int)
    g = p.groupby("series_id")["lp"]
    p["mom1"], p["mom4"] = p["lp"] - g.shift(1), p["lp"] - g.shift(4)
    p["last"] = np.log(p["last_price"] / p["price"])
    for h in fc.HORIZONS:
        p[f"y{h}"] = g.shift(-h) - p["lp"]
    return fc.add_seasonal(p)


def method():
    """The same blend as the produce forecast, without the shipping-point and USDA tone inputs meat doesn't have."""
    return fc._blend(fc._huber_group(COLS), fc._gbm(COLS))


def replay(p, h=H, how=None):
    """Forecasts h weeks out, each year fitted only on earlier years, beef and chicken apart."""
    fit, predict = how or method()
    out = []
    usable = p.dropna(subset=["lp"])
    for kind, first in FIRST_TEST.items():
        k = usable[usable["kind"] == kind]
        for Y in range(first, int(k["year"].max()) + 1):
            train = k[k["week"] + pd.Timedelta(weeks=h) < f"{Y}-01-01"].dropna(subset=[f"y{h}"])
            test = k[k["year"] == Y].dropna(subset=[f"y{h}"])
            if not test.empty:
                out.append(test.assign(pred=predict(fit(train, h), test, h)))
    return pd.concat(out, ignore_index=True)


def choose(r, h=H):
    """True where the model had beaten "no change" in earlier years, as forecast.py chooses for produce."""
    r = r.assign(ape=np.abs(np.expm1(r["pred"]) - np.expm1(r[f"y{h}"])), still=np.abs(np.expm1(r[f"y{h}"])))
    use = []
    for Y, cur in r.groupby("year", sort=True):
        prior = r[r["year"] < Y].groupby("series_id")[["ape", "still"]].mean()
        ok = (prior["ape"] <= prior["still"]).to_dict()
        use.append(pd.Series([ok.get(s, True) for s in cur["series_id"]], index=cur.index))
    return pd.concat(use).sort_index()


def called(r, on, h=H):
    """Calls scored as the site shows them: expected change from the latest quote, 5%+ to count as a call."""
    gap = r["last"].fillna(0.0)
    final = (r["pred"] - gap).where(on, 0.0)
    return np.abs(np.expm1(final)) >= brief.MOVE, final, r[f"y{h}"] - gap


def record(r, on):
    """Right-way share of two-week calls per kind, plus the 10%+ swings called ahead."""
    calls, final, move = called(r, on)
    out = {}
    for kind, g in r.groupby("kind"):
        k = g.index
        right = np.sign(final[k]) == np.sign(move[k])
        big = np.abs(np.expm1(move[k])) >= 0.10
        out[kind] = {"from": int(g["year"].min()), "calls": int(calls[k].sum()),
                     "right_pct": round(100 * float(right[calls[k]].mean()), 1),
                     "big_called_pct": round(100 * float((calls[k] & right & big).sum() / max(big.sum(), 1)), 1),
                     "miss_pct": round(100 * float(np.abs(np.expm1(final[k]) - np.expm1(move[k])).mean()), 2),
                     "no_change_pct": round(100 * float(np.abs(np.expm1(move[k])).mean()), 2)}
    return out


def forecasts(p):
    """Per horizon: live prediction, whether to use it, and the past errors behind the 80% range. Also the record."""
    usable = p.dropna(subset=["lp"])
    latest = usable.sort_values("week").groupby("series_id").tail(1)
    out, scored = {}, {}
    for h in HORIZONS:
        r = replay(p, h)
        on = choose(r, h)
        if h == H:
            scored = record(r, on)
        err = r[f"y{h}"] - r["pred"].where(on, 0.0)
        ape = r.assign(ape=np.abs(np.expm1(r["pred"]) - np.expm1(r[f"y{h}"])), still=np.abs(np.expm1(r[f"y{h}"]))).groupby("series_id")[["ape", "still"]].mean()
        pred = {}
        fit, predict = method()
        for kind, k in usable.groupby("kind"):
            cur = latest[latest["kind"] == kind]
            pred.update(zip(cur["series_id"], predict(fit(k.dropna(subset=[f"y{h}"]), h), cur, h)))
        out[h] = {"pred": pred, "use": (ape["ape"] <= ape["still"]).to_dict(),
                  "range": {s: (e.quantile(fc.LO_Q), e.quantile(fc.HI_Q)) for s, e in err.groupby(r["series_id"])}}
    return out, scored


def usual(real, week):
    band = export.seasonal_status(real, week, real.get(week, 0.0))
    return (band["usual_low"], band["usual_high"]) if band["usual_low"] != "" else (None, None)


def item(slug, g, rows_, fits):
    """Today's numbers for one item, in its trade unit: beef per hundredweight, chicken per pound."""
    now, kind = g.iloc[-1], g["kind"].iloc[-1]
    scale = 100.0 if kind == "Beef" else 1.0
    cur = rows_.iloc[-1]
    price = float(now["price"]) * scale
    real = {w.date(): float(np.exp(v)) * scale for w, v in zip(rows_["week"], rows_["lr"]) if pd.notna(v)}
    norm = export.seasonal_status(real, cur["week"].date(), price * float(np.exp(cur["lr"] - cur["lp"])))
    use = fits[H]["use"].get(slug, False)
    points = []
    for h in HORIZONS:
        pred = fits[h]["pred"][slug] if use else 0.0
        lo, hi = fits[h]["range"].get(slug, (-0.1, 0.1))
        points.append({"week": (cur["week"] + pd.Timedelta(weeks=h)).date().isoformat(), "h": h,
                       "mid": round(float(np.exp(cur["lp"] + pred)) * scale, 2),
                       "lo": round(float(np.exp(cur["lp"] + pred + lo)) * scale, 2),
                       "hi": round(float(np.exp(cur["lp"] + pred + hi)) * scale, 2)})
    change, change1 = points[1]["mid"] / price - 1, points[0]["mid"] / price - 1
    direction = brief.direction(change, not use, change1)
    status = norm["status"]
    action = ACTION.get(direction) or (ACTION.get(status, "") if direction == "steady" else "")
    if direction == "softening" and status == "expensive":
        action += " Relief is coming on a high market."
    hist = []
    for _, x in rows_.tail(TREND_WEEKS).iterrows():
        lo, hi = usual(real, x["week"].date())
        hist.append([x["week"].date().isoformat(), round(float(x["price"]) * scale, 2), lo, hi])
    money = lambda v: None if pd.isna(v) else round(float(v) * scale, 2)  # noqa: E731
    return {"slug": slug, "kind": kind, "name": NAMES[slug], "date": now["date"].date().isoformat(), "price": round(price, 2),
            "per_lb": round(float(now["price"]), 2), "low": money(now["low"]), "high": money(now["high"]),
            "prev": money(g["price"].iloc[-2]), "status": status,
            "vs_norm": norm["pct_vs_norm"] if norm["pct_vs_norm"] != "" else None,
            "usual_low": norm["usual_low"] or None, "usual_high": norm["usual_high"] or None,
            "change": round(change, 4), "dir": direction, "action": action, "points": points, "hist": hist}


def log_calls(items, today):
    """Every night's two-week call, kept so the live record can be scored as those weeks finish."""
    fields = ["made", "slug", "date", "price", "change", "dir", "target_week"]
    seen = set()
    if LOG.exists():
        with open(LOG, newline="", encoding="utf-8") as f:
            seen = {(r["made"], r["slug"]) for r in csv.DictReader(f)}
    new = [{"made": today, "slug": i["slug"], "date": i["date"], "price": i["price"], "change": i["change"], "dir": i["dir"],
            "target_week": i["points"][1]["week"]} for i in items if (today, i["slug"]) not in seen]
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        if not seen:
            w.writeheader()
        w.writerows(new)


def main():
    daily = rows()
    p = panel(daily, cpi.Deflator(cpi.load()))
    fits, scored = forecasts(p)
    usable = p.dropna(subset=["lp"]).sort_values("week")
    by_slug = {s: g for s, g in daily.sort_values("date").groupby("slug")}
    items = [item(s, by_slug[s], usable[usable["series_id"] == s], fits) for s in NAMES if s in by_slug]
    OUT.write_text(json.dumps({"asOf": dt.date.today().isoformat(), "record": scored, "items": items}, separators=(",", ":")), encoding="utf-8")
    log_calls(items, dt.date.today().isoformat())
    print("meat:", len(items), "items;", scored)


if __name__ == "__main__":
    main()
