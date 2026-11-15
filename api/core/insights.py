"""Personal insights: how a user's own weekly pain ratings relate to their own slouching. Pure.

This is deliberately NOT a prediction or a risk score. Research has not established that slouching
causes pain (docs/health-claims.md), so all we do is show whether, in THIS person's data, weeks with
more slouching tended to line up with more pain. Always paired with plain hedging in the UI.

Method: for each check-in, slouch exposure = share of seated time spent SLOUCHING in the 7 days
before it. Points are kept at least 6 days apart so the 7-day windows don't overlap, and the
relationship is Spearman's rank correlation (robust to outliers and to non-linearity). It is only
reported once there are MIN_POINTS points; even then n is small, so the wording must say so.
"""
from __future__ import annotations

import math
from typing import Any, Optional, Sequence

from api.core import scoring

DAY_MS = scoring.DAY_MS
WINDOW_MS = 7 * DAY_MS          # exposure window before each check-in
MIN_SPACING_MS = 6 * DAY_MS     # keep points this far apart so windows don't overlap
MIN_SEATED_SEC = 2 * 3600       # need at least this much seated data in the window
MIN_POINTS = 5                  # below this we show no correlation at all
WEAK, MODEST = 0.3, 0.6         # |rho| cut-offs for the plain-language bucket (rough rules of thumb)


def slouch_exposure(segs: list[scoring.Segment], t_end: int) -> tuple[Optional[float], int]:
    """(slouch % of seated time in the 7 days before t_end or None if too little data, seated seconds)."""
    a = t_end - WINDOW_MS
    s = scoring.summarize(scoring.clip(segs, a, t_end), [], a, t_end)
    seated = int(s["seatedSec"])
    if seated < MIN_SEATED_SEC:
        return None, seated
    return round(100 * s["slouchSec"] / seated, 1), seated


def spaced(points: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """Greedy oldest-first selection keeping points at least MIN_SPACING_MS apart."""
    out: list[dict[str, Any]] = []
    for p in sorted(points, key=lambda p: p["t"]):
        if not out or p["t"] - out[-1]["t"] >= MIN_SPACING_MS:
            out.append(p)
    return out


def _ranks(xs: Sequence[float]) -> list[float]:
    """1-based ranks, ties get the average rank."""
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    ranks = [0.0] * len(xs)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        avg = (i + j) / 2 + 1
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return ranks


def spearman(xs: Sequence[float], ys: Sequence[float]) -> Optional[float]:
    """Spearman's rho, or None if undefined (fewer than 3 points or no variation in x or y)."""
    n = len(xs)
    if n != len(ys) or n < 3:
        return None
    rx, ry = _ranks(xs), _ranks(ys)
    mx, my = sum(rx) / n, sum(ry) / n
    sxx = sum((a - mx) ** 2 for a in rx)
    syy = sum((b - my) ** 2 for b in ry)
    if sxx == 0 or syy == 0:
        return None
    sxy = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    return sxy / math.sqrt(sxx * syy)


def pain_vs_slouch(points: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """`points`: dicts with t, pain, slouchPct (None = excluded). Marks `used` points in place and
    returns the correlation summary:
        {enough, n, needed, rho, strength: none|modest|stronger|None, direction: positive|negative|None}"""
    valid = [p for p in points if p.get("slouchPct") is not None]
    chosen = spaced(valid)
    chosen_ids = {id(p) for p in chosen}
    for p in points:
        p["used"] = id(p) in chosen_ids
    n = len(chosen)
    out: dict[str, Any] = {"enough": n >= MIN_POINTS, "n": n, "needed": MIN_POINTS,
                           "rho": None, "strength": None, "direction": None}
    if n < MIN_POINTS:
        return out
    rho = spearman([p["slouchPct"] for p in chosen], [p["pain"] for p in chosen])
    if rho is None:                                  # e.g. every pain rating identical
        out["strength"] = "none"
        return out
    out["rho"] = round(rho, 2)
    out["strength"] = "none" if abs(rho) < WEAK else ("modest" if abs(rho) < MODEST else "stronger")
    out["direction"] = "positive" if rho > 0 else "negative"
    return out
