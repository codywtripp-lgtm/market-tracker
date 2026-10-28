"""This week's real conditions, layered on the quality calendar (pipeline/quality.py).

The calendar says what to expect in a normal year. These are the signs that this year isn't normal:

- **Quality flags**: USDA terminal-market reporters mark lots as fair appearance, fair quality, fair condition
  or holdovers. If an item's share of flagged quotes over the last two weeks is well above its share in the
  same weeks of earlier years, quality is worse than usual right now.
- **Short supply at the source**: shipping-point reports saying supplies are very light, in few hands, or too
  short to quote.
- **Shipments well below last year** (USDA movement reports).

Only the 18 wholesale items have these reports; other grocery items use the calendar alone.
"""

import datetime as dt
import re
from collections import defaultdict

from . import store

DAYS = 14
FLAGS = re.compile(r"fair appearance|fair quality|fair condition|holdover|ordinary condition", re.I)
SHORT = re.compile(r"very light|few hands|insufficient|too few|very limited", re.I)
# grocery (retail report) name -> wholesale names
TO_RETAIL = {"Lettuce, Iceberg": "Lettuce", "Lettuce, Romaine": "Lettuce", "Tomatoes, Plum Type": "Tomatoes"}


def _rows(source, start, end):
    months = set()
    d = start
    while d <= end:
        months.add(d.isoformat()[:7])
        d += dt.timedelta(days=27)
    months.add(end.isoformat()[:7])
    for m in sorted(months):
        yield from store.read_partition(store.partition_path(source, m + "-01")).values()


def flagged_shares(as_of, years=6):
    """retail commodity -> (share of flagged quotes now, usual share in the same weeks of earlier years)."""
    now, usual = defaultdict(lambda: [0, 0]), defaultdict(lambda: [0, 0])
    for back in range(0, years + 1):
        end = as_of.replace(year=as_of.year - back)
        start = end - dt.timedelta(days=DAYS)
        lo, hi = start.isoformat(), end.isoformat()
        for r in _rows("terminal", start, end):
            if not (lo < r["report_date"] <= hi) or r.get("organic", "") in ("Y", "Yes"):
                continue
            c = TO_RETAIL.get(r["commodity"], r["commodity"])
            bucket = now if back == 0 else usual
            bucket[c][1] += 1
            bucket[c][0] += bool(FLAGS.search(" ".join((r["appearance"], r["condition"], r["quality"]))))
    return {c: (n[0] / n[1], usual[c][0] / usual[c][1] if usual[c][1] else None) for c, n in now.items() if n[1] >= 20}


def short_supply(as_of):
    """retail commodity -> share of reporting growing areas calling supply very short in the last week.
    One small district at the tail of its season ("too few to quote") doesn't make the item short."""
    # USDA often says "insufficient to establish a market" about one pack or size, so a district counts as short
    # only when most of its quotes that week say so
    rows = defaultdict(lambda: [0, 0])  # (commodity, district) -> [short quotes, quotes]
    start = as_of - dt.timedelta(days=7)
    for r in _rows("shipping_point", start, as_of):
        if r["report_date"] <= start.isoformat() or not r["market"]:
            continue
        key = (TO_RETAIL.get(r["commodity"], r["commodity"]), r["market"])
        rows[key][1] += 1
        rows[key][0] += bool(SHORT.search(" ".join((r.get("supply_tone", ""), r["reporter_comment"]))))
    seen, short = defaultdict(int), defaultdict(int)
    for (c, _), (n_short, n) in rows.items():
        seen[c] += 1
        short[c] += n_short / n >= 0.5
    return {c: short[c] / seen[c] for c in seen if seen[c] >= 2 and short[c] / seen[c] >= 0.5}


def build(as_of, shipments=None):
    """retail commodity -> {"down": quality worse than the calendar says, "notes": [plain sentences]}."""
    shipments = shipments or {}
    out = defaultdict(lambda: {"down": False, "notes": []})
    for c, (share, usual) in flagged_shares(as_of).items():
        if usual is not None and share >= 0.15 and share >= max(2 * usual, usual + 0.10):
            out[c]["down"] = True
            out[c]["notes"].append(f"This week USDA market reporters are flagging {round(100 * share)}% of lots for "
                                   f"fair quality or condition, against {round(100 * usual)}% in a usual year.")
    for c, share in short_supply(as_of).items():
        out[c]["notes"].append(f"{'Most' if share < 1 else 'All'} of the growing areas USDA covers are reporting very "
                               "short supplies this week.")
    for c, pct in shipments.items():
        c = TO_RETAIL.get(c, c)
        if pct is not None and pct <= -25:
            out[c]["notes"].append(f"Shipments are {abs(round(pct))}% below this time last year.")
    return dict(out)
