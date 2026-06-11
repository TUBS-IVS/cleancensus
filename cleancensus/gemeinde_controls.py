"""Parse Zensus Regionaltabellen (P2/P4) into Gemeinde-level control tables.

Source file: Regionaltabelle_Bildung_Erwerbstaetigkeit.xlsx
Three CSV-sheets are parsed:
  - CSV-Erwerbsstatus         -> erwerbsstatus.parquet
  - CSV-Hoechster_Schulabschluss -> schulabschluss.parquet
  - CSV-Hoechster_berufl_Abschluss -> berufl_abschluss.parquet

Each output table contains only Gemeinde-level rows (Regionalebene == 'Gemeinde'),
identified by 12-digit ARS key. Suppressed values ('/' in the source) become NaN.

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


def run_gemeinde_controls(cfg) -> None:
    """Parse Regionaltabellen and write one parquet per table.

    Output directory: cfg.outputs_dir / "gemeinde_controls"/
    Files: erwerbsstatus.parquet, schulabschluss.parquet, berufl_abschluss.parquet

    The xlsx_path is resolved as:
    1. cfg.regionaltabellen_xlsx if set (explicit TOML override)
    2. data/raw/regionaltabellen/Regionaltabelle_Bildung_Erwerbstaetigkeit.xlsx
       (sibling of inputs_dir)

    Args:
        cfg: Config instance (cleancensus.config.Config).
    """
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

    tables = build_gemeinde_controls(xlsx_path)

    for name, df in tables.items():
        out_path = out_dir / f"{name}.parquet"
        df.to_parquet(out_path, index=False)
        gem_count = len(df)
        data_cols = [c for c in df.columns if c not in ("ARS", "Name")]
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
