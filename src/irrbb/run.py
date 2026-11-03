"""Run the full IRRBB analysis and write tables / figures to outputs/ and report/figures/.

    python -m irrbb.run          (with src/ on PYTHONPATH; see Makefile)
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from . import balance_sheet as bs
from . import behavioural as bh
from . import engine as e
from . import hedge as hd
from . import market as mk
from .curves import SCENARIOS, discount_factor, par_swap_rate

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "outputs"
FIG = ROOT / "report" / "figures"

PROGRAMME_TENORS = (3, 5, 7)
RECOMMENDED_NOTIONAL = 6_000.0  # SGD m; trade-off between the NII excess and EVE robustness to
                                # CASA behaviour, read from notional_scan (see memo section 5)


def book() -> list[bs.Position]:
    return bs.SGD_BOOK + bs.MYR_BOOK


def balance_sheet_table() -> pd.DataFrame:
    rows = []
    for p in book():
        rows.append({"Ccy": p.ccy, "Side": p.side, "Position": p.name, "Balance (m)": p.balance,
                     "Rate %": round(100 * p.rate, 2), "Type": p.kind,
                     "Beta": p.beta if p.kind in ("nmd", "fixed", "floating") and p.side == "L" else "",
                     "Core %": f"{p.core_pct:.0%}" if p.kind == "nmd" else "",
                     "Core life (y)": p.core_life if p.kind == "nmd" else ""})
    return pd.DataFrame(rows)


def nii_table(pos) -> pd.DataFrame:
    base = e.base_nii(pos)
    rows = {}
    for s in (-200, -100, 100, 200):
        d = e.delta_nii(pos, s, by_ccy=True)
        rows[f"{s:+d}bp"] = {"SGD book": d["SGD"], "MYR book (in SGD)": d["MYR"],
                             "Total": sum(d.values()), "% base NII": 100 * sum(d.values()) / base}
    return pd.DataFrame(rows).T


def house_view(pos) -> dict:
    """Analyst scenario linked to the current environment (not a regulatory shock):
    SGD +25bp (USD hikes leak into SORA despite MAS holding the S$NEER slope);
    MYR +25bp (street expects a 2027 OPR hike to 3.00%)."""
    d = e.delta_nii(pos, {"SGD": 25, "MYR": 25}, by_ccy=True)
    return {"SGD +25bp / MYR +25bp dNII (SGD m)": round(sum(d.values()), 1)}


def behavioural_grid(pos) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(a) worst dEVE %T1 by core-share shift (all retail NMDs, SGD and MYR) x core
    life of retail transactional CASA (SGD and MYR); (b) dNII by SGD retail
    transactional CASA beta (MYR held at its base 0.20, so the 0.15 row is the
    base case)."""
    eve_rows = {}
    for life in (2.0, 3.0, 4.0, 4.5, 5.0):
        r = {}
        for dc in (-0.20, -0.10, 0.0, 0.05):
            p2 = bh.scale_nmds(pos, core_pct_delta=dc)
            p2 = bh.scale_nmds(p2, core_life=life, categories=("retail_tx",))
            r[f"core {100 * dc:+.0f}pp"] = round(e.worst_eve(p2)[1], 1)
        eve_rows[f"retail CASA core life {life:g}y"] = r
    nii_rows = {}
    for beta in (0.05, 0.15, 0.30, 0.50):
        p2 = bh.scale_nmds(pos, beta=beta, categories=("retail_tx",), ccys=("SGD",))
        b = e.base_nii(p2)
        nii_rows[f"SGD retail CASA beta {beta:.2f}"] = {
            "dNII -200bp": round(e.delta_nii(p2, -200), 1),
            "dNII +200bp": round(e.delta_nii(p2, 200), 1),
            "-200bp % NII": round(100 * e.delta_nii(p2, -200) / b, 1),
        }
    return pd.DataFrame(eve_rows).T, pd.DataFrame(nii_rows).T


def hedged_behavioural_grid(pos, legs) -> pd.DataFrame:
    """Worst dEVE %T1 of the HEDGED book over the same grid as behavioural_grid(a)."""
    rows = {}
    for life in (2.0, 3.0, 4.0, 4.5, 5.0):
        r = {}
        for dc in (-0.20, -0.10, 0.0, 0.05):
            p2 = bh.scale_nmds(bh.scale_nmds(pos, core_pct_delta=dc), core_life=life, categories=("retail_tx",))
            sc, w = e.worst_eve(p2 + legs)
            r[f"core {100 * dc:+.0f}pp"] = f"{w:.1f} ({sc})"
        rows[f"retail CASA core life {life:g}y"] = r
    return pd.DataFrame(rows).T


def notional_scan(pos) -> pd.DataFrame:
    """3/5/7Y ladder notional vs base-case limits and CASA-behaviour robustness."""
    adverse = bh.scale_nmds(bh.scale_nmds(pos, core_pct_delta=-0.20), core_life=3.0, categories=("retail_tx",))
    grid = [bh.scale_nmds(bh.scale_nmds(pos, core_pct_delta=dc), core_life=life, categories=("retail_tx",))
            for life in (2.0, 3.0, 4.0, 4.5, 5.0) for dc in (-0.20, -0.10, 0.0, 0.05)]
    nii0 = e.base_nii(pos)
    rows = []
    for n in range(3000, 12001, 750):
        legs = hd.ladder_legs("SGD", float(n), PROGRAMME_TENORS)
        h = pos + legs
        b = e.base_nii(h)
        cells = [e.worst_eve(g + legs)[1] for g in grid]
        rows.append({"Notional (S$m)": n, "Worst dEVE % T1": round(e.worst_eve(h)[1], 1),
                     "dNII -200bp % NII": round(100 * e.delta_nii(h, -200) / b, 1),
                     "dNII +200bp % NII": round(100 * e.delta_nii(h, 200) / b, 1),
                     "Adverse CASA dEVE % T1": round(e.worst_eve(adverse + legs)[1], 1),
                     "Grid cells > 12%": int(sum(w > mk.EVE_LIMIT_PCT_T1 for w in cells)),
                     "Carry 12M (S$m)": round(b - nii0, 1)})
    return pd.DataFrame(rows)


def hedge_robustness(pos, legs) -> pd.DataFrame:
    """Worst dEVE %T1 with and without the recommended hedge if behaviour is wrong."""
    cases = {
        "Base (core +0pp, CASA life 4.5y)": pos,
        "Less sticky: CASA life 3y": bh.scale_nmds(pos, core_life=3.0, categories=("retail_tx",)),
        "Less sticky: core -20pp, life 3y": bh.scale_nmds(
            bh.scale_nmds(pos, core_pct_delta=-0.20), core_life=3.0, categories=("retail_tx",)),
        "Stickier: CASA life 5y (cap)": bh.scale_nmds(pos, core_life=5.0, categories=("retail_tx",)),
    }
    rows = {}
    for k, p2 in cases.items():
        s0, w0 = e.worst_eve(p2)
        s1, w1 = e.worst_eve(p2 + legs)
        rows[k] = {"Unhedged worst % T1": w0, "Unhedged scenario": s0,
                   "Hedged worst % T1": w1, "Hedged scenario": s1}
    return pd.DataFrame(rows).T


def hedge_options(pos) -> pd.DataFrame:
    n_min5 = hd.size_hedge(pos, "SGD", 5, "receive")
    n_full = hd.size_programme(pos, tenors=PROGRAMME_TENORS)
    opts = {
        "A: EVE minimum (5Y only)": hd.swap_legs("SGD", n_min5, 5, "receive"),
        "B: Recommended ladder 3/5/7Y": hd.ladder_legs("SGD", RECOMMENDED_NOTIONAL, PROGRAMME_TENORS),
        "C: Meets EVE and NII limits": hd.ladder_legs("SGD", n_full, PROGRAMME_TENORS),
    }
    notionals = {"A: EVE minimum (5Y only)": n_min5, "B: Recommended ladder 3/5/7Y": RECOMMENDED_NOTIONAL,
                 "C: Meets EVE and NII limits": n_full}
    nii0 = e.base_nii(pos)
    rows = {"Unhedged": {"Notional (S$m)": 0.0, "Worst dEVE % T1": e.worst_eve(pos)[1],
                         "Worst scenario": e.worst_eve(pos)[0], "Carry 12M (S$m)": 0.0,
                         "dNII -200bp % NII": 100 * e.delta_nii(pos, -200) / nii0,
                         "dNII +200bp % NII": 100 * e.delta_nii(pos, 200) / nii0,
                         "SGD PV01 (S$m/bp)": e.pv01(pos, "SGD")}}
    for k, legs in opts.items():
        h = pos + legs
        b = e.base_nii(h)
        sc, w = e.worst_eve(h)
        rows[k] = {"Notional (S$m)": notionals[k], "Worst dEVE % T1": w, "Worst scenario": sc,
                   "Carry 12M (S$m)": b - nii0,
                   "dNII -200bp % NII": 100 * e.delta_nii(h, -200) / b,
                   "dNII +200bp % NII": 100 * e.delta_nii(h, 200) / b,
                   "SGD PV01 (S$m/bp)": e.pv01(h, "SGD")}
    return pd.DataFrame(rows).T


def figures(pos, legs) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    blue, orange, ink, muted, grid = "#2a78d6", "#eb6834", "#0b0b0b", "#52514e", "#e4e3df"
    plt.rcParams.update({"font.size": 9, "axes.edgecolor": muted, "axes.labelcolor": ink,
                         "xtick.color": muted, "ytick.color": muted, "axes.spines.top": False,
                         "axes.spines.right": False})
    FIG.mkdir(parents=True, exist_ok=True)

    # 1. Repricing gap (SGD-equivalent, both books)
    g = e.gap_table(pos, "SGD").loc["Period gap"].drop("Non-sensitive") + \
        e.gap_table(pos, "MYR").loc["Period gap"].drop("Non-sensitive") / mk.SGDMYR
    fig, ax = plt.subplots(figsize=(7, 2.8))
    ax.bar(g.index, g.values / 1000, color=blue, width=0.6, label="Period gap")
    ax.plot(g.index, g.cumsum().values / 1000, color=orange, lw=2, marker="o", ms=4, label="Cumulative gap")
    ax.axhline(0, color=muted, lw=0.8)
    ax.yaxis.grid(True, color=grid, lw=0.6); ax.set_axisbelow(True)
    ax.set_ylabel("S$ bn"); ax.legend(frameon=False, loc="upper right")
    ax.set_title("Behavioural repricing gap, group (S$ equivalent)", loc="left", color=ink)
    fig.tight_layout(); fig.savefig(FIG / "repricing_gap.png", dpi=200); plt.close(fig)

    # 2. EVE before / after hedge by scenario
    before = e.delta_eve_table(pos)["% Tier 1"]
    after = e.delta_eve_table(pos + legs)["% Tier 1"]
    x = range(len(SCENARIOS))
    fig, ax = plt.subplots(figsize=(7, 2.8))
    ax.bar([i - 0.18 for i in x], before.values, width=0.34, color=blue, label="Unhedged")
    ax.bar([i + 0.18 for i in x], after.values, width=0.34, color=orange, label="After S$6bn receive-fixed ladder")
    ax.axhline(-mk.EVE_LIMIT_PCT_T1, color=ink, lw=1, ls="--")
    ax.text(len(SCENARIOS) - 0.5, -mk.EVE_LIMIT_PCT_T1 + 0.4, "ALCO limit -12%", ha="right", color=ink, fontsize=8)
    ax.axhline(-mk.EVE_OUTLIER_PCT_T1, color=muted, lw=1, ls=":")
    ax.text(len(SCENARIOS) - 0.5, -mk.EVE_OUTLIER_PCT_T1 + 0.4, "MAS outlier test -15%", ha="right", color=muted, fontsize=8)
    ax.set_xticks(list(x), [s.replace("_", " ") for s in SCENARIOS])
    ax.set_ylim(-17, 1); ax.set_ylabel("ΔEVE, % of Tier 1")
    ax.yaxis.grid(True, color=grid, lw=0.6); ax.set_axisbelow(True)
    ax.legend(frameon=False, loc="center right", fontsize=8)
    ax.set_title("EVE loss by MAS Notice 637 scenario (losses only, aggregated across SGD and MYR)", loc="left", color=ink)
    fig.tight_layout(); fig.savefig(FIG / "eve_before_after.png", dpi=200); plt.close(fig)


def headline() -> dict:
    pos = book()
    legs = hd.ladder_legs("SGD", RECOMMENDED_NOTIONAL, PROGRAMME_TENORS)
    h = pos + legs
    sc0, w0 = e.worst_eve(pos)
    sc1, w1 = e.worst_eve(h)
    nii0, nii1 = e.base_nii(pos), e.base_nii(h)
    adverse = bh.scale_nmds(bh.scale_nmds(pos, core_pct_delta=-0.20), core_life=3.0, categories=("retail_tx",))
    g_u, g_h, grids = [], [], []
    reg_up = {c: mk.SHOCKS[c]["parallel"] for c in mk.SHOCKS}
    reg_dn = {c: -mk.SHOCKS[c]["parallel"] for c in mk.SHOCKS}
    for life in (2.0, 3.0, 4.0, 4.5, 5.0):
        for dc in (-0.20, -0.10, 0.0, 0.05):
            p2 = bh.scale_nmds(bh.scale_nmds(pos, core_pct_delta=dc), core_life=life, categories=("retail_tx",))
            g_u.append(e.worst_eve(p2)[1]); g_h.append(e.worst_eve(p2 + legs)[1]); grids.append(p2)
    floor0 = mk.EVE_POST_SHOCK_FLOOR
    mk.EVE_POST_SHOCK_FLOOR = 0.0  # sensitivity: 0% floor instead of the MAS -100bp floor
    worst_zero_floor = e.worst_eve(pos)[1]
    mk.EVE_POST_SHOCK_FLOOR = floor0
    return {
        "total_assets_sgd_m": round(bs.totals(bs.SGD_BOOK)["assets"] + bs.totals(bs.MYR_BOOK)["assets"] / mk.SGDMYR),
        "base_nii_sgd_m": round(nii0, 1),
        "worst_eve_scenario": sc0, "worst_eve_pct_t1": round(w0, 1),
        "worst_eve_sgd_m": round(w0 * mk.TIER1_SGD_M / 100, 1),
        "nii_m200_pct": round(100 * e.delta_nii(pos, -200) / nii0, 1),
        "nii_p200_pct": round(100 * e.delta_nii(pos, 200) / nii0, 1),
        "nii_m100_pct": round(100 * e.delta_nii(pos, -100) / nii0, 1),
        "hedge_notional_sgd_m": RECOMMENDED_NOTIONAL,
        "hedge_par_rates_pct": {t: round(100 * par_swap_rate("SGD", t), 3) for t in PROGRAMME_TENORS},
        "post_worst_eve_scenario": sc1, "post_worst_eve_pct_t1": round(w1, 1),
        "post_nii_m200_pct": round(100 * e.delta_nii(h, -200) / nii1, 1),
        "post_nii_p200_pct": round(100 * e.delta_nii(h, 200) / nii1, 1),
        "hedge_carry_12m_sgd_m": round(nii1 - nii0, 1),
        "sgd_pv01_before": round(e.pv01(pos, "SGD"), 2), "sgd_pv01_after": round(e.pv01(h, "SGD"), 2),
        "myr_pv01": round(e.pv01(pos, "MYR"), 2),
        # hedge risk: regulatory (bucket-midpoint) vs mark-to-market (exact dates)
        "hedge_pv01_slotted_sgd_m": round(-e.pv01(legs, "SGD"), 2),
        "hedge_pv01_exact_sgd_m": round(-e.parallel_mtm(legs, "SGD", 1.0), 2),
        "hedge_mtm_p50bp_exact_sgd_m": round(e.parallel_mtm(legs, "SGD", 50.0), 1),
        "hedge_mtm_p50bp_slotted_sgd_m": round(e.parallel_mtm(legs, "SGD", 50.0, exact=False), 1),
        # carry if floating fixings follow today's forward curve (not today's 3M rate)
        "hedge_carry_12m_fwd_sgd_m": round(sum(
            l.balance * (l.rate - (1 / float(discount_factor("SGD", 1.0)) - 1))
            for l in legs if l.kind == "fixed"), 1),
        "option_c_notional_sgd_m": hd.size_programme(pos, tenors=PROGRAMME_TENORS),
        "option_a_notional_sgd_m": hd.size_hedge(pos, "SGD", 5, "receive"),
        "hedged_adverse_core_m20_life3_pct_t1": round(e.worst_eve(adverse + legs)[1], 1),
        "hedged_adverse_option_c_pct_t1": round(e.worst_eve(
            adverse + hd.ladder_legs("SGD", hd.size_programme(pos, tenors=PROGRAMME_TENORS), PROGRAMME_TENORS))[1], 1),
        "hedged_grid_max_pct_t1": round(max(g_h), 1),
        "hedged_grid_cells_above_limit": int(sum(w > mk.EVE_LIMIT_PCT_T1 for w in g_h)),
        "unhedged_grid_min_pct_t1": round(min(g_u), 1), "unhedged_grid_max_pct_t1": round(max(g_u), 1),
        "nii_p200_sgd_m": round(e.delta_nii(pos, 200), 1),
        "nii_p200_sgd_beta050_sgd_m": round(e.delta_nii(
            bh.scale_nmds(pos, beta=0.50, categories=("retail_tx",), ccys=("SGD",)), 200), 1),
        "house_view_dnii_sgd_m": round(e.delta_nii(pos, {"SGD": 25, "MYR": 25}), 1),
        # MAS Annex 10 para 5.37: regulatory dNII under Annex 10C parallel shocks
        "nii_reg_parallel_up_pct": round(100 * e.delta_nii(pos, reg_up) / nii0, 1),
        "nii_reg_parallel_down_pct": round(100 * e.delta_nii(pos, reg_dn) / nii0, 1),
        "option_c_grid_cells_above_limit": int(sum(
            e.worst_eve(g + hd.ladder_legs("SGD", hd.size_programme(pos, tenors=PROGRAMME_TENORS), PROGRAMME_TENORS))[1]
            > mk.EVE_LIMIT_PCT_T1 for g in grids)),
        "worst_eve_pct_t1_zero_floor": round(worst_zero_floor, 1),
    }


def md(df: pd.DataFrame, fmt: str = "{:,.1f}") -> str:
    d = df.copy()
    for c in d.columns:
        d[c] = [fmt.format(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else v for v in d[c]]
    return d.to_markdown()


def main() -> None:
    OUT.mkdir(exist_ok=True)
    pos = book()
    legs = hd.ladder_legs("SGD", RECOMMENDED_NOTIONAL, PROGRAMME_TENORS)

    sections: list[tuple[str, str]] = []
    bst = balance_sheet_table()
    bst.to_csv(OUT / "balance_sheet.csv", index=False)
    sections.append(("Balance sheet (local ccy m, illustrative)", bst.to_markdown(index=False)))
    for c in ("SGD", "MYR"):
        g = e.gap_table(pos, c)
        g.to_csv(OUT / f"gap_{c}.csv")
        sections.append((f"Repricing gap, {c} book ({c} m, behavioural)", md(g, "{:,.0f}")))
    nt = nii_table(pos); nt.to_csv(OUT / "nii_sensitivity.csv")
    sections.append((f"12M NII sensitivity (S$m; base NII S${e.base_nii(pos):,.0f}m)", md(nt)))
    hv = house_view(pos)
    sections.append(("House-view scenario", "\n".join(f"- {k}: {v}" for k, v in hv.items())))
    et = e.delta_eve_table(pos); et.to_csv(OUT / "eve_sensitivity.csv")
    sections.append((f"dEVE by scenario (S$m; Tier 1 S${mk.TIER1_SGD_M:,.0f}m)", md(et)))
    et16 = e.delta_eve_table(pos, shocks={**mk.SHOCKS, **mk.SHOCKS_2016})
    sections.append(("dEVE with 2016 SGD calibration (150/200/100) for comparison", md(et16)))
    g1, g2 = behavioural_grid(pos)
    g1.to_csv(OUT / "behavioural_eve_grid.csv"); g2.to_csv(OUT / "behavioural_nii_beta.csv")
    sections.append(("Behavioural: worst dEVE % T1 by retail core share shift (pp) and retail CASA core life (base: +0pp, 4.5y)", md(g1)))
    sections.append(("Behavioural: NII by SGD retail transactional CASA beta (S$m; base 0.15)", md(g2)))
    gh = hedged_behavioural_grid(pos, legs); gh.to_csv(OUT / "behavioural_eve_grid_hedged.csv")
    sections.append(("Behavioural: worst dEVE % T1 AFTER the S$6bn ladder, same grid (limit 12%)", gh.to_markdown()))
    menu = hd.hedge_menu(pos); menu.to_csv(OUT / "hedge_menu.csv", index=False)
    sections.append(("Single-tenor receive-fixed SGD OIS needed for dEVE <= 10% T1", menu.to_markdown(index=False)))
    ho = hedge_options(pos); ho.to_csv(OUT / "hedge_options.csv")
    sections.append(("Hedge options", md(ho, "{:,.2f}")))
    sc = notional_scan(pos); sc.to_csv(OUT / "hedge_notional_scan.csv", index=False)
    sections.append(("Ladder notional scan (base-case limits: EVE 12% / target 10%, NII 20%; "
                     "adverse CASA = core -20pp, life 3y)", sc.to_markdown(index=False)))
    hr = hedge_robustness(pos, legs); hr.to_csv(OUT / "hedge_robustness.csv")
    sections.append(("Recommended hedge under alternative CASA behaviour", md(hr)))
    ba = hd.before_after(pos, legs)
    ba["eve"].to_csv(OUT / "hedge_before_after_eve.csv"); ba["nii"].to_csv(OUT / "hedge_before_after_nii.csv")
    sections.append(("Recommended hedge: dEVE before / after", md(ba["eve"])))
    sections.append(("Recommended hedge: dNII before / after", md(ba["nii"])))

    hl = headline()
    (OUT / "headline.json").write_text(json.dumps(hl, indent=2))
    body = "\n\n".join(f"## {t}\n\n{s}" for t, s in sections)
    (OUT / "results.md").write_text(
        f"# Model output (as of {mk.AS_OF}) - generated by `make run`, do not edit\n\n"
        f"Illustrative bank; not any real institution.\n\n{body}\n")
    figures(pos, legs)
    print(json.dumps(hl, indent=2))


if __name__ == "__main__":
    main()
