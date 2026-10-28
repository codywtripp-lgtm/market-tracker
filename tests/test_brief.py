from pipeline import brief


def test_call_rising_cheap_is_buy_ahead():
    assert brief.call("cheap", 0.12, False).startswith("Buy ahead")


def test_call_falling_expensive_is_buy_as_needed():
    assert brief.call("expensive", -0.10, False).startswith("Buy as needed")


def test_small_moves_and_stable_items_are_steady():
    assert brief.call("normal", 0.03, False) == "Steady"
    assert brief.call("expensive", 0.20, True) == "High, no relief expected yet"


def test_vs_usual_wording():
    assert brief.vs_usual(None) == "—"
    assert brief.vs_usual(3) == "about usual"
    assert brief.vs_usual(-42.6) == "43% below"


def test_build_from_current_export():
    as_of, body = brief.build()
    assert as_of.weekday() < 6  # a market day
    assert "<h2>What moved today</h2>" in body
    assert body.startswith("<h1>Produce Buyer's Brief")
    assert "At a glance: New York" in body
    assert "<svg class=\"spark\"" in body
