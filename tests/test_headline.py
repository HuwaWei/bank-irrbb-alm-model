"""Regression guard: the numbers quoted in report/alco_memo.md and README.md."""
import pytest

from irrbb.run import headline

EXPECTED = {
    "worst_eve_scenario": "parallel_down",
    "worst_eve_pct_t1": 14.4,
    "post_worst_eve_pct_t1": 5.6,
    "nii_m200_pct": -30.6,
    "nii_p200_pct": 23.3,
    "post_nii_m200_pct": -22.9,
    "hedge_carry_12m_sgd_m": 9.3,
    "base_nii_sgd_m": 1383.8,
    "worst_eve_sgd_m": 748.6,
    "post_nii_p200_pct": 15.6,
    "sgd_pv01_before": 4.05,
    "sgd_pv01_after": 1.56,
    "myr_pv01": -0.76,
    "hedge_pv01_slotted_sgd_m": 2.49,
    "hedge_pv01_exact_sgd_m": 2.77,
    "hedge_mtm_p50bp_exact_sgd_m": -136.6,
    "hedge_carry_12m_fwd_sgd_m": 4.7,
    "option_a_notional_sgd_m": 3000.0,
    "option_c_notional_sgd_m": 9000.0,
    "hedged_adverse_core_m20_life3_pct_t1": 10.2,
    "hedged_adverse_option_c_pct_t1": 14.2,
    "hedged_grid_max_pct_t1": 14.0,
    "hedged_grid_cells_above_limit": 1,
    "unhedged_grid_min_pct_t1": 4.8,
    "unhedged_grid_max_pct_t1": 18.2,
    "nii_p200_sgd_m": 321.8,
    "nii_p200_sgd_beta050_sgd_m": 212.7,
    "house_view_dnii_sgd_m": 40.2,
    "worst_eve_pct_t1_zero_floor": 14.4,
    "nii_reg_parallel_up_pct": 21.1,
    "nii_reg_parallel_down_pct": -26.1,
    "option_c_grid_cells_above_limit": 5,
    "post_worst_eve_scenario": "parallel_down",
}

_HL = None


def _headline():
    global _HL
    if _HL is None:
        _HL = headline()
    return _HL


@pytest.mark.parametrize("key", EXPECTED)
def test_headline(key):
    assert _headline()[key] == EXPECTED[key]
