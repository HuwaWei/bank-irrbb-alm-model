"""Market environment, curves and regulatory parameters.

Market and policy inputs cite their source and as-of date. Numbers marked [A]
are author assumptions for the illustrative bank (balances, limits, curve
shape between quoted anchors).
"""
from __future__ import annotations

import numpy as np

AS_OF = "2026-11-03"

# --- Macro / policy backdrop: value, source, as-of (documentation only) -------
ENVIRONMENT = {
    "Fed funds target": ("3.75-4.00%", "Federal Reserve FOMC statements (+25bp 16 Sep; held 28 Oct, 10-2)", "2026-10-28"),
    "MAS policy band": ("rate of appreciation unchanged", "MAS Monetary Policy Statement", "2026-10-14"),
    "S$NEER slope": ("~1.25% p.a.", "analyst estimates; MAS does not publish the slope", "2026-10-14"),
    "BNM OPR": ("2.75%", "BNM Monetary Policy Committee (unchanged since 9 Jul 2025)", "2026-09-03"),
    "12-week MAS bill": ("1.84%", "MAS auction cut-off (via Growbeansprout)", "2026-10-13"),
    "6M / 1Y T-bill": ("1.90% / 1.90%", "MAS SGS benchmark closing yields", "2026-11-03"),
    "SGS 2Y / 5Y / 10Y": ("1.85% / 2.00% / 2.21%", "MAS SGS benchmark closing yields", "2026-11-03"),
    "SGS 15Y / 20Y / 30Y": ("2.25% / 2.22% / 2.25%", "MAS SGS benchmark closing yields", "2026-11-03"),
    "MYOR": ("2.75%", "BNM Malaysia Overnight Rate", "2026-11-02"),
    "MGS 10Y": ("3.90%", "AsianBondsOnline (ADB), 3.897% close", "2026-11-02"),
    "3M compounded SORA": ("~1.2%", "MAS parliamentary reply ('around 1.2%'); context only, not a curve input", "2026-10-07"),
    "3M KLIBOR": ("3.46%", "KLIBOR fixing reported by BusinessToday", "2026-08-15"),
    "SGD/MYR": ("3.18", "Twelve Data spot (3.1815)", "2026-11-03"),
}

SGDMYR = 3.18  # MYR per 1 SGD (Twelve Data, 3 Nov 2026); translates the MYR book to SGD

# --- Base zero curves (continuously compounded, decimal) --------------------
# SGD: government curve as the risk-free proxy. Up to 1Y from MAS bills / T-bills:
#      3M 1.84% (12-week MAS bill cut-off, 13 Oct 2026), flat to O/N and 1M; 6M and
#      1Y 1.90% (T-bill closing yields, MAS, 3 Nov 2026). 2Y+ from SGS benchmark
#      closing yields (MAS, 3 Nov 2026): 2Y 1.85, 5Y 2.00, 10Y 2.21, 15Y 2.25,
#      20Y 2.22, 30Y 2.25. 3Y and 7Y are linear interpolations of the SGS points.
# MYR: O/N 2.75% (MYOR, BNM, 2 Nov 2026). 3M ~3.46% (KLIBOR, 15 Aug 2026): no
#      MYOR term rate exists, so KLIBOR is kept at 3M. 10Y 3.90% (MGS,
#      AsianBondsOnline, 2 Nov 2026). Other MYR nodes [A].
# Market quotes are used directly as continuously compounded zero rates (no
# bootstrapping or day-count conversion; error of a few bp) [A].
TENORS = np.array([0.0028, 0.083, 0.25, 0.5, 1, 2, 3, 5, 7, 10, 15, 20, 30])
CURVES = {
    "SGD": np.array([1.84, 1.84, 1.84, 1.90, 1.90, 1.85, 1.90, 2.00, 2.084, 2.21, 2.25, 2.22, 2.25]) / 100,
    "MYR": np.array([2.75, 3.20, 3.45, 3.48, 3.50, 3.54, 3.58, 3.68, 3.80, 3.90, 4.04, 4.10, 4.18]) / 100,
}

# --- Specified shocks (bp): parallel, short, long ---------------------------
# SGD: MAS Notice 637 Annex 10C Table 10C-1, effective 31 Dec 2025 (= BCBS SRP31.90
#      Table 2 as recalibrated July 2024, d578; implement by
#      1 Jan 2026): 175 / 250 / 225 (2016 calibration was 150 / 200 / 100).
#      Cross-checked to BNM IRRBB Exposure Draft (30 Sep 2025) App. 5 Table 8.
# MYR: not in Table 10C-1 (Annex 10C para 4: bank-derived); BNM Exposure Draft
#      App. 5 Table 6 bucket
#      values imply 200 / 175 / 225 (back-solved; reproduced to +/-1bp in tests).
SHOCKS = {
    "SGD": {"parallel": 175, "short": 250, "long": 225},
    "MYR": {"parallel": 200, "short": 175, "long": 225},
}
SHOCKS_2016 = {  # for comparison only
    "SGD": {"parallel": 150, "short": 200, "long": 100},
}
SHORT_DECAY_X = 4.0  # MAS Annex 10C para 7 / BCBS SRP31.91, x = 4

# Post-shock floor: MAS Notice 637 Annex 10C para 8 floors all post-shock rates
# (excluding commercial margins) at -100bp. Applied to EVE discounting and to
# market-rate instruments in NII (Annex 10 para 5.38(c): no other floor allowed).
# Administered client rates (deposits, client loans) are floored at 0% in NII,
# as permitted for Board-approved floors under para 5.38(b) [A].
EVE_POST_SHOCK_FLOOR = -0.01
MARKET_RATE_FLOOR = -0.01

# MAS / BCBS 19 time buckets: (lower, upper) in years and midpoint
BUCKETS = [
    ("O/N", 0.0, 1 / 365, 0.0028), ("O/N-1M", 1 / 365, 1 / 12, 0.0417),
    ("1M-3M", 1 / 12, 0.25, 0.1667), ("3M-6M", 0.25, 0.5, 0.375),
    ("6M-9M", 0.5, 0.75, 0.625), ("9M-1Y", 0.75, 1.0, 0.875),
    ("1Y-1.5Y", 1.0, 1.5, 1.25), ("1.5Y-2Y", 1.5, 2.0, 1.75),
    ("2Y-3Y", 2.0, 3.0, 2.5), ("3Y-4Y", 3.0, 4.0, 3.5), ("4Y-5Y", 4.0, 5.0, 4.5),
    ("5Y-6Y", 5.0, 6.0, 5.5), ("6Y-7Y", 6.0, 7.0, 6.5), ("7Y-8Y", 7.0, 8.0, 7.5),
    ("8Y-9Y", 8.0, 9.0, 8.5), ("9Y-10Y", 9.0, 10.0, 9.5),
    ("10Y-15Y", 10.0, 15.0, 12.5), ("15Y-20Y", 15.0, 20.0, 17.5),
    (">20Y", 20.0, 50.0, 25.0),
]


# --- Capital and limits ------------------------------------------------------
TIER1_SGD_M = 5_200.0           # [A] Tier 1 capital, SGD m (book equity ~S$5.6bn less deductions)
EVE_LIMIT_PCT_T1 = 12.0         # [A] internal ALCO limit on worst-case dEVE / Tier 1
EVE_OUTLIER_PCT_T1 = 15.0       # MAS Notice 637 Annex 10 para 5.33 outlier test (15% of Tier 1)
EVE_HEDGE_TARGET_PCT_T1 = 10.0  # [A] hedge to 10% to leave 2pp headroom to limit
NII_LIMIT_PCT = 20.0            # [A] max 12M NII decline vs base NII under +/-200bp
