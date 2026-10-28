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
