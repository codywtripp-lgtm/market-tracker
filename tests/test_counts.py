import datetime as dt

from pipeline import brief, export


def opt(count, vs, status, main=False):
    return {"count": count, "label": f"{count}s", "case": 30.0, "date": "2026-11-06", "vs_norm": vs,
            "status": status, "main": main}


def test_next_count_down_is_the_better_buy():
    opts = [opt(70, 70, "expensive", main=True), opt(80, 53, "expensive"), opt(90, 10, "cheap")]
    assert brief.best_count(opts)["count"] == 80  # 90s are two steps away


def test_no_pick_when_both_inside_usual_range():
    assert brief.best_count([opt(48, 20, "normal", main=True), opt(60, 2, "normal")]) is None


def test_no_pick_for_a_count_far_from_the_main_one():
    assert brief.best_count([opt(72, -7, "cheap", main=True), opt(113, -23, "cheap")]) is None


def test_no_pick_into_a_worse_band():
    assert brief.best_count([opt(140, -15, "cheap", main=True), opt(165, -30, "normal")]) is None


def test_narrow_history_is_not_high():
    # contract-priced item: past years all within a dollar, today 4.6% over the usual price
    weekly = {dt.date(y, 11, 2) + dt.timedelta(weeks=k): 21.0 + 0.1 * k for y in range(2019, 2026) for k in range(-2, 3)}
    out = export.seasonal_status(weekly, dt.date(2026, 11, 2), 22.0)
    assert out["status"] == "normal"
    assert out["usual_low"] < 21.0 * 0.96 and out["usual_high"] > 22.0
    assert export.seasonal_status(weekly, dt.date(2026, 11, 2), 23.5)["status"] == "expensive"
