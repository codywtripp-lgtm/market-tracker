"""The meat, poultry, dairy and egg items a shopper looks for, matched to USDA's weekly grocery feature reports.

USDA lists hundreds of cuts and deli items, and renamed many over the years ("SLICED BACON, 1 LB PKG" became
"Sliced Bacon"), so each shopper item is a set of patterns on the report's commodity, product type, unit and
fresh/frozen/prepared, matched case-insensitively. Rows that match no item (deli tubs, prepared foods) are left out.
"""

import re

AISLES = {"meat": "Meat & poultry", "dairy": "Dairy & eggs"}

# (item, aisle, USDA commodity, product-type pattern, unit pattern or None, condition pattern or None)
CATALOG = [
    ("Chicken breasts", "meat", "Chicken", r"breast.*boneless.*skinless(?!.*iqf)", r"per lb", r"fresh"),
    ("Chicken thighs", "meat", "Chicken", r"^thighs?\b(?!.*boneless)", r"per lb", r"fresh"),
    ("Boneless chicken thighs", "meat", "Chicken", r"thighs?.*boneless", r"per lb", r"fresh"),
    ("Chicken drumsticks", "meat", "Chicken", r"drumsticks?", r"per lb", r"fresh"),
    ("Chicken wings", "meat", "Chicken", r"^wings?\b|wings?, whole", r"per lb", r"fresh"),
    ("Whole chicken", "meat", "Chicken", r"whole (bagged )?fryer|^whole fryer|whole chicken", r"per lb", r"fresh"),
    ("Rotisserie chicken", "meat", "Chicken", r"rotisserie", r"each", None),
    ("Ground beef", "meat", "Beef", r"ground beef 80|ground beef, 80", r"per lb", r"fresh"),
    ("Lean ground beef", "meat", "Beef", r"ground beef 90|ground beef, 9[0-9]", r"per lb", r"fresh"),
    ("Chuck roast", "meat", "Beef", r"chuck roast|chuck/shldr/arm roast", r"per lb", r"fresh"),
    ("T-bone steak", "meat", "Beef", r"t-bone", r"per lb", r"fresh"),
    ("London broil", "meat", "Beef", r"london broil", r"per lb", r"fresh"),
    ("Strip steak", "meat", "Beef", r"strip steak", r"per lb", r"fresh"),
    ("Ribeye steak", "meat", "Beef", r"ribeye steak|rib ?eye steak", r"per lb", r"fresh"),
    ("Sirloin steak", "meat", "Beef", r"sirloin steak", r"per lb", r"fresh"),
    ("Stew beef", "meat", "Beef", r"stew meat", r"per lb", r"fresh"),
    ("Bacon", "meat", "Pork", r"sliced bacon", None, r"fresh"),
    ("Pork chops", "meat", "Pork", r"chops?", r"per lb", r"fresh"),
    ("Pork tenderloin", "meat", "Pork", r"tenderloin", r"per lb", r"fresh"),
    ("Pork shoulder", "meat", "Pork", r"butt roast|shoulder|boston butt|butt fresh", r"per lb", r"fresh"),
    ("Pork loin roast", "meat", "Pork", r"loin roast", r"per lb", r"fresh"),
    ("Pork ribs", "meat", "Pork", r"backribs|back ribs|spareribs|st[.] louis", r"per lb", r"fresh"),
    ("Italian sausage", "meat", "Pork", r"italian sausage", None, r"fresh"),
    ("Spiral ham", "meat", "Pork", r"spiral", r"per lb", None),
    ("Breakfast sausage", "meat", "Pork", r"breakfast sausage|bkfst sausage", None, r"fresh"),
    ("Whole turkey", "meat", "Turkey", r"whole turkey", r"per lb", r"frozen"),
    ("Fresh whole turkey", "meat", "Turkey", r"whole turkey", r"per lb", r"^fresh"),
    ("Turkey breast", "meat", "Turkey", r"whole breast|breast, bone-in", r"per lb", None),
    ("Ground turkey", "meat", "Turkey", r"ground turkey", None, r"fresh"),
    ("Leg of lamb", "meat", "Lamb", r"^leg\b|leg, ", r"per lb", r"fresh"),
    ("Eggs", "dairy", "Egg", r"large white|white large", r"12 count|carton", None),
    ("Milk", "dairy", "Milk", r".*", r"^gallon", None),
    ("Butter", "dairy", "Butter", r".*", r"^1 lb", None),
    ("Shredded cheese", "dairy", "Cheese", r".*", r"shred", None),
    ("Sliced cheese", "dairy", "Cheese", r".*", r"slice", None),
    ("Block cheese", "dairy", "Cheese", r".*", r"block", None),
    ("Greek yogurt", "dairy", "Yogurt", r"greek", None, None),
    ("Yogurt", "dairy", "Yogurt", r"^yogurt$|^$|regular", None, None),
    ("Ice cream", "dairy", "Ice Cream", r".*", r"48|56|64|1.5 qt|half gallon", None),
    ("Sour cream", "dairy", "Sour Cream", r".*", None, None),
    ("Cream cheese", "dairy", "Cream Cheese", r".*", None, None),
    ("Cottage cheese", "dairy", "Cottage Cheese", r".*", None, None),
    ("Eggnog", "dairy", "Eggnog", r".*", None, None),
]
AISLE = {item: aisle for item, aisle, *_ in CATALOG}
# USDA's egg report also lists eggnog under "Egg"; deli tubs, fried chicken and service-deli items are not shopper staples
SKIP = re.compile(r"deli|tub|pouch|fried|baked|egg nog|liquid|cooked|marinated|seasoned|breaded|stuffed", re.I)


def match(row):
    """Shopper item for a USDA staples row, or None."""
    variety, pack, cond = row["variety"] or "", row["pack_size"] or "", row.get("properties") or ""
    if SKIP.search(variety):
        return None
    for item, _, commodity, kind, unit, condition in CATALOG:
        if row["commodity"].lower() != commodity.lower():
            continue
        if not re.search(kind, variety, re.I):
            continue
        if unit and not re.search(unit, pack, re.I):
            continue
        if condition and not re.search(condition, cond, re.I):
            continue
        return item
    return None
