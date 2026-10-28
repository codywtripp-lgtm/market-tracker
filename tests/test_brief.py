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


def test_build_from_current_export():
    as_of, body = brief.build()
    assert as_of.weekday() < 6  # a market day
    assert "<h2>What moved today</h2>" in body
    assert "<h2>New York summary</h2>" in body
    assert "<svg class=\"spark\"" in body
    for banned in ("Wait if you can", "Hold off", "Good time to buy"):
        assert banned not in body
    # no app-style widgets: the page is set as ruled entries and tables
    for widget in ('class="pill', 'class="tile', 'class="chip', 'class="stat"', " — "):
        assert widget not in body


def test_lede_agreement():
    rows = lambda *names: [{"name": n} for n in names]  # noqa: E731
    groups = {"firming": rows("Romaine"), "softening": rows("Limes", "Roma tomatoes"), "steady": []}
    assert brief.lede(groups, rows("Strawberries"), []) == (
        "Romaine is firming at Hunts Point, while limes and Roma tomatoes are softening. "
        "Strawberries are high for the season.")
