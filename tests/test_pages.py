import importlib.util
from pathlib import Path

from pipeline import pages


def _site():
    path = Path(__file__).resolve().parent.parent / "scripts" / "build_site.py"
    spec = importlib.util.spec_from_file_location("build_site", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_slugs_match_site_builder():
    assert pages.PAGES == _site().PAGE_NAMES


def test_plural():
    assert pages.plural("Tomato") == "tomatoes"
    assert pages.plural("Strawberry") == "strawberries"
    assert pages.plural("Romaine lettuce") == "romaine lettuce"
    assert pages.plural("Roma tomato") == "Roma tomatoes"


def test_pages_answer_the_search_question():
    as_of, out = pages.build_all()
    body = out["romaine-lettuce-prices"]
    assert '<p class="answer">' in body and "a case" in body
    assert "Will romaine lettuce prices go up or down?" in body
