"""Zero curves and the six MAS Notice 637 Annex 10C (BCBS SRP31) shock scenarios."""
from __future__ import annotations

import numpy as np

from . import market as mk

SCENARIOS = ["parallel_up", "parallel_down", "steepener", "flattener", "short_up", "short_down"]


def zero_rate(ccy: str, t) -> np.ndarray:
    """Base zero rate (cont. comp.), linear in t, flat extrapolation."""
    return np.interp(np.asarray(t, dtype=float), mk.TENORS, mk.CURVES[ccy])


def shock_bp(ccy: str, scenario: str, t, shocks: dict | None = None) -> np.ndarray:
    """Rate change in bp at maturity t under SRP31.91 parameterisation."""
    s = (shocks or mk.SHOCKS)[ccy]
    t = np.asarray(t, dtype=float)
    w_short = np.exp(-t / mk.SHORT_DECAY_X)
    d_short = s["short"] * w_short
    d_long = s["long"] * (1.0 - w_short)
    table = {
        "parallel_up": np.full_like(t, s["parallel"]),
        "parallel_down": np.full_like(t, -s["parallel"]),
        "steepener": -0.65 * d_short + 0.9 * d_long,
        "flattener": 0.8 * d_short - 0.6 * d_long,
        "short_up": d_short,
        "short_down": -d_short,
    }
    return table[scenario]


def shocked_rate(ccy: str, scenario: str | None, t, shocks: dict | None = None) -> np.ndarray:
    r = zero_rate(ccy, t)
    if scenario is None:
        return r
    r = r + shock_bp(ccy, scenario, t, shocks) / 1e4
    if mk.EVE_POST_SHOCK_FLOOR is not None:
        r = np.maximum(r, mk.EVE_POST_SHOCK_FLOOR)
    return r


def discount_factor(ccy: str, t, scenario: str | None = None, shocks: dict | None = None) -> np.ndarray:
    t = np.asarray(t, dtype=float)
    return np.exp(-shocked_rate(ccy, scenario, t, shocks) * t)


def par_swap_rate(ccy: str, tenor: float, freq: int = 4) -> float:
    """Par fixed rate of an OIS-style swap paying `freq` times a year."""
    times = np.arange(1, int(round(tenor * freq)) + 1) / freq
    df = discount_factor(ccy, times)
    return float((1 - df[-1]) / (df.sum() / freq))
