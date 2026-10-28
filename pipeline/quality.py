"""What quality a shopper can expect for each item this month: one word, and the reason behind it.

A low price is only a good buy if the produce is good. August apples are last fall's crop out of storage;
October watermelon is imported and late. Shoppers see one word (Excellent / Good / Fair / Poor); the reason
(peak harvest, storage, imports, end of season, growing-area changeovers) shows on hover or tap.

The calendar is U.S. supermarket timing: harvest seasons from the USDA SNAP-Ed Seasonal Produce Guide and
trade timing (storage, import windows, growing-area transitions). Items not listed fall back to the USDA
guide: in season = Good, out of season = Fair. Owner (former Hunts Point buyer) reviews this table.
"""

LEVELS = ["Poor", "Fair", "Good", "Excellent"]

# commodity -> list of (months, level, reason); months not covered fall through to the USDA-guide default
CALENDAR = {
    "Apples": [
        ((9, 10, 11, 12), "Excellent", "New-crop apples, fresh from the fall harvest."),
        ((1, 2, 3, 4), "Good", "Last fall's crop from controlled-atmosphere storage, still crisp."),
        ((5, 6, 7), "Fair", "Late-storage apples, softer and less juicy, plus some imports from New Zealand and Chile."),
        ((8,), "Poor", "The oldest storage apples of the year: often soft and mealy. New-crop apples arrive in September."),
    ],
    "Pears": [
        ((8, 9, 10, 11, 12), "Excellent", "New-crop Bartlett, Anjou and Bosc from the Pacific Northwest."),
        ((1, 2, 3, 4), "Good", "Stored Anjou and Bosc, still good."),
        ((5, 6, 7), "Fair", "Late storage and imports from Argentina and Chile."),
    ],
    "Oranges": [
        ((12, 1, 2, 3, 4), "Excellent", "Peak navel orange season from California and Florida."),
        ((5, 6), "Good", "Late navels and early Valencias."),
        ((7, 8, 9, 10), "Fair", "Valencias and imports from South Africa and Chile; juicy but often greener-skinned."),
        ((11,), "Good", "Early navels, sometimes tart until December."),
    ],
    "Tangerines/Mandarins": [
        ((11, 12, 1, 2), "Excellent", "Peak California mandarin season."),
        ((3, 4), "Good", "Late-season California mandarins."),
        ((5, 6, 7, 8, 9, 10), "Fair", "Imports from Peru, Chile and South Africa."),
    ],
    "Clementines": [
        ((11, 12, 1), "Excellent", "Peak season."),
        ((2, 3, 4), "Good", "Late season."),
        ((5, 6, 7, 8, 9, 10), "Fair", "Imported, between U.S. seasons."),
    ],
    "Grapefruit": [
        ((11, 12, 1, 2, 3, 4), "Excellent", "Peak Florida and Texas season."),
        ((5, 6, 7, 8, 9, 10), "Fair", "Late season and imports."),
    ],
    "Lemons": [((tuple(range(1, 13))), "Good", "Grown year-round in California, Arizona and Mexico.")],
    "Limes": [((tuple(range(1, 13))), "Good", "Imported from Mexico year-round.")],
    "Strawberries": [
        ((3, 4, 5, 6), "Excellent", "Peak California and Florida season."),
        ((7, 8, 9), "Good", "California summer berries."),
        ((10, 11), "Fair", "End of the California season; fall rain and heat can mean soft, short-lived berries."),
        ((12, 1, 2), "Good", "Florida and Mexico winter berries."),
    ],
    "Blueberries": [
        ((5, 6, 7, 8), "Excellent", "Peak U.S. season."),
        ((9, 10), "Fair", "End of the U.S. season, before imports ramp up."),
        ((11, 12, 1, 2, 3), "Good", "Imported from Peru and Chile."),
        ((4,), "Good", "Early berries from Florida, Georgia and Mexico."),
    ],
    "Raspberries": [
        ((6, 7, 8, 9), "Excellent", "Peak U.S. season."),
        ((10, 11, 12, 1, 2, 3, 4, 5), "Good", "Mostly from Mexico and California's coast."),
    ],
    "Blackberries": [
        ((6, 7, 8), "Excellent", "Peak U.S. season."),
        ((9, 10, 11, 12, 1, 2, 3, 4, 5), "Good", "Mostly from Mexico."),
    ],
    "Grapes": [
        ((7, 8, 9, 10, 11), "Excellent", "Peak California season."),
        ((12, 1), "Fair", "California grapes from storage."),
        ((2, 3, 4), "Good", "Imported from Chile and Peru."),
        ((5, 6), "Fair", "Between seasons: early Mexican and late Chilean grapes."),
    ],
    "Cherries": [
        ((6, 7), "Excellent", "Peak Northwest and California season."),
        ((8,), "Fair", "End of the season."),
        ((11, 12, 1), "Fair", "Imported from Chile."),
    ],
    "Peaches": [
        ((6, 7, 8), "Excellent", "Peak U.S. season."),
        ((5, 9), "Fair", "Early or late in the season; can be hard or mealy."),
        ((10, 11, 12, 1, 2, 3, 4), "Poor", "Imported from Chile: often mealy and slow to ripen."),
    ],
    "Nectarines": [
        ((6, 7, 8), "Excellent", "Peak U.S. season."),
        ((5, 9), "Fair", "Early or late in the season."),
        ((10, 11, 12, 1, 2, 3, 4), "Poor", "Imported from Chile: often mealy."),
    ],
    "Plums": [
        ((6, 7, 8, 9), "Excellent", "Peak U.S. season."),
        ((10, 11, 12, 1, 2, 3, 4, 5), "Fair", "Imported from Chile."),
    ],
    "Apricots": [((5, 6, 7), "Excellent", "Short U.S. season."), ((8, 9, 10, 11, 12, 1, 2, 3, 4), "Poor", "Out of season; imported.")],
    "Watermelons": [
        ((6, 7, 8), "Excellent", "Peak U.S. season."),
        ((5, 9), "Good", "Early or late U.S. season."),
        ((10, 11, 12, 1, 2, 3, 4), "Fair", "Imported from Mexico and Central America; flavor is hit and miss."),
    ],
    "Cantaloupes": [
        ((6, 7, 8, 9), "Excellent", "Peak California and Arizona season."),
        ((10, 11, 12, 1, 2, 3, 4, 5), "Fair", "Imported from Central America; often less sweet."),
    ],
    "Honeydews": [
        ((7, 8, 9, 10), "Excellent", "Peak season."),
        ((11, 12, 1, 2, 3, 4, 5, 6), "Fair", "Imported; often less sweet."),
    ],
    "Mangoes": [
        ((4, 5, 6, 7, 8), "Excellent", "Peak Mexico season."),
        ((9, 10, 11, 12, 1, 2, 3), "Good", "Imported from Peru, Ecuador and Brazil."),
    ],
    "Cranberries": [((10, 11, 12), "Excellent", "Fresh harvest."), ((1, 2, 3, 4, 5, 6, 7, 8, 9), "Fair", "From storage, out of season.")],
    "Pomegranates": [((10, 11, 12), "Excellent", "Peak California season."), ((1, 2, 3, 4, 5, 6, 7, 8, 9), "Fair", "From storage or imported.")],
    "Persimmons": [((10, 11, 12), "Excellent", "Peak season."), ((1, 2), "Fair", "Late season.")],
    "Corn-Sweet": [
        ((6, 7, 8, 9), "Excellent", "Peak U.S. season; local corn is at its sweetest."),
        ((5, 10), "Good", "Early or late in the season."),
        ((11, 12, 1, 2, 3, 4), "Fair", "Shipped from Florida and Mexico; less sweet."),
    ],
    "Asparagus": [
        ((3, 4, 5), "Excellent", "Peak U.S. spring season."),
        ((6, 7, 8, 9, 10, 11, 12, 1, 2), "Good", "Imported from Peru and Mexico."),
    ],
    "Tomatoes": [
        ((7, 8, 9), "Excellent", "Peak field-grown season."),
        ((10, 11, 12, 1, 2, 3, 4, 5, 6), "Good", "Greenhouse and Mexican or Florida tomatoes: steady, but less flavor than summer."),
    ],
    "Brussels Sprouts": [((9, 10, 11, 12), "Excellent", "Peak fall harvest."), ((1, 2, 3), "Good", "Late season."),
                         ((4, 5, 6, 7, 8), "Fair", "Imported, out of season.")],
    "Sweet Potatoes": [((9, 10, 11, 12), "Excellent", "Fresh-harvested and cured."), ((1, 2, 3, 4, 5, 6, 7, 8), "Good", "From storage; they keep well.")],
    "Potatoes": [((8, 9, 10, 11, 12), "Excellent", "New-crop potatoes."), ((1, 2, 3, 4, 5), "Good", "From storage; they keep well."),
                 ((6, 7), "Fair", "The oldest storage potatoes before the new crop.")],
    "Pumpkins": [((9, 10), "Excellent", "Peak season."), ((11,), "Good", "End of the season.")],
    "Lettuce": [
        ((5, 6, 7, 8, 9, 10), "Good", "From the Salinas Valley, California."),
        ((11, 12), "Fair", "Growing moves from Salinas to Yuma, Arizona; supply and quality can be uneven."),
        ((1, 2), "Good", "From Yuma, Arizona and the Imperial Valley."),
        ((3, 4), "Fair", "Growing moves back from the desert to Salinas; supply and quality can be uneven."),
    ],
    "Kale": [((10, 11, 12, 1, 2, 3, 4), "Excellent", "Cool-season green, at its best now."), ((5, 6, 7, 8, 9), "Good", "Fine, though tougher in the heat.")],
    "Collards": [((10, 11, 12, 1, 2, 3), "Excellent", "Cool-season green, sweetest after frost."), ((4, 5, 6, 7, 8, 9), "Good", "Available, but tougher in the heat.")],
    "Spinach": [((10, 11, 12, 1, 2, 3, 4, 5), "Excellent", "Cool-season green, at its best now."), ((6, 7, 8, 9), "Good", "Available, but heat can shorten shelf life.")],
}


# Staples supplied all year from rotating growing areas: the USDA guide's season lists would mislabel them.
ALL_YEAR = tuple(range(1, 13))
for _c, _why in {
    "Avocados": "Hass avocados come from Mexico and California all year.",
    "Bananas": "Imported from Central and South America all year.",
    "Pineapples": "Imported from Costa Rica all year.",
    "Papaya": "Imported all year.", "Plantains": "Imported all year.", "Coconut": "Imported all year.",
    "Mushrooms": "Grown indoors all year.", "Carrots": "Grown and stored all year.", "Celery": "Grown all year in California.",
    "Onions, Dry": "Fresh or from storage all year.", "Garlic": "From storage and imports all year.",
    "Cabbage": "Grown all year.", "Broccoli": "Grown all year in California and Arizona.",
    "Cauliflower": "Grown all year in California and Arizona.", "Cucumbers": "Grown all year in rotating regions.",
    "Peppers, Bell Type": "Field and greenhouse peppers all year.", "Squash": "Grown all year in rotating regions.",
    "Beans": "Grown all year in rotating regions.", "Cilantro": "Grown all year.", "Kiwifruit": "From California and New Zealand all year.",
    "Salad (Mixed Types)": "Bagged greens all year.", "Onions, Green": "Grown all year.", "Radishes": "Grown all year.",
    "Mixed Mini Sweet Peppers": "Greenhouse-grown all year.", "Jalapeno Peppers": "Grown all year.",
}.items():
    CALENDAR.setdefault(_c, [(ALL_YEAR, "Good", _why)])


def quality(commodity, month, in_season=None):
    """(level, reason) for this month, or None when there's nothing reliable to say."""
    for months, level, reason in CALENDAR.get(commodity, []):
        if month in months:
            return level, reason
    if commodity in CALENDAR:
        return None
    if in_season is True:
        return "Good", "In season now, per USDA's seasonal produce guide."
    if in_season is False:
        return "Fair", "Out of season now, so most likely imported or from storage."
    return None


def best_months(commodity):
    """Months the calendar rates Excellent (empty when the item isn't in the calendar)."""
    return sorted({m for months, level, _ in CALENDAR.get(commodity, []) if level == "Excellent" for m in months})
