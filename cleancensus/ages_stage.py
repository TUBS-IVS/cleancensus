"""Ages stage: single-year age decomposition AGE_0..AGE_100.

Ported faithfully from notebooks_archive/ages.ipynb cells [6] and [7].

Cell [6]: fit_single_years_10km — multiplicative trust-mixed bin fitting with
    IPF raking to produce per-cell single-year age distributions for the 10km
    grid, constrained to match national per-age totals and per-cell totals.

Cell [7]: downscale_single_years — hierarchical downscaling 10km->1km->100m
    using trust-mixed local bin scaling and hard IPF margins (child row totals
    HARD; parent per-age column totals HARD).

No random numbers are used anywhere in this stage.  Results are deterministic.

Inputs (work_dir):
    totals_{level}.parquet for level in {10km, 1km, 100m}
    (plus the national age vector CSV at cfg.national_age_csv_path)

Outputs (work_dir):
    df10_with_single_years.parquet
    df1_with_single_years.parquet
    df100_with_single_years.parquet
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Bin specifications (ported from cells [6] and [7])
# ---------------------------------------------------------------------------

# ---- 10km bin definitions (cell [6]) ----------------------------------------

POP_COL_10KM = "POP_TOTAL_10km"

INFR_BINS_10KM: Dict[str, Tuple[int, int]] = {
    "Unter3_Alter_INFR_10km-Gitter":       (0, 2),
    "a3bis5_Alter_INFR_10km-Gitter":       (3, 5),
    "a6bis9_Alter_INFR_10km-Gitter":       (6, 9),
    "a10bis15_Alter_INFR_10km-Gitter":     (10, 15),
    "a16bis18_Alter_INFR_10km-Gitter":     (16, 18),
    "a19bis24_Alter_INFR_10km-Gitter":     (19, 24),
    "a25bis39_Alter_INFR_10km-Gitter":     (25, 39),
    "a40bis59_Alter_INFR_10km-Gitter":     (40, 59),
    "a60bis66_Alter_INFR_10km-Gitter":     (60, 66),
    "a67bis74_Alter_INFR_10km-Gitter":     (67, 74),
    "a75undaelter_Alter_INFR_10km-Gitter": (75, 100),
}

TENYEAR_BINS_10KM: Dict[str, Tuple[int, int]] = {
    "Unter10_Alter_in_10er-Jahresgruppen_10km-Gitter":    (0, 9),
    "a10bis19_Alter_in_10er-Jahresgruppen_10km-Gitter":   (10, 19),
    "a20bis29_Alter_in_10er-Jahresgruppen_10km-Gitter":   (20, 29),
    "a30bis39_Alter_in_10er-Jahresgruppen_10km-Gitter":   (30, 39),
    "a40bis49_Alter_in_10er-Jahresgruppen_10km-Gitter":   (40, 49),
    "a50bis59_Alter_in_10er-Jahresgruppen_10km-Gitter":   (50, 59),
    "a60bis69_Alter_in_10er-Jahresgruppen_10km-Gitter":   (60, 69),
    "a70bis79_Alter_in_10er-Jahresgruppen_10km-Gitter":   (70, 79),
    "a80undaelter_Alter_in_10er-Jahresgruppen_10km-Gitter": (80, 100),
}

FIVECLASS_BINS_10KM: Dict[str, Tuple[int, int]] = {
    "Unter18_Alter_in_5_Altersklassen_10km-Gitter":    (0, 17),
    "a18bis29_Alter_in_5_Altersklassen_10km-Gitter":   (18, 29),
    "a30bis49_Alter_in_5_Altersklassen_10km-Gitter":   (30, 49),
    "a50bis64_Alter_in_5_Altersklassen_10km-Gitter":   (50, 64),
    "a65undaelter_Alter_in_5_Altersklassen_10km-Gitter": (65, 100),
}

# ---- Hierarchical bin specs (cell [7]) --------------------------------------


@dataclass(frozen=True)
class BinSpec:
    """Maps column name -> inclusive age range [lo, hi]."""
    cols_to_ranges: Dict[str, Tuple[int, int]]


def make_infr_bins(level: str, top_age: int = 100) -> BinSpec:
    suf = {"10km": "10km-Gitter", "1km": "1km-Gitter", "100m": "100m-Gitter"}[level]
    return BinSpec({
        f"Unter3_Alter_INFR_{suf}":       (0, 2),
        f"a3bis5_Alter_INFR_{suf}":       (3, 5),
        f"a6bis9_Alter_INFR_{suf}":       (6, 9),
        f"a10bis15_Alter_INFR_{suf}":     (10, 15),
        f"a16bis18_Alter_INFR_{suf}":     (16, 18),
        f"a19bis24_Alter_INFR_{suf}":     (19, 24),
        f"a25bis39_Alter_INFR_{suf}":     (25, 39),
        f"a40bis59_Alter_INFR_{suf}":     (40, 59),
        f"a60bis66_Alter_INFR_{suf}":     (60, 66),
        f"a67bis74_Alter_INFR_{suf}":     (67, 74),
        f"a75undaelter_Alter_INFR_{suf}": (75, top_age),
    })


def make_tenyear_bins(level: str, top_age: int = 100) -> BinSpec:
    suf = {"10km": "_10km-Gitter", "1km": "_1km-Gitter", "100m": "_100m-Gitter"}[level]
    return BinSpec({
        f"Unter10_Alter_in_10er-Jahresgruppen{suf}":    (0, 9),
        f"a10bis19_Alter_in_10er-Jahresgruppen{suf}":   (10, 19),
        f"a20bis29_Alter_in_10er-Jahresgruppen{suf}":   (20, 29),
        f"a30bis39_Alter_in_10er-Jahresgruppen{suf}":   (30, 39),
        f"a40bis49_Alter_in_10er-Jahresgruppen{suf}":   (40, 49),
        f"a50bis59_Alter_in_10er-Jahresgruppen{suf}":   (50, 59),
        f"a60bis69_Alter_in_10er-Jahresgruppen{suf}":   (60, 69),
        f"a70bis79_Alter_in_10er-Jahresgruppen{suf}":   (70, 79),
        f"a80undaelter_Alter_in_10er-Jahresgruppen{suf}": (80, top_age),
    })


def make_fiveclass_bins(level: str, top_age: int = 100) -> BinSpec:
    suf = {"10km": "_10km-Gitter", "1km": "_1km-Gitter", "100m": "_100m-Gitter"}[level]
    return BinSpec({
        f"Unter18_Alter_in_5_Altersklassen{suf}":    (0, 17),
        f"a18bis29_Alter_in_5_Altersklassen{suf}":   (18, 29),
        f"a30bis49_Alter_in_5_Altersklassen{suf}":   (30, 49),
        f"a50bis64_Alter_in_5_Altersklassen{suf}":   (50, 64),
        f"a65undaelter_Alter_in_5_Altersklassen{suf}": (65, top_age),
    })


# ---------------------------------------------------------------------------
# Utilities shared by both cells [6] and [7]
# ---------------------------------------------------------------------------


def age_cols(top_age: int = 100) -> List[str]:
    return [f"AGE_{a}" for a in range(0, top_age + 1)]


def _age_idx(lo: int, hi: int, top_age: int) -> np.ndarray:
    return np.arange(lo, min(hi, top_age) + 1, dtype=np.intp)


def _collect_existing_bins(
    df: pd.DataFrame, spec: BinSpec, top_age: int
) -> List[Tuple[str, np.ndarray]]:
    return [
        (col, _age_idx(lo, hi, top_age))
        for col, (lo, hi) in spec.cols_to_ranges.items()
        if col in df.columns
    ]


def _collect_bins_raw(
    df: pd.DataFrame, bin_map: Dict[str, Tuple[int, int]], top_age: int
) -> List[Tuple[str, np.ndarray]]:
    return [
        (col, _age_idx(lo, hi, top_age))
        for col, (lo, hi) in bin_map.items()
        if col in df.columns
    ]


def _final_rake_to_margins(
    X: np.ndarray,
    row_targets: np.ndarray,
    col_targets: np.ndarray,
    *,
    tol: float = 1e-10,
    max_iter: int = 10,
) -> None:
    """In-place IPF to meet row and column hard margins (cells [6] and [7])."""
    for _ in range(max_iter):
        col_sums = X.sum(axis=0)
        with np.errstate(divide="ignore", invalid="ignore"):
            cscale = np.divide(col_targets, np.maximum(col_sums, tol))
        X *= cscale

        row_sums = X.sum(axis=1, keepdims=True)
        with np.errstate(divide="ignore", invalid="ignore"):
            rscale = np.divide(row_targets[:, None], np.maximum(row_sums, tol))
        X *= rscale

        if np.allclose(X.sum(axis=0), col_targets, rtol=1e-9, atol=tol) and \
                np.allclose(X.sum(axis=1), row_targets, rtol=1e-9, atol=tol):
            break


# ---------------------------------------------------------------------------
# National age vector loader
# ---------------------------------------------------------------------------


def load_national_single_years(
    csv_path,
    label_col: str = "Alter",
    value_col: str = "Zahl",
    top_age: int = 100,
) -> pd.Series:
    """Parse national single-year age CSV (ported from cell [6]).

    Expected format: ';'-delimited, label column like "0 Jahre", "1 Jahre", …
    Returns a Series indexed 0..top_age (100 = 100+ bucket).
    """
    df = pd.read_csv(csv_path, sep=";")
    tmp = df[[label_col, value_col]].copy()
    tmp.columns = ["label", "value"]
    tmp = tmp.dropna(subset=["label", "value"])

    ages = (
        tmp["label"]
        .astype(str)
        .str.extract(r"^\s*(\d+)\s+jahr(?:e)?\s*$", flags=re.IGNORECASE)[0]
        .astype(float)
    )
    tmp["age"] = ages.clip(lower=0, upper=top_age).astype("Int64")
    tmp = tmp.dropna(subset=["age"])
    tmp["age"] = tmp["age"].astype(int)
    tmp["value"] = pd.to_numeric(tmp["value"], errors="coerce").fillna(0).astype(float)

    nat = tmp.groupby("age")["value"].sum().reindex(range(0, top_age + 1), fill_value=0.0)
    if nat.sum() <= 0:
        raise ValueError("National total is zero — check CSV.")
    return nat


# ---------------------------------------------------------------------------
# Cell [6]: 10km single-year fitting
# ---------------------------------------------------------------------------


def _apply_bin_scalings_mixed(
    df: pd.DataFrame,
    X: np.ndarray,
    bins: List[Tuple[str, np.ndarray]],
    totals: np.ndarray,
    nat_share: np.ndarray,
    bin_nat_cache: dict,
    *,
    alpha: float,
    trust_local: float,
    eps: float,
) -> None:
    """Trust-mixed multiplicative bin scaling for the 10km level (cell [6])."""
    if not bins:
        return
    for col, idx in bins:
        y = pd.to_numeric(df[col], errors="coerce").fillna(0.0).to_numpy(float)

        key = tuple(idx)
        if key in bin_nat_cache:
            bin_share, within = bin_nat_cache[key]
        else:
            w = nat_share[idx].sum()
            bin_share = w
            within = np.full(idx.size, 1.0 / max(idx.size, 1))

        nat_expected = bin_share * totals
        target = trust_local * y + (1.0 - trust_local) * nat_expected

        s = X[:, idx].sum(axis=1)
        f = np.ones_like(s)
        good = (s > eps) & np.isfinite(s)
        f[good] = (np.maximum(target[good], 0.0) / s[good]) ** alpha
        np.clip(f, 1e-6, 1e6, out=f)

        seed = (s <= eps) & (target > 0)
        if seed.any():
            X[np.ix_(seed, idx)] = target[seed, None] * within[None, :]

        X[:, idx] *= f[:, None]


def fit_single_years_10km(
    df10: pd.DataFrame,
    national_by_age: pd.Series,
    *,
    top_age: int = 100,
    alpha_5c: float = 0.9,
    alpha_10y: float = 0.85,
    alpha_infr: float = 0.8,
    trust_5c: float = 0.99,
    trust_10y: float = 0.99,
    trust_infr: float = 0.99,
    inner_passes: int = 30,
    outer_iters: int = 10,
    tol_rel: float = 1e-6,
    verbose: bool = True,
) -> Tuple[pd.DataFrame, np.ndarray]:
    """Fit single-year ages for 10km cells (cell [6]).

    Returns:
        ages_per_cell: DataFrame (n_cells x top_age+1), columns 0..top_age
        adjusted_totals: np.ndarray (n_cells,) — cell totals rescaled to national
    """
    df = df10.copy()

    nat = national_by_age.copy()
    if not (
        isinstance(nat.index, pd.RangeIndex)
        and nat.index.equals(pd.RangeIndex(0, top_age + 1))
    ):
        raise AssertionError("national_by_age must have index 0..top_age.")
    nat = nat.astype(float).values
    A = top_age + 1

    nat_sum = float(nat.sum())
    if not np.isfinite(nat_sum) or nat_sum <= 0:
        raise ValueError("National vector invalid (sum<=0).")
    nat_share = nat / nat_sum

    totals_raw = pd.to_numeric(df[POP_COL_10KM], errors="coerce").fillna(0.0).to_numpy(float)
    total_cells = float(totals_raw.sum())
    if total_cells <= 0:
        raise ValueError("Sum of cell totals <= 0 after NaNs->0.")
    scale_all = nat_sum / total_cells
    totals = totals_raw * scale_all

    five_bins = _collect_bins_raw(df, FIVECLASS_BINS_10KM, top_age)
    ten_bins  = _collect_bins_raw(df, TENYEAR_BINS_10KM,  top_age)
    infr_bins = _collect_bins_raw(df, INFR_BINS_10KM,     top_age)

    X = np.outer(totals, nat_share)

    def _bin_nat_shares(idx):
        w = nat[idx].sum()
        bin_share = w / nat_sum if w > 0 else 0.0
        within = nat[idx] / w if w > 0 else np.full(idx.size, 1.0 / max(idx.size, 1))
        return bin_share, within

    bin_nat = {
        tuple(idx): _bin_nat_shares(idx)
        for _, idx in (five_bins + ten_bins + infr_bins)
    }

    for it in range(outer_iters):
        for _ in range(inner_passes):
            _apply_bin_scalings_mixed(
                df, X, five_bins, totals, nat_share, bin_nat,
                alpha=alpha_5c, trust_local=trust_5c, eps=tol_rel,
            )
            _apply_bin_scalings_mixed(
                df, X, ten_bins, totals, nat_share, bin_nat,
                alpha=alpha_10y, trust_local=trust_10y, eps=tol_rel,
            )
            _apply_bin_scalings_mixed(
                df, X, infr_bins, totals, nat_share, bin_nat,
                alpha=alpha_infr, trust_local=trust_infr, eps=tol_rel,
            )
            row_sums = X.sum(axis=1, keepdims=True)
            np.divide(totals[:, None], np.maximum(row_sums, tol_rel), out=row_sums)
            X *= row_sums

        _final_rake_to_margins(X, totals, nat)

        if verbose:
            S = X.sum(axis=0)
            err = np.mean(np.abs(S - nat) / np.maximum(nat, 1.0))
            log.info("[ages|10km] iter %d/%d national rel.err ~ %.3e", it + 1, outer_iters, err)

    age_index = list(range(0, top_age + 1))
    out = pd.DataFrame(X, index=df.index, columns=age_index)
    return out, totals


# ---------------------------------------------------------------------------
# Cell [7]: child total adjustment
# ---------------------------------------------------------------------------


def make_child_totals_adj(
    parent_df: pd.DataFrame,
    child_df: pd.DataFrame,
    *,
    parent_id_col: str,
    child_parent_id_col: str,
    parent_adj_col: str,
    child_pop_col: str,
    out_col: str | None = None,
) -> pd.DataFrame:
    """Proportionally adjust child totals so group sums match parent_adj (cell [7])."""
    out_col = out_col or f"{child_pop_col}_adj"

    pids_parent = parent_df[parent_id_col].astype(str)
    pids_child = child_df[child_parent_id_col].astype(str)

    pmap = (
        parent_df.assign(_pid=pids_parent)
        .set_index("_pid")[parent_adj_col]
        .astype(float)
    )

    child_tot = pd.to_numeric(child_df[child_pop_col], errors="coerce").fillna(0.0)

    gsum = pd.Series(child_tot.values, index=pids_child).groupby(level=0).sum().astype(float)

    tgt = pmap.reindex(gsum.index).fillna(0.0)

    scale = pd.Series(0.0, index=gsum.index)
    nonzero = gsum > 0
    scale.loc[nonzero] = tgt.loc[nonzero] / gsum.loc[nonzero]

    s = pids_child.map(scale).fillna(0.0)
    adj = child_tot * s

    deg_groups = tgt.index[(~nonzero) & (tgt > 0)]
    if len(deg_groups) > 0:
        deg_counts = pids_child.value_counts().reindex(deg_groups).fillna(0).astype(int)
        per_cap_group = (tgt.loc[deg_groups] / deg_counts.replace(0, np.nan)).fillna(0.0)
        per_cap_row = pids_child.map(per_cap_group).fillna(0.0)
        use_deg = pids_child.isin(deg_groups)
        adj.loc[use_deg] = per_cap_row.loc[use_deg].values

    child_df[out_col] = adj.values
    return child_df


# ---------------------------------------------------------------------------
# Cell [7]: trust-mixed child bin scaling (downscale)
# ---------------------------------------------------------------------------


def _apply_child_bin_scalings_mixed(
    df_child: pd.DataFrame,
    X: np.ndarray,
    child_totals: np.ndarray,
    parent_share: np.ndarray,
    bins: List[Tuple[str, np.ndarray]],
    *,
    alpha: float = 0.85,
    trust_threshold: float = 200.0,
    eps: float = 1e-9,
) -> None:
    """Trust-mixed bin scaling for downscaling children (cell [7])."""
    if not bins:
        return

    n, A = X.shape
    assert child_totals.shape == (n,)

    parent_bin_share_cache: Dict[Tuple[int, ...], float] = {}

    w_min = 0.4
    w_base = np.minimum(1.0, child_totals / max(trust_threshold, eps))
    w = w_min + (1.0 - w_min) * w_base

    for col, idx in bins:
        key = tuple(idx.tolist())
        p_share = parent_bin_share_cache.get(key)
        if p_share is None:
            p_share = float(parent_share[idx].sum())
            parent_bin_share_cache[key] = p_share

        local_bin = pd.to_numeric(df_child[col], errors="coerce").fillna(0.0).to_numpy(float)
        nat_expected = p_share * child_totals
        target = w * local_bin + (1.0 - w) * nat_expected

        s = X[:, idx].sum(axis=1)
        f = np.ones_like(s)
        good = (s > eps) & np.isfinite(s)
        f[good] = (np.maximum(target[good], 0.0) / s[good]) ** alpha
        np.clip(f, 1e-6, 1e6, out=f)

        need_seed = (s <= eps) & (target > 0)
        if need_seed.any():
            pbin = parent_share[idx]
            pw = pbin.sum()
            within = (pbin / pw) if pw > 0 else np.full(idx.size, 1.0 / max(idx.size, 1))
            X[np.ix_(need_seed, idx)] = target[need_seed, None] * within[None, :]

        X[:, idx] *= f[:, None]


# ---------------------------------------------------------------------------
# Cell [7]: core downscaler config & function
# ---------------------------------------------------------------------------


@dataclass
class DownscaleConfig:
    top_age: int = 100
    alpha_infr: float = 0.80
    alpha_10y: float = 0.85
    alpha_5c: float = 0.90
    trust_threshold: float = 200.0
    inner_passes: int = 20
    outer_iters: int = 5
    tol_rel_row: float = 2e-4
    rake_tol: float = 1e-10
    rake_max_iter: int = 50


def downscale_single_years(
    parent_df: pd.DataFrame,
    child_df: pd.DataFrame,
    *,
    parent_id_col: str,
    child_parent_id_col: str,
    child_pop_col: str,
    parent_age_cols: Optional[List[str]] = None,
    child_level_for_bins: str,
    cfg: DownscaleConfig = DownscaleConfig(),
) -> pd.DataFrame:
    """Downscale single-year ages from parent to child level (cell [7]).

    For each parent group:
        - initialise X = child_totals x parent_per-age_shares
        - trust-mixed bin scaling (INFR, 10y, 5c) inner passes
        - rake to (rows=child totals HARD, cols=parent per-age totals HARD)

    Returns DataFrame aligned to child_df.index with AGE_0..AGE_{top_age}.
    """
    try:
        from tqdm import tqdm as _tqdm
        def _wrap(it, **kw):
            return _tqdm(it, **kw)
    except ImportError:
        def _wrap(it, **kw):
            return it

    top_age = cfg.top_age
    Acols = parent_age_cols or age_cols(top_age)
    A = len(Acols)
    assert A == (top_age + 1), "parent_age_cols must cover 0..top_age"

    infr_bins  = _collect_existing_bins(child_df, make_infr_bins(child_level_for_bins, top_age), top_age)
    teny_bins  = _collect_existing_bins(child_df, make_tenyear_bins(child_level_for_bins, top_age), top_age)
    fivec_bins = _collect_existing_bins(child_df, make_fiveclass_bins(child_level_for_bins, top_age), top_age)

    for c in [parent_id_col]:
        if c not in parent_df.columns:
            raise KeyError(f"Missing column in parent_df: {c}")
    for c in [child_parent_id_col, child_pop_col]:
        if c not in child_df.columns:
            raise KeyError(f"Missing column in child_df: {c}")
    for c in Acols:
        if c not in parent_df.columns:
            raise KeyError(f"Missing parent per-age column: {c}")

    out = pd.DataFrame(index=child_df.index, columns=Acols, dtype=float)

    groups = child_df.groupby(child_parent_id_col, sort=False)

    parent_age_map: Dict[object, np.ndarray] = {}
    for pid, psub in parent_df[[parent_id_col] + Acols].groupby(parent_id_col):
        parent_age_map[pid] = psub[Acols].astype(float).to_numpy().sum(axis=0)

    for pid, child_idx in _wrap(groups.groups.items(), desc=f"downscale {child_level_for_bins}"):
        p = parent_age_map.get(pid)
        if p is None:
            out.loc[child_idx, :] = 0.0
            continue

        cdf = child_df.loc[child_idx]
        totals = pd.to_numeric(cdf[child_pop_col], errors="coerce").fillna(0.0).to_numpy(float)
        n = totals.size
        if n == 0:
            continue

        Psum = float(p.sum())
        if Psum <= 0:
            out.loc[child_idx, :] = 0.0
            continue

        parent_share = p / Psum
        X = np.outer(totals, parent_share)

        for _ in range(cfg.outer_iters):
            for _inner in range(cfg.inner_passes):
                if infr_bins:
                    _apply_child_bin_scalings_mixed(
                        cdf, X, totals, parent_share, infr_bins,
                        alpha=cfg.alpha_infr, trust_threshold=cfg.trust_threshold,
                    )
                if teny_bins:
                    _apply_child_bin_scalings_mixed(
                        cdf, X, totals, parent_share, teny_bins,
                        alpha=cfg.alpha_10y, trust_threshold=cfg.trust_threshold,
                    )
                if fivec_bins:
                    _apply_child_bin_scalings_mixed(
                        cdf, X, totals, parent_share, fivec_bins,
                        alpha=cfg.alpha_5c, trust_threshold=cfg.trust_threshold,
                    )
                rs = X.sum(axis=1, keepdims=True)
                np.divide(totals[:, None], np.maximum(rs, 1e-12), out=rs)
                X *= rs

            _final_rake_to_margins(
                X, row_targets=totals, col_targets=p,
                tol=cfg.rake_tol, max_iter=cfg.rake_max_iter,
            )

        _final_rake_to_margins(X, row_targets=totals, col_targets=p,
                               tol=cfg.rake_tol, max_iter=150)

        out.loc[child_idx, :] = X

        # validation: rows within 0.02%
        calc_totals = X.sum(axis=1)
        rel_err = np.abs(calc_totals - totals) / np.maximum(totals, 1.0)
        max_rel = float(rel_err.max(initial=0.0))
        if max_rel > cfg.tol_rel_row:
            raise AssertionError(
                f"[{child_level_for_bins}] Row totals dev > 0.02% for parent {pid}. "
                f"Max rel.err={max_rel:.3e}."
            )

        # validation: columns equal parent per-age (tight tol)
        child_totals_per_age = X.sum(axis=0)
        if not np.allclose(child_totals_per_age, p, rtol=0.0, atol=1e-5):
            if not np.allclose(child_totals_per_age, p, rtol=0.0, atol=1):
                raise AssertionError(
                    f"[{child_level_for_bins}] Col totals != parent per-age for parent {pid}."
                )

    return out


# ---------------------------------------------------------------------------
# Pipeline entry point
# ---------------------------------------------------------------------------


def _load_nat(cfg) -> pd.Series:
    """Locate and load the national age vector CSV."""
    # The notebook used:  raw/national_age_vector.csv relative to the raw CSVs dir.
    # We look in work_dir/../raw and also in a cfg attribute if provided.
    candidates = []
    if hasattr(cfg, "national_age_csv"):
        candidates.append(cfg.national_age_csv)
    work = cfg.work_dir
    candidates += [
        work.parent / "raw" / "national_age_vector.csv",
        work.parent.parent / "raw" / "national_age_vector.csv",
    ]
    # Also support T: path as last resort (dev only)
    t_path = r"T:\petre\UCFL\Synthetic Population\Zensus\raw\national_age_vector.csv"
    import os
    if os.path.exists(t_path):
        candidates.append(t_path)
    for p in candidates:
        from pathlib import Path
        pp = Path(p)
        if pp.exists():
            log.info("[ages] loading national age vector from %s", pp)
            return load_national_single_years(pp)
    raise FileNotFoundError(
        f"national_age_vector.csv not found. Searched: {candidates}"
    )


def run_ages(cfg) -> None:  # cfg: Config
    """Run the ages stage: 10km fitting + 1km/100m downscaling."""
    work = cfg.work_dir

    # ------------------------------------------------------------------
    # Load totals outputs
    # ------------------------------------------------------------------
    log.info("[ages] loading totals parquets")
    df10_raw = pd.read_parquet(work / "totals_10km.parquet")
    df1_raw  = pd.read_parquet(work / "totals_1km.parquet")
    df100_raw = pd.read_parquet(work / "totals_100m.parquet")

    # Global hygiene: NaN/±inf -> 0 (exactly as notebook cell [6])
    df10 = df10_raw.replace([np.inf, -np.inf], np.nan).fillna(0)
    df1  = df1_raw.replace([np.inf, -np.inf], np.nan).fillna(0)
    df100 = df100_raw.replace([np.inf, -np.inf], np.nan).fillna(0)

    # ------------------------------------------------------------------
    # Step 1: 10km single-year fitting (cell [6])
    # ------------------------------------------------------------------
    log.info("[ages] fitting 10km single years")
    if "GITTER_ID_10km" in df10.columns:
        df10 = df10.set_index("GITTER_ID_10km")

    nat = _load_nat(cfg)

    ages_per_cell, adjusted_cell_totals = fit_single_years_10km(df10, nat)

    df10_with_ages = df10.join(ages_per_cell)
    df10_with_ages = df10_with_ages.rename(columns={i: f"AGE_{i}" for i in ages_per_cell.columns})
    df10_with_ages[f"{POP_COL_10KM}_adj"] = adjusted_cell_totals

    out10 = work / "df10_with_single_years.parquet"
    df10_with_ages.to_parquet(out10)
    log.info("[ages] wrote %s  (rows=%d)", out10.name, len(df10_with_ages))

    # ------------------------------------------------------------------
    # Step 2: 10km -> 1km downscaling (cell [7])
    # ------------------------------------------------------------------
    log.info("[ages] downscaling 10km -> 1km")

    df10_reset = df10_with_ages.reset_index()  # restore GITTER_ID_10km as column

    # Normalize IDs to str
    df10_reset["GITTER_ID_10km"] = df10_reset["GITTER_ID_10km"].astype(str).str.strip()
    df1["GITTER_ID_10km"] = df1["GITTER_ID_10km"].astype(str).str.strip()
    df1["GITTER_ID_1km"] = df1["GITTER_ID_1km"].astype(str).str.strip()

    # Tag 1km rows that have no 100m children (for later)
    p_1km = set(df1["GITTER_ID_1km"].unique())
    c_100_set = set(df100["GITTER_ID_1km"].astype(str).str.strip().unique())
    missing_in_child = p_1km - c_100_set
    df1["has_no_children"] = df1["GITTER_ID_1km"].isin(missing_in_child)

    # Adjust 1km totals to 10km_adj
    make_child_totals_adj(
        parent_df=df10_reset,
        child_df=df1,
        parent_id_col="GITTER_ID_10km",
        child_parent_id_col="GITTER_ID_10km",
        parent_adj_col=f"{POP_COL_10KM}_adj",
        child_pop_col="POP_TOTAL_1km",
    )

    ages_1km = downscale_single_years(
        parent_df=df10_reset,
        child_df=df1,
        parent_id_col="GITTER_ID_10km",
        child_parent_id_col="GITTER_ID_10km",
        child_pop_col="POP_TOTAL_1km_adj",
        parent_age_cols=age_cols(100),
        child_level_for_bins="1km",
        cfg=DownscaleConfig(
            top_age=100, alpha_infr=0.80, alpha_10y=0.85, alpha_5c=0.90,
            trust_threshold=100.0, inner_passes=10, outer_iters=2,
            tol_rel_row=2e-4, rake_tol=1e-10, rake_max_iter=50,
        ),
    )

    df1_with_ages = df1.join(ages_1km)
    out1 = work / "df1_with_single_years.parquet"
    df1_with_ages.to_parquet(out1)
    log.info("[ages] wrote %s  (rows=%d)", out1.name, len(df1_with_ages))

    # ------------------------------------------------------------------
    # Step 3: 1km -> 100m downscaling (cell [7])
    # ------------------------------------------------------------------
    log.info("[ages] downscaling 1km -> 100m")

    df100["GITTER_ID_1km"] = df100["GITTER_ID_1km"].astype(str).str.strip()
    orphans_in_child = c_100_set - p_1km
    df100["is_orphan"] = df100["GITTER_ID_1km"].isin(orphans_in_child)

    df1_par_ok     = df1_with_ages.loc[~df1_with_ages["has_no_children"]].copy()
    df100_child_ok = df100.loc[~df100["is_orphan"]].copy()

    make_child_totals_adj(
        parent_df=df1_par_ok,
        child_df=df100_child_ok,
        parent_id_col="GITTER_ID_1km",
        child_parent_id_col="GITTER_ID_1km",
        parent_adj_col="POP_TOTAL_1km_adj",
        child_pop_col="POP_TOTAL_100m",
    )

    # Back-fill POP_TOTAL_100m_adj for orphans (use raw value)
    df100["POP_TOTAL_100m_adj"] = df100["POP_TOTAL_100m"]
    df100.loc[df100_child_ok.index, "POP_TOTAL_100m_adj"] = df100_child_ok["POP_TOTAL_100m_adj"].values

    ages_100m_ok = downscale_single_years(
        parent_df=df1_par_ok,
        child_df=df100_child_ok,
        parent_id_col="GITTER_ID_1km",
        child_parent_id_col="GITTER_ID_1km",
        child_pop_col="POP_TOTAL_100m_adj",
        parent_age_cols=age_cols(100),
        child_level_for_bins="100m",
        cfg=DownscaleConfig(
            top_age=100, alpha_infr=0.80, alpha_10y=0.85, alpha_5c=0.90,
            trust_threshold=100.0, inner_passes=10, outer_iters=2,
            tol_rel_row=2e-4, rake_tol=1e-10, rake_max_iter=50,
        ),
    )

    df100_with_ages = df100.join(ages_100m_ok)
    out100 = work / "df100_with_single_years.parquet"
    df100_with_ages.to_parquet(out100)
    log.info("[ages] wrote %s  (rows=%d)", out100.name, len(df100_with_ages))


def ages_complete(cfg) -> bool:
    work = cfg.work_dir
    return all(
        (work / f"df{n}_with_single_years.parquet").exists()
        for n in ("10", "1", "100")
    )
