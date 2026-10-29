"""Cook this week: everyday meals ranked by how much of each one is a good buy right now.

We don't publish recipes (the big recipe sites do that better, with photos and reviews); each meal is a name and a
shopping list of the tracked ingredients, with the amount in the unit stores price them in (so cost per serving is
this week's average supermarket price times the amount). The meal's name links to a web search for recipes.
Ranking: ingredients that are a great price and good quality push a recipe up, pricey or unavailable ones push it
down; the main ingredient (listed first) counts double; cost per serving breaks ties.

The meal list is reviewed by the owner.
"""

# (item, amount in the item's priced unit, the unit we expect, what the shopper buys)
R = [
    {"slug": "sheet-pan-chicken-thighs-broccoli", "name": "Sheet-pan chicken thighs with broccoli", "serves": 4, "minutes": 45,
     "kind": "Dinner",
     "items": [("Chicken thighs", 2.5, "/lb", "2½ lb bone-in chicken thighs"), ("Broccoli", 1.5, "/lb", "1½ lb broccoli crowns"),
               ("Lemons", 1, "each", "1 lemon"), ("Garlic", 0.1, "a sleeve", "4 cloves garlic")],},
    {"slug": "roast-drumsticks-potatoes-carrots", "name": "Roast chicken drumsticks with potatoes and carrots", "serves": 4,
     "minutes": 55, "kind": "Dinner",
     "items": [("Chicken drumsticks", 3, "/lb", "3 lb chicken drumsticks"), ("Potatoes", 0.4, "for 5 lb", "2 lb potatoes"),
               ("Carrots", 1, "for 1 lb", "1 lb bag of carrots"), ("Onions, Dry", 0.17, "for 3 lb", "1 onion")],},
    {"slug": "roast-whole-chicken-vegetables", "name": "Roast whole chicken with vegetables", "serves": 6, "minutes": 90, "kind": "Dinner",
     "items": [("Whole chicken", 4.5, "/lb", "1 whole chicken, about 4½ lb"), ("Carrots", 1, "for 1 lb", "1 lb bag of carrots"),
               ("Potatoes", 0.3, "for 5 lb", "1½ lb potatoes"), ("Onions, Dry", 0.17, "for 3 lb", "1 onion"),
               ("Lemons", 1, "each", "1 lemon")],},
    {"slug": "chicken-vegetable-stir-fry", "name": "Chicken and vegetable stir-fry", "serves": 4, "minutes": 30, "kind": "Dinner",
     "items": [("Chicken breasts", 1.5, "/lb", "1½ lb boneless chicken breasts"), ("Broccoli", 1, "/lb", "1 lb broccoli crowns"),
               ("Peppers, Bell Type", 2, "each", "2 bell peppers"), ("Carrots", 0.5, "for 1 lb", "2 carrots"),
               ("Onions, Green", 0.5, "a bunch", "4 green onions"), ("Garlic", 0.1, "a sleeve", "3 cloves garlic")],},
    {"slug": "lemon-garlic-chicken-green-beans", "name": "Lemon-garlic chicken with green beans", "serves": 4, "minutes": 30,
     "kind": "Dinner",
     "items": [("Chicken breasts", 1.5, "/lb", "1½ lb boneless chicken breasts"), ("Beans", 1, "/lb", "1 lb green beans"),
               ("Lemons", 1, "each", "1 lemon"), ("Garlic", 0.1, "a sleeve", "4 cloves garlic")],},
    {"slug": "chicken-tacos-lime-slaw", "name": "Chicken tacos with lime slaw", "serves": 4, "minutes": 35, "kind": "Dinner",
     "items": [("Boneless chicken thighs", 1.5, "/lb", "1½ lb boneless chicken thighs"), ("Cabbage", 0.75, "/lb", "¼ head cabbage"),
               ("Limes", 2, "each", "2 limes"), ("Cilantro", 0.5, "a bunch", "½ bunch cilantro"), ("Avocados", 2, "each", "2 avocados")],},
    {"slug": "pork-tenderloin-apples-onions", "name": "Pork tenderloin with roasted apples and onions", "serves": 4, "minutes": 40,
     "kind": "Dinner",
     "items": [("Pork tenderloin", 1.5, "/lb", "1½ lb pork tenderloin"), ("Apples", 1.5, "/lb", "3 apples"),
               ("Onions, Dry", 0.33, "for 3 lb", "2 onions")],},
    {"slug": "pork-chops-sweet-potatoes", "name": "Pork chops with sweet potatoes and green beans", "serves": 4, "minutes": 40,
     "kind": "Dinner",
     "items": [("Pork chops", 2, "/lb", "4 pork chops, about 2 lb"), ("Sweet Potatoes", 2, "/lb", "2 lb sweet potatoes"),
               ("Beans", 1, "/lb", "1 lb green beans")],},
    {"slug": "slow-cooker-pulled-pork", "name": "Slow-cooker pulled pork", "serves": 8, "minutes": 480, "kind": "Dinner",
     "items": [("Pork shoulder", 3, "/lb", "3 lb pork shoulder"), ("Onions, Dry", 0.17, "for 3 lb", "1 onion"),
               ("Garlic", 0.1, "a sleeve", "4 cloves garlic"), ("Cabbage", 0.75, "/lb", "¼ head cabbage, for slaw")],},
    {"slug": "oven-barbecue-ribs-corn", "name": "Oven barbecue ribs with corn on the cob", "serves": 4, "minutes": 180, "kind": "Dinner",
     "items": [("Pork ribs", 3, "/lb", "3 lb pork ribs"), ("Corn-Sweet", 4, "each", "4 ears of corn")],},
    {"slug": "sausage-peppers-onions", "name": "Italian sausage with peppers and onions", "serves": 4, "minutes": 35, "kind": "Dinner",
     "items": [("Italian sausage", 1.5, "/lb", "1½ lb Italian sausage"), ("Peppers, Bell Type", 3, "each", "3 bell peppers"),
               ("Onions, Dry", 0.33, "for 3 lb", "2 onions")],},
    {"slug": "beef-chili", "name": "Beef chili", "serves": 6, "minutes": 60, "kind": "Dinner",
     "items": [("Ground beef", 1.5, "/lb", "1½ lb ground beef"), ("Onions, Dry", 0.17, "for 3 lb", "1 onion"),
               ("Peppers, Bell Type", 1, "each", "1 bell pepper"), ("Tomatoes", 1, "/lb", "1 lb tomatoes"),
               ("Jalapeno Peppers", 0.1, "/lb", "1 jalapeño"), ("Garlic", 0.1, "a sleeve", "3 cloves garlic")],},
    {"slug": "turkey-taco-lettuce-wraps", "name": "Turkey taco lettuce wraps", "serves": 4, "minutes": 25, "kind": "Dinner",
     "items": [("Ground turkey", 1.5, "/lb", "1½ lb ground turkey"), ("Lettuce", 0.67, "for 3", "2 romaine hearts"),
               ("Tomatoes", 0.5, "/lb", "2 tomatoes"), ("Shredded cheese", 0.6, "for 6-8 oz", "1 cup shredded cheese")],},
    {"slug": "beef-and-broccoli", "name": "Beef and broccoli", "serves": 4, "minutes": 30, "kind": "Dinner",
     "items": [("London broil", 1.5, "/lb", "1½ lb London broil"), ("Broccoli", 1, "/lb", "1 lb broccoli crowns"),
               ("Garlic", 0.1, "a sleeve", "3 cloves garlic"), ("Onions, Green", 0.5, "a bunch", "4 green onions")],},
    {"slug": "pot-roast-carrots-potatoes", "name": "Pot roast with carrots and potatoes", "serves": 6, "minutes": 210, "kind": "Dinner",
     "items": [("Chuck roast", 3, "/lb", "3 lb chuck roast"), ("Carrots", 1, "for 1 lb", "1 lb bag of carrots"),
               ("Potatoes", 0.4, "for 5 lb", "2 lb potatoes"), ("Onions, Dry", 0.33, "for 3 lb", "2 onions"),
               ("Celery", 0.2, "each", "2 stalks celery")],},
    {"slug": "steak-mushrooms-spinach", "name": "Steak with mushrooms and spinach", "serves": 4, "minutes": 25, "kind": "Dinner",
     "items": [("Strip steak", 1.5, "/lb", "2 strip steaks, about 1½ lb"), ("Mushrooms", 1, "for 8 oz", "8 oz mushrooms"),
               ("Spinach", 1, "for 8-10 oz", "1 bag spinach"), ("Butter", 0.06, "for 1 lb", "2 tbsp butter")],},
    {"slug": "bacon-egg-potato-hash", "name": "Bacon, egg and potato hash", "serves": 4, "minutes": 35, "kind": "Breakfast",
     "items": [("Bacon", 0.5, "/lb", "½ lb bacon"), ("Eggs", 0.33, "a dozen", "4 eggs"), ("Potatoes", 0.3, "for 5 lb", "1½ lb potatoes"),
               ("Peppers, Bell Type", 1, "each", "1 bell pepper"), ("Onions, Dry", 0.17, "for 3 lb", "1 onion")],},
    {"slug": "spinach-mushroom-frittata", "name": "Spinach and mushroom frittata", "serves": 4, "minutes": 30, "kind": "Breakfast",
     "items": [("Eggs", 0.67, "a dozen", "8 eggs"), ("Spinach", 1, "for 8-10 oz", "1 bag spinach"),
               ("Mushrooms", 1, "for 8 oz", "8 oz mushrooms"), ("Shredded cheese", 0.6, "for 6-8 oz", "1 cup shredded cheese"),
               ("Onions, Green", 0.5, "a bunch", "4 green onions")],},
    {"slug": "sausage-egg-breakfast-burritos", "name": "Sausage and egg breakfast burritos", "serves": 4, "minutes": 25, "kind": "Breakfast",
     "items": [("Eggs", 0.67, "a dozen", "8 eggs"), ("Breakfast sausage", 0.5, "/lb", "½ lb breakfast sausage"),
               ("Shredded cheese", 0.6, "for 6-8 oz", "1 cup shredded cheese"), ("Peppers, Bell Type", 1, "each", "1 bell pepper")],},
    {"slug": "loaded-baked-potatoes", "name": "Loaded baked potatoes", "serves": 4, "minutes": 70, "kind": "Dinner",
     "items": [("Potatoes", 0.4, "for 5 lb", "4 large potatoes"), ("Broccoli", 1, "/lb", "1 lb broccoli crowns"),
               ("Bacon", 0.25, "/lb", "4 slices bacon"), ("Shredded cheese", 0.6, "for 6-8 oz", "1 cup shredded cheese"),
               ("Sour cream", 0.25, "for 16 oz", "½ cup sour cream"), ("Onions, Green", 0.5, "a bunch", "4 green onions")],},
    {"slug": "sweet-potato-black-bean-tacos", "name": "Sweet potato and black bean tacos", "serves": 4, "minutes": 35, "kind": "Dinner",
     "items": [("Sweet Potatoes", 2, "/lb", "2 lb sweet potatoes"), ("Avocados", 2, "each", "2 avocados"), ("Limes", 2, "each", "2 limes"),
               ("Cilantro", 0.5, "a bunch", "½ bunch cilantro"), ("Cabbage", 0.5, "/lb", "a wedge of cabbage")],},
    {"slug": "vegetable-soup", "name": "Hearty vegetable soup", "serves": 6, "minutes": 50, "kind": "Dinner",
     "items": [("Carrots", 1, "for 1 lb", "1 lb carrots"), ("Celery", 0.3, "each", "3 stalks celery"), ("Onions, Dry", 0.17, "for 3 lb", "1 onion"),
               ("Potatoes", 0.2, "for 5 lb", "2 potatoes"), ("Beans", 0.5, "/lb", "½ lb green beans"), ("Tomatoes", 1, "/lb", "1 lb tomatoes"),
               ("Squash", 0.5, "/lb", "1 zucchini")],},
    {"slug": "roasted-brussels-sprouts-bacon", "name": "Roasted Brussels sprouts with bacon", "serves": 4, "minutes": 30, "kind": "Side",
     "items": [("Brussels Sprouts", 1, "for 1 lb", "1 lb Brussels sprouts"), ("Bacon", 0.25, "/lb", "4 slices bacon")],},
    {"slug": "stuffed-bell-peppers", "name": "Stuffed bell peppers", "serves": 4, "minutes": 60, "kind": "Dinner",
     "items": [("Peppers, Bell Type", 4, "each", "4 bell peppers"), ("Ground beef", 1, "/lb", "1 lb ground beef"),
               ("Tomatoes", 0.75, "/lb", "3 tomatoes"), ("Shredded cheese", 0.6, "for 6-8 oz", "1 cup shredded cheese"),
               ("Onions, Dry", 0.17, "for 3 lb", "1 onion")],},
    {"slug": "glazed-ham-sweet-potatoes", "name": "Glazed ham with roasted sweet potatoes", "serves": 6, "minutes": 75, "kind": "Dinner",
     "items": [("Spiral ham", 3, "/lb", "3 lb spiral ham"), ("Sweet Potatoes", 2, "/lb", "2 lb sweet potatoes")],},
    {"slug": "turkey-breast-cranberry-sauce", "name": "Roast turkey breast with cranberry sauce", "serves": 6, "minutes": 120,
     "kind": "Dinner",
     "items": [("Turkey breast", 3, "/lb", "3 lb bone-in turkey breast"), ("Cranberries", 1, "for 12 oz", "12 oz cranberries"),
               ("Oranges", 0.5, "/lb", "1 orange")],},
    {"slug": "greek-chicken-salad", "name": "Greek chicken salad", "serves": 4, "minutes": 25, "kind": "Dinner",
     "items": [("Chicken breasts", 1, "/lb", "1 lb boneless chicken breasts"), ("Cucumbers", 2, "each", "2 cucumbers"),
               ("Tomatoes", 1, "/lb", "1 lb tomatoes"), ("Lettuce", 0.67, "for 3", "2 romaine hearts"), ("Lemons", 1, "each", "1 lemon"),
               ("Onions, Dry", 0.08, "for 3 lb", "½ red onion")],},
    {"slug": "mushroom-spinach-pasta", "name": "Mushroom and spinach pasta", "serves": 4, "minutes": 25, "kind": "Dinner",
     "items": [("Mushrooms", 2, "for 8 oz", "16 oz mushrooms"), ("Spinach", 1, "for 8-10 oz", "1 bag spinach"),
               ("Garlic", 0.1, "a sleeve", "3 cloves garlic"), ("Butter", 0.06, "for 1 lb", "2 tbsp butter"),
               ("Block cheese", 0.5, "for 6-8 oz", "a 4 oz piece of hard cheese, grated")],},
    {"slug": "sausage-cabbage-skillet", "name": "Sausage and cabbage skillet", "serves": 4, "minutes": 30, "kind": "Dinner",
     "items": [("Italian sausage", 1, "/lb", "1 lb Italian sausage"), ("Cabbage", 1.5, "/lb", "½ head cabbage"),
               ("Onions, Dry", 0.17, "for 3 lb", "1 onion"), ("Apples", 0.5, "/lb", "1 apple")],},
    {"slug": "chicken-broccoli-rice-bake", "name": "Cheesy chicken and broccoli rice bake", "serves": 6, "minutes": 60, "kind": "Dinner",
     "items": [("Chicken breasts", 1.5, "/lb", "1½ lb boneless chicken breasts"), ("Broccoli", 1, "/lb", "1 lb broccoli crowns"),
               ("Shredded cheese", 1.2, "for 6-8 oz", "2 cups shredded cheese"), ("Milk", 0.0625, "for a gallon", "1 cup milk"),
               ("Onions, Dry", 0.17, "for 3 lb", "1 onion")],},
]
RECIPES = {r["slug"]: r for r in R}
WEIGHT = {"low": 2, "typical": 0, "new": 0, "high": -2, "absent": -3}


def cost_and_score(recipe, items):
    """(cost per serving or None, cost is partial, score, good-price items, pricey items) from this week's prices."""
    by_c = {i["commodity"]: i for i in items}
    total, partial, score, good, pricey = 0.0, False, 0.0, [], []
    for n, (commodity, amount, unit, _) in enumerate(recipe["items"]):
        i = by_c.get(commodity)
        weight = 2 if n == 0 else 1  # the main ingredient counts double
        if not i or not i["this_week"]:
            score += WEIGHT["absent"] * weight
            partial = True
            continue
        w = WEIGHT.get(i["status"], 0)
        if i["status"] == "low" and i.get("quality") and i["quality"][0] in ("Poor", "Fair"):
            w = 0  # cheap but poor quality isn't a reason to cook it
        score += w * weight
        if i["status"] == "low" and w > 0:
            good.append(i)
        elif i["status"] == "high":
            pricey.append(i)
        if i["unit"].strip() == unit.strip():
            total += i["price"] * amount
        else:
            partial = True
    per = round(total / recipe["serves"], 2) if total else None
    return per, partial, score / sum(2 if n == 0 else 1 for n in range(len(recipe["items"]))), good, pricey


def ranked(items):
    """Recipes for this week, best first: [(recipe, cost per serving, partial, score, good, pricey)]."""
    rows = [(r, *cost_and_score(r, items)) for r in R]
    return sorted(rows, key=lambda x: (-x[3], x[1] if x[1] is not None else 99))
