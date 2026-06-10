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

# Default path for the RegioStaR reference file (BBSR Referenzdatei 2020).
# Override via config key ``regiostar_ref`` (not yet wired into the TOML
# schema but respected if present on cfg as an attribute or in cfg.stages).
_DEFAULT_REGIOSTAR_REF = (
    Path(__file__).parent.parent  # repo root
    / "data" / "inputs" / "regiostar_referenzdatei.xlsx"
)
# Fallback to the eqasim-bs copy that is known to exist on this machine:
_FALLBACK_REGIOSTAR_REF = (
    Path.home()
    / "Documents" / "GitHub" / "eqasim-bs"
    / "eqasim-data" / "data" / "regiostar"
    / "regiostar_referenzdatei.xlsx"
)

REGIOSTAR_SHEET = "ReferenzGebietsstand2020"


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
    1. ``regiostar_ref`` attribute on cfg (if someone adds it later).
    2. Default path in the repo's data/inputs directory.
    3. Fallback to the known eqasim-bs copy.
    """
    # Allow future config extension
    ref_attr = getattr(cfg, "regiostar_ref", None)
    if ref_attr is not None:
        p = Path(ref_attr)
        if p.exists():
            return p
        raise FileNotFoundError(
            f"[regiostar] regiostar_ref path does not exist: {p}"
        )

    if _DEFAULT_REGIOSTAR_REF.exists():
        return _DEFAULT_REGIOSTAR_REF

    if _FALLBACK_REGIOSTAR_REF.exists():
        log.info(
            "[regiostar] using fallback RegioStaR reference: %s",
            _FALLBACK_REGIOSTAR_REF,
        )
        return _FALLBACK_REGIOSTAR_REF

    raise FileNotFoundError(
        f"[regiostar] RegioStaR reference file not found.\n"
        f"  Tried: {_DEFAULT_REGIOSTAR_REF}\n"
        f"         {_FALLBACK_REGIOSTAR_REF}\n"
        f"  Place regiostar_referenzdatei.xlsx (BBSR ReferenzGebietsstand2020) in\n"
        f"  data/inputs/ or set cfg.regiostar_ref to its path."
    )


def _load_regiostar_ref(ref_path: Path) -> pd.DataFrame:
    """Load the RegioStaR reference table keyed on 8-digit AGS (commune_id).

    Returns a DataFrame with columns [commune_id, RegioStaR2, RegioStaR4,
    RegioStaR17, RegioStaR7, RegioStaR5, RegioStaRGem7, RegioStaRGem5].

    The source sheet is ReferenzGebietsstand2020 (Gebietsstand 2020 matches the
    ARS structure used in Zensus 2022 cells).
    """
    print(f"[regiostar] loading reference from {ref_path} (sheet={REGIOSTAR_SHEET!r}) ...")
    raw = pd.read_excel(ref_path, sheet_name=REGIOSTAR_SHEET, engine="openpyxl")

    # commune_id: gem_20 zero-padded to 8 digits
    raw["commune_id"] = raw["gem_20"].astype("Int64").astype(str).str.zfill(8)

    keep = ["commune_id"] + REGIOSTAR_COLS
    ref = raw[keep].copy()

    # Cast RegioStaR columns to float64 (they're integers in the ref but stored
    # as float in the target parquet to accommodate NaN for unmatched cells)
    for col in REGIOSTAR_COLS:
        ref[col] = pd.to_numeric(ref[col], errors="coerce")

    print(f"[regiostar] reference loaded: {len(ref):,} Gemeinden")
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
    ref = _load_regiostar_ref(ref_path)

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
