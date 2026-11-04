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

# Added 2026-11-04: the biggest items by pounds shipped that weren't on the list, plus mushrooms (owner approved).
ITEMS_ADDED = {
    "Apples",
    "Watermelons",
    "Pineapples",
    "Cantaloupes",
    "Mangoes",
    "Pears",
    "Cabbage",
    "Oranges",
    "Corn, Sweet",
    "Cauliflower",
    "Sweet Potatoes",
    "Mushrooms",
}

# Retail report 3324 (supermarket ads, weekly): all regions for the wholesale items above, national
# ads only for every other item (the grocery view covers the whole produce aisle).
# Retail report 3324 uses its own commodity names (a single "Lettuce", "Peppers (Bell Type)").
# normalize.RETAIL_NAMES maps them back to the wholesale names where they differ.
RETAIL_COMMODITIES = PRODUCE_COMMODITIES | {"Lettuce", "Peppers (Bell Type)"}
PRODUCE_COMMODITIES = PRODUCE_COMMODITIES | ITEMS_ADDED

TERMINAL_REPORTS = {
    # slug: market name
    "2314": "New York", "2315": "New York", "2316": "New York",
    "2306": "Los Angeles", "2307": "Los Angeles", "2308": "Los Angeles",
    "2290": "Chicago", "2291": "Chicago", "2292": "Chicago",
    "2318": "Philadelphia", "2319": "Philadelphia", "2320": "Philadelphia",
    "2285": "Boston", "2286": "Boston", "2287": "Boston",
    "2277": "Atlanta", "2278": "Atlanta", "2279": "Atlanta",
    "2302": "Detroit", "2303": "Detroit", "2304": "Detroit",
    "2310": "Miami", "2311": "Miami", "2312": "Miami",
}
MARKETS_ADDED = {"Philadelphia", "Boston", "Atlanta", "Detroit", "Miami"}  # history from 2021

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

# Shipping-point reports kept for ITEMS_ADDED only, so forecasts for the older items keep their inputs.
SHIPPING_POINT_ADDED_ONLY = [
    "2412",  # Yakima SP fruit: Washington apples, pears
    "2394",  # Inwood SP fruit: eastern apples
    "2386",  # Benton Harbor SP fruit: Michigan apples
    "2392",  # Idaho Falls SP fruit: Idaho apples
    "2401",  # Orlando SP fruit imports: oranges, pears
    "2399",  # Orlando SP fruit: Florida watermelons
    "2405",  # Raleigh SP veg: Carolina sweet potatoes
    "2411",  # Thomasville SP veg: sweet potatoes
]

RETAIL_REPORTS = ["3324"]

# Weekly grocery feature reports for the other aisles (national rows only, for the grocery view):
# chicken, eggs, turkey, pork, beef, lamb, dairy.
STAPLE_REPORTS = ["2756", "2757", "2867", "2868", "3228", "3229", "2995"]

# Shipment volumes (truck/air/boat movement, pounds). USDA moved the Mexico-crossing and
# Miami numbers from the regional reports into the national one (WA_FV170) around 2024, so
# all are fetched and de-duplicated when volumes are totalled (pipeline/volumes.py).
MOVEMENT_REPORTS = [
    "3283",  # National (WA_FV170): imports, Mexico crossings (recent years), Canada
    "3119",  # El Centro: CA lettuce, celery, broccoli, carrots
    "3127",  # Phoenix: AZ lettuce, celery, broccoli
    "2899",  # Fresno: strawberries, CA avocados, grapes
    "2925",  # Idaho Falls: potatoes, onions
    "3123",  # McAllen: Mexico via Texas (avocados, limes, tomatoes) until ~2024
    "3125",  # Nogales: Mexico via Arizona (tomatoes, cucumbers, peppers) until ~2024
    "3031",  # Miami: bananas and Caribbean imports until ~2024
    "3105",  # Orlando: Florida tomatoes, peppers, cucumbers
    "2717",  # Thomasville: Georgia vegetables
    "3165",  # Raleigh: Carolina vegetables
    "2768",  # Benton Harbor: Michigan
    "3332",  # Yakima: Washington
]

BEEF_REPORT = "2453"  # LMR datamart, National Daily Boxed Beef Cutout (LM_XB403), $/cwt
BEEF_SECTIONS = ["Current Cutout Values", "Choice Cuts", "Select Cuts", "Ground Beef"]

CHICKEN_REPORT = "3646"  # Weekly National Chicken Report, cents/lb
CHICKEN_SECTION = "Report Detail"

# Days re-fetched on every daily run, to pick up late reports and corrections.
DAILY_LOOKBACK_DAYS = 10
