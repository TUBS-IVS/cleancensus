"""Gemeinde stage: join Gemeinde/Kreis/ARS attributes onto 100m cells.

Ported faithfully from notebooks_archive/gender.ipynb cell [4]:
  "Merge Gemeinde (and Kreis etc) info onto census 100m cells -> Parquet (streaming)"

The stage performs a spatial join of 100m cell centroids (EPSG:3035 LAEA) against
the German administrative-area polygons (EPSG:25832 UTM32N, reprojected), attaching
the ARS-derived columns (RegionalSchlüssel_ARS, Land, Regierungsbezirk, Kreis,
VerwaltungsgemeinschaftTeil1, VerwaltungsgemeinschaftTeil2, Gemeinde) to every cell.

Reference data
--------------
The Gemeinde geometry comes from the official BKG VG250 GeoPackage:
    vg250_01-01.utm32s.gpkg.ebenen/vg250_ebenen_0101/DE_VG250.gpkg
    Layer: v_vg250_gem
Available on T:\\petre\\UCFL\\Synthetic Population\\Zensus\\additional_data\\

The 12-digit Regionalschlüssel (ARS) in that layer uniquely identifies each
Gemeinde; it is decomposed into the 7 fixed-length sub-fields above.

Input
-----
    cfg.work_dir / "df100_with_single_years.parquet"   (ages stage output)

    Additionally requires:
        vg250_gpkg_path  : pathlib.Path to DE_VG250.gpkg  (cfg.vg250_gpkg_path or T: default)
        vg250_gpkg_layer : str, layer name (default "v_vg250_gem")

    These are parameterised via Config attributes (if present) or fall back to the
    T: path known to exist during development.

Output
------
    cfg.work_dir / "cells_100m_with_gemeinde.parquet"
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

import geopandas as gpd
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from tqdm import tqdm

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CELLS_ID_COL = "GITTER_ID_100m"
GEM_KEY_COL  = "Regionalschlüssel_ARS"   # column name in the VG250 layer
EPSG_POINTS  = 3035   # cell IDs are LAEA Europe (EPSG:3035)
EPSG_GEM     = 25832  # UTM32N (expected for the VG250 GeoPackage)

ARS_NEW_COLS = [
    "RegionalSchlüssel_ARS",
    "Land",
    "Regierungsbezirk",
    "Kreis",
    "VerwaltungsgemeinschaftTeil1",
    "VerwaltungsgemeinschaftTeil2",
    "Gemeinde",
]

FORCE_STRING_COLS = {
    "GITTER_ID_100m", "GITTER_ID_1km", "GITTER_ID_10km",
    "RegionalSchlüssel_ARS", "Land", "Regierungsbezirk", "Kreis",
    "VerwaltungsgemeinschaftTeil1", "VerwaltungsgemeinschaftTeil2", "Gemeinde",
}

CHUNK_SIZE = 1_000_000

# ---------------------------------------------------------------------------
# Helpers (ported directly from cell [4])
# ---------------------------------------------------------------------------


def _parse_centroids_3035(df: pd.DataFrame, id_col: str) -> gpd.GeoDataFrame:
    """From IDs like 'CRS3035RES100mN2689100E4337000' -> centroid points (+50, +50)."""
    ne = df[id_col].astype(str).str.extract(r"N(\d+)E(\d+)", expand=True)
    if ne.isna().any().any():
        bad = df.loc[ne.isna().any(axis=1), id_col].head(5).tolist()
        raise ValueError(f"Could not parse N/E from: {bad}")
    n = ne[0].astype(np.int64) + 50
    e = ne[1].astype(np.int64) + 50
    return gpd.GeoDataFrame(
        df[[id_col]].copy(),
        geometry=gpd.points_from_xy(e, n, crs=f"EPSG:{EPSG_POINTS}"),
    )


def _require_exact_12_digit_key(gem: gpd.GeoDataFrame) -> str:
    """Validate Gemeinde key column: exactly 12 numeric digits."""
    if GEM_KEY_COL not in gem.columns:
        raise KeyError(f"Missing '{GEM_KEY_COL}' on Gemeinde layer.")
    s = gem[GEM_KEY_COL].astype(str)
    ok = s.str.fullmatch(r"\d{12}")
    if not ok.all():
        bad = gem.loc[~ok, [GEM_KEY_COL]].head(5)
        raise ValueError(
            f"Gemeinde key '{GEM_KEY_COL}' must be exactly 12 digits.\n{bad}"
        )
    return GEM_KEY_COL


def _add_ars_parts(gem: gpd.GeoDataFrame, key_col: str) -> gpd.GeoDataFrame:
    """Derive fixed-length sub-fields from the validated 12-digit ARS."""
    ars = gem[key_col].astype(str)
    gem = gem.copy()
    gem["RegionalSchlüssel_ARS"]        = ars
    gem["Land"]                         = ars.str.slice(0, 2)
    gem["Regierungsbezirk"]             = ars.str.slice(2, 3)
    gem["Kreis"]                        = ars.str.slice(3, 5)
    gem["VerwaltungsgemeinschaftTeil1"] = ars.str.slice(5, 7)
    gem["VerwaltungsgemeinschaftTeil2"] = ars.str.slice(7, 9)
    gem["Gemeinde"]                     = ars.str.slice(9, 12)

    expected = {
        "RegionalSchlüssel_ARS": 12, "Land": 2, "Regierungsbezirk": 1, "Kreis": 2,
        "VerwaltungsgemeinschaftTeil1": 2, "VerwaltungsgemeinschaftTeil2": 2, "Gemeinde": 3,
    }
    for c, L in expected.items():
        if not (gem[c].astype(str).str.len() == L).all():
            raise ValueError(f"{c} has wrong length; expected {L}.")
    return gem


def _coerce_for_arrow(df: pd.DataFrame, force_string_cols: set) -> pd.DataFrame:
    """Force specific columns to Arrow-friendly string dtype, keep booleans stable."""
    df = df.copy()
    for c in force_string_cols:
        if c in df.columns:
            df[c] = df[c].astype("string[pyarrow]")
    if "is_orphan" in df.columns:
        df["is_orphan"] = df["is_orphan"].astype("bool")
    return df


# ---------------------------------------------------------------------------
# Locate input files
# ---------------------------------------------------------------------------

_T_VG250 = Path(
    r"T:\petre\UCFL\Synthetic Population\Zensus\additional_data"
    r"\vg250_01-01.utm32s.gpkg.ebenen\vg250_ebenen_0101\DE_VG250.gpkg"
)
_VG250_LAYER_DEFAULT = "v_vg250_gem"

# data/raw local copy — resolved at import time relative to this file's package root
_LOCAL_VG250 = Path(__file__).resolve().parent.parent / "data" / "raw" / "vg250" / "DE_VG250.gpkg"


def _resolve_vg250(cfg) -> tuple[Path, str]:
    """Return (gpkg_path, layer_name).

    Resolution order:
      1. cfg.vg250_gpkg_path  — explicit config key (highest priority)
      2. data/raw/vg250/DE_VG250.gpkg  — local copy under the repo
      3. T: legacy path  — fallback with a warning
    """
    gpkg = getattr(cfg, "vg250_gpkg_path", None)
    layer = getattr(cfg, "vg250_gpkg_layer", _VG250_LAYER_DEFAULT)
    if gpkg is None:
        if _LOCAL_VG250.exists():
            gpkg = _LOCAL_VG250
        elif _T_VG250.exists():
            log.warning(
                "[gemeinde] VG250 local copy not found at %s; "
                "falling back to T: path %s — consider copying with "
                "'data/raw/vg250/DE_VG250.gpkg'",
                _LOCAL_VG250,
                _T_VG250,
            )
            gpkg = _T_VG250
        else:
            raise FileNotFoundError(
                "VG250 GeoPackage not found. Expected one of:\n"
                f"  1. cfg.vg250_gpkg_path (TOML key [data].vg250_gpkg_path)\n"
                f"  2. {_LOCAL_VG250}\n"
                f"  3. {_T_VG250}"
            )
    return Path(gpkg), layer


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_gemeinde_layer(gpkg_path: Path, layer: str) -> gpd.GeoDataFrame:
    """Load and prepare the Gemeinde GeoDataFrame (EPSG:25832 -> 3035)."""
    log.info("[gemeinde] loading layer %r from %s", layer, gpkg_path)
    gem = gpd.read_file(gpkg_path, layer=layer)

    if gem.crs is None:
        raise ValueError("Gemeinde layer has no CRS. Expected EPSG:25832.")
    if gem.crs.to_epsg() != EPSG_GEM:
        raise ValueError(
            f"Gemeinde layer CRS is {gem.crs}, expected EPSG:{EPSG_GEM} (UTM32N)."
        )

    key_col = _require_exact_12_digit_key(gem)
    gem = gem.to_crs(EPSG_POINTS)
    gem = _add_ars_parts(gem, key_col)
    gem = gem[ARS_NEW_COLS + ["geometry"]].copy()
    _ = gem.sindex   # build spatial index once
    log.info("[gemeinde] Gemeinde layer loaded: %d polygons", len(gem))
    return gem


def join_gemeinde_streaming(
    cells_path: Path,
    gem: gpd.GeoDataFrame,
    out_path: Path,
    *,
    chunk_size: int = CHUNK_SIZE,
) -> None:
    """Stream-join Gemeinde attributes onto 100m cells and write Parquet (zstd).

    Reads cells_path in chunks of chunk_size rows, spatially joins each chunk
    against the pre-built Gemeinde spatial index, and appends to a ParquetWriter.
    """
    log.info("[gemeinde] reading cells from %s", cells_path)
    cells_all = pd.read_parquet(cells_path)

    if CELLS_ID_COL not in cells_all.columns:
        raise KeyError(f"Missing column '{CELLS_ID_COL}' in cells parquet.")

    # Determine output column order: original cols + new ARS cols
    extra_string_cols = {c for c in cells_all.columns if c.startswith("werterlaeuternde_Zeichen_")}
    force_string = FORCE_STRING_COLS | extra_string_cols
    out_cols = list(cells_all.columns) + ARS_NEW_COLS

    out_path.parent.mkdir(parents=True, exist_ok=True)
    writer: Optional[pq.ParquetWriter] = None
    schema: Optional[pa.Schema] = None

    n_rows = len(cells_all)
    log.info("[gemeinde] streaming %d rows in chunks of %d", n_rows, chunk_size)

    for start in tqdm(range(0, n_rows, chunk_size), desc="gemeinde join"):
        chunk_full = cells_all.iloc[start : start + chunk_size, :].copy()

        pts = _parse_centroids_3035(chunk_full, CELLS_ID_COL)
        joined = gpd.sjoin(pts, gem, how="left", predicate="within")
        joined = joined.drop(columns=["index_left", "index_right"], errors="ignore")

        attrs = pd.DataFrame(joined.drop(columns="geometry"))[
            [CELLS_ID_COL] + ARS_NEW_COLS
        ]
        enriched = chunk_full.merge(attrs, on=CELLS_ID_COL, how="left")

        enriched = _coerce_for_arrow(enriched, force_string)

        table = pa.Table.from_pandas(
            enriched[out_cols], preserve_index=False, schema=schema
        )
        if writer is None:
            schema = table.schema
            writer = pq.ParquetWriter(out_path.as_posix(), schema, compression="zstd")
        writer.write_table(table)

    if writer is not None:
        writer.close()

    log.info("[gemeinde] wrote %s (%d rows)", out_path.name, n_rows)


def run_gemeinde(cfg) -> None:
    """Pipeline entry point for the gemeinde stage."""
    work = cfg.work_dir
    work.mkdir(parents=True, exist_ok=True)

    cells_in  = work / "df100_with_single_years.parquet"
    cells_out = work / "cells_100m_with_gemeinde.parquet"

    gpkg_path, gpkg_layer = _resolve_vg250(cfg)
    gem = load_gemeinde_layer(gpkg_path, gpkg_layer)

    join_gemeinde_streaming(cells_in, gem, cells_out)


def gemeinde_complete(cfg) -> bool:
    return (cfg.work_dir / "cells_100m_with_gemeinde.parquet").exists()
