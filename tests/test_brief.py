from pipeline import brief


def test_firming_hard_item_says_buy_deeper():
    d, action = brief.call("normal", 0.12, False, "Onions, Dry")
    assert d == "firming" and action.startswith("It stores (1–8 months cold)")


def test_storage_rule_uses_low_end_of_storage_life():
    assert brief.stores("Celery") and brief.stores("Limes")
    assert not brief.stores("Grapes") and not brief.stores("Avocados") and not brief.stores("Lettuce, Romaine")


def test_firming_perishable_never_says_buy_ahead():
    d, action = brief.call("cheap", 0.12, False, "Lettuce, Romaine")
    assert d == "firming" and "Buy to need" in action


def test_softening_keeps_inventory_tight():
    d, action = brief.call("expensive", -0.10, False, "Limes")
    assert d == "softening" and action.startswith("Keep inventory tight") and "Relief" in action


def test_small_moves_and_stable_items_are_steady():
    assert brief.call("normal", 0.03, False) == ("steady", "")
    assert brief.call("expensive", 0.20, True)[1].startswith("High for the season")
    assert "specials" in brief.call("cheap", None, False)[1]


def test_vs_usual_wording():
    assert brief.vs_usual(None) == "—"
    assert brief.vs_usual(3) == "about usual"
    assert brief.vs_usual(-42.6) == "43% below"


def test_turning_markets_are_called_as_turns():
    # strawberries Oct 2026: $34 now, about $35 next week, about $31 in two weeks
    assert brief.direction(-0.09, False, 0.03) == "topping"
    assert brief.direction(0.10, False, -0.04) == "bottoming"
    assert brief.direction(-0.09, False, -0.02) == "softening"
    d, action = brief.call("normal", -0.09, False, "Strawberries", 0.03)
    assert d == "topping" and "don't lock price at the top" in action
