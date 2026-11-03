"""Stylised balance sheet of an illustrative Singapore bank with a Malaysian
subsidiary. NOT any real bank. Balances in local-currency millions.

Each position carries a repricing profile: list of (repricing time in years,
weight). Fixed instruments reprice at maturity; floating ones at next reset.
Non-maturity deposits (NMDs) are split into core / non-core by behavioural
parameters (see behavioural.py).
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace

import numpy as np


def spread(lo: float, hi: float, n: int = 12) -> list[tuple[float, float]]:
    """Balance spread evenly across (lo, hi]: n equal slices at slice midpoints."""
    edges = np.linspace(lo, hi, n + 1)
    mids = (edges[:-1] + edges[1:]) / 2
    return [(float(m), 1.0 / n) for m in mids]


def ladder(points: list[tuple[float, float, float]]) -> list[tuple[float, float]]:
    """Combine weighted spreads: [(lo, hi, weight)]."""
    out: list[tuple[float, float]] = []
    for lo, hi, w in points:
        out += [(t, w * x) for t, x in spread(lo, hi)]
    return out


@dataclass(frozen=True)
class Position:
    name: str
    ccy: str
    side: str            # "A" asset, "L" liability
    balance: float       # local ccy millions
    rate: float          # current client / coupon rate, decimal
    kind: str            # "fixed" | "floating" | "nmd" | "nonrate"
    profile: list = field(default_factory=list)  # (t, weight); unused for nmd/nonrate
    beta: float = 1.0    # pass-through of market rate changes on repricing (NII)
    # NMD behavioural parameters
    core_pct: float = 0.0      # share of balance treated as core (sticky, rate-insensitive)
    core_life: float = 0.0     # average life of core in years (slotted uniformly 0..2L)
    nmd_category: str = ""     # retail_tx | retail_ntx | wholesale
    freq: int = 1              # coupon frequency for fixed cash flows (EVE)
    off_bs: bool = False       # derivative leg (excluded from balance sheet totals)
    market_rate: bool = False  # priced off market rates (interbank, HQLA, bonds, swaps):
                               # NII post-shock floor -100bp, not the 0% client-rate floor

    @property
    def sign(self) -> int:
        return 1 if self.side == "A" else -1

    def with_(self, **kw) -> "Position":
        return replace(self, **kw)


# --- Stylised positions -------------------------------------------------------
# All rates and balances are [A] illustrative assumptions, sized to resemble a
# mid-sized Singapore commercial bank (S$53.5bn SGD book) with a RM58bn Malaysian
# subsidiary (S$71.7bn group assets). Client rates are set off the base curves in
# market.py. Fixed cash flows pay annual coupons unless `freq` is set [A].

SGD_BOOK = [
    # Assets
    Position("Cash & MAS reserve balances", "SGD", "A", 2_000, 0.0, "nonrate"),
    Position("Interbank placements", "SGD", "A", 3_000, 0.0130, "fixed", spread(0, 0.25, 6), market_rate=True),
    Position("HQLA: MAS bills / T-bills", "SGD", "A", 2_000, 0.0187, "fixed", spread(0, 0.5, 6), market_rate=True),
    Position("HQLA: SGS bonds (FVOCI)", "SGD", "A", 6_000, 0.0185, "fixed",
             ladder([(1, 3, 0.30), (3, 5, 0.30), (5, 10, 0.40)]), market_rate=True),
    Position("Mortgages: floating (3M SORA)", "SGD", "A", 14_000, 0.0285, "floating", spread(0, 0.25, 6)),
    Position("Mortgages: 2-3Y fixed packages", "SGD", "A", 7_000, 0.0245, "fixed", spread(0, 3)),
    Position("Corporate loans: floating (1M/3M SORA)", "SGD", "A", 11_000, 0.0300, "floating", spread(0, 0.25, 6)),
    Position("SME / term loans: fixed", "SGD", "A", 6_000, 0.0380, "fixed", spread(0, 5)),
    Position("Other non-rate-sensitive assets", "SGD", "A", 2_500, 0.0, "nonrate"),
    # Liabilities
    Position("CASA: retail transactional", "SGD", "L", 17_000, 0.0010, "nmd", beta=0.15,
             core_pct=0.85, core_life=4.5, nmd_category="retail_tx"),
    Position("Savings: retail non-transactional", "SGD", "L", 9_000, 0.0060, "nmd", beta=0.40,
             core_pct=0.65, core_life=3.5, nmd_category="retail_ntx"),
    Position("CASA: wholesale operational", "SGD", "L", 5_000, 0.0040, "nmd", beta=0.60,
             core_pct=0.40, core_life=2.0, nmd_category="wholesale"),
    Position("Fixed deposits", "SGD", "L", 13_000, 0.0150, "fixed", ladder([(0, 1, 0.9), (1, 2, 0.1)]), beta=0.85),
    Position("Interbank borrowing", "SGD", "L", 3_000, 0.0120, "fixed", spread(0, 0.25, 6), market_rate=True),
    Position("Senior unsecured bonds (fixed)", "SGD", "L", 2_000, 0.0250, "fixed", spread(3, 5, 4), market_rate=True),
    Position("Other non-rate-sensitive liabilities", "SGD", "L", 500, 0.0, "nonrate"),
]

MYR_BOOK = [
    Position("Cash & BNM SRR balances", "MYR", "A", 2_000, 0.0, "nonrate"),
    Position("Interbank placements", "MYR", "A", 4_000, 0.0300, "fixed", spread(0, 0.25, 6), market_rate=True),
    Position("HQLA: MGS / GII (FVOCI)", "MYR", "A", 10_000, 0.0370, "fixed",
             ladder([(1, 3, 0.20), (3, 7, 0.40), (7, 15, 0.40)]), market_rate=True),
    Position("Mortgages: floating (SBR-linked)", "MYR", "A", 18_000, 0.0410, "floating", spread(0, 1 / 12, 2), beta=1.0),
    Position("Hire purchase: fixed-rate", "MYR", "A", 8_000, 0.0480, "fixed", spread(0, 7)),
    Position("Corporate loans: floating (COF/KLIBOR)", "MYR", "A", 13_000, 0.0450, "floating", spread(0, 0.25, 6)),
    Position("Other non-rate-sensitive assets", "MYR", "A", 3_000, 0.0, "nonrate"),
    Position("CASA: retail transactional", "MYR", "L", 14_000, 0.0025, "nmd", beta=0.20,
             core_pct=0.75, core_life=4.0, nmd_category="retail_tx"),
    Position("Savings: retail non-transactional", "MYR", "L", 7_000, 0.0100, "nmd", beta=0.40,
             core_pct=0.55, core_life=3.0, nmd_category="retail_ntx"),
    Position("CASA: wholesale operational", "MYR", "L", 5_000, 0.0150, "nmd", beta=0.60,
             core_pct=0.40, core_life=2.0, nmd_category="wholesale"),
    Position("Fixed deposits", "MYR", "L", 22_000, 0.0240, "fixed", ladder([(0, 1, 0.9), (1, 2, 0.1)]), beta=0.85),
    Position("Interbank borrowing", "MYR", "L", 3_000, 0.0300, "fixed", spread(0, 0.25, 6), market_rate=True),
    Position("Other non-rate-sensitive liabilities", "MYR", "L", 2_000, 0.0, "nonrate"),
]


def book(ccy: str) -> list[Position]:
    return {"SGD": SGD_BOOK, "MYR": MYR_BOOK}[ccy]


def totals(positions: list[Position]) -> dict:
    a = sum(p.balance for p in positions if p.side == "A" and not p.off_bs)
    lia = sum(p.balance for p in positions if p.side == "L" and not p.off_bs)
    return {"assets": a, "liabilities": lia, "equity": a - lia}
