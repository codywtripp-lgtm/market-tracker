"""A cheaper grade or a different variety must not stand in for the product a page names."""

from pipeline import config, export


def _row(d, grade, price=40.0):
    return {"report_date": d, "grade": grade, "unit_price": str(price)}


def test_lower_grade_waits_three_days_before_taking_over():
    days = {"2026-11-02": [_row("2026-11-02", "Shippers First Grade", 42.25)],
            "2026-11-03": [_row("2026-11-03", "Shippers Choice", 33)],
            "2026-11-04": [_row("2026-11-04", "Shippers First Grade", 42)],
            "2026-11-05": [_row("2026-11-05", "Shippers Choice", 33)],
            "2026-11-06": [_row("2026-11-06", "Shippers Choice", 33)],
            "2026-11-09": [_row("2026-11-09", "Shippers Choice", 33)]}
    kept = export.drop_stand_ins(days)
    assert "2026-11-03" not in kept and "2026-11-05" not in kept and "2026-11-06" not in kept
    assert kept["2026-11-09"][0]["grade"] == "Shippers Choice"  # the market has switched


def test_lower_grade_dropped_when_standard_quoted_same_day():
    kept = export.drop_stand_ins({"2026-11-02": [_row("2026-11-02", "U.S. One"), _row("2026-11-02", "U.S. Two", 20)]})
    assert [r["grade"] for r in kept["2026-11-02"]] == ["U.S. One"]


def test_apple_fancy_grade_is_not_standard_but_pear_fancy_is():
    base = {"appearance": "", "condition": "", "quality": ""}
    assert not export.is_standard({**base, "commodity": "Apples", "grade": "U.S. Fancy"})
    assert not export.is_standard({**base, "commodity": "Apples", "grade": "WA Fancy"})
    assert export.is_standard({**base, "commodity": "Apples", "grade": "WA Extra Fancy"})
    assert export.is_standard({**base, "commodity": "Pears", "grade": "OR Fancy"})
    assert export.is_standard({**base, "commodity": "Lemons", "grade": "Marked Fancy"})


def test_apples_split_by_variety():
    assert config.item_of("Apples", "GALA") == "Apples, Gala"
    assert config.item_of("Apples", "Granny smith") == "Apples, Granny Smith"
    assert config.item_of("Apples", "Ambrosia") == "Apples"
    assert config.item_of("Pears", "Bosc") == "Pears"
    assert config.base("Apples, Fuji") == "Apples"
