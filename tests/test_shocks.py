"""Shock parameterisation reproduces the BNM IRRBB Exposure Draft (30 Sep 2025)
Appendix 5 bucket tables to within rounding (+/-1bp)."""
import numpy as np
import pytest

from irrbb import market as mk
from irrbb.curves import SCENARIOS, discount_factor, par_swap_rate, shock_bp

MID = np.array([b[3] for b in mk.BUCKETS])
# Columns: parallel up, parallel down, steepener, flattener, short up, short down
# Rows checked: O/N, 3M-6M, 2Y-3Y, 4Y-5Y, 9Y-10Y, >20Y
ROWS = [0, 3, 8, 10, 15, 18]
BNM_SGD = [
    [175, -175, -162, 200, 250, -250],
    [175, -175, -130, 170, 228, -228],
    [175, -175, 7, 44, 134, -134],
    [175, -175, 84, -26, 81, -81],
    [175, -175, 169, -104, 23, -23],
    [175, -175, 202, -134, 0, 0],
]
BNM_MYR = [
    [200, -200, -114, 140, 175, -175],
    [200, -200, -85, 115, 159, -159],
    [200, -200, 33, 12, 94, -94],
    [200, -200, 100, -46, 57, -57],
    [200, -200, 173, -109, 16, -16],
    [200, -200, 202, -134, 0, 0],
]


@pytest.mark.parametrize("ccy,table", [("SGD", BNM_SGD), ("MYR", BNM_MYR)])
def test_shocks_match_bnm_appendix5(ccy, table):
    for row, expected in zip(ROWS, table):
        got = [shock_bp(ccy, s, MID[row]) for s in SCENARIOS]
        assert np.allclose(got, expected, atol=1.0), (ccy, mk.BUCKETS[row][0], got, expected)


def test_rotation_identities():
    t = np.linspace(0.01, 30, 50)
    s = mk.SHOCKS["SGD"]
    w = np.exp(-t / 4)
    assert np.allclose(shock_bp("SGD", "steepener", t), -0.65 * s["short"] * w + 0.9 * s["long"] * (1 - w))
    assert np.allclose(shock_bp("SGD", "short_up", t), -shock_bp("SGD", "short_down", t))


def test_discount_factor_monotone_and_par_rate_sane():
    t = np.linspace(0.1, 30, 100)
    for c in ("SGD", "MYR"):
        assert np.all(np.diff(discount_factor(c, t)) < 0)
        assert 0.01 < par_swap_rate(c, 5) < 0.05
