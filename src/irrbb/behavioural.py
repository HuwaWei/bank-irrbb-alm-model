"""Behavioural treatment of non-maturity deposits (CASA).

Core share is capped and slotted uniformly over (0, 2L] so its average life is
L years; the non-core share reprices overnight. Caps per MAS Notice 637
Annex 10B Table 10B-2 (same as BCBS SRP31 and BNM ED Table 1): retail transactional 90% / 5.0y, retail non-transactional
70% / 4.5y, wholesale 50% / 4.0y.
"""
from __future__ import annotations

from .balance_sheet import Position, spread

NMD_CAPS = {
    "retail_tx": (0.90, 5.0),
    "retail_ntx": (0.70, 4.5),
    "wholesale": (0.50, 4.0),
}
ON_T = 1 / 365 / 2  # overnight slot
ADMIN_RATE_LAG = 1 / 12  # [A] administered deposit rates move ~1 month after market


def check_caps(p: Position) -> None:
    cap_pct, cap_life = NMD_CAPS[p.nmd_category]
    if p.core_pct > cap_pct + 1e-12 or p.core_life > cap_life + 1e-12:
        raise ValueError(
            f"{p.ccy} {p.name}: core {p.core_pct:.0%}/{p.core_life}y breaches cap "
            f"{cap_pct:.0%}/{cap_life}y")


def nmd_profile(p: Position) -> list[tuple[float, float]]:
    """Behavioural repricing profile of an NMD as (t, weight)."""
    check_caps(p)
    prof = [(ON_T, 1.0 - p.core_pct)]
    if p.core_pct > 0:
        prof += [(t, w * p.core_pct) for t, w in spread(0, 2 * p.core_life, 24)]
    return prof


def scale_nmds(positions: list[Position], core_pct_delta: float = 0.0,
               core_life: float | None = None, beta: float | None = None,
               categories: tuple[str, ...] = ("retail_tx", "retail_ntx"),
               ccys: tuple[str, ...] = ("SGD", "MYR")) -> list[Position]:
    """Return a copy of the book with retail NMD assumptions flexed (caps enforced
    by clipping, so the flexed case is always a permissible regulatory case)."""
    out = []
    for p in positions:
        if p.kind == "nmd" and p.nmd_category in categories and p.ccy in ccys:
            cap_pct, cap_life = NMD_CAPS[p.nmd_category]
            kw = {"core_pct": min(cap_pct, max(0.0, p.core_pct + core_pct_delta))}
            if core_life is not None:
                kw["core_life"] = min(cap_life, core_life)
            if beta is not None:
                kw["beta"] = beta
            p = p.with_(**kw)
        out.append(p)
    return out
