# -*- coding: utf-8 -*-
"""
Verbatim extraction of notebooks_archive/other_binned_data.ipynb cell 1 (machinery only).
Do NOT edit logic here; this is the reference implementation already used
for the 8 existing harmonized topics. Driver: extend_topics.py
Generic hierarchical downscaling for NON-AGE categorical vectors.

Core idea (per topic):
  - Child HARD rows  : child topic total column (e.g., "Insgesamt_*") [optionally *_adj]
  - Parent HARD cols : parent per-category totals (sum over categories at parent level)
  - Trust-blended local -> parent shares (configurable w_min / t_pc) + damping alpha
  - Robust raking/IPF to satisfy both margins

Configure topics in build_topic_specs_for_level(), run 10km→1km and/or 1km→100m.
"""

from __future__ import annotations
import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from tqdm import tqdm

# for memory-safe full-output writing at 100m
import pyarrow as pa
import pyarrow.dataset as ds
import pyarrow.parquet as pq

from cleancensus.logsetup import get_logger

log = get_logger("harmonize")

# ---------------------------------------------------------------------
# 0) Trust blending (central, easy-to-tune)
# ---------------------------------------------------------------------

@dataclass
class TrustBlend:
    """
    Compute local trust weight w_i in [w_min, 1] from child row totals T_i.
    - w_min : baseline trust even for tiny totals
    - t_pc  : "people per category" target; when T_i ≈ K * t_pc, w_i ~ 1
              (K = number of categories in the topic)
    """
    w_min: float = 0.40
    t_pc: float  = 5.0

    def weights(self, totals: np.ndarray, n_categories: int) -> np.ndarray:
        cutoff = max(self.t_pc * max(n_categories, 1), 1e-9)
        base = np.minimum(1.0, totals / cutoff)
        return self.w_min + (1.0 - self.w_min) * base


# ---------------------------------------------------------------------
# 1) IPF / raking with hard margins
# ---------------------------------------------------------------------
def rake_to_margins(X: np.ndarray,
                    row_targets: np.ndarray,
                    col_targets: np.ndarray,
                    *,
                    tol: float = 1e-10,
                    max_iter: int = 1000,
                    denom_eps: float = 1e-12,
                    seed_eps: float = 1e-15) -> None:
    """
    In-place IPF so rows -> row_targets and cols -> col_targets.
    Adds tiny 'support seeding' so columns with positive targets aren't stuck at zero.
    """
    assert X.ndim == 2
    n, k = X.shape
    assert row_targets.shape == (n,)
    assert col_targets.shape == (k,)

    # ---- seed support: if both margins want positive mass but X==0, sprinkle tiny >0
    if seed_eps is not None and seed_eps > 0:
        want = (row_targets > 0)[:, None] & (col_targets > 0)[None, :]
        need = want & (X <= 0)
        if need.any():
            # proportional to outer product of margins (very tiny)
            R = row_targets / max(float(row_targets.sum()), 1.0)
            C = col_targets / max(float(col_targets.sum()), 1.0)
            X[need] = seed_eps * (R[:, None] * C[None, :])[need]

    # ---- IPF
    eps = denom_eps
    for _ in range(max_iter):
        # columns
        col_sums = X.sum(axis=0)
        cscale = np.divide(col_targets, np.maximum(col_sums, eps), where=np.isfinite(col_sums), out=np.ones_like(col_sums))
        X *= cscale  # broadcast over rows

        # rows
        row_sums = X.sum(axis=1, keepdims=True)
        rscale = np.divide(row_targets[:, None], np.maximum(row_sums, eps), where=np.isfinite(row_sums), out=np.ones_like(row_sums))
        X *= rscale  # broadcast over cols

        if (np.allclose(X.sum(axis=0), col_targets, rtol=1e-12, atol=1e-12) and
            np.allclose(X.sum(axis=1), row_targets, rtol=1e-12, atol=1e-12)):
            break



# ---------------------------------------------------------------------
# 2) Child totals adjuster (scalar per parent group)
# ---------------------------------------------------------------------

def make_child_totals_adj(
    parent_df: pd.DataFrame,
    child_df: pd.DataFrame,
    *,
    parent_id_col: str,
    child_parent_id_col: str,
    parent_adj_col: str,   # parent-level HARD total to hit (e.g. "Insgesamt_*_adj" or raw "Insgesamt_*")
    child_total_col: str,  # child-level "Insgesamt_*" to be scaled (writes *_adj)
    out_col: Optional[str] = None
) -> pd.Series:
    """
    For each parent id, multiply child totals by a scalar so
    sum(children)_adj == parent_adj. Returns the new child series (also added as column).
    If a group's child sum is 0 but parent_adj > 0, split equally across its children.
    """
    out_col = out_col or f"{child_total_col}_adj"

    pids_parent = parent_df[parent_id_col].astype(str).str.strip()
    pids_child  = child_df[child_parent_id_col].astype(str).str.strip()

    parent_target = (parent_df
        .assign(_pid=pids_parent)
        .set_index("_pid")[parent_adj_col]
        .astype(float)
        .reindex(pids_child.unique())
        .fillna(0.0))

    child_tot = pd.to_numeric(child_df[child_total_col], errors="coerce").fillna(0.0)
    group_sum = pd.Series(child_tot.values, index=pids_child).groupby(level=0).sum().astype(float)

    scale = pd.Series(0.0, index=group_sum.index)
    mask_nz = group_sum > 0
    scale.loc[mask_nz] = parent_target.loc[mask_nz] / group_sum.loc[mask_nz]

    s = pids_child.map(scale).fillna(0.0)
    adj = child_tot * s

    # degenerate: group_sum==0 & parent_target>0  -> equal split (row-based, robust)
    group_sum_by_pid = group_sum  # (index = pid)
    parent_by_pid    = parent_target  # (index = pid)

    rows_deg = pids_child.map(group_sum_by_pid).le(0) & pids_child.map(parent_by_pid).gt(0)
    if rows_deg.any():
        counts_by_pid = pids_child.value_counts().reindex(parent_target.index).fillna(0).astype(int)
        per_cap_by_pid = (parent_target / counts_by_pid.replace(0, np.nan)).fillna(0.0)
        adj.loc[rows_deg] = pids_child.map(per_cap_by_pid).loc[rows_deg].to_numpy()


    child_df[out_col] = adj.values
    return child_df[out_col]


# ---------------------------------------------------------------------
# 3) Topic spec & downscaler
# ---------------------------------------------------------------------

@dataclass
class TopicSpec:
    """
    One categorical vector at a given level pair (parent→child).
    Provide:
      - parent category columns (order matters),
      - child  category columns (same order, same length),
      - child HARD row-total column (usually "Insgesamt_*", ideally *_adj).
    Optional:
      - alpha (damping),
      - blend (TrustBlend) for row weights w_i.
    """
    name: str
    parent_cat_cols: List[str]
    child_cat_cols:  List[str]
    child_row_total_col: str
    alpha: float = 0.85
    blend: TrustBlend = field(default_factory=TrustBlend)


def _assert_topic_columns(parent_df, child_df, parent_id_col, child_parent_id_col, spec: TopicSpec) -> None:
    missing_parent = [c for c in spec.parent_cat_cols if c not in parent_df.columns]
    missing_child  = [c for c in spec.child_cat_cols  if c not in child_df.columns]
    if missing_parent:
        raise KeyError(f"[{spec.name}] Missing parent cols: {missing_parent[:5]}{'...' if len(missing_parent)>5 else ''}")
    if missing_child:
        raise KeyError(f"[{spec.name}] Missing child cols: {missing_child[:5]}{'...' if len(missing_child)>5 else ''}")
    if spec.child_row_total_col not in child_df.columns:
        raise KeyError(f"[{spec.name}] Missing child total col: {spec.child_row_total_col}")
    if len(spec.parent_cat_cols) != len(spec.child_cat_cols):
        raise ValueError(f"[{spec.name}] Category length mismatch parent({len(spec.parent_cat_cols)}) "
                         f"vs child({len(spec.child_cat_cols)})")
    if parent_id_col not in parent_df.columns:
        raise KeyError(f"[{spec.name}] Missing parent_id_col: {parent_id_col}")
    if child_parent_id_col not in child_df.columns:
        raise KeyError(f"[{spec.name}] Missing child_parent_id_col: {child_parent_id_col}")


def _apply_topic_trust_blend(
    cdf: pd.DataFrame,
    X: np.ndarray,
    child_totals: np.ndarray,
    parent_shares: np.ndarray,
    child_cat_cols: List[str],
    alpha: float,
    blend: TrustBlend,
    eps: float = 1e-9
) -> None:
    """
    For each category k:
      target_i = w_i * local_ik + (1 - w_i) * (parent_share_k * child_total_i)
      Then scale X[:, k] by (target/s) ** alpha, with protections & seeding.
    """
    n, K = X.shape
    assert K == len(child_cat_cols)
    w = blend.weights(child_totals, K)

    for k, col in enumerate(child_cat_cols):
        local = pd.to_numeric(cdf[col], errors="coerce").fillna(0.0).to_numpy(float)
        nat_exp = parent_shares[k] * child_totals
        target  = w * local + (1.0 - w) * nat_exp

        s = X[:, k]
        need_seed = (s <= eps) & (target > 0)
        if need_seed.any():
            X[need_seed, k] = target[need_seed]
            s = X[:, k]

        good = (s > eps) & np.isfinite(s)
        f = np.ones_like(s)
        f[good] = (np.maximum(target[good], 0.0) / s[good]) ** alpha
        np.clip(f, 1e-6, 1e6, out=f)
        X[:, k] *= f


def downscale_topic(
    parent_df: pd.DataFrame,
    child_df: pd.DataFrame,
    *,
    parent_id_col: str,
    child_parent_id_col: str,
    spec: TopicSpec,
    inner_passes: int = 10,
    outer_iters: int = 2,
    rake_tol: float = 1e-10,
    rake_max_iter: int = 50,
    validate_row_tol: float = 2e-4,
    verbose: bool = False
) -> pd.DataFrame:
    """Downscale one TopicSpec from parent -> child."""
    _assert_topic_columns(parent_df, child_df, parent_id_col, child_parent_id_col, spec)

    parent_df = parent_df.copy()
    child_df  = child_df.copy()
    parent_df[parent_id_col]      = parent_df[parent_id_col].astype(str).str.strip()
    child_df[child_parent_id_col] = child_df[child_parent_id_col].astype(str).str.strip()

    K = len(spec.child_cat_cols)
    out = pd.DataFrame(index=child_df.index, columns=spec.child_cat_cols, dtype=float)

    parent_map: Dict[object, np.ndarray] = {}
    for pid, psub in parent_df[[parent_id_col] + spec.parent_cat_cols].groupby(parent_id_col):
        parent_map[pid] = psub[spec.parent_cat_cols].astype(float).to_numpy().sum(axis=0)

    parent_sum_0_counter = 0
    diffcouter = 0
    for pid, cdf in tqdm(child_df.groupby(child_parent_id_col, sort=False, group_keys=False),
                         disable=not verbose):

        idx = cdf.index
        p = parent_map.get(pid)

        if p is None or cdf.empty:
            out.loc[idx, :] = 0.0
            continue

        t = pd.to_numeric(cdf[spec.child_row_total_col], errors="coerce").fillna(0.0).to_numpy(float)
        if t.size == 0:
            continue

        Psum = float(np.sum(p))
        if Psum == 0:
            parent_sum_0_counter += 1
            out.loc[idx, :] = 0.0
            continue
        if Psum < 1e-9:
            raise ValueError(f"[{spec.name}] Parent sum < 1e-9: {Psum}")

        # Mask tiny values to true 0
        mask_tiny = np.abs(p) < 1e-9
        if mask_tiny.any():
            p[mask_tiny] = 0.0
            if p.sum() > 0:
                p /= p.sum() / Psum  # rescale so total stays consistent


        Tsum = float(np.sum(t))
        if not np.isclose(Tsum, Psum, rtol=0, atol=1e-12):
            rel = abs(Psum - Tsum) / max(Psum, 1.0)
            if rel <= 1e-8:
                # tiny numeric drift -> silent rescale
                t *= Psum / max(Tsum, 1e-30)
            elif rel <= 1e-4:
                log.warning(f"adjust row mass by {rel:.2e} for {pid}")
                t *= Psum / max(Tsum, 1e-30)
            else:
                raise AssertionError(
                    f"[fatal] infeasible margins (Δ={Psum-Tsum:.6g}, rel={rel:.2e}) for {pid}"
                )

        parent_shares = p / Psum
        zero_cols = parent_shares <= 0
        X = np.outer(t, parent_shares)

        for _ in range(outer_iters):
            for _inner in range(inner_passes):
                _apply_topic_trust_blend(
                    cdf, X, t, parent_shares, spec.child_cat_cols,
                    alpha=spec.alpha, blend=spec.blend
                )
                if zero_cols.any():
                    X[:, zero_cols] = 0.0  # ← keep pruned cols at 0

                # row re-projection
                rs = X.sum(axis=1, keepdims=True)
                np.divide(t[:, None], np.maximum(rs, 1e-12), out=rs)
                X *= rs

            # final rake (with support seeding, but only for positive cols)
            rake_to_margins(
                X, row_targets=t, col_targets=p,
                tol=rake_tol, max_iter=rake_max_iter,
                denom_eps=1e-12, seed_eps=1e-15
            )
            if zero_cols.any():
                X[:, zero_cols] = 0.0


        out.loc[idx, :] = X

        calc_rows = X.sum(axis=1)
        rel = np.abs(calc_rows - t) / np.maximum(t, 1.0)
        if rel.max(initial=0.0) > validate_row_tol:
            raise AssertionError(
                f"[{spec.name}] Row totals dev > {validate_row_tol:.2e} for parent {pid}. "
                f"max rel.err={rel.max():.3e}"
            )
        if not np.allclose(X.sum(axis=0), p, rtol=0, atol=1e-2):
            log.debug("INFO: abs difference > 0.01")
            diffcouter += 1
            if not np.allclose(X.sum(axis=0), p, rtol=0, atol=1): # May get close for large or many child cells
                diff = X.sum(axis=0) - p
                rel = np.divide(diff, np.maximum(np.abs(p), 1e-12))
                log.debug("WARNING: abs difference > 1")
                log.debug(f"Parent ID: {pid}")
                log.debug("Parent totals (p):")
                log.debug(p)
                log.debug("Child sums (X.sum(axis=0)):")
                log.debug(X.sum(axis=0))
                log.debug("Difference (child - parent):")
                log.debug(diff)
                log.debug("Relative difference:")
                log.debug(rel)
                if not np.allclose(X.sum(axis=0), p, rtol=0.02, atol=0):
                    log.debug("WARNING: rel difference > 0.02")

    log.debug(f"Diffcouter: {diffcouter}")
    log.debug(f"Parent sum 0: {parent_sum_0_counter} out of {len(parent_map)}")
    return out


# ---------------------------------------------------------------------
# 4) Helpers for level-specific column names (simple suffix swap)
# ---------------------------------------------------------------------

def levelize(cols_10km: List[str], level: str) -> List[str]:
    """
    Replace the trailing suffix *_10km-Gitter with *_{level}-Gitter
    level ∈ {"10km","1km","100m"}
    """
    from_str = "_10km-Gitter"
    to_str   = f"_{level}-Gitter"
    return [c.replace(from_str, to_str) for c in cols_10km]

# ---------------------------------------------------------------------
# 4.5) Normalize parent category vectors to their parent totals
# ---------------------------------------------------------------------

def _make_topic_prior_shares(df, cols):
    cols = [c for c in cols if c in df.columns]   # guard, though you already do this upstream
    if not cols:
        return np.full(1, 1.0)  # or return a uniform over K when you know K; see note below

    vals = df.loc[:, cols].apply(pd.to_numeric, errors="coerce").fillna(0.0)
    w = vals.sum(axis=0).to_numpy(dtype=float)
    s = float(w.sum())
    if s > 0:
        return w / s
    return np.full(len(cols), 1.0 / len(cols), dtype=float)


def normalize_parent_categories_for_specs(
    parent_df: pd.DataFrame,
    *,
    specs: List[TopicSpec],
    child_level: str,            # '1km'
    cap_factor: float = 10.0,    # optional: flag overly large corrections
    verbose: bool = True,
) -> None:
    """
    For each TopicSpec:
      - compute a global prior over its parent category columns,
      - per parent row, scale cats so sum(cats) == parent total,
      - if sum(cats)==0 < and total>0, inject prior * total,
      - if total==0, set cats to 0.
    Operates IN-PLACE on parent_df.
    """
    for spec in specs:
        cat_cols = [c for c in spec.parent_cat_cols if c in parent_df.columns]
        if not cat_cols:
            if verbose:
                log.info(f"skip '{spec.name}': no parent category cols present")
            continue

        if child_level == "1km":
            tot_col = spec.child_row_total_col.replace("_1km-Gitter", "_10km-Gitter")
        # elif child_level == "100m":
        #     tot_col = spec.child_row_total_col.replace("_100m-Gitter", "_1km-Gitter") # NOT to be used at that level. Just for 10km init.
        else:
            raise ValueError(f"Unknown child_level: {child_level}")

        if tot_col not in parent_df.columns:
            if verbose:
                log.info(f"skip '{spec.name}': parent total '{tot_col}' not found")
            continue

        # Global prior shares for this topic
        prior = _make_topic_prior_shares(parent_df, cat_cols)  # (K,)

        # Numeric frames
        C = parent_df[cat_cols].apply(pd.to_numeric, errors="coerce").fillna(0.0).to_numpy(dtype=float)  # (N,K)
        T = pd.to_numeric(parent_df[tot_col], errors="coerce").fillna(0.0).to_numpy(dtype=float)         # (N,)

        S = C.sum(axis=1)  # (N,)
        N, K = C.shape

        # Cases
        # 1) total == 0 -> set row to 0
        zero_tot = T <= 0
        if np.any(zero_tot):
            C[zero_tot, :] = 0.0

        # 2) sum(cats) == 0 & total > 0 -> inject prior * total
        need_inject = (S <= 0) & (T > 0)
        if np.any(need_inject):
            C[need_inject, :] = T[need_inject, None] * prior[None, :]

        # 3) baseline scaling for all rows with S > 0
        S = C.sum(axis=1)  # recompute after injection
        good = S > 0
        f = np.ones_like(S)
        f[good] = T[good] / S[good]

        # Optional: flag extreme factors
        if verbose:
            big = np.abs(f[good]) > cap_factor
            if np.any(big):
                n_big = int(np.sum(big))
                log.warning(f"'{spec.name}' warning: {n_big} rows have |scale| > {cap_factor} (max={float(np.max(np.abs(f[good]))):.2f})")

        C *= f[:, None]

        # Write back
        parent_df.loc[:, cat_cols] = C
        if verbose:
            # cheap audit: check new sums vs totals
            new_s = C.sum(axis=1)
            err = np.abs(new_s - T) / np.maximum(T, 1.0)
            log.info(f"'{spec.name}' rows={len(err):,} | max rel.err={float(err.max()):.2e} | mean={float(err.mean()):.2e}")


# ---------------------------------------------------------------------
# 5) Configuration for PRIORITY topics
# ---------------------------------------------------------------------
# For 10-1 we did t_pc = 10
BLEND_STRONG = TrustBlend(w_min=0.50, t_pc=5.0)
BLEND_STD    = TrustBlend(w_min=0.40, t_pc=5.0)
BLEND_WEAK   = TrustBlend(w_min=0.30, t_pc=30.0)

def build_topic_specs_for_level(level: str) -> List[TopicSpec]:
    """
    Returns TopicSpec list for a given child level, assuming parent is the next coarser level:
      - for level="1km": parent is 10km
      - for level="100m": parent is 1km
    """
    # --- Familienstand (population by marital status) ---
    fam_tot_10 = "Insgesamt_Bevoelkerung_Familienstand_10km-Gitter"
    fam_cats_10 = [
        "Ledig_Familienstand_10km-Gitter",
        "Verheiratet_Familienstand_10km-Gitter",
        "Verwitwet_Familienstand_10km-Gitter",
        "Geschieden_Familienstand_10km-Gitter",
        "EingetrLebenspartnerschaft_Familienstand_10km-Gitter",
        "EingetrLebenspartVerstorben_Familienstand_10km-Gitter",
        "EingetrLebenspartAufgehoben_Familienstand_10km-Gitter",
        "OhneAngabe_Familienstand_10km-Gitter",
    ]

    # --- Energieträger (population; NOT buildings-by-energy) ---
    et_tot_10 = "Insgesamt_Energietraeger_Energietraeger_10km-Gitter"
    et_cats_10 = [
        "Gas_Energietraeger_10km-Gitter",
        "Heizoel_Energietraeger_10km-Gitter",
        "Holz_Holzpellets_Energietraeger_10km-Gitter",
        "Biomasse_Biogas_Energietraeger_10km-Gitter",
        "Solar_Geothermie_Waermepumpen_Energietraeger_10km-Gitter",
        "Strom_Energietraeger_10km-Gitter",
        "Kohle_Energietraeger_10km-Gitter",
        "Fernwaerme_Energietraeger_10km-Gitter",
        "kein_Energietraeger_Energietraeger_10km-Gitter",
    ]

    # --- Heizungsart (Gebäude nach überwiegender Heizungsart) ---
    hz_tot_10 = "Insgesamt_Heizungsart_Gebaeude_nach_ueberwiegender_Heizungsart_10km-Gitter"
    hz_cats_10 = [
        "Fernheizung_Gebaeude_nach_ueberwiegender_Heizungsart_10km-Gitter",
        "Etagenheizung_Gebaeude_nach_ueberwiegender_Heizungsart_10km-Gitter",
        "Blockheizung_Gebaeude_nach_ueberwiegender_Heizungsart_10km-Gitter",
        "Zentralheizung_Gebaeude_nach_ueberwiegender_Heizungsart_10km-Gitter",
        "Einzel_Mehrraumoefen_Gebaeude_nach_ueberwiegender_Heizungsart_10km-Gitter",
        "keine_Heizung_Gebaeude_nach_ueberwiegender_Heizungsart_10km-Gitter",
    ]

    # --- Haushaltsgröße (size of private household) ---
    hh_tot_10 = "Insgesamt_Haushalte_Groesse_des_privaten_Haushalts_10km-Gitter"
    hh_cats_10 = [
        "1_Person_Groesse_des_privaten_Haushalts_10km-Gitter",
        "2_Personen_Groesse_des_privaten_Haushalts_10km-Gitter",
        "3_Personen_Groesse_des_privaten_Haushalts_10km-Gitter",
        "4_Personen_Groesse_des_privaten_Haushalts_10km-Gitter",
        "5_Personen_Groesse_des_privaten_Haushalts_10km-Gitter",
        "6_Personen_und_mehr_Groesse_des_privaten_Haushalts_10km-Gitter",
    ]

    # --- Lebensform (private HH life form) ---
    lf_tot_10 = "Insgesamt_Haushalte_Typ_priv_HH_Lebensform_10km-Gitter"
    lf_cats_10 = [
        "EinpersHH_SingleHH_Typ_priv_HH_Lebensform_10km-Gitter",
        "Ehepaare_Typ_priv_HH_Lebensform_10km-Gitter",
        "EingetrLebensp_Typ_priv_HH_Lebensform_10km-Gitter",
        "NichtehelLebensg_Typ_priv_HH_Lebensform_10km-Gitter",
        "AlleinerzMuetter_Typ_priv_HH_Lebensform_10km-Gitter",
        "AlleinerzVaeter_Typ_priv_HH_Lebensform_10km-Gitter",
        "MehrpersHHohneKernfam_Typ_priv_HH_Lebensform_10km-Gitter",
    ]

    # --- Räume (Wohnungen nach Zahl der Räume) ---
    rm_tot_10 = "Insgesamt_Wohnungen_Wohnungen_nach_Zahl_der_Raeume_10km-Gitter"
    rm_cats_10 = [
        "1Raum_Wohnungen_nach_Zahl_der_Raeume_10km-Gitter",
        "2Raeume_Wohnungen_nach_Zahl_der_Raeume_10km-Gitter",
        "3Raeume_Wohnungen_nach_Zahl_der_Raeume_10km-Gitter",
        "4Raeume_Wohnungen_nach_Zahl_der_Raeume_10km-Gitter",
        "5Raeume_Wohnungen_nach_Zahl_der_Raeume_10km-Gitter",
        "6Raeume_Wohnungen_nach_Zahl_der_Raeume_10km-Gitter",
        "7undmehrRaeume_Wohnungen_nach_Zahl_der_Raeume_10km-Gitter",
    ]

    # --- Wohnungsfläche (10 m² intervals) ---
    fl_tot_10 = "Insgesamt_Wohnungen_Flaeche_der_Wohnung_10m2_Intervalle_10km-Gitter"
    fl_cats_10 = [
        "unter30_Flaeche_der_Wohnung_10m2_Intervalle_10km-Gitter",
        "30bis39_Flaeche_der_Wohnung_10m2_Intervalle_10km-Gitter",
        "40bis49_Flaeche_der_Wohnung_10m2_Intervalle_10km-Gitter",
        "50bis59_Flaeche_der_Wohnung_10m2_Intervalle_10km-Gitter",
        "60bis69_Flaeche_der_Wohnung_10m2_Intervalle_10km-Gitter",
        "70bis79_Flaeche_der_Wohnung_10m2_Intervalle_10km-Gitter",
        "80bis89_Flaeche_der_Wohnung_10m2_Intervalle_10km-Gitter",
        "90bis99_Flaeche_der_Wohnung_10m2_Intervalle_10km-Gitter",
        "100bis109_Flaeche_der_Wohnung_10m2_Intervalle_10km-Gitter",
        "110bis119_Flaeche_der_Wohnung_10m2_Intervalle_10km-Gitter",
        "120bis129_Flaeche_der_Wohnung_10m2_Intervalle_10km-Gitter",
        "130bis139_Flaeche_der_Wohnung_10m2_Intervalle_10km-Gitter",
        "140bis149_Flaeche_der_Wohnung_10m2_Intervalle_10km-Gitter",
        "150bis159_Flaeche_der_Wohnung_10m2_Intervalle_10km-Gitter",
        "160bis169_Flaeche_der_Wohnung_10m2_Intervalle_10km-Gitter",
        "170bis179_Flaeche_der_Wohnung_10m2_Intervalle_10km-Gitter",
        "180undmehr_Flaeche_der_Wohnung_10m2_Intervalle_10km-Gitter",
    ]

    # --- Geburtsland (groups) ---
    gl_tot_10 = "Insgesamt_Bevoelkerung_Geburtsland_Gruppen_10km-Gitter"
    gl_cats_10 = [
        "Deutschland_Geburtsland_Gruppen_10km-Gitter",
        "Ausland_Sonstige_Geburtsland_Gruppen_10km-Gitter",
        "EU27_Land_Geburtsland_Gruppen_10km-Gitter",
        "Sonstiges_Europa_Geburtsland_Gruppen_10km-Gitter",
        "Sonstige_Welt_Geburtsland_Gruppen_10km-Gitter",
        "Sonstige_Geburtsland_Gruppen_10km-Gitter",
    ]

    def topic(name, tot_10, cats_10, alpha, blend):
        if level == "1km":
            parent_cols = cats_10
            child_cols  = levelize(cats_10, "1km")
            child_total = tot_10.replace("_10km-Gitter", "_1km-Gitter")
        elif level == "100m":
            parent_cols = levelize(cats_10, "1km")
            child_cols  = levelize(cats_10, "100m")
            child_total = tot_10.replace("_10km-Gitter", "_100m-Gitter")
        else:
            raise ValueError(f"Unknown level: {level}")

        return TopicSpec(
            name=name,
            parent_cat_cols=parent_cols,
            child_cat_cols=child_cols,
            child_row_total_col=child_total,
            alpha=alpha,
            blend=blend,
        )

    specs = [
        topic("Familienstand",    fam_tot_10, fam_cats_10, alpha=0.90, blend=BLEND_STD),
        topic("Energietraeger",   et_tot_10,  et_cats_10,  alpha=0.85, blend=BLEND_STD),
        topic("Heizungsart",      hz_tot_10,  hz_cats_10,  alpha=0.85, blend=BLEND_STD),
        topic("Haushaltsgroesse", hh_tot_10,  hh_cats_10,  alpha=0.90, blend=BLEND_STD),
        topic("Lebensform",       lf_tot_10,  lf_cats_10,  alpha=0.85, blend=BLEND_STD),
        topic("Raeume",           rm_tot_10,  rm_cats_10,  alpha=0.85, blend=BLEND_STD),
        topic("Wohnflaeche",      fl_tot_10,  fl_cats_10,  alpha=0.85, blend=BLEND_STD),
        topic("Geburtsland",      gl_tot_10,  gl_cats_10,  alpha=0.85, blend=BLEND_STD),
    ]
    return specs



# ---------------------------------------------------------------------
# 5.5) Shim: create *_adj child totals for ALL topics and flip specs
# ---------------------------------------------------------------------


def _require_parent_adj_for_child_total(parent_df: pd.DataFrame, child_total_col: str) -> str:
    if child_total_col.endswith("_100m-Gitter"):
        base = child_total_col.replace("_100m-Gitter", "_1km-Gitter")
        adj = f"{base}_adj"
        if adj not in parent_df.columns:
            raise KeyError(f"Missing required parent total: {adj} for {child_total_col}")
        return adj
    if child_total_col.endswith("_1km-Gitter"):
        return child_total_col.replace("_1km-Gitter", "_10km-Gitter")
    return child_total_col


def apply_adj_for_all_topics(
    parent_df: pd.DataFrame,
    child_df: pd.DataFrame,
    *,
    parent_id_col: str,
    child_parent_id_col: str,
    specs: List[TopicSpec],
    verbose: bool = True,
) -> List[TopicSpec]:
    """For each TopicSpec, create a *_adj child row-total and switch the spec to use it."""
    specs_out: List[TopicSpec] = []
    for spec in specs:
        total_col = spec.child_row_total_col
        adj_col = f"{total_col}_adj"
        if adj_col not in child_df.columns:
            parent_total = _require_parent_adj_for_child_total(parent_df, total_col)
            make_child_totals_adj(
                parent_df=parent_df,
                child_df=child_df,
                parent_id_col=parent_id_col,
                child_parent_id_col=child_parent_id_col,
                parent_adj_col=parent_total,
                child_total_col=total_col,
                out_col=adj_col,
            )
            if verbose:
                log.info(f"Created {adj_col} for topic '{spec.name}'")
        specs_out.append(TopicSpec(
            name=spec.name,
            parent_cat_cols=spec.parent_cat_cols,
            child_cat_cols=spec.child_cat_cols,
            child_row_total_col=adj_col,
            alpha=spec.alpha,
            blend=spec.blend,
        ))
    return specs_out


def impute_orphan_rows_100m(
    df: pd.DataFrame,
    *,
    specs: List[TopicSpec],
    orphan_flag_col: str = "is_orphan",
    dtype_out = np.float32,
    eps: float = 1e-12,
    verbose: bool = True,
) -> None:
    """
    For 100m rows marked as orphans:
      - If the row has category signal, scale to its *_adj* total.
      - Else allocate the total using a prior from non-orphan 100m category sums.

    Operates IN-PLACE on `df`.
    """
    if orphan_flag_col not in df.columns:
        if verbose:
            log.info(f"'{orphan_flag_col}' not found; nothing to do.")
        return

    mask_orphan = df[orphan_flag_col].to_numpy(bool)
    mask_non    = ~mask_orphan
    n_orph = int(mask_orphan.sum())
    if n_orph == 0:
        if verbose:
            log.info("no orphan rows.")
        return

    for spec in specs:
        # Ensure columns exist
        cats = [c for c in spec.child_cat_cols if c in df.columns]
        totc = spec.child_row_total_col
        if not cats or totc not in df.columns:
            if verbose:
                log.info(f"[{spec.name}] skip (missing cols).")
            continue

        # Build prior from non-orphans (sum over computed 100m results)
        prior_counts = (
            df.loc[mask_non, cats]
              .apply(pd.to_numeric, errors="coerce")
              .fillna(0.0)
              .sum(axis=0)
              .to_numpy(dtype=float)
        )
        prior = prior_counts + eps
        psum  = float(prior.sum())
        if psum <= 0:
            # fallback uniform if absolutely no mass
            prior = np.full(len(cats), 1.0 / max(len(cats), 1), dtype=float)
        else:
            prior = prior / psum  # normalized prior

        # Orphan rows: read totals + current cat signals
        T = pd.to_numeric(df.loc[mask_orphan, totc], errors="coerce").fillna(0.0).to_numpy(dtype=float)
        Y = df.loc[mask_orphan, cats].apply(pd.to_numeric, errors="coerce").fillna(0.0).to_numpy(dtype=float)

        # Classify
        S = Y.sum(axis=1)
        caseA = (S > eps) & (T > 0)   # has signal -> scale to total
        caseB = (S <= eps) & (T > 0)  # no signal -> use prior
        caseZ = (T <= 0)              # zero total -> all zeros

        Xo = np.zeros_like(Y, dtype=float)

        # Case A: preserve shape, scale to T
        if np.any(caseA):
            scale = T[caseA] / np.maximum(S[caseA], eps)
            Xo[caseA, :] = Y[caseA, :] * scale[:, None]

        # Case B: use prior
        if np.any(caseB):
            Xo[caseB, :] = T[caseB, None] * prior[None, :]

        # Case Z already zeros

        # Hygiene: clip tiny negatives, cast, and write back
        np.maximum(Xo, 0.0, out=Xo)
        df.loc[mask_orphan, cats] = Xo.astype(dtype_out)

        if verbose:
            # quick audits
            rows = int(np.sum(mask_orphan))
            used_A = int(np.sum(caseA))
            used_B = int(np.sum(caseB))
            used_Z = int(np.sum(caseZ))
            # row-sum check (aggregate)
            rs = Xo.sum(axis=1)
            rel = np.abs(rs - T) / np.maximum(T, 1.0)
            log.info(f"[{spec.name}] rows={rows} | A={used_A} B={used_B} Z={used_Z} "
                     f"| max row rel.err={float(rel.max()):.3e} | mean={float(rel.mean()):.3e}")

# ---------------------------------------------------------------------
# 6) Run
# ---------------------------------------------------------------------

