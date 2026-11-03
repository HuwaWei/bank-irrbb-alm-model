import numpy as np
import pytest

from irrbb import balance_sheet as bs
from irrbb import behavioural as bh
from irrbb import engine as e
from irrbb import hedge as hd
from irrbb import market as mk
from irrbb.balance_sheet import Position

BOOK = bs.SGD_BOOK + bs.MYR_BOOK


def test_profiles_sum_to_one():
    for p in BOOK:
        if p.kind in ("fixed", "floating"):
            assert sum(w for _, w in p.profile) == pytest.approx(1.0)
        if p.kind == "nmd":
            assert sum(w for _, w in bh.nmd_profile(p)) == pytest.approx(1.0)


def test_gap_table_balances():
    for c in ("SGD", "MYR"):
        g = e.gap_table(BOOK, c)
        assert g.loc["Cumulative gap"].iloc[-1] == pytest.approx(0.0, abs=1e-6)


def test_nmd_caps_enforced():
    p = bs.SGD_BOOK[9].with_(core_pct=0.95)
    with pytest.raises(ValueError):
        bh.nmd_profile(p)
    flexed = bh.scale_nmds(BOOK, core_pct_delta=0.5, core_life=10)
    for q in flexed:
        if q.kind == "nmd":
            bh.check_caps(q)  # clipped to caps, so no exception


def test_single_fixed_asset_eve_matches_closed_form():
    # 100 zero-coupon asset repricing at 5Y mid-bucket (4.5y) -> dEVE = 100(e^{-(r+s)t}-e^{-rt})
    p = Position("zc", "SGD", "A", 100, 0.0, "fixed", [(4.5, 1.0)])
    r = float(np.interp(4.5, mk.TENORS, mk.CURVES["SGD"]))
    expected = 100 * (np.exp(-(r + 0.0175) * 4.5) - np.exp(-r * 4.5))
    got = e.eve([p], "SGD", "parallel_up") - e.eve([p], "SGD")
    assert got == pytest.approx(expected, rel=1e-9)


def test_nii_floating_asset_and_floor():
    a = Position("frn", "SGD", "A", 1000, 0.03, "floating", [(0.25, 1.0)])
    assert e.delta_nii([a], 100) == pytest.approx(1000 * 0.01 * 0.75)
    dep = Position("casa", "SGD", "L", 1000, 0.001, "nmd", beta=0.5, core_pct=0.5, core_life=2,
                   nmd_category="retail_tx")
    # -200bp x 0.5 beta = -100bp, but client rate floored at 0 -> only -10bp passes through
    assert e.delta_nii([dep], -200) == pytest.approx(1000 * 0.001 * (1 - bh.ADMIN_RATE_LAG))


def test_losses_only_aggregation():
    t = e.delta_eve_table(BOOK)
    for _, r in t.iterrows():
        assert r["Aggregate (losses only)"] == pytest.approx(min(0, r["SGD"]) + min(0, r["MYR"]))


def test_receive_fixed_swap_reduces_sgd_pv01_and_is_par():
    legs = hd.swap_legs("SGD", 1000, 5, "receive")
    # At par: ~zero value when cash flows are discounted at their own dates.
    # (Standardised slotting to bucket midpoints leaves a small artefact.)
    assert e.pv_exact(legs, "SGD") == pytest.approx(0.0, abs=0.5)
    assert e.pv01(BOOK + legs, "SGD") < e.pv01(BOOK, "SGD")


def test_hedge_sizing_meets_target():
    n = hd.size_hedge(BOOK, "SGD", 5, "receive")
    assert e.worst_eve(BOOK + hd.swap_legs("SGD", n, 5, "receive"))[1] <= mk.EVE_HEDGE_TARGET_PCT_T1
    assert e.worst_eve(BOOK + hd.swap_legs("SGD", n - 250, 5, "receive"))[1] > mk.EVE_HEDGE_TARGET_PCT_T1


def test_market_rate_floor_is_mas_minus_100bp_not_zero():
    # Pay-SORA swap leg at 1.84%: -200bp passes through in full (post-shock -0.16% > -1%).
    leg = Position("IRS float", "SGD", "L", 1000, 0.0184, "floating", [(0.125, 1.0)],
                   off_bs=True, market_rate=True)
    assert e.delta_nii([leg], -200) == pytest.approx(-1000 * -0.02 * 0.875)
    # At 0.50% the MAS -100bp post-shock floor binds: only -150bp passes through.
    low = leg.with_(rate=0.005)
    assert e.delta_nii([low], -200) == pytest.approx(-1000 * -0.015 * 0.875)


def test_swap_legs_flagged_as_market_rate():
    assert all(p.market_rate for p in hd.swap_legs("SGD", 1000, 5, "receive"))
