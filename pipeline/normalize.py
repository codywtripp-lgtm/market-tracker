"""Map raw USDA rows from each report family onto one common schema.

Normalization rules are documented in docs/normalization.md — keep them in sync.
"""

import datetime as dt
import hashlib
import re

COLUMNS = [
    "row_id", "report_date", "commodity", "variety", "pack_size", "count_size", "item_size",
    "properties", "grade", "organic", "appearance", "condition", "quality",
    "low_price", "high_price", "mostly_low_price", "mostly_high_price",
    "unit_price", "price_unit", "normalized_price", "normalized_unit",
    "market", "market_type", "origin", "origin_detail", "other_attributes",
    "reporter_comment", "market_tone", "volume", "volume_unit", "store_count",
    "report_id", "report_title", "fetched_at",
]

# Fields that make a price row unique within a report and date.
KEY_FIELDS = [
    "report_id", "report_date", "commodity", "variety", "pack_size", "item_size", "properties",
    "grade", "organic", "appearance", "condition", "quality", "market", "origin",
    "origin_detail", "other_attributes", "reporter_comment", "price_unit",
]

# Retail names that differ from the wholesale reports.
RETAIL_NAMES = {"Peppers (Bell Type)": "Peppers, Bell Type"}

# Less common produce descriptors, kept as "k=v; ..." in other_attributes (only when set).
# Terminal and shipping-point names both listed; whichever exists is used.
OTHER_ATTRIBUTES = ["repack", "storage", "crop", "environment", "env", "unit_sales",
                    "transportation_mode", "season", "import_export_flag", "basis_of_sale"]

BLANKS = {"", "n/a", "null", "none", None}

# Commodities where a per-each price is more useful than per-lb.
PER_UNIT_COMMODITIES = {"Avocados", "Lettuce, Iceberg", "Lettuce, Romaine"}

# Containers whose weight isn't in the package text. Industry-typical net weights —
# ASSUMPTIONS, see docs/normalization.md.
CONTAINER_LB = {
    ("Peppers, Bell Type", "1 1/9 bushel cartons"): 25.0,
    ("Peppers, Bell Type", "1 1/9 bushel cartons place pack"): 25.0,
    ("Tomatoes", "cartons 2 layer"): 20.0,
    ("Avocados", "cartons 2 layer"): 25.0,
}

LB_PER_KG = 2.20462
LB_PER_PINT_STRAWBERRY = 0.75  # assumption


def clean(v):
    if v is None:
        return ""
    s = str(v).strip()
    return "" if s.lower() in BLANKS else s


def num(v):
    s = clean(v).replace(",", "")
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def iso_date(v):
    s = clean(v)
    if not s:
        return ""
    return dt.datetime.strptime(s[:10], "%m/%d/%Y").date().isoformat()


def midpoint(lo, hi):
    vals = [x for x in (lo, hi) if x is not None and x > 0]
    return round(sum(vals) / len(vals), 4) if vals else None


def representative_price(low, high, mostly_low, mostly_high):
    """Mostly-range midpoint when USDA gives one, else the low/high midpoint."""
    return midpoint(mostly_low, mostly_high) or midpoint(low, high)


def package_lb(commodity, pack):
    """Net weight in pounds from the package description, or None."""
    p = pack.lower()
    # "8 1-lb containers", "10 5-lb film bags", "12 10-oz containers", "12 1-pint baskets"
    m = re.search(r"(\d+)\s+(\d+(?:\.\d+)?)-(lb|oz|pint)", p)
    if m:
        n, size, unit = int(m.group(1)), float(m.group(2)), m.group(3)
        per = {"lb": size, "oz": size / 16, "pint": size * LB_PER_PINT_STRAWBERRY}[unit]
        return round(n * per, 3)
    m = re.search(r"(\d+(?:\.\d+)?)\s*kg\s*/\s*(\d+(?:\.\d+)?)\s*lb", p)  # "5 kg/11 lb"
    if m:
        return float(m.group(2))
    m = re.search(r"(\d+(?:\.\d+)?)\s*lb", p)  # "25 lb cartons", "50 lb sacks"
    if m:
        return float(m.group(1))
    m = re.search(r"(\d+(?:\.\d+)?)\s*kg", p)  # "4 kg cartons"
    if m:
        return round(float(m.group(1)) * LB_PER_KG, 3)
    return CONTAINER_LB.get((commodity, pack.strip()))


def count_size(item_size, pack):
    """Units per package: '48s' -> 48, '24s film wrapped' -> 24, '12 3-count packages' -> 36."""
    m = re.search(r"(\d+)\s+(\d+)-count", pack.lower())
    if m:
        return int(m.group(1)) * int(m.group(2))
    s = item_size.lower()
    if re.search(r"\d+x\d+", s):  # tomato layer sizes like 4x5s are not counts
        return None
    m = re.search(r"\b(\d+)s\b", s)
    return int(m.group(1)) if m else None


def normalize_price(commodity, unit_price, pack, count):
    """Returns (normalized_price, normalized_unit)."""
    if unit_price is None:
        return None, ""
    if commodity in PER_UNIT_COMMODITIES and count:
        return round(unit_price / count, 4), "per each"
    lb = package_lb(commodity, pack)
    if lb:
        return round(unit_price / lb, 4), "per lb"
    if count:
        return round(unit_price / count, 4), "per each"
    return None, ""


def other_attributes(raw):
    return "; ".join(f"{k}={clean(raw.get(k))}" for k in OTHER_ATTRIBUTES if clean(raw.get(k)))


def row_id(r):
    raw = "|".join(str(r.get(k, "")) for k in KEY_FIELDS)
    return hashlib.sha1(raw.encode()).hexdigest()[:16]


def finish(r, fetched_at):
    r["fetched_at"] = fetched_at
    r["row_id"] = row_id(r)
    return {c: ("" if r.get(c) is None else r.get(c)) for c in COLUMNS}


def _produce(raw, market, market_type, fetched_at, field_map):
    g = lambda k: clean(raw.get(field_map.get(k, k)))  # noqa: E731
    commodity = g("commodity")
    pack = g("package")
    item_size = g("item_size")
    low, high = num(raw.get("low_price")), num(raw.get("high_price"))
    mlo, mhi = num(raw.get("mostly_low_price")), num(raw.get("mostly_high_price"))
    unit_price = representative_price(low, high, mlo, mhi)
    count = count_size(item_size, pack)
    norm, norm_unit = normalize_price(commodity, unit_price, pack, count)
    if market_type == "shipping point":
        origin, origin_detail = g("district"), ""
        market = g("district")
    else:
        origin, origin_detail = g("origin"), g("district")
    other = other_attributes(raw)
    return finish({
        "report_date": iso_date(raw.get("report_date") or raw.get("report_begin_date")),
        "commodity": commodity, "variety": g("variety"), "pack_size": pack,
        "count_size": count, "item_size": item_size, "properties": g("properties"),
        "grade": g("grade"), "organic": g("organic"), "appearance": g("appearance"),
        "condition": g("condition"), "quality": g("quality"),
        "low_price": low, "high_price": high, "mostly_low_price": mlo, "mostly_high_price": mhi,
        "unit_price": unit_price, "price_unit": "$/package",
        "normalized_price": norm, "normalized_unit": norm_unit,
        "market": market, "market_type": market_type,
        "origin": origin, "origin_detail": origin_detail, "other_attributes": other,
        # often holds pack detail ("5lb. film bag orange", "(35 Lb) (Peeled)"), so it's part of the key
        "reporter_comment": clean(raw.get("reporter_comment") or raw.get("rep_cmt")),
        "market_tone": g("market_tone_comments"),
        "report_id": clean(raw.get("slug_id")), "report_title": g("report_title"),
    }, fetched_at)


def terminal(raw, market, fetched_at):
    return _produce(raw, market, "terminal", fetched_at, {})


# Shipping-point reports use abbreviated column names.
SP_FIELDS = {"variety": "var", "package": "pkg", "appearance": "appear", "condition": "cond"}


def shipping_point(raw, fetched_at):
    return _produce(raw, "", "shipping point", fetched_at, SP_FIELDS)


def retail(raw, fetched_at):
    unit = clean(raw.get("size"))
    price = num(raw.get("wtd_avg_price"))
    u = unit.lower()
    if u in ("per lb", "lb"):
        norm, norm_unit = price, "per lb"
    elif u == "each":
        norm, norm_unit = price, "per each"
    else:
        lb = package_lb(clean(raw.get("commodity")), unit)
        norm, norm_unit = (round(price / lb, 4), "per lb") if (price and lb) else (None, "")
    return finish({
        "report_date": iso_date(raw.get("report_end_date") or raw.get("report_begin_date")),
        "commodity": RETAIL_NAMES.get(clean(raw.get("commodity")), clean(raw.get("commodity"))),
        "variety": clean(raw.get("variety")),
        "pack_size": unit, "organic": clean(raw.get("organic")),
        "other_attributes": other_attributes(raw),  # e.g. environment=Greenhouse
        "unit_price": price, "price_unit": "$/" + (unit or "unit"),
        "normalized_price": norm, "normalized_unit": norm_unit,
        "market": clean(raw.get("region")), "market_type": "retail",
        "store_count": num(raw.get("store_count")),
        "report_id": clean(raw.get("slug_id")), "report_title": clean(raw.get("report_title")),
    }, fetched_at)


def beef(raw, section, fetched_at):
    """LM_XB403 rows. Prices are $/cwt; normalized to $/lb. One raw cutout row -> two rows."""
    base = {
        "report_date": iso_date(raw.get("report_date")), "commodity": "Beef",
        "price_unit": "$/cwt", "normalized_unit": "per lb", "market": "National",
        "market_type": "wholesale", "report_id": clean(raw.get("slug_id")),
        "report_title": clean(raw.get("report_title")),
    }
    out = []
    if section == "Current Cutout Values":
        for grade, field in (("Choice", "choice_600_900_current"), ("Select", "select_600_900_current")):
            price = num(raw.get(field))
            if price:
                out.append(finish({**base, "variety": "Cutout 600-900 lb", "grade": grade,
                                   "unit_price": price, "normalized_price": round(price / 100, 4)},
                                  fetched_at))
        return out
    price = num(raw.get("weighted_average"))
    if not price:
        return out  # no trades
    grade = {"Choice Cuts": "Choice", "Select Cuts": "Select"}.get(section, "")
    out.append(finish({
        # cuts use item_description; the Ground Beef section uses trim_description
        **base, "variety": clean(raw.get("item_description") or raw.get("trim_description")), "grade": grade,
        "pack_size": section, "low_price": num(raw.get("price_range_low")),
        "high_price": num(raw.get("price_range_high")), "unit_price": price,
        "normalized_price": round(price / 100, 4),
        "volume": num(raw.get("total_pounds")), "volume_unit": "lb",
    }, fetched_at))
    return out


def chicken(raw, fetched_at):
    """3646 rows. Prices are cents/lb; normalized to $/lb."""
    price = num(raw.get("wtd_avg_price"))
    if not price:
        return None
    return finish({
        "report_date": iso_date(raw.get("report_date") or raw.get("report_begin_date")),
        "commodity": "Chicken", "variety": clean(raw.get("item")),
        "pack_size": " ".join(x for x in (clean(raw.get("condition")), clean(raw.get("trade_status"))) if x),
        "item_size": clean(raw.get("size")), "grade": clean(raw.get("grade")),
        "condition": clean(raw.get("condition")),
        "low_price": num(raw.get("low_price")), "high_price": num(raw.get("high_price")),
        "unit_price": price, "price_unit": "cents/lb",
        "normalized_price": round(price / 100, 4), "normalized_unit": "per lb",
        "market": clean(raw.get("region")) or "National", "market_type": "wholesale",
        "origin_detail": clean(raw.get("trade_status")),
        "volume": num(raw.get("volume")), "volume_unit": clean(raw.get("volume_traded_unit")),
        "report_id": clean(raw.get("slug_id")), "report_title": clean(raw.get("report_title")),
    }, fetched_at)
