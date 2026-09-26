"""What to fetch. Edit this file to add markets, reports, or commodities."""

MARS = "https://marsapi.ams.usda.gov/services/v1.2"
DATAMART = "https://mpr.datamart.ams.usda.gov/services/v1.1"

# Commodities to keep from produce reports (exact USDA names; filtered client-side
# because the API treats commas in names as OR).
# Chosen for high volume and near-daily NY reporting (see docs/shortlist-and-storage.md).
PRODUCE_COMMODITIES = {
    # owner's core list
    "Avocados",
    "Strawberries",
    "Tomatoes",
    "Tomatoes, Plum Type",
    "Peppers, Bell Type",
    "Lettuce, Iceberg",
    "Lettuce, Romaine",
    "Onions, Dry",
    # added for volume (2026-09-26)
    "Potatoes",
    "Lemons",
    "Limes",
    "Cucumbers",
    "Broccoli",
    "Celery",
    "Carrots",
    "Bananas",
    "Blueberries",
    "Grapes",
}

# Retail report 3324 uses its own commodity names (e.g. a single "Lettuce").
RETAIL_COMMODITIES = PRODUCE_COMMODITIES | {"Lettuce"}

TERMINAL_REPORTS = {
    # slug: market name
    "2314": "New York", "2315": "New York", "2316": "New York",
    "2306": "Los Angeles", "2307": "Los Angeles", "2308": "Los Angeles",
    "2290": "Chicago", "2291": "Chicago", "2292": "Chicago",
}

SHIPPING_POINT_REPORTS = [
    "2390",  # Fresno SP fruit: Mexico avocados via Texas, CA avocados, CA strawberries, grapes
    "2391",  # Fresno SP veg: San Joaquin Valley / CA vegetables
    "2402",  # Phoenix SP fruit: Mexico limes and lemons via Texas, CA citrus
    "2403",  # Phoenix SP veg: CA/AZ lettuce, tomatoes, peppers; Mexico crossings
    "2393",  # Idaho Falls SP onions: Idaho-Malheur, Columbia Basin
    "2400",  # Orlando SP veg: FL / TN-VA tomatoes, peppers
    "2396",  # Miami SP veg: south Florida winter veg
    "2395",  # Miami SP fruit: Florida avocados
    "2410",  # Thomasville SP veg: Georgia peppers
    "2387",  # Benton Harbor SP veg: Michigan peppers
    "2388",  # Benton Harbor SP onions
]

RETAIL_REPORTS = ["3324"]

BEEF_REPORT = "2453"  # LMR datamart, National Daily Boxed Beef Cutout (LM_XB403), $/cwt
BEEF_SECTIONS = ["Current Cutout Values", "Choice Cuts", "Select Cuts", "Ground Beef"]

CHICKEN_REPORT = "3646"  # Weekly National Chicken Report, cents/lb
CHICKEN_SECTION = "Report Detail"

# Days re-fetched on every daily run, to pick up late reports and corrections.
DAILY_LOOKBACK_DAYS = 10
