"""Totals stage: collapse population total columns and proportionally adjust
to parent levels.

Ported faithfully from notebooks_archive/ages.ipynb cells [2] and [4].

Cell [2]: add_parent_ids_for_level — derive GITTER_ID_1km / GITTER_ID_10km from
    finer resolution IDs (1km->10km, 100m->1km and 10km).

Cell [4]: collapse_population_totals / proportional_adjust_to_parent —
    consensus-based deduplication of population total columns followed by a
    proportional scaling step so child sums match parent totals.

Inputs (work_dir):
    merged_{level}_gitter.parquet for level in {10km, 1km, 100m}

Outputs (work_dir):
    totals_{level}.parquet for level in {10km, 1km, 100m}
    Adds POP_TOTAL_{level} (consensus) and, for 1km/100m, a "scale" column.

No randomness is used in this stage.  Results are deterministic.
"""
from __future__ import annotations

import re
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

from cleancensus import names
from cleancensus.logsetup import get_logger

if TYPE_CHECKING:
    from pathlib import Path

log = get_logger("totals")

# ---------------------------------------------------------------------------
# Cell [2]: parent ID derivation
# ---------------------------------------------------------------------------

_ID_RE = re.compile(r"^CRS3035RES(\d+)mN(\d+)E(\+?\-?\d+)$")


def parent_gitter_id(gid: str, target_res: int) -> str | None:
    """Convert any CRS3035RESXmN..E.. ID to the parent grid at target_res (m).

    Floors N/E to the nearest target_res and replaces the RES prefix.

    Examples:
        CRS3035RES1000mN2689000E4337000, 10000
            -> CRS3035RES10000mN2680000E4330000
        CRS3035RES100mN2689400E4337600, 1000
            -> CRS3035RES1000mN2689000E4337000
    """
    if not isinstance(gid, str):
        return None
    m = _ID_RE.match(gid.strip())
    if not m:
        return None
    _, n_str, e_str = m.groups()
    n = int(n_str)
    e = int(e_str)
    n_parent = (n // target_res) * target_res
    e_parent = (e // target_res) * target_res
    return f"CRS3035RES{target_res}mN{n_parent}E{e_parent}"


def add_parent_ids_for_level(df: pd.DataFrame, level: str) -> pd.DataFrame:
    """Add GITTER_ID parent columns if missing.

    level in {"100m", "1km"}:
        "1km"  -> adds GITTER_ID_10km from GITTER_ID_1km.
        "100m" -> adds GITTER_ID_1km and GITTER_ID_10km from GITTER_ID_100m.

    Returns df (mutated in place) for convenience.
    """
    assert level in {"100m", "1km"}, "level must be '100m' or '1km'"
    if level == "1km":
        id_col = "GITTER_ID_1km"
        if "GITTER_ID_10km" not in df.columns:
            df["GITTER_ID_10km"] = df[id_col].apply(
                lambda x: parent_gitter_id(x, 10_000)
            )
    else:  # "100m"
        id_col = "GITTER_ID_100m"
        if "GITTER_ID_1km" not in df.columns:
            df["GITTER_ID_1km"] = df[id_col].apply(
                lambda x: parent_gitter_id(x, 1_000)
            )
        if "GITTER_ID_10km" not in df.columns:
            df["GITTER_ID_10km"] = df[id_col].apply(
                lambda x: parent_gitter_id(x, 10_000)
            )
    return df


# ---------------------------------------------------------------------------
# Cell [4]: population total collapse
# ---------------------------------------------------------------------------


def collapse_population_totals(
    df: pd.DataFrame,
    level: str,
    tol: float = 1e-6,
    verbose: bool = True,
    sample_n: int = 20,
) -> tuple[pd.DataFrame, str]:
    """Collapse multiple population total columns into a single consensus column.

    Strategy (faithfully ported from cell [4]):
    - For each row, place non-null values into tolerance-aware groups.
    - Choose the group with the most members; break ties by proximity to the
      row median; if still tied, pick the first encountered.
    - Consensus = median of the winning group values.
    - Output column name: ``POP_TOTAL_{level}``.

    Returns: (df, pop_col_name)
    """
    pop_cols = [
        c
        for c in df.columns
        if re.match(r"^(Einwohner_Bevoelkerungszahl|Insgesamt_Bevoelkerung_)", c)
    ]
    if not pop_cols:
        raise ValueError(
            f"No population total columns found for level='{level}'. "
            "Expected columns matching ^(Einwohner_Bevoelkerungszahl|Insgesamt_Bevoelkerung_)"
        )

    for c in pop_cols:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    id_col = f"GITTER_ID_{level}" if f"GITTER_ID_{level}" in df.columns else None
    values = df[pop_cols].copy()

    def _row_consensus(row_vals: pd.Series):
        non_null = row_vals.dropna()
        total_non_na = len(non_null)
        if total_non_na == 0:
            return np.nan, 0, 0, False, {}

        groups: list[dict] = []
        for col_name, val in non_null.items():
            placed = False
            for g in groups:
                if abs(val - g["rep"]) <= tol:
                    g["idxs"].append(col_name)
                    g["vals"].append(val)
                    g["rep"] = float(np.median(g["vals"]))
                    placed = True
                    break
            if not placed:
                groups.append({"idxs": [col_name], "vals": [val], "rep": float(val)})

        sizes = [len(g["idxs"]) for g in groups]
        max_size = max(sizes)
        winners = [g for g in groups if len(g["idxs"]) == max_size]
        tie = len(winners) > 1

        if tie:
            row_median = float(np.median(non_null.values))
            winners.sort(key=lambda g: abs(g["rep"] - row_median))
        winner = winners[0]
        consensus_value = float(np.median(winner["vals"]))

        support_map = {g["rep"]: g["idxs"] for g in groups}
        return consensus_value, len(winner["idxs"]), total_non_na, tie, support_map

    cons_vals: list[float] = []
    cons_support: list[int] = []
    cons_total_non_na: list[int] = []
    cons_tie: list[bool] = []

    for i in range(len(values)):
        row = values.iloc[i]
        v, sup, tot, tie, _ = _row_consensus(row)
        cons_vals.append(v)
        cons_support.append(sup)
        cons_total_non_na.append(tot)
        cons_tie.append(tie)

    pop_col = f"POP_TOTAL_{level}"
    df[pop_col] = cons_vals

    if verbose:
        cs = pd.Series(cons_support, index=df.index)
        ctna = pd.Series(cons_total_non_na, index=df.index)
        ct = pd.Series(cons_tie, index=df.index)
        unanimity = (cs == ctna) & (ctna > 0)
        log.info(
            "%s: rows=%d unanimous=%d conflicts=%d ties=%d",
            level,
            len(df),
            int(unanimity.sum()),
            int((~unanimity & (ctna > 0)).sum()),
            int(ct.sum()),
        )

    return df, pop_col


# ---------------------------------------------------------------------------
# Cell [4]: proportional adjustment to parent level
# ---------------------------------------------------------------------------


def _ensure_parent_column(
    df: pd.DataFrame, level: str
) -> tuple[pd.DataFrame, str]:
    """Add/return the parent ID column for a child level."""
    if level == "100m":
        child_id, parent_id, tgt = "GITTER_ID_100m", "GITTER_ID_1km", 1_000
    elif level == "1km":
        child_id, parent_id, tgt = "GITTER_ID_1km", "GITTER_ID_10km", 10_000
    else:
        raise ValueError("Only 100m and 1km have parents for proportional adjustment.")
    if parent_id not in df.columns:
        df[parent_id] = df[child_id].apply(lambda x: parent_gitter_id(x, tgt))
    return df, parent_id


def proportional_adjust_to_parent(
    child_df: pd.DataFrame,
    parent_df: pd.DataFrame,
    child_level: str,
    parent_level: str,
    child_pop_col: str,
    parent_pop_col: str,
) -> pd.DataFrame:
    """Scale child POP_TOTAL so that group sums match the parent POP_TOTAL.

    Factor per parent = parent_total / sum(child_total_in_group).
    Where group sum is 0, uses factor 1 (no change).

    Note: leaves a "scale" column on child_df (faithful port of cell [4]).
    """
    child_df, parent_col = _ensure_parent_column(child_df, child_level)

    parent_id_col = f"GITTER_ID_{parent_level}"
    if parent_id_col not in parent_df.columns:
        raise ValueError(f"{parent_id_col} missing in parent_df.")

    p_tot = (
        parent_df[[parent_id_col, parent_pop_col]]
        .dropna(subset=[parent_id_col])
        .copy()
    )
    p_tot[parent_pop_col] = pd.to_numeric(p_tot[parent_pop_col], errors="coerce")
    p_tot = p_tot.groupby(parent_id_col)[parent_pop_col].sum(min_count=1)

    child_df[child_pop_col] = pd.to_numeric(child_df[child_pop_col], errors="coerce")
    c_sum = child_df.groupby(parent_col)[child_pop_col].sum(min_count=1)

    factors = (p_tot / c_sum).rename("scale")
    factors = factors.replace([pd.NA, pd.NaT], 1.0).fillna(1.0)

    child_df = child_df.merge(
        factors.to_frame(), left_on=parent_col, right_index=True, how="left"
    )
    child_df["scale"] = child_df["scale"].replace([pd.NA, pd.NaT], 1.0).fillna(1.0)
    child_df[child_pop_col] = (
        child_df[child_pop_col].astype(float) * child_df["scale"].astype(float)
    )

    log.info(
        "proportional adjust %s -> %s: max_scale=%.3f mean_scale=%.3f",
        child_level,
        parent_level,
        float(factors.max()),
        float(factors.mean()),
    )
    return child_df


# ---------------------------------------------------------------------------
# Pipeline entry point
# ---------------------------------------------------------------------------


def run_totals(cfg) -> None:  # cfg: Config
    """Run the totals stage: collapse + adjust all three levels, write parquets."""
    work = cfg.work_dir
    work.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # 10km: collapse only (no parent)
    # ------------------------------------------------------------------
    inp10 = names.resolve(work, names.work("merge", "10km"))
    out10 = work / names.work("totals", "10km")
    log.info("loading %s", inp10)
    df10 = pd.read_parquet(inp10)
    df10, pop10 = collapse_population_totals(df10, "10km")
    df10.to_parquet(out10, index=False)
    log.info("wrote %s  (rows=%d, col=%s)", out10.name, len(df10), pop10)

    # ------------------------------------------------------------------
    # 1km: collapse + adjust to 10km
    # ------------------------------------------------------------------
    inp1 = names.resolve(work, names.work("merge", "1km"))
    out1 = work / names.work("totals", "1km")
    log.info("loading %s", inp1)
    df1 = pd.read_parquet(inp1)
    add_parent_ids_for_level(df1, "1km")  # ensure GITTER_ID_10km present
    df1, pop1 = collapse_population_totals(df1, "1km")
    # adjust to 10km
    df1 = proportional_adjust_to_parent(df1, df10, "1km", "10km", pop1, pop10)
    df1.to_parquet(out1, index=False)
    log.info("wrote %s  (rows=%d, col=%s)", out1.name, len(df1), pop1)

    # ------------------------------------------------------------------
    # 100m: collapse + adjust to 1km
    # ------------------------------------------------------------------
    inp100 = names.resolve(work, names.work("merge", "100m"))
    out100 = work / names.work("totals", "100m")
    log.info("loading %s", inp100)
    df100 = pd.read_parquet(inp100)
    add_parent_ids_for_level(df100, "100m")  # ensure GITTER_ID_1km and _10km
    df100, pop100 = collapse_population_totals(df100, "100m")
    # adjust to 1km (use updated df1 from above)
    df100 = proportional_adjust_to_parent(df100, df1, "100m", "1km", pop100, pop1)
    df100.to_parquet(out100, index=False)
    log.info("wrote %s  (rows=%d, col=%s)", out100.name, len(df100), pop100)


def totals_complete(cfg) -> bool:
    work = cfg.work_dir
    return all(
        names.resolve(work, names.work("totals", lvl)).exists()
        for lvl in ("10km", "1km", "100m")
    )
