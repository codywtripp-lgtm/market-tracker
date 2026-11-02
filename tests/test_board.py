from pipeline import board


def test_home_puts_what_to_do_first():
    as_of, out = board.build()
    home = out["home"]
    assert home.index("What to do today") < home.index("All prices")
    assert home.count('class="brow"') >= 45  # every item, three markets
    assert 'role="tablist"' in home and '<svg class="spark"' in home
    for banned in ("Wait if you can", "Hold off", "Good time to buy", "Alerts only fire", " — "):
        assert banned not in home


def test_item_page_answers_the_search_and_shows_a_real_chart():
    _, out = board.build()
    page = out["items/romaine-lettuce-prices"]
    assert '<p class="answer">' in page and "a case" in page
    assert '<figure class="chart">' in page and "Usual range for the time of year" in page
    assert "Will romaine lettuce prices go up or down?" in page
    assert '"@type": "FAQPage"' in page
    la = out["items/romaine-lettuce-prices--los-angeles"]
    assert "Romaine lettuce prices today, Los Angeles" in la and 'role="tablist"' not in la


def test_lede_agreement():
    row = lambda c, d="steady", s="normal", ch=0.0: {"commodity": c, "dir": d, "status": s, "change": ch}  # noqa: E731
    rows = [row("Lettuce, Romaine", "firming", ch=0.1), row("Limes", "softening", ch=-0.1),
            row("Tomatoes, Plum Type", "softening", ch=-0.08), row("Strawberries", s="expensive")]
    assert board.lede(rows, "New York") == (
        "Romaine lettuce is firming at Hunts Point, while limes and Roma tomatoes are softening. "
        "Strawberries are high for the season with no relief in sight.")


def test_usda_place_and_tone_in_plain_words():
    assert board.place("SALINAS-WATSONVILLE CALIFORNIA") == "Salinas-Watsonville, California"
    assert board.place("CENTRAL AND SOUTHERN CALIFORNIA AND ARIZONA") == "Central and Southern California and Arizona"
    assert board._simple_tone("Slightly Higher") == "slightly higher"
    assert board._simple_tone("Conventional slightly higher, organic higher") == "higher"
    assert board._simple_tone("Crown cuts slightly higher, others about steady") == "higher on some packs"
    assert board._simple_tone("Hearts slightly higher, 24s lower") == "mixed"


def test_new_packs_compare_with_last_year_not_a_dead_end():
    i = {"status": "not enough history", "vs_year": 12.0, "vs_norm": None}
    assert "12% above last year" in board.season(i)
    assert "Not enough history" not in board.season(i)


def test_usda_supply_words_read_as_plain_sentences():
    from pipeline.board import _tone_words
    assert _tone_words("LIGHT") == "light" and _tone_words("MODERATE") == "moderate"
    assert _tone_words("Very Light and in few hands.") == "very light and in few hands"
    assert _tone_words("Carton 40-80s exceeds supply , others moderate.") == "carton 40-80s exceeds supply, others moderate"
    assert _tone_words("Mexico crossings light") == "Mexico crossings light"


def test_normal_items_show_the_usual_range_not_a_percent():
    from pipeline import board
    i = {"status": "normal", "usual_low": 33.0, "usual_high": 58.0, "vs_norm": -29.2}
    assert board.usual_range(i) == "$33 to $58"
    assert "usually $33 to $58" in board.season(i) and "29%" not in board.season(i)
    assert board.usual_range({"status": "cheap", "usual_low": 33.0, "usual_high": 58.0}) == ""


def test_supply_news_leads_with_the_areas_shipping_the_most():
    shipped = {"MEXICO CROSSINGS THROUGH PHARR TEXAS": 84.0, "MEXICO CROSSINGS THROUGH LAREDO TEXAS": 61.0, "SOUTH FLORIDA": 1.5}
    areas = {"MEXICO CROSSINGS THROUGH TEXAS", "SOUTH FLORIDA", "CARIBBEAN IMPORTS - PORTS OF ENTRY SOUTH FLORIDA"}
    assert board.main_areas(areas, shipped)[0] == "MEXICO CROSSINGS THROUGH TEXAS"
    assert "SOUTH FLORIDA" not in board.main_areas(areas, shipped)
    # no shipments on record for an area: USDA leaves it out, so it can't be ruled out
    lemons = {"CENTRAL AND SOUTHERN CALIFORNIA AND ARIZONA", "MEXICO CROSSINGS THROUGH TEXAS"}
    assert board.main_areas(lemons, {"MEXICO CROSSINGS THROUGH PHARR TEXAS": 6.0}) == [
        "MEXICO CROSSINGS THROUGH TEXAS", "CENTRAL AND SOUTHERN CALIFORNIA AND ARIZONA"]
    assert board._ships_from("FLORIDA WEST AND GEORGIA DISTRICT", "FLORIDA")
    assert not board._ships_from("SOUTH FLORIDA", "FLORIDA WEST")


def test_usda_ratings_lose_their_side_remarks():
    assert board._rating("Shippers First Grade light.") == "light"
    assert board._rating("Very Light and in few hands. Too few quote.") == "very light and in few hands"
    assert board._rating("VERY LIGHT") == "very light"
