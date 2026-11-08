import datetime as dt

from pipeline import board, seasons


def weeks_each_year(first, last, years=range(2019, 2026)):
    return {(y, w) for y in years for w in range(first, last + 1)}


def test_area_that_usually_starts_soon():
    seen = {("Broccoli", "DESERT"): weeks_each_year(47, 52) | weeks_each_year(1, 14)}
    ev = seasons.events(seen, dt.date(2025, 11, 7))  # ISO week 45
    assert [e["kind"] for e in ev["Broccoli"]] == ["start"]
    assert ev["Broccoli"][0]["week"] == dt.date(2025, 11, 17)


def test_area_that_usually_finishes_soon():
    seen = {("Lettuce, Iceberg", "SALINAS-WATSONVILLE CALIFORNIA"):
            weeks_each_year(14, 47) | {(2025, w) for w in range(14, 46)}}
    ev = seasons.events(seen, dt.date(2025, 11, 7))
    assert ev["Lettuce, Iceberg"][0]["kind"] == "finish"


def test_year_round_and_dropped_areas_say_nothing():
    seen = {("Carrots", "KERN DISTRICT CALIFORNIA"): weeks_each_year(1, 52) | {(2025, w) for w in range(1, 46)},
            ("Celery", "MICHIGAN"): weeks_each_year(47, 50, range(2017, 2023))}
    assert seasons.events(seen, dt.date(2025, 11, 7)) == {}


def test_renamed_districts_are_one_area():
    assert seasons.area("Lettuce, Iceberg", "IMPERIAL, COACHELLA AND PALO VERDE VALLEYS CALIFORNIA") == "DESERT"
    assert seasons.area("Lettuce, Iceberg", "WESTERN ARIZONA") == "DESERT"
    assert seasons.area("Celery", "SANTA MARIA DISTRICT CALIFORNIA") == "SANTA MARIA CALIFORNIA"


def test_place_names():
    assert board.short_place("SOUTH GEORGIA") == "South Georgia"
    assert board.short_place("SOUTH AFRICA IMPORTS - PORT OF ENTRY PHILADELPHIA AREA") == "South Africa imports via Philadelphia"
    assert board.short_place("SALINAS-WATSONVILLE CALIFORNIA") == "Salinas-Watsonville, CA"
