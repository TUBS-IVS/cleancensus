"""Parse Zensus Regionaltabellen (P2/P4) into Gemeinde- and Kreis-level control tables.

Source file: Regionaltabelle_Bildung_Erwerbstaetigkeit.xlsx
Three CSV-sheets are parsed:
  - CSV-Erwerbsstatus         -> erwerbsstatus.parquet
  - CSV-Hoechster_Schulabschluss -> schulabschluss.parquet
  - CSV-Hoechster_berufl_Abschluss -> berufl_abschluss.parquet

Each Gemeinde output table contains only Gemeinde-level rows (Regionalebene == 'Gemeinde'),
identified by 12-digit ARS key. Suppressed values ('/' in the source) become NaN.

Each Kreis output table contains only Kreis-level rows (Regionalebene contains
'Stadtkreis/kreisfreie Stadt/Landkreis'), identified by a 5-digit ARS prefix.
Kreis tables have 0% suppression (all 400 Kreise fully observed).

Optional fill (--fill harmonize): suppressed Gemeinde cells are estimated by downscaling
the Kreis distribution to each Gemeinde using the repo's harmonization machinery.
Child row totals for suppressed Gemeinden are population-weighted remainders from the Kreis.
An is_estimated bool column flags rows where ANY category or total was suppressed.

These tables are NOT pipeline stages — they are Gemeinde-level, not grid cells.
They serve as PopulationSim (eqasim) Gemeinde-level controls, not as inputs to
the grid harmonization pipeline.

Coverage note:
  - Erwerbsstatus universe: residents 15+ classified by employment status (80,777,360 total)
  - Schulabschluss universe: persons 15+ by highest school qualification (69,439,520 total)
  - Berufl. Abschluss universe: persons 15+ by highest vocational qualification (same total)
"""
from __future__ import annotations

import warnings
from pathlib import Path

import numpy as np
import pandas as pd


# --- Category code -> label maps -------------------------------------------
# These are derived from the named sheets in the Excel workbook.

# Erwerbsstatus (ERWERBSTAT_KURZ_STP)
# Total code: ERWERBSTAT_KURZ_STP (no suffix)
# Category codes correspond to the suffix after __ in the column name
ERWERBSSTATUS_CATS = {
    "Insgesamt": "ERWERBSTAT_KURZ_STP",           # 15+ Bevölkerung
    "Erwerbspersonen": "ERWERBSTAT_KURZ_STP__1",   # Erwerbspersonen gesamt
    "Erwerbstaetige": "ERWERBSTAT_KURZ_STP__11",   # Erwerbstätige
    "Erwerbslose": "ERWERBSTAT_KURZ_STP__12",      # Erwerbslose (ILO)
    "Nichterwerbspersonen": "ERWERBSTAT_KURZ_STP__2",  # Nichterwerbspersonen
}
# Including gender breakdowns
ERWERBSSTATUS_ALL_CATS = [
    "ERWERBSTAT_KURZ_STP",       # Insgesamt
    "ERWERBSTAT_KURZ_STP__M",    # Männlich
    "ERWERBSTAT_KURZ_STP__W",    # Weiblich
    "ERWERBSTAT_KURZ_STP__1",    # Erwerbspersonen gesamt
    "ERWERBSTAT_KURZ_STP__1_M",  # EP männlich
    "ERWERBSTAT_KURZ_STP__1_W",  # EP weiblich
    "ERWERBSTAT_KURZ_STP__11",   # Erwerbstätige
    "ERWERBSTAT_KURZ_STP__11_M", # ET männlich
    "ERWERBSTAT_KURZ_STP__11_W", # ET weiblich
    "ERWERBSTAT_KURZ_STP__12",   # Erwerbslose
    "ERWERBSTAT_KURZ_STP__12_M", # EL männlich
    "ERWERBSTAT_KURZ_STP__12_W", # EL weiblich
    "ERWERBSTAT_KURZ_STP__2",    # Nichterwerbspersonen
    "ERWERBSTAT_KURZ_STP__2_M",  # NEP männlich
    "ERWERBSTAT_KURZ_STP__2_W",  # NEP weiblich
]

# Schulabschluss (SCHULABS_STP)
SCHULABSCHLUSS_CATS = {
    "Insgesamt": "SCHULABS_STP",        # 15+ Personen
    "InAusbildung": "SCHULABS_STP__1",  # noch in schulischer Ausbildung
    "MitAbschluss": "SCHULABS_STP__2",  # mit allgemeinbildendem Schulabschluss
    "Hauptschule": "SCHULABS_STP__21",  # Haupt-/Volksschulabschluss
    "Polytechnisch": "SCHULABS_STP__22",  # Abschluss POS (DDR)
    "Realschule": "SCHULABS_STP__23",   # Realschule / Mittlere Reife
    "Abitur": "SCHULABS_STP__24",       # Fachhochschul- oder Hochschulreife
    "OhneAbschluss": "SCHULABS_STP__3", # ohne allgemeinbildenden Schulabschluss
}

# Berufl. Abschluss (BERUFABS_AUSF_STP)
BERUFL_ABSCHLUSS_CATS = {
    "Insgesamt": "BERUFABS_AUSF_STP",        # 15+ Personen
    "MitBerufsabs": "BERUFABS_AUSF_STP__1",  # mit beruflichem Bildungsabschluss
    "Lehre": "BERUFABS_AUSF_STP__11",        # Lehre / duales System
    "Fachschule": "BERUFABS_AUSF_STP__12",   # Fachschulabschluss (West)
    "FachschuleDDR": "BERUFABS_AUSF_STP__13",  # Fachschulabschluss DDR
    "Bachelor": "BERUFABS_AUSF_STP__14",     # Bachelor
    "Master": "BERUFABS_AUSF_STP__15",       # Master
    "Diplom": "BERUFABS_AUSF_STP__16",       # Diplom
    "Promotion": "BERUFABS_AUSF_STP__17",    # Promotion
    "OhneBerufsabs": "BERUFABS_AUSF_STP__2", # ohne beruflichen Bildungsabschluss
}

# Sheets to parse: logical_name -> (sheet_name, suppression_marker)
DEFAULT_SHEETS = {
    "erwerbsstatus": "CSV-Erwerbsstatus",
    "schulabschluss": "CSV-Hoechster_Schulabschluss",
    "berufl_abschluss": "CSV-Hoechster_berufl_Abschluss",
}

SUPPRESSION_MARKERS = {"/", "-", "–", "—", "x", "X", "."}

# The Regionaltabellen use '/' as the suppression marker.

# Regionalebene value for Kreis/Stadtkreis rows (contains this substring)
_KREIS_EBENE_SUBSTR = "Stadtkreis/kreisfreie Stadt/Landkreis"


def _parse_sheet(
    xlsx_path: Path,
    sheet_name: str,
    *,
    dtype_str_cols: tuple[str, ...] = ("_RS",),
) -> pd.DataFrame:
    """Parse a single CSV-sheet from the Regionaltabellen workbook.

    Returns a tidy DataFrame with:
    - ARS column ('_RS') zero-padded to 12 characters
    - 'Name' and 'Regionalebene' preserved
    - All data columns coerced to float64; suppression markers -> NaN
    """
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        df = pd.read_excel(
            xlsx_path,
            sheet_name=sheet_name,
            header=0,
            dtype={col: str for col in dtype_str_cols},
        )

    # Zero-pad ARS to 12 digits (pandas reads numeric columns dropping leading zeros)
    if "_RS" in df.columns:
        df["_RS"] = df["_RS"].astype(str).str.strip().str.zfill(12)

    # Coerce data columns to numeric, suppression -> NaN
    meta_cols = {"Berichtszeitpunkt", "_RS", "Name", "Regionalebene"}
    data_cols = [c for c in df.columns if c not in meta_cols]
    for col in data_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    return df


def build_gemeinde_controls(
    xlsx_path: Path | str,
    sheets: dict[str, str] | None = None,
) -> dict[str, pd.DataFrame]:
    """Parse each CSV-sheet into a tidy Gemeinde-only DataFrame.

    Args:
        xlsx_path: Path to Regionaltabelle_Bildung_Erwerbstaetigkeit.xlsx
        sheets: Override sheet mapping {logical_name: sheet_name}.
                Defaults to DEFAULT_SHEETS (erwerbsstatus, schulabschluss, berufl_abschluss).

    Returns:
        dict mapping logical name -> DataFrame with columns:
          ARS (str, 12-digit), Name (str), + all data columns (float64, NaN for suppressed).
          Rows = Gemeinde-level only (Regionalebene == 'Gemeinde').
    """
    xlsx_path = Path(xlsx_path)
    if sheets is None:
        sheets = DEFAULT_SHEETS

    result: dict[str, pd.DataFrame] = {}
    for logical_name, sheet_name in sheets.items():
        df = _parse_sheet(xlsx_path, sheet_name)

        # Keep Gemeinde rows only
        gem = df[df["Regionalebene"] == "Gemeinde"].copy()
        gem = gem.reset_index(drop=True)

        # Rename _RS to ARS and drop non-essential meta columns
        gem = gem.rename(columns={"_RS": "ARS"})
        drop_cols = {"Berichtszeitpunkt", "Regionalebene"}
        gem = gem.drop(columns=[c for c in drop_cols if c in gem.columns])

        result[logical_name] = gem

    return result


def build_kreis_controls(
    xlsx_path: Path | str,
    sheets: dict[str, str] | None = None,
) -> dict[str, pd.DataFrame]:
    """Parse each CSV-sheet into a tidy Kreis-only DataFrame.

    Kreis rows have 0% suppression (all 400 Kreise complete, including ZGB Kreise).
    The ARS key for Kreis rows is 5 digits (Land 2 + RB 1 + Kreis 2), zero-padded to 12
    then truncated to 5 for use as a join key.

    Args:
        xlsx_path: Path to Regionaltabelle_Bildung_Erwerbstaetigkeit.xlsx
        sheets: Override sheet mapping {logical_name: sheet_name}.

    Returns:
        dict mapping logical name -> DataFrame with columns:
          ARS_kreis (str, 5-digit), Name (str), + all data columns (float64, no NaN).
    """
    xlsx_path = Path(xlsx_path)
    if sheets is None:
        sheets = DEFAULT_SHEETS

    result: dict[str, pd.DataFrame] = {}
    for logical_name, sheet_name in sheets.items():
        df = _parse_sheet(xlsx_path, sheet_name)

        # Keep Kreis rows: Regionalebene contains the Kreis-level label
        kreis = df[df["Regionalebene"] == _KREIS_EBENE_SUBSTR].copy()
        kreis = kreis.reset_index(drop=True)

        # Rename _RS -> ARS_kreis.
        # After _parse_sheet zero-pads to 12, a 5-digit Kreis code "01001" becomes
        # "000000001001". Take the last 5 chars to recover the original 5-digit code.
        # This is consistent with how Gemeinde rows encode the Kreis: their first 5
        # chars of the 12-digit ARS are the Kreis code (e.g. "010010000000"[:5]="01001").
        kreis = kreis.rename(columns={"_RS": "ARS_kreis"})
        kreis["ARS_kreis"] = kreis["ARS_kreis"].str[-5:]

        drop_cols = {"Berichtszeitpunkt", "Regionalebene"}
        kreis = kreis.drop(columns=[c for c in drop_cols if c in kreis.columns])

        result[logical_name] = kreis

    return result


def _load_gemeinde_population(bevoelkerung_xlsx: Path) -> pd.Series:
    """Load Gemeinde Einwohnerzahl (EWZ) from Regionaltabelle_Bevoelkerung.xlsx.

    Returns a Series indexed by 12-digit ARS string.
    """
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        df = pd.read_excel(
            bevoelkerung_xlsx,
            sheet_name="CSV-Einwohnerzahl",
            header=0,
            dtype={"_RS": str},
        )

    df["_RS"] = df["_RS"].astype(str).str.strip().str.zfill(12)
    gem = df[df["Regionalebene"] == "Gemeinde"].copy()
    ewz = pd.to_numeric(gem["EWZ"], errors="coerce").fillna(0.0)
    return pd.Series(ewz.values, index=gem["_RS"].values, name="EWZ")


def fill_gemeinde_harmonize(
    gemeinde_df: pd.DataFrame,
    kreis_df: pd.DataFrame,
    *,
    table_name: str,
    total_col: str,
    cat_cols: list[str],
    ewz: pd.Series,
    alpha: float = 0.85,
) -> pd.DataFrame:
    """Fill suppressed Gemeinde cells using Kreis distributions via harmonization.

    Algorithm per Kreis:
    1. Build is_estimated mask (any NaN in categories or total).
    2. For suppressed Gemeinden, estimate child_row_total as:
       population-weighted share of (Kreis_total - sum(unsuppressed Gemeinden_total)).
    3. Fill category NaNs with 0 (no-signal prior) before downscaling.
    4. Run downscale_topic (trust-blended IPF) — parent = Kreis distribution,
       child = Gemeinden with their estimated/observed totals.
    5. Post: overwrite category columns with downscaled output;
       rake columns so Σ(Gemeinden) == Kreis per category (assert < 0.5 abs).
    6. Add is_estimated bool column.

    Args:
        gemeinde_df: Gemeinde table with ARS (12-digit), Name, total_col, cat_cols.
                     NaN = suppressed.
        kreis_df: Kreis table with ARS_kreis (5-digit), cat_cols (same names).
        table_name: Logical name for logging.
        total_col: Name of the total/Insgesamt column.
        cat_cols: Category columns to downscale (excluding total_col).
        ewz: Series indexed by 12-digit ARS with Gemeinde Einwohnerzahl.
        alpha: Damping exponent for trust blend (default 0.85).

    Returns:
        Copy of gemeinde_df with cat_cols filled, total_col filled, is_estimated added.
    """
    from cleancensus.harmonization import TopicSpec, downscale_topic, BLEND_STD

    gem = gemeinde_df.copy().reset_index(drop=True)

    # Pre-fill NaN mask: True where ANY of cat_cols or total_col was originally NaN
    nan_in_any_cat = gem[cat_cols].isna().any(axis=1)
    nan_in_total = gem[total_col].isna()
    is_estimated_mask = (nan_in_any_cat | nan_in_total).values.copy()

    # ARS_kreis for each Gemeinde = first 5 chars of 12-digit ARS
    gem["_kreis_key"] = gem["ARS"].str[:5]

    # Build Kreis lookup: ARS_kreis -> {col -> value}
    kreis_lookup = kreis_df.set_index("ARS_kreis")

    # Fill category NaNs with 0 (no local signal)
    for col in cat_cols:
        gem[col] = gem[col].fillna(0.0)

    # --- Compute child_row_total per Gemeinde ---
    # For unsuppressed Gemeinden: use observed total
    # For suppressed Gemeinden: population-weighted remainder
    child_totals = gem[total_col].copy().astype(float)

    # Per-Kreis remainder allocation
    for kreis_key, grp_idx in gem.groupby("_kreis_key").groups.items():
        grp = gem.loc[grp_idx]

        if kreis_key not in kreis_lookup.index:
            # Unknown Kreis: leave totals as-is (will be 0 for suppressed)
            continue

        kreis_total = float(kreis_lookup.loc[kreis_key, total_col]) if total_col in kreis_lookup.columns else np.nan
        if not np.isfinite(kreis_total) or kreis_total <= 0:
            continue

        orig_total = gemeinde_df.loc[grp_idx, total_col]  # original (with NaN)
        supp_mask = orig_total.isna().values
        n_supp = int(supp_mask.sum())

        if n_supp == 0:
            continue

        # Sum of unsuppressed Gemeinden totals
        obs_sum = float(orig_total.fillna(0.0).sum())
        remainder = max(0.0, kreis_total - obs_sum)

        if remainder <= 0:
            # Degenerate: no remainder to allocate; log and assign zeros
            print(
                f"[gemeinde-controls][{table_name}] Kreis {kreis_key}: "
                f"remainder ≤0 ({remainder:.1f}); assigning 0 to {n_supp} suppressed Gemeinden"
            )
            child_totals.loc[grp_idx[supp_mask]] = 0.0
            continue

        # Population weights for suppressed Gemeinden
        supp_idx = grp_idx[supp_mask]
        supp_ars = gem.loc[supp_idx, "ARS"].values
        pop_weights = ewz.reindex(supp_ars).fillna(0.0).values
        pop_sum = float(pop_weights.sum())

        if pop_sum <= 0:
            # No population info: split equally
            pop_weights = np.ones(n_supp)
            pop_sum = float(n_supp)

        alloc = remainder * pop_weights / pop_sum
        np.clip(alloc, 0.0, None, out=alloc)
        child_totals.loc[supp_idx] = alloc

    gem[total_col] = child_totals

    # Normalize child totals onto the parent CATEGORY mass per Kreis (the
    # make_child_totals_adj principle used throughout the pipeline). The published
    # Gemeinde/Kreis "Insgesamt" values are independently rounded/suppressed, so
    # sums can drift by a few persons (e.g. kreisfreie Stadt 01004: delta=10,
    # rel 1.3e-4) which exceeds downscale_topic's hard 1e-4 feasibility bound.
    # A per-Kreis scalar rescale makes the margins exactly feasible; observed
    # Gemeinden shift only by that scalar (typically rel < 1e-3, reported below).
    _pcat = kreis_df.set_index("ARS_kreis")[[c for c in cat_cols if c in kreis_df.columns]]
    _psum = _pcat.fillna(0.0).sum(axis=1)
    max_total_rescale = 0.0
    gem[total_col] = gem[total_col].fillna(0.0)
    n_degenerate = 0
    for kreis_key, grp_idx in gem.groupby("_kreis_key").groups.items():
        if kreis_key not in _psum.index:
            continue
        psum = float(_psum.loc[kreis_key])
        tsum = float(gem.loc[grp_idx, total_col].sum())
        if psum > 0 and tsum > 0:
            scale = psum / tsum
            max_total_rescale = max(max_total_rescale, abs(scale - 1.0))
            gem.loc[grp_idx, total_col] = gem.loc[grp_idx, total_col] * scale
        elif psum > 0:
            # degenerate: parent mass but zero child signal (e.g. the Kreis value of
            # this category's own total was suppressed, so no remainder was allocated)
            # -> equal split, mirroring make_child_totals_adj's degenerate case.
            n_degenerate += 1
            gem.loc[grp_idx, total_col] = psum / len(grp_idx)
        else:
            gem.loc[grp_idx, total_col] = 0.0
    if n_degenerate:
        print(f"[gemeinde-controls][{table_name}] degenerate Kreise (parent>0, no child "
              f"signal -> equal split): {n_degenerate}")
    print(f"[gemeinde-controls][{table_name}] child-total rescale onto parent mass: "
          f"max |scale-1| = {max_total_rescale:.2e}")

    # Build parent (Kreis) frame for downscale_topic
    # parent_cat_cols = cat_cols (same names used at Kreis level)
    parent_for_ds = kreis_df[["ARS_kreis"] + [c for c in cat_cols if c in kreis_df.columns]].copy()
    parent_for_ds = parent_for_ds.rename(columns={"ARS_kreis": "_kreis_key"})

    # Ensure all cat_cols exist in parent
    for col in cat_cols:
        if col not in parent_for_ds.columns:
            parent_for_ds[col] = 0.0

    # Downscale spec: parent_cat_cols == child_cat_cols (same column names, different rows)
    spec = TopicSpec(
        name=table_name,
        parent_cat_cols=cat_cols,
        child_cat_cols=cat_cols,
        child_row_total_col=total_col,
        alpha=alpha,
        blend=BLEND_STD,
    )

    # Run downscale_topic
    out_cats = downscale_topic(
        parent_df=parent_for_ds,
        child_df=gem,
        parent_id_col="_kreis_key",
        child_parent_id_col="_kreis_key",
        spec=spec,
    )

    # Write filled category columns back
    gem[cat_cols] = out_cats[cat_cols].values

    # Final rake: ensure Σ(Gemeinden) == Kreis per category (< 0.5 abs)
    max_abs_diff = 0.0
    for kreis_key, grp_idx in gem.groupby("_kreis_key").groups.items():
        if kreis_key not in kreis_lookup.index:
            continue
        for col in cat_cols:
            if col not in kreis_lookup.columns:
                continue
            kreis_val = float(kreis_lookup.loc[kreis_key, col])
            child_sum = float(gem.loc[grp_idx, col].sum())
            diff = abs(child_sum - kreis_val)
            if diff > max_abs_diff:
                max_abs_diff = diff
            if diff >= 0.5:
                # Should not happen after IPF, but rake explicitly if needed
                if child_sum > 0:
                    gem.loc[grp_idx, col] = gem.loc[grp_idx, col] * (kreis_val / child_sum)

    # Add is_estimated flag
    gem["is_estimated"] = is_estimated_mask

    # Log honest summary
    n_estimated = int(is_estimated_mask.sum())
    n_total = len(gem)
    est_pop = float(ewz.reindex(gem.loc[is_estimated_mask, "ARS"]).fillna(0.0).sum())
    total_pop = float(ewz.reindex(gem["ARS"]).fillna(0.0).sum())
    pop_share = 100.0 * est_pop / max(total_pop, 1.0)
    print(
        f"[gemeinde-controls][{table_name}] estimated Gemeinden: "
        f"{n_estimated:,}/{n_total:,} | pop share: {pop_share:.1f}% | "
        f"max sum-vs-Kreis abs diff: {max_abs_diff:.4f}"
    )

    # Drop helper column
    gem = gem.drop(columns=["_kreis_key"])
    return gem


def run_gemeinde_controls(cfg, *, fill: str = "none") -> None:
    """Parse Regionaltabellen and write one parquet per table.

    Output directory: cfg.outputs_dir / "gemeinde_controls"/
    Files: erwerbsstatus.parquet, schulabschluss.parquet, berufl_abschluss.parquet
           kreis_erwerbsstatus.parquet, kreis_schulabschluss.parquet,
           kreis_berufl_abschluss.parquet

    The xlsx_path is resolved as:
    1. cfg.regionaltabellen_xlsx if set (explicit TOML override)
    2. data/raw/regionaltabellen/Regionaltabelle_Bildung_Erwerbstaetigkeit.xlsx
       (sibling of inputs_dir)

    Args:
        cfg: Config instance (cleancensus.config.Config).
        fill: "none" (default) — Gemeinde parquets keep NaN for suppressed cells.
              "harmonize" — fill suppressed cells using Kreis-level harmonization.
    """
    if fill not in ("none", "harmonize"):
        raise ValueError(f"[gemeinde-controls] fill must be 'none' or 'harmonize', got {fill!r}")

    # Resolve path
    xlsx_path = getattr(cfg, "regionaltabellen_xlsx", None)
    if xlsx_path is None:
        xlsx_path = (
            cfg.inputs_dir.parent / "raw" / "regionaltabellen"
            / "Regionaltabelle_Bildung_Erwerbstaetigkeit.xlsx"
        )
    xlsx_path = Path(xlsx_path)
    if not xlsx_path.exists():
        raise FileNotFoundError(
            f"[gemeinde-controls] Regionaltabelle not found at {xlsx_path}. "
            "Download from the Zensus 2022 portal and place it under "
            "data/raw/regionaltabellen/ (or set regionaltabellen_xlsx in your config)."
        )

    out_dir = cfg.outputs_dir / "gemeinde_controls"
    out_dir.mkdir(parents=True, exist_ok=True)

    # --- Parse Gemeinde tables ---
    tables = build_gemeinde_controls(xlsx_path)

    # --- Parse Kreis tables (always written) ---
    kreis_tables = build_kreis_controls(xlsx_path)

    # Write Kreis tables
    for name, df in kreis_tables.items():
        out_path = out_dir / f"kreis_{name}.parquet"
        df.to_parquet(out_path, index=False)
        data_cols = [c for c in df.columns if c not in ("ARS_kreis", "Name")]
        nan_count = int(df[data_cols].isna().sum().sum())
        n_cells = len(df) * len(data_cols)
        print(
            f"[gemeinde-controls] kreis_{name}: "
            f"{len(df):,} Kreise | suppressed {nan_count}/{n_cells} "
            f"({100.0 * nan_count / max(n_cells, 1):.1f}%) | "
            f"wrote {out_path}"
        )

    # --- Optional fill ---
    ewz: pd.Series | None = None
    if fill == "harmonize":
        bev_path = (
            cfg.inputs_dir.parent / "raw" / "regionaltabellen"
            / "Regionaltabelle_Bevoelkerung.xlsx"
        )
        bev_path = Path(bev_path)
        if not bev_path.exists():
            raise FileNotFoundError(
                f"[gemeinde-controls] Bevoelkerung file not found at {bev_path}. "
                "Required for fill=harmonize. Download from Zensus 2022 portal."
            )
        print(f"[gemeinde-controls] loading Gemeinde population from {bev_path.name} ...")
        ewz = _load_gemeinde_population(bev_path)

    # Table-specific metadata: list of (total_col, [cat_cols]) flat-partition groups.
    # Each group must be a flat non-overlapping partition: sum(cat_cols) == total_col.
    # downscale_topic requires sum(child row totals) == sum(parent cat_cols).
    # Multiple groups per table handle the hierarchical/gender sub-partitions independently.
    #
    # Erwerbsstatus flat partitions:
    #   total = ET + EL + NEP               (main)
    #   total = EP + NEP                    (coarser — redundant, skip)
    #   total = M + W                       (gender)
    #   EP    = ET_M + ET_W (skip fine-grained; gender of subtotals handled via gender group)
    # => We fill: (total, [ET, EL, NEP]), (total, [M, W]), (EP, [EP_M, EP_W]),
    #             (ET, [ET_M, ET_W]), (EL, [EL_M, EL_W]), (NEP, [NEP_M, NEP_W])
    #
    # Schulabschluss: total = __1 + __2 + __3; __2 = __21 + __22 + __23 + __24
    # Berufl_Abschluss: total = __1 + __2; __1 = __11+__12+__13+__14+__15+__16+__17
    _TABLE_PARTITION_GROUPS: dict[str, list[tuple[str, list[str]]]] = {
        "erwerbsstatus": [
            # Main coarse partition: ET + EL + NEP = total
            ("ERWERBSTAT_KURZ_STP",
             ["ERWERBSTAT_KURZ_STP__11", "ERWERBSTAT_KURZ_STP__12", "ERWERBSTAT_KURZ_STP__2"]),
            # Gender: M + W = total
            ("ERWERBSTAT_KURZ_STP",
             ["ERWERBSTAT_KURZ_STP__M", "ERWERBSTAT_KURZ_STP__W"]),
            # EP + NEP = total
            ("ERWERBSTAT_KURZ_STP",
             ["ERWERBSTAT_KURZ_STP__1", "ERWERBSTAT_KURZ_STP__2"]),
            # Gender sub-partitions (within sub-totals)
            ("ERWERBSTAT_KURZ_STP__1",
             ["ERWERBSTAT_KURZ_STP__1_M", "ERWERBSTAT_KURZ_STP__1_W"]),
            ("ERWERBSTAT_KURZ_STP__11",
             ["ERWERBSTAT_KURZ_STP__11_M", "ERWERBSTAT_KURZ_STP__11_W"]),
            ("ERWERBSTAT_KURZ_STP__12",
             ["ERWERBSTAT_KURZ_STP__12_M", "ERWERBSTAT_KURZ_STP__12_W"]),
            ("ERWERBSTAT_KURZ_STP__2",
             ["ERWERBSTAT_KURZ_STP__2_M", "ERWERBSTAT_KURZ_STP__2_W"]),
        ],
        "schulabschluss": [
            # Main partition: InAusb + MitAbschluss + OhneAbschluss = total
            ("SCHULABS_STP",
             ["SCHULABS_STP__1", "SCHULABS_STP__2", "SCHULABS_STP__3"]),
            # Gender: M + W = total
            ("SCHULABS_STP",
             ["SCHULABS_STP__M", "SCHULABS_STP__W"]),
            # Sub-partition within MitAbschluss: Haupt + POS + Real + Abitur = __2
            ("SCHULABS_STP__2",
             ["SCHULABS_STP__21", "SCHULABS_STP__22", "SCHULABS_STP__23", "SCHULABS_STP__24"]),
            # Gender within sub-groups
            ("SCHULABS_STP__1",
             ["SCHULABS_STP__1_M", "SCHULABS_STP__1_W"]),
            ("SCHULABS_STP__2",
             ["SCHULABS_STP__2_M", "SCHULABS_STP__2_W"]),
            ("SCHULABS_STP__21",
             ["SCHULABS_STP__21_M", "SCHULABS_STP__21_W"]),
            ("SCHULABS_STP__22",
             ["SCHULABS_STP__22_M", "SCHULABS_STP__22_W"]),
            ("SCHULABS_STP__23",
             ["SCHULABS_STP__23_M", "SCHULABS_STP__23_W"]),
            ("SCHULABS_STP__24",
             ["SCHULABS_STP__24_M", "SCHULABS_STP__24_W"]),
            ("SCHULABS_STP__3",
             ["SCHULABS_STP__3_M", "SCHULABS_STP__3_W"]),
        ],
        "berufl_abschluss": [
            # Main partition: MitBerufsabs + OhneBerufsabs = total (0 Kreis NaN)
            ("BERUFABS_AUSF_STP",
             ["BERUFABS_AUSF_STP__1", "BERUFABS_AUSF_STP__2"]),
            # Gender: M + W = total
            ("BERUFABS_AUSF_STP",
             ["BERUFABS_AUSF_STP__M", "BERUFABS_AUSF_STP__W"]),
            # Sub-partition within MitBerufsabs (leaf cats, may have Kreis NaN for __13)
            ("BERUFABS_AUSF_STP__1",
             ["BERUFABS_AUSF_STP__11", "BERUFABS_AUSF_STP__12", "BERUFABS_AUSF_STP__13",
              "BERUFABS_AUSF_STP__14", "BERUFABS_AUSF_STP__15", "BERUFABS_AUSF_STP__16",
              "BERUFABS_AUSF_STP__17"]),
            # Gender within sub-groups
            ("BERUFABS_AUSF_STP__1",
             ["BERUFABS_AUSF_STP__1_M", "BERUFABS_AUSF_STP__1_W"]),
            ("BERUFABS_AUSF_STP__11",
             ["BERUFABS_AUSF_STP__11_M", "BERUFABS_AUSF_STP__11_W"]),
            ("BERUFABS_AUSF_STP__12",
             ["BERUFABS_AUSF_STP__12_M", "BERUFABS_AUSF_STP__12_W"]),
            ("BERUFABS_AUSF_STP__13",
             ["BERUFABS_AUSF_STP__13_M", "BERUFABS_AUSF_STP__13_W"]),
            ("BERUFABS_AUSF_STP__14",
             ["BERUFABS_AUSF_STP__14_M", "BERUFABS_AUSF_STP__14_W"]),
            ("BERUFABS_AUSF_STP__15",
             ["BERUFABS_AUSF_STP__15_M", "BERUFABS_AUSF_STP__15_W"]),
            ("BERUFABS_AUSF_STP__16",
             ["BERUFABS_AUSF_STP__16_M", "BERUFABS_AUSF_STP__16_W"]),
            ("BERUFABS_AUSF_STP__17",
             ["BERUFABS_AUSF_STP__17_M", "BERUFABS_AUSF_STP__17_W"]),
            ("BERUFABS_AUSF_STP__2",
             ["BERUFABS_AUSF_STP__2_M", "BERUFABS_AUSF_STP__2_W"]),
        ],
    }

    for name, df in tables.items():
        if fill == "harmonize" and ewz is not None:
            partition_groups = _TABLE_PARTITION_GROUPS.get(name, [])
            # Pass 1: fill the first (main coarse) group — this establishes is_estimated.
            # Subsequent passes use the filled values as new row totals.
            is_estimated_col: "pd.Series | None" = None
            for i, (total_col, cat_cols) in enumerate(partition_groups):
                actual_cat_cols = [c for c in cat_cols if c in df.columns]
                if not actual_cat_cols or total_col not in df.columns:
                    continue
                # For passes after the first, also filter Kreis parent to only rows with
                # non-NaN in all cat_cols (avoid passing NaN Kreis cats to downscale_topic).
                kreis_sub = kreis_tables[name].copy()
                # Drop Kreis rows where any of the cat_cols is NaN (e.g. __13 in West Kreise)
                kreis_sub = kreis_sub.dropna(subset=[c for c in actual_cat_cols if c in kreis_sub.columns])
                if kreis_sub.empty:
                    continue
                filled = fill_gemeinde_harmonize(
                    df,
                    kreis_sub,
                    table_name=f"{name}[{i}]",
                    total_col=total_col,
                    cat_cols=actual_cat_cols,
                    ewz=ewz,
                )
                # Merge filled columns back into df
                for col in actual_cat_cols:
                    if col in filled.columns:
                        df[col] = filled[col].values
                # Also update total_col if it was filled (for sub-partition row totals)
                df[total_col] = filled[total_col].values
                # Capture is_estimated from the FIRST partition group
                if i == 0 and "is_estimated" in filled.columns:
                    is_estimated_col = filled["is_estimated"]
            # Re-attach is_estimated from first group
            if is_estimated_col is not None:
                df["is_estimated"] = is_estimated_col.values

        out_path = out_dir / f"{name}.parquet"
        df.to_parquet(out_path, index=False)
        gem_count = len(df)
        data_cols = [c for c in df.columns if c not in ("ARS", "Name", "is_estimated")]
        total_vals = gem_count * len(data_cols)
        supp = int(df[data_cols].isna().sum().sum())
        supp_pct = 100.0 * supp / max(total_vals, 1)

        # National sum from total column (first data col)
        total_col = data_cols[0]
        nat_sum = float(df[total_col].sum(skipna=True))

        print(
            f"[gemeinde-controls] {name}: "
            f"{gem_count:,} Gemeinden | "
            f"suppressed {supp:,}/{total_vals:,} ({supp_pct:.1f}%) | "
            f"national sum ({total_col}) = {nat_sum:,.0f}"
        )
        print(f"[gemeinde-controls] wrote {out_path}")
