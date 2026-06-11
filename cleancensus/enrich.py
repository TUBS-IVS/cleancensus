"""Enrichment stages for the cleancensus pipeline (R6).

Implements two post-gender stages:

  aggs      — derive decade-binned gendered age aggregates + totals from the
              single-year M_AGE_*/F_AGE_* columns produced by the gender stage.
  regiostar — join the BBSR RegioStaR 2022 municipality classification onto
              100m cells via the RegionalSchlüssel_ARS key.

Both stages are config-driven (like cleancensus/stages.py) and append the
derived columns to the predecessor work-dir parquet file rather than recomputing
the full table.

Reconstruction note
-------------------
Neither stage's original creation code exists in any archived notebook.  The
logic below was reconstructed from the column names and values present in
``data/inputs/cells_100m_with_gender_backf_binneds_happyorphans_with_aggs_regiostar.parquet``
and verified against that file (local equivalence gate):

  * agg columns: exact zero difference for gendered bins; float-precision noise
    (~1e-7) for the undifferentiated AGE_*_agg (M+F summation).
  * M_TOTAL / F_TOTAL: float noise < 2e-5 (sum of 101 single-year floats).
  * RegioStaR columns: 100 % match rate against ReferenzGebietsstand2020 from
    regiostar_referenzdatei.xlsx (joined via 8-digit AGS derived from ARS).
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Sequence

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from cleancensus.config import Config

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module constants — auditable bin spec
# ---------------------------------------------------------------------------

# Decade bins: (label, lo_inclusive, hi_inclusive)
# The last bin captures ages 80-100 (all remaining single-year columns).
AGE_BINS: tuple[tuple[str, int, int], ...] = (
    ("0_9",    0,   9),
    ("10_19", 10,  19),
    ("20_29", 20,  29),
    ("30_39", 30,  39),
    ("40_49", 40,  49),
    ("50_59", 50,  59),
    ("60_69", 60,  69),
    ("70_79", 70,  79),
    ("80_plus", 80, 100),
)

# Age range covered (single-year columns AGE_0 .. AGE_TOP for M and F)
AGE_TOP = 100

# Column names produced by run_aggs
GENDERED_AGG_COLS = (
    [f"M_AGE_{label}_agg" for label, _, _ in AGE_BINS]
    + [f"F_AGE_{label}_agg" for label, _, _ in AGE_BINS]
)
UNDIFF_AGG_COLS = [f"AGE_{label}_agg" for label, _, _ in AGE_BINS]
TOTAL_COLS = ["M_TOTAL", "F_TOTAL"]

ALL_AGG_OUTPUT_COLS = GENDERED_AGG_COLS + UNDIFF_AGG_COLS + TOTAL_COLS

# RegioStaR output columns (in the order they appear in the reference file)
REGIOSTAR_COLS = [
    "RegioStaR2",
    "RegioStaR4",
    "RegioStaR17",
    "RegioStaR7",
    "RegioStaR5",
    "RegioStaRGem7",
    "RegioStaRGem5",
]

# Primary: BBSR Referenz Gemeinden Gebietsstand 31.12.2022 (downloaded to data/raw/regiostar/).
# This is the correct Gebietsstand for Zensus 2022 ARS.
_DEFAULT_REGIOSTAR_REF = (
    Path(__file__).parent.parent  # repo root
    / "data" / "raw" / "regiostar" / "bbsr-referenz-gebietsstand-2022.xlsx"
)
# Fallback A: old BMDV Gebietsstand2020 file in data/inputs/ (legacy location):
_FALLBACK_REGIOSTAR_REF_A = (
    Path(__file__).parent.parent
    / "data" / "inputs" / "regiostar_referenzdatei.xlsx"
)
# Fallback B: the eqasim-bs copy (Gebietsstand 2020, known to exist on this machine):
_FALLBACK_REGIOSTAR_REF_B = (
    Path.home()
    / "Documents" / "GitHub" / "eqasim-bs"
    / "eqasim-data" / "data" / "regiostar"
    / "regiostar_referenzdatei.xlsx"
)

# Sheet name for the BBSR 2022 Gemeindereferenz:
REGIOSTAR_SHEET_BBSR2022 = "Gemeindereferenz (inkl. Kreise)"
# Sheet name for the legacy BMDV Gebietsstand2020 file:
REGIOSTAR_SHEET = "ReferenzGebietsstand2020"

# Column mapping: BBSR 2022 Gemeindereferenz -> our canonical RegioStaR output columns.
# RegioStaR4 is derived from RSS2022 (RegioStaR17) via integer floor-division by 10.
# RegioStaR5 and RegioStaRGem7 are NOT present in the BBSR 2022 Gemeindereferenz sheet
# (they appear in the BMDV 2020 file only); cells will receive NaN for these two columns
# when loading the BBSR 2022 reference.
_BBSR2022_COL_MAP: dict[str, str] = {
    "RS22022": "RegioStaR2",
    "RSS2022": "RegioStaR17",   # RegioStaR4 = RSS2022 // 10, derived below
    "RS72022": "RegioStaR7",
    "RS52022": "RegioStaRGem5",
}


# ---------------------------------------------------------------------------
# Helper: ARS -> 8-digit AGS (join key for RegioStaR table)
# ---------------------------------------------------------------------------

def _ars_to_ags8(ars: str) -> str:
    """Convert a 12-digit ARS to the 8-digit AGS used by the RegioStaR table.

    ARS layout (12 chars): LL RR KKK VV GGG
      LL  = 2-digit Bundesland
      RR  = 1-digit Regierungsbezirk (padded to 2)  <- actually 1 char in Zensus
      KKK = 2-digit Kreis (padded from 3)
      VV  = 2-digit Verbandsgemeinde part 1
      GGG = 3-digit Gemeinde

    8-digit AGS = ARS[0:5] + ARS[9:12]  (strips the 4-char Verbandsgemeinde block).
    An 8-digit input is returned unchanged (idempotent).

    Logic matches eqasim-bs/braunschweig/data/bbsr/regiostar.py::ars_to_ags8.
    """
    s = str(ars)
    if len(s) == 12:
        return s[0:5] + s[9:12]
    return s


# ---------------------------------------------------------------------------
# Work-dir file name contract (mirrors topics8.py / pipeline.py naming)
# ---------------------------------------------------------------------------

def _aggs_input(cfg: Config) -> Path:
    """The predecessor parquet that run_aggs reads (output of the gender stage)."""
    return cfg.work_dir / "cells_100m_with_gender_backf_binneds_happyorphans.parquet"


def _aggs_output(cfg: Config) -> Path:
    return cfg.work_dir / "cells_100m_with_gender_backf_binneds_happyorphans_with_aggs.parquet"


def _regiostar_input(cfg: Config) -> Path:
    """The predecessor parquet that run_regiostar reads (output of the aggs stage)."""
    return _aggs_output(cfg)


def _regiostar_output(cfg: Config) -> Path:
    return cfg.work_dir / "cells_100m_with_gender_backf_binneds_happyorphans_with_aggs_regiostar.parquet"


# ---------------------------------------------------------------------------
# run_aggs
# ---------------------------------------------------------------------------

def _compute_aggs(df: pd.DataFrame) -> pd.DataFrame:
    """Given a DataFrame with M_AGE_0..M_AGE_100 and F_AGE_0..F_AGE_100 columns,
    return a DataFrame with only the derived aggregate columns (same index).

    Also computes the undifferentiated AGE_*_agg columns as M+F sums.
    """
    out: dict[str, pd.Series] = {}

    for label, lo, hi in AGE_BINS:
        m_src = [f"M_AGE_{i}" for i in range(lo, hi + 1)]
        f_src = [f"F_AGE_{i}" for i in range(lo, hi + 1)]
        m_sum = df[m_src].sum(axis=1)
        f_sum = df[f_src].sum(axis=1)
        out[f"M_AGE_{label}_agg"] = m_sum
        out[f"F_AGE_{label}_agg"] = f_sum
        out[f"AGE_{label}_agg"]   = m_sum + f_sum

    out["M_TOTAL"] = df[[f"M_AGE_{i}" for i in range(AGE_TOP + 1)]].sum(axis=1)
    out["F_TOTAL"] = df[[f"F_AGE_{i}" for i in range(AGE_TOP + 1)]].sum(axis=1)

    return pd.DataFrame(out, index=df.index)


def run_aggs(cfg: Config) -> None:
    """Aggs stage: bin single-year gendered ages into decade aggregates.

    Reads the gender-stage output (work_dir predecessor), appends the agg
    columns, and writes the next work_dir file.  For the national 7.7 GB file
    the data is processed in streaming batches to stay within memory.
    """
    in_path  = _aggs_input(cfg)
    out_path = _aggs_output(cfg)
    cfg.work_dir.mkdir(parents=True, exist_ok=True)

    print(f"[aggs] reading {in_path} ...")
    pf = pq.ParquetFile(in_path)

    # Build the required source columns list
    m_src_all = [f"M_AGE_{i}" for i in range(AGE_TOP + 1)]
    f_src_all = [f"F_AGE_{i}" for i in range(AGE_TOP + 1)]
    src_cols   = m_src_all + f_src_all

    # Validate that source columns exist
    schema_names = set(pf.schema_arrow.names)
    missing = [c for c in src_cols if c not in schema_names]
    if missing:
        raise ValueError(
            f"[aggs] source columns missing from {in_path}: {missing[:10]}..."
        )

    n_rows = pf.metadata.num_rows
    print(f"[aggs] {n_rows:,} rows, computing decade bins ...")

    writer: pq.ParquetWriter | None = None
    rows_written = 0

    # Adaptive batch size: ~500k rows for national, all-at-once for small files
    batch_size = 500_000 if n_rows > 2_000_000 else n_rows

    for batch in pf.iter_batches(batch_size=batch_size):
        tbl = pa.Table.from_batches([batch])
        df  = tbl.to_pandas()

        aggs_df = _compute_aggs(df)

        # Append agg columns to the existing table
        for col in aggs_df.columns:
            arr = pa.array(aggs_df[col].to_numpy(dtype="float64"))
            tbl = tbl.append_column(col, arr)

        if writer is None:
            writer = pq.ParquetWriter(out_path, tbl.schema, compression="snappy")
        writer.write_table(tbl)
        rows_written += len(tbl)

    if writer is not None:
        writer.close()

    print(f"[aggs] wrote {rows_written:,} rows -> {out_path}")
    print(f"[aggs] new columns: {ALL_AGG_OUTPUT_COLS}")


# ---------------------------------------------------------------------------
# run_regiostar
# ---------------------------------------------------------------------------

def _find_regiostar_ref(cfg: Config) -> Path:
    """Locate the RegioStaR reference XLSX.

    Priority:
    1. ``regiostar_ref`` on cfg (set via TOML key [data].regiostar_ref).
    2. BBSR Referenz Gemeinden Gebietsstand 31.12.2022 in data/raw/regiostar/.
    3. Legacy BMDV Gebietsstand2020 file in data/inputs/ (warn if used).
    4. Legacy BMDV Gebietsstand2020 file in eqasim-bs copy (warn if used).
    """
    # Explicit TOML override
    ref_attr = getattr(cfg, "regiostar_ref", None)
    if ref_attr is not None:
        p = Path(ref_attr)
        if p.exists():
            return p
        raise FileNotFoundError(
            f"[regiostar] regiostar_ref path does not exist: {p}"
        )

    # Primary: BBSR 2022
    if _DEFAULT_REGIOSTAR_REF.exists():
        return _DEFAULT_REGIOSTAR_REF

    # Fallback A: BMDV 2020 in data/inputs/
    if _FALLBACK_REGIOSTAR_REF_A.exists():
        log.warning(
            "[regiostar] BBSR 2022 ref not found at %s; falling back to "
            "Gebietsstand2020 reference at %s. "
            "Download bbsr-referenz-gebietsstand-2022.xlsx to data/raw/regiostar/ "
            "for the correct Zensus 2022 ARS alignment.",
            _DEFAULT_REGIOSTAR_REF,
            _FALLBACK_REGIOSTAR_REF_A,
        )
        return _FALLBACK_REGIOSTAR_REF_A

    # Fallback B: eqasim-bs copy
    if _FALLBACK_REGIOSTAR_REF_B.exists():
        log.warning(
            "[regiostar] BBSR 2022 ref not found; falling back to eqasim-bs "
            "Gebietsstand2020 reference at %s.",
            _FALLBACK_REGIOSTAR_REF_B,
        )
        return _FALLBACK_REGIOSTAR_REF_B

    raise FileNotFoundError(
        f"[regiostar] RegioStaR reference file not found.\n"
        f"  Primary  : {_DEFAULT_REGIOSTAR_REF}\n"
        f"  Fallback A: {_FALLBACK_REGIOSTAR_REF_A}\n"
        f"  Fallback B: {_FALLBACK_REGIOSTAR_REF_B}\n"
        f"  Download BBSR Referenz Gemeinden Gebietsstand 31.12.2022 from\n"
        f"  https://www.bbsr.bund.de/ and place it at data/raw/regiostar/"
        f"bbsr-referenz-gebietsstand-2022.xlsx,\n"
        f"  or set [data].regiostar_ref in your config.toml."
    )


def _is_bbsr2022_format(raw: pd.DataFrame) -> bool:
    """Return True if ``raw`` looks like the BBSR 2022 Gemeindereferenz sheet."""
    return "GEM2022" in raw.columns and "RS22022" in raw.columns


def _normalize_bbsr2022(raw: pd.DataFrame) -> pd.DataFrame:
    """Map BBSR 2022 Gemeindereferenz columns to our canonical REGIOSTAR_COLS.

    Column mapping (BBSR 2022 -> canonical):
      GEM2022   -> commune_id (8-digit AGS, zero-padded)
      RS22022   -> RegioStaR2
      RSS2022   -> RegioStaR17
      RSS2022//10 -> RegioStaR4  (derived; 100% match verified against BMDV2020)
      RS72022   -> RegioStaR7
      RS52022   -> RegioStaRGem5

    NOT available in BBSR 2022 Gemeindereferenz (set to NaN):
      RegioStaR5  (Stadtregion 5-type, only in BMDV2020 file)
      RegioStaRGem7 (Gemeinde 7-type, only in BMDV2020 file)
    """
    # Skip the description row (row 0 has long German descriptions as values)
    if raw.iloc[0].astype(str).str.contains("Kennziffer|Regionalschl").any():
        raw = raw.iloc[1:].reset_index(drop=True)

    ref = pd.DataFrame()
    ref["commune_id"] = raw["GEM2022"].astype("Int64").astype(str).str.zfill(8)
    ref["RegioStaR2"]  = pd.to_numeric(raw["RS22022"], errors="coerce")
    ref["RegioStaR17"] = pd.to_numeric(raw["RSS2022"], errors="coerce")
    ref["RegioStaR4"]  = (ref["RegioStaR17"] // 10).astype("float64")
    ref["RegioStaR7"]  = pd.to_numeric(raw["RS72022"], errors="coerce")
    ref["RegioStaRGem5"] = pd.to_numeric(raw["RS52022"], errors="coerce")
    # Not available in BBSR 2022 Gemeindereferenz:
    ref["RegioStaR5"]   = np.nan
    ref["RegioStaRGem7"] = np.nan
    return ref


def _normalize_bmdv2020(raw: pd.DataFrame) -> pd.DataFrame:
    """Map the legacy BMDV Gebietsstand2020 columns to our canonical REGIOSTAR_COLS."""
    # Skip the description row if present
    if "gem_20" not in raw.columns and raw.iloc[0].astype(str).str.contains("Gemeinde").any():
        raw = raw.iloc[1:].reset_index(drop=True)

    ref = pd.DataFrame()
    ref["commune_id"] = raw["gem_20"].astype("Int64").astype(str).str.zfill(8)
    for col in REGIOSTAR_COLS:
        ref[col] = pd.to_numeric(raw[col], errors="coerce")
    return ref


def _load_regiostar_ref(ref_path: Path, sheet: str = "") -> pd.DataFrame:
    """Load the RegioStaR reference table keyed on 8-digit AGS (commune_id).

    Returns a DataFrame with columns [commune_id] + REGIOSTAR_COLS.

    Supports two formats:
    - BBSR Gemeindereferenz 31.12.2022 (sheet 'Gemeindereferenz (inkl. Kreise)'):
        RS22022, RSS2022, RS72022, RS52022 columns;
        RegioStaR4 derived from RegioStaR17; RegioStaR5 and RegioStaRGem7 = NaN.
    - Legacy BMDV Gebietsstand2020 (sheet 'ReferenzGebietsstand2020'):
        gem_20 + direct RegioStaR* columns.

    The sheet is auto-detected if ``sheet`` is empty.
    """
    # Auto-detect sheet if not specified
    if not sheet:
        xl = pd.ExcelFile(ref_path, engine="openpyxl")
        sheets = xl.sheet_names
        xl.close()
        if REGIOSTAR_SHEET_BBSR2022 in sheets:
            sheet = REGIOSTAR_SHEET_BBSR2022
        elif REGIOSTAR_SHEET in sheets:
            sheet = REGIOSTAR_SHEET
        else:
            raise ValueError(
                f"[regiostar] Could not find a known RegioStaR sheet in {ref_path}. "
                f"Sheets found: {sheets}. "
                f"Expected one of {REGIOSTAR_SHEET_BBSR2022!r} or {REGIOSTAR_SHEET!r}."
            )

    print(
        f"[regiostar] loading reference from {ref_path.name} (sheet={sheet!r}) ..."
    )
    raw = pd.read_excel(ref_path, sheet_name=sheet, engine="openpyxl")

    if _is_bbsr2022_format(raw):
        ref = _normalize_bbsr2022(raw)
        n_rs5_nan = ref["RegioStaR5"].isna().sum()
        print(
            f"[regiostar] BBSR 2022 format detected: {len(ref):,} Gemeinden "
            f"(RegioStaR5 and RegioStaRGem7 not available in this sheet -> NaN)"
        )
    else:
        ref = _normalize_bmdv2020(raw)
        print(f"[regiostar] BMDV 2020 format: {len(ref):,} Gemeinden")

    return ref


def run_regiostar(cfg: Config) -> None:
    """RegioStaR stage: join the 7 RegioStaR columns onto 100m cells by AGS8.

    Reads the aggs-stage output, derives 8-digit AGS from the 12-digit ARS,
    joins the RegioStaR reference, and writes the final work_dir file.

    Cells with no municipality match (ARS is NULL, or ARS not in the reference)
    receive NaN for all RegioStaR columns — matching the null pattern in the
    canonical input file (~5 188 NaN rows out of 3 148 482).
    """
    in_path  = _regiostar_input(cfg)
    out_path = _regiostar_output(cfg)
    cfg.work_dir.mkdir(parents=True, exist_ok=True)

    ref_path = _find_regiostar_ref(cfg)
    sheet = getattr(cfg, "regiostar_sheet", "") or ""
    ref = _load_regiostar_ref(ref_path, sheet=sheet)

    # Build AGS8 -> RegioStaR* lookup dict (fast Series.map)
    lookup: dict[str, dict[str, float]] = {
        col: ref.set_index("commune_id")[col].to_dict()
        for col in REGIOSTAR_COLS
    }

    print(f"[regiostar] reading {in_path} ...")
    pf = pq.ParquetFile(in_path)
    n_rows = pf.metadata.num_rows

    ARS_COL = "RegionalSchlüssel_ARS"
    if ARS_COL not in set(pf.schema_arrow.names):
        raise ValueError(
            f"[regiostar] ARS column {ARS_COL!r} not found in {in_path}"
        )

    writer: pq.ParquetWriter | None = None
    rows_written  = 0
    total_matched = 0
    total_unmatched = 0

    batch_size = 500_000 if n_rows > 2_000_000 else n_rows

    for batch in pf.iter_batches(batch_size=batch_size):
        tbl = pa.Table.from_batches([batch])
        ars_col = tbl[ARS_COL].to_pylist()

        # Derive 8-digit AGS from ARS
        ags8_series = pd.Series(ars_col, dtype=object).apply(
            lambda x: _ars_to_ags8(x) if x is not None else None
        )

        for col in REGIOSTAR_COLS:
            mapped = ags8_series.map(lookup[col])  # NaN for no match
            arr = pa.array(mapped.to_numpy(dtype="float64"), type=pa.float64())
            tbl = tbl.append_column(col, arr)

        # Tally match rate (once per batch using first RegioStaR col)
        n_matched = int((~ags8_series.map(lookup[REGIOSTAR_COLS[0]]).isna()).sum())
        total_matched   += n_matched
        total_unmatched += len(ags8_series) - n_matched

        if writer is None:
            writer = pq.ParquetWriter(out_path, tbl.schema, compression="snappy")
        writer.write_table(tbl)
        rows_written += len(tbl)

    if writer is not None:
        writer.close()

    print(
        f"[regiostar] wrote {rows_written:,} rows -> {out_path}\n"
        f"[regiostar] matched={total_matched:,}  unmatched={total_unmatched:,} "
        f"(NaN for RegioStaR cols)"
    )


# ---------------------------------------------------------------------------
# is_complete predicates (used by pipeline.py)
# ---------------------------------------------------------------------------

def aggs_complete(cfg: Config) -> bool:
    """True if the aggs output file exists with at least one agg column."""
    out = _aggs_output(cfg)
    if not out.exists():
        return False
    names = set(pq.read_schema(out).names)
    return "M_AGE_0_9_agg" in names


def regiostar_complete(cfg: Config) -> bool:
    """True if the regiostar output file exists with at least one RegioStaR column."""
    out = _regiostar_output(cfg)
    if not out.exists():
        return False
    names = set(pq.read_schema(out).names)
    return "RegioStaR2" in names
