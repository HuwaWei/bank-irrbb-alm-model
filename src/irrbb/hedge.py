"""Size a plain-vanilla OIS interest rate swap to bring EVE within limit."""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import market as mk
from .balance_sheet import Position
from .curves import par_swap_rate, zero_rate
from .engine import base_nii, delta_eve_table, delta_nii, worst_eve


def swap_legs(ccy: str, notional: float, tenor: float, direction: str) -> list[Position]:
    """IRS as two balance-sheet-equivalent legs.

    receive-fixed = long a fixed-rate asset (quarterly coupons to `tenor`)
                    + short a floating liability resetting quarterly.
    pay-fixed     = the reverse.
    """
    k = par_swap_rate(ccy, tenor)
    flt = float(zero_rate(ccy, 0.25))  # current 3M compounded fixing proxy
    fixed_side, float_side = ("A", "L") if direction == "receive" else ("L", "A")
    return [
        Position(f"IRS {direction}-fixed {tenor:g}Y fixed leg", ccy, fixed_side, notional, k,
                 "fixed", [(tenor, 1.0)], freq=4, off_bs=True, market_rate=True),
        Position(f"IRS {direction}-fixed {tenor:g}Y float leg", ccy, float_side, notional, flt,
                 "floating", [(0.125, 1.0)], off_bs=True, market_rate=True),
    ]


def size_hedge(positions: list[Position], ccy: str, tenor: float, direction: str,
               target_pct: float = mk.EVE_HEDGE_TARGET_PCT_T1, step: float = 250.0,
               max_notional: float = 30_000.0) -> float:
    """Smallest notional (multiple of `step`, local ccy m) bringing worst-case
    dEVE/Tier 1 to <= target. Returns nan if not achievable."""
    for n in np.arange(step, max_notional + step, step):
        if worst_eve(positions + swap_legs(ccy, n, tenor, direction))[1] <= target_pct:
            return float(n)
    return float("nan")


def hedge_menu(positions: list[Position], ccy: str = "SGD", direction: str = "receive",
               tenors=(3, 5, 7, 10)) -> pd.DataFrame:
    """Notional needed per tenor and the side effects on NII."""
    nii0 = base_nii(positions)
    rows = []
    for t in tenors:
        n = size_hedge(positions, ccy, t, direction)
        legs = swap_legs(ccy, n, t, direction)
        h = positions + legs
        sc, w = worst_eve(h)
        rows.append({
            "Tenor (Y)": t,
            "Par rate %": round(100 * legs[0].rate, 3),
            "Notional (m)": n,
            "Worst dEVE % T1": round(w, 1),
            "Worst scenario": sc,
            "Carry 12M (SGD m)": round(base_nii(h) - nii0, 1),
            "dNII -200bp (SGD m)": round(delta_nii(h, -200), 1),
            "dNII +200bp (SGD m)": round(delta_nii(h, 200), 1),
        })
    return pd.DataFrame(rows)


def before_after(positions: list[Position], legs: list[Position]) -> dict[str, pd.DataFrame]:
    h = positions + legs
    eve = pd.DataFrame({
        "Before (SGD m)": delta_eve_table(positions)["Aggregate (losses only)"],
        "After (SGD m)": delta_eve_table(h)["Aggregate (losses only)"],
    })
    eve["Before % T1"] = 100 * eve["Before (SGD m)"] / mk.TIER1_SGD_M
    eve["After % T1"] = 100 * eve["After (SGD m)"] / mk.TIER1_SGD_M
    nii = pd.DataFrame({
        "Before (SGD m)": {f"{s:+d}bp": delta_nii(positions, s) for s in (-200, -100, 100, 200)},
        "After (SGD m)": {f"{s:+d}bp": delta_nii(h, s) for s in (-200, -100, 100, 200)},
    })
    nii["Before % NII"] = 100 * nii["Before (SGD m)"] / base_nii(positions)
    nii["After % NII"] = 100 * nii["After (SGD m)"] / base_nii(h)
    return {"eve": eve, "nii": nii}


def ladder_legs(ccy: str, notional: float, tenors=(3, 5, 7), direction: str = "receive") -> list[Position]:
    """Equal-weighted ladder of swaps across `tenors` (structural hedge style)."""
    legs: list[Position] = []
    for t in tenors:
        legs += swap_legs(ccy, notional / len(tenors), t, direction)
    return legs


def size_programme(positions: list[Position], ccy: str = "SGD", tenors=(3, 5, 7),
                   direction: str = "receive", eve_target: float = mk.EVE_HEDGE_TARGET_PCT_T1,
                   nii_limit: float = mk.NII_LIMIT_PCT, step: float = 750.0,
                   max_notional: float = 30_000.0) -> float:
    """Smallest ladder notional meeting BOTH the EVE target and the NII limit
    (worst of +/-200bp). Step is a multiple of len(tenors) x 250m."""
    for n in np.arange(step, max_notional + step, step):
        h = positions + ladder_legs(ccy, n, tenors, direction)
        nii0 = base_nii(h)
        worst_nii = min(delta_nii(h, -200), delta_nii(h, 200))
        if worst_eve(h)[1] <= eve_target and -100 * worst_nii / nii0 <= nii_limit:
            return float(n)
    return float("nan")
