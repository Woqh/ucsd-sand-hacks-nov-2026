import pytest

from api.core.insights import (DAY_MS, MIN_POINTS, MIN_SEATED_SEC, _ranks, pain_vs_slouch, slouch_exposure,
                               spaced, spearman)
from api.core.scoring import Segment

D0 = 1_731_542_400_000


def pt(week, pain, slouch, **kw):
    return {"t": D0 + week * 7 * DAY_MS, "pain": pain, "slouchPct": slouch, **kw}


def test_ranks_average_ties():
    assert _ranks([10, 20, 20, 30]) == [1.0, 2.5, 2.5, 4.0]
    assert _ranks([3, 1, 2]) == [3.0, 1.0, 2.0]


def test_spearman_known_values():
    assert spearman([1, 2, 3, 4, 5], [10, 20, 30, 40, 50]) == pytest.approx(1.0)
    assert spearman([1, 2, 3, 4, 5], [50, 40, 30, 20, 10]) == pytest.approx(-1.0)
    assert spearman([1, 2, 3, 4, 5], [1, 3, 2, 5, 4]) == pytest.approx(0.8)
    # monotonic but non-linear still scores 1 (that's why we use ranks)
    assert spearman([1, 2, 3, 4], [1, 10, 100, 1000]) == pytest.approx(1.0)


def test_spearman_undefined_cases():
    assert spearman([1, 2], [1, 2]) is None                      # too few points
    assert spearman([1, 2, 3, 4], [5, 5, 5, 5]) is None          # no variation in pain
    assert spearman([2, 2, 2, 2], [1, 2, 3, 4]) is None


def test_slouch_exposure_needs_enough_seated_time():
    t_end = D0 + 7 * DAY_MS
    # 10 h seated in the window, 2 h of it slouching -> 20%
    segs = [Segment("GOOD", D0 + 10 * 3600_000, D0 + 18 * 3600_000), Segment("SLOUCHING", D0 + 18 * 3600_000, D0 + 20 * 3600_000)]
    assert slouch_exposure(segs, t_end) == (20.0, 10 * 3600)
    # only 30 minutes of data: refuse to report a percentage
    tiny = [Segment("SLOUCHING", D0, D0 + 1800_000)]
    pct, seated = slouch_exposure(tiny, t_end)
    assert pct is None and seated == 1800 < MIN_SEATED_SEC
    # data from before the 7-day window doesn't count
    old = [Segment("GOOD", D0 - 5 * DAY_MS, D0 - 4 * DAY_MS)]
    assert slouch_exposure(old, t_end)[0] is None


def test_spaced_keeps_windows_from_overlapping():
    pts = [{"t": D0 + h * 3600_000} for h in (0, 24, 24 * 6, 24 * 7, 24 * 13, 24 * 14)]
    kept = [(p["t"] - D0) // 3600_000 for p in spaced(pts)]
    assert kept == [0, 24 * 6, 24 * 13]          # >= 6 days apart, oldest first


def test_not_enough_points_reports_no_correlation():
    pts = [pt(i, 3, 10 + i) for i in range(MIN_POINTS - 1)]
    out = pain_vs_slouch(pts)
    assert out["enough"] is False and out["n"] == MIN_POINTS - 1 and out["rho"] is None and out["strength"] is None
    assert all(p["used"] for p in pts)


def test_positive_pattern_is_bucketed_and_labelled():
    pts = [pt(i, pain, slouch) for i, (pain, slouch) in enumerate([(1, 10), (2, 15), (4, 30), (6, 45), (8, 60), (9, 70)])]
    out = pain_vs_slouch(pts)
    assert out["enough"] and out["n"] == 6 and out["direction"] == "positive" and out["strength"] == "stronger"
    assert out["rho"] == 1.0


def test_negative_and_no_pattern():
    neg = pain_vs_slouch([pt(i, 9 - i, 10 + 10 * i) for i in range(6)])
    assert neg["direction"] == "negative" and neg["strength"] == "stronger"
    # pain ranks 1..5 vs slouch ranks 3,5,1,2,4 -> rho = -0.1: no clear pattern
    flat = pain_vs_slouch([pt(i, p, s) for i, (p, s) in enumerate([(1, 30), (2, 50), (3, 10), (4, 20), (5, 40)])])
    assert flat["enough"] and flat["rho"] == -0.1 and flat["strength"] == "none" and flat["direction"] == "negative"
    same_pain = pain_vs_slouch([pt(i, 4, 10 + 5 * i) for i in range(6)])  # every rating identical
    assert same_pain["rho"] is None and same_pain["strength"] == "none"


def test_points_without_exposure_or_too_close_are_excluded_and_flagged():
    pts = [pt(0, 2, 10), pt(1, 3, None), pt(2, 4, 30), pt(3, 5, 40), pt(4, 6, 50), pt(5, 7, 60)]
    pts.append({"t": pts[0]["t"] + DAY_MS, "pain": 9, "slouchPct": 99})   # one day after the first: overlaps
    out = pain_vs_slouch(pts)
    assert out["n"] == 5
    assert [p["used"] for p in pts] == [True, False, True, True, True, True, False]
