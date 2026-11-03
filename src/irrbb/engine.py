"""Repricing gap, NII sensitivity and EVE sensitivity."""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import market as mk
from .balance_sheet import Position
from .behavioural import ADMIN_RATE_LAG, nmd_profile
from .curves import SCENARIOS, discount_factor

BUCKET_NAMES = [b[0] for b in mk.BUCKETS]
BUCKET_MID = np.array([b[3] for b in mk.BUCKETS])
BUCKET_UPPER = np.array([b[2] for b in mk.BUCKETS])

GAP_BUCKETS = [("<=1M", 1 / 12), ("1-3M", 0.25), ("3-6M", 0.5), ("6-12M", 1.0), ("1-2Y", 2.0),
               ("2-3Y", 3.0), ("3-5Y", 5.0), ("5-7Y", 7.0), ("7-10Y", 10.0), (">10Y", 99.0)]


def fx(ccy: str) -> float:
    """Multiply local-ccy amounts by this to get SGD."""
    return 1.0 if ccy == "SGD" else 1.0 / mk.SGDMYR


def repricing_profile(p: Position) -> list[tuple[float, float]]:
    if p.kind == "nmd":
        return nmd_profile(p)
    return p.profile


# ---------------------------------------------------------------- gap -------
def gap_table(positions: list[Position], ccy: str) -> pd.DataFrame:
    """Behavioural repricing gap (local ccy m). Rows: positions; cols: buckets."""
    cols = [g[0] for g in GAP_BUCKETS] + ["Non-sensitive"]
    rows = {}
    for p in positions:
        if p.ccy != ccy:
            continue
        v = dict.fromkeys(cols, 0.0)
        if p.kind == "nonrate":
            v["Non-sensitive"] = p.sign * p.balance
        else:
            for t, w in repricing_profile(p):
                name = next(n for n, ub in GAP_BUCKETS if t <= ub + 1e-12)
                v[name] += p.sign * p.balance * w
        rows[f"{'A' if p.sign > 0 else 'L'} | {p.name}"] = v
    df = pd.DataFrame(rows).T[cols]
    eq = -df.sum().sum()
    df.loc["L | Equity (non-sensitive)"] = 0.0
    df.loc["L | Equity (non-sensitive)", "Non-sensitive"] = eq
    gap = df.sum()
    df.loc["Period gap"] = gap
    df.loc["Cumulative gap"] = gap.cumsum()
    return df


# ---------------------------------------------------------------- NII -------
def base_nii(positions: list[Position]) -> float:
    """12M NII at current rates, constant balance sheet, SGD m."""
    return float(sum(p.sign * p.balance * p.rate * fx(p.ccy) for p in positions))


def delta_nii(positions: list[Position], shock_bp: dict[str, float] | float,
              horizon: float = 1.0, by_ccy: bool = False):
    """12M NII change (SGD m) for an instantaneous parallel shock per currency.

    Each repricing slice earns the passed-through shock from repricing to
    horizon. Administered client rates are floored at zero; market-rate
    instruments (interbank, HQLA, bonds, swap legs) only at the MAS -100bp
    post-shock floor. NMD rates move after an administered-rate lag, by
    beta x shock.
    """
    if not isinstance(shock_bp, dict):
        shock_bp = {"SGD": shock_bp, "MYR": shock_bp}
    out: dict[str, float] = {}
    for p in positions:
        if p.kind == "nonrate":
            continue
        d = shock_bp[p.ccy] / 1e4
        floor = mk.MARKET_RATE_FLOOR if p.market_rate else 0.0
        dr = max(p.beta * d, floor - p.rate)  # post-shock rate floored at `floor`
        if p.kind == "nmd":
            slices = [(ADMIN_RATE_LAG, 1.0)]
        else:
            slices = p.profile
        x = sum(w * max(0.0, horizon - t) for t, w in slices if t < horizon)
        out[p.ccy] = out.get(p.ccy, 0.0) + p.sign * p.balance * dr * x * fx(p.ccy)
    return out if by_ccy else float(sum(out.values()))


# ---------------------------------------------------------------- EVE -------
def cash_flows(p: Position) -> list[tuple[float, float]]:
    """Notional repricing cash flows (t, amount, signed, local ccy m)."""
    if p.kind == "nonrate":
        return []
    cfs: list[tuple[float, float]] = []
    for t, w in repricing_profile(p):
        n = p.sign * p.balance * w
        if p.kind == "fixed":
            step = 1.0 / p.freq
            k = step
            while k < t - 1e-9:
                cfs.append((k, n * p.rate * step))
                k += step
            cfs.append((t, n * (1 + p.rate * (t - (k - step)))))
        else:  # floating / nmd: principal + accrued coupon at next repricing
            cfs.append((t, n * (1 + p.rate * t)))
    return cfs


def slotted(positions: list[Position], ccy: str) -> np.ndarray:
    """Net cash flows by the 19 standard buckets (local ccy m)."""
    v = np.zeros(len(mk.BUCKETS))
    for p in positions:
        if p.ccy != ccy:
            continue
        for t, a in cash_flows(p):
            v[int(np.searchsorted(BUCKET_UPPER, t - 1e-12))] += a
    return v


def eve(positions: list[Position], ccy: str, scenario: str | None = None, shocks=None) -> float:
    return float(slotted(positions, ccy) @ discount_factor(ccy, BUCKET_MID, scenario, shocks))


def delta_eve_table(positions: list[Position], shocks=None) -> pd.DataFrame:
    """dEVE by scenario and currency in SGD m, plus the MAS Annex 10B para 6.3 aggregate
    (sum of currency losses; gains set to zero) and % of Tier 1."""
    rows = {}
    for s in SCENARIOS:
        r = {}
        for c in ("SGD", "MYR"):
            r[c] = (eve(positions, c, s, shocks) - eve(positions, c, None)) * fx(c)
        r["Aggregate (losses only)"] = sum(min(0.0, r[c]) for c in ("SGD", "MYR"))
        r["% Tier 1"] = 100 * r["Aggregate (losses only)"] / mk.TIER1_SGD_M
        rows[s] = r
    return pd.DataFrame(rows).T


def worst_eve(positions: list[Position], shocks=None) -> tuple[str, float]:
    """(scenario, loss as positive % of Tier 1)."""
    t = delta_eve_table(positions, shocks)
    s = t["% Tier 1"].idxmin()
    return s, -float(t.loc[s, "% Tier 1"])


def pv01(positions: list[Position], ccy: str) -> float:
    """EVE change for +1bp parallel, SGD m."""
    base = slotted(positions, ccy)
    df0 = discount_factor(ccy, BUCKET_MID)
    df1 = df0 * np.exp(-1e-4 * BUCKET_MID)
    return float(base @ (df1 - df0)) * fx(ccy)


def parallel_mtm(positions: list[Position], ccy: str, bp: float, exact: bool = True) -> float:
    """Value change (SGD m) for a parallel shift of `bp`; exact cash-flow dates by
    default (mark-to-market view), bucket midpoints if exact=False."""
    sh = {c: {"parallel": bp, "short": 0.0, "long": 0.0} for c in mk.SHOCKS}
    if exact:
        d = pv_exact(positions, ccy, "parallel_up", sh) - pv_exact(positions, ccy)
    else:
        d = eve(positions, ccy, "parallel_up", sh) - eve(positions, ccy)
    return d * fx(ccy)


def pv_exact(positions: list[Position], ccy: str, scenario: str | None = None, shocks=None) -> float:
    """PV discounting each cash flow at its own time (no bucket slotting).
    Used to validate instruments and for mark-to-market; the regulatory
    measure uses `eve`."""
    total = 0.0
    for p in positions:
        if p.ccy != ccy:
            continue
        for t, a in cash_flows(p):
            total += a * float(discount_factor(ccy, t, scenario, shocks))
    return total
