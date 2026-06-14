"""topics8 stage: harmonize the 8 ORIGINAL categorical topics (10km -> 1km -> 100m).

Port of notebooks_archive/other_binned_data.ipynb (cell 1 main block + cell 2 orphan pass),
with the happyorphans imputation run INLINE after the 100m downscale instead of as a
separate second pass.

Numerics are IDENTICAL to the notebook. Reuses harmonization.py machinery and
stages.DOWNSCALE_KW; do not re-tune.

Topics (8):
    Familienstand, Energietraeger, Heizungsart, Haushaltsgroesse,
    Lebensform, Raeume, Wohnflaeche, Geburtsland
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from cleancensus.harmonization import (
    build_topic_specs_for_level,
    normalize_parent_categories_for_specs,
    apply_adj_for_all_topics,
    downscale_topic,
    impute_orphan_rows_100m,
)
from cleancensus import names
from cleancensus.logsetup import get_logger
from cleancensus.progress import progress_iter
from cleancensus.stages import DOWNSCALE_KW

log = get_logger("topics8")


# ---------------------------------------------------------------------------
# 1km stage: 10km -> 1km
# ---------------------------------------------------------------------------

def run_topics8_1km(df10_path: str | Path, df1_path: str | Path, out_1_path: str | Path) -> None:
    """Port of the notebook 10km->1km block for the 8 original categorical topics.

    Reads the 10km and 1km pickles, applies the 8-topic harmonization, and writes
    the enriched 1km parquet to out_1_path.
    """
    df10_path = Path(df10_path)
    df1_path = Path(df1_path)
    out_1_path = Path(out_1_path)

    from cleancensus.stages import load_frame

    log.info(f"reading {df10_path} ...")
    df10 = load_frame(df10_path).reset_index(drop=False)
    log.info(f"reading {df1_path} ...")
    df1 = load_frame(df1_path).reset_index(drop=False)

    # Clean NaNs/±inf
    for df in (df10, df1):
        df.replace([np.inf, -np.inf], np.nan, inplace=True)
        df.fillna(0, inplace=True)

    # Drop werterlaeuternde_Zeichen columns
    drop_pat = "werterlaeuternde_Zeichen"
    df10 = df10.drop(columns=[c for c in df10.columns if drop_pat in c])
    df1 = df1.drop(columns=[c for c in df1.columns if drop_pat in c])

    # Normalize IDs
    df10["GITTER_ID_10km"] = df10["GITTER_ID_10km"].astype(str).str.strip()
    df1["GITTER_ID_10km"] = df1["GITTER_ID_10km"].astype(str).str.strip()
    df1["GITTER_ID_1km"] = df1["GITTER_ID_1km"].astype(str).str.strip()

    log.info("building specs ...")
    specs = build_topic_specs_for_level("1km")
    log.info(f"{len(specs)} topics: {[s.name for s in specs]}")

    normalize_parent_categories_for_specs(
        parent_df=df10,
        specs=specs,
        child_level="1km",
        verbose=True,
    )

    specs = apply_adj_for_all_topics(
        parent_df=df10,
        child_df=df1,
        parent_id_col="GITTER_ID_10km",
        child_parent_id_col="GITTER_ID_10km",
        specs=specs,
        verbose=True,
    )

    for spec in progress_iter(specs, "topics8/1km", total=len(specs)):
        res = downscale_topic(
            parent_df=df10,
            child_df=df1,
            parent_id_col="GITTER_ID_10km",
            child_parent_id_col="GITTER_ID_10km",
            spec=spec,
            **DOWNSCALE_KW,
        )
        for c in spec.child_cat_cols:
            df1[c] = res[c].values

    out_1_path.parent.mkdir(parents=True, exist_ok=True)
    df1.to_parquet(out_1_path, index=False)
    log.info(f"wrote {out_1_path} ({len(df1):,} rows, {len(df1.columns)} cols)")


# ---------------------------------------------------------------------------
# 100m stage: 1km -> 100m
# ---------------------------------------------------------------------------

def run_topics8_100m(
    df1_path_or_frame,
    path_100: str | Path,
    out_100_path: str | Path,
    parents: Optional[set] = None,
) -> None:
    """Port of the notebook 1km->100m block + inline happyorphans pass.

    Parameters
    ----------
    df1_path_or_frame : path or DataFrame
        The 1km binneds output from run_topics8_1km (or the path to it).
    path_100 : path
        Input 100m parquet (cells_100m_with_gender_backfilled.parquet).
    out_100_path : path
        Output path for the enriched 100m parquet.
    parents : set of str, optional
        If given, restrict to these GITTER_ID_1km values (subset mode).
        In subset mode, writes in-memory directly (no streaming).
    """
    import pyarrow as pa
    import pyarrow.dataset as ds
    import pyarrow.parquet as pq

    path_100 = Path(path_100)
    out_100_path = Path(out_100_path)

    # Load 1km frame
    if isinstance(df1_path_or_frame, (str, Path)):
        df1 = pd.read_parquet(df1_path_or_frame)
    else:
        df1 = df1_path_or_frame.copy()
    df1["GITTER_ID_1km"] = df1["GITTER_ID_1km"].astype(str).str.strip()

    # Build needed columns for 100m
    topics_100m = build_topic_specs_for_level("100m")
    needed_cols_100 = {"GITTER_ID_1km", "GITTER_ID_100m"}
    for spec in topics_100m:
        needed_cols_100.add(spec.child_row_total_col)
        needed_cols_100.update(spec.child_cat_cols)
    # Intersect with columns actually present in the file
    _pq_avail = set(pq.ParquetFile(path_100).schema_arrow.names)
    needed_cols_100 = sorted(needed_cols_100 & _pq_avail)

    log.info(f"reading {path_100} (cols={len(needed_cols_100)}) ...")
    df100_min = pd.read_parquet(path_100, columns=needed_cols_100).reset_index(drop=False)

    # Clean + downcast
    df100_min.replace([np.inf, -np.inf], np.nan, inplace=True)
    df100_min.fillna(0, inplace=True)
    for c in df100_min.columns:
        if pd.api.types.is_float_dtype(df100_min[c]):
            df100_min[c] = df100_min[c].astype(np.float32)
    df100_min["GITTER_ID_1km"] = df100_min["GITTER_ID_1km"].astype(str).str.strip()

    # Subset filter
    if parents is not None:
        df1 = df1[df1["GITTER_ID_1km"].isin(parents)].copy()
        df100_min = df100_min[df100_min["GITTER_ID_1km"].isin(parents)].copy()
        df100_min.reset_index(drop=True, inplace=True)
        log.info(f"subset: {len(df1):,} parent 1km cells, {len(df100_min):,} 100m cells")

    # Orphan flag: 100m cells whose 1km parent is not in df1
    p_1km = set(df1["GITTER_ID_1km"].unique())
    df100_min["is_orphan"] = ~df100_min["GITTER_ID_1km"].isin(p_1km)
    df100_ok = df100_min.loc[~df100_min["is_orphan"]].copy()
    df1_ok = df1.loc[df1["GITTER_ID_1km"].isin(df100_ok["GITTER_ID_1km"])].copy()

    log.info(f"non-orphan 100m cells: {len(df100_ok):,} | orphan: {df100_min['is_orphan'].sum():,}")

    # Create *_adj totals and flip specs
    topics_100m = apply_adj_for_all_topics(
        parent_df=df1_ok,
        child_df=df100_ok,
        parent_id_col="GITTER_ID_1km",
        child_parent_id_col="GITTER_ID_1km",
        specs=topics_100m,
        verbose=True,
    )
    adj_total_cols = [spec.child_row_total_col for spec in topics_100m]
    for col in adj_total_cols:
        if col in df100_ok.columns:
            df100_min.loc[df100_ok.index, col] = df100_ok[col].astype(np.float32).values

    # Downscale each topic
    for spec in progress_iter(topics_100m, "topics8/100m", total=len(topics_100m)):
        res = downscale_topic(
            parent_df=df1_ok,
            child_df=df100_ok,
            parent_id_col="GITTER_ID_1km",
            child_parent_id_col="GITTER_ID_1km",
            spec=spec,
            **DOWNSCALE_KW,
        )
        for c in spec.child_cat_cols:
            df100_min.loc[df100_ok.index, c] = res[c].values.astype(np.float32)

    # Inline happyorphans pass: fill orphan _adj totals from raw Insgesamt before impute
    # (mirrors stages.py run_stage_b pattern exactly)
    for spec in topics_100m:
        raw_tot = spec.child_row_total_col[: -len("_adj")]
        mask = df100_min["is_orphan"]
        if raw_tot in df100_min.columns:
            df100_min.loc[mask, spec.child_row_total_col] = df100_min.loc[mask, raw_tot].values

    impute_orphan_rows_100m(
        df=df100_min,
        specs=topics_100m,
        orphan_flag_col="is_orphan",
        dtype_out=np.float32,
        verbose=True,
    )

    out_100_path.parent.mkdir(parents=True, exist_ok=True)

    if parents is not None:
        # Subset mode: write in-memory directly
        df100_min.to_parquet(out_100_path, index=False)
        log.info(f"subset wrote {out_100_path} ({len(df100_min):,} rows, {len(df100_min.columns)} cols)")
        return

    # National mode: stream-append new columns onto path_100 -> out_100_path
    dataset = ds.dataset(path_100, format="parquet")

    drop_pat = "werterlaeuternde_Zeichen"
    orig_names = dataset.schema.names
    drop_cols_100 = [c for c in orig_names if drop_pat in c]
    keep_cols_100 = [c for c in orig_names if c not in drop_cols_100]

    # new_cols: _adj totals + per-category results
    new_cols = []
    for spec in topics_100m:
        new_cols.append(spec.child_row_total_col)
        new_cols.extend(spec.child_cat_cols)

    # Ensure all new_cols exist in df100_min (fill with nan if missing)
    for c in new_cols:
        if c not in df100_min.columns:
            df100_min[c] = np.nan

    # Build writer schema: original (without dropped cols) + extra fields
    orig_schema = dataset.schema
    base_fields = [f for f in orig_schema if f.name in keep_cols_100]
    extra_fields = [pa.field(c, pa.float32()) for c in new_cols if c not in keep_cols_100]
    full_schema = pa.schema(list(base_fields) + extra_fields)

    writer = None
    pos = 0
    batch_size = 1_000_000

    scanner = dataset.scanner(columns=keep_cols_100, batch_size=batch_size)
    for rb in scanner.to_reader():
        tbl = pa.Table.from_batches([rb])
        n = tbl.num_rows

        combined = tbl
        for c in new_cols:
            if c in combined.schema.names:
                expected_type = combined.schema.field(c).type
            else:
                expected_type = pa.float32()

            arr = pa.array(df100_min[c].iloc[pos : pos + n].to_numpy(), type=expected_type)

            if c in combined.schema.names:
                idx = combined.schema.get_field_index(c)
                combined = combined.set_column(idx, c, arr)
            else:
                combined = combined.append_column(c, arr)

        combined = combined.select([f.name for f in full_schema])

        if writer is None:
            writer = pq.ParquetWriter(out_100_path, full_schema)
        writer.write_table(combined)
        pos += n

    if writer:
        writer.close()

    assert pos == len(df100_min), (
        f"[topics8-100m] row mismatch: streamed {pos} vs frame {len(df100_min)}"
    )
    log.info(f"wrote {out_100_path} (+{len(extra_fields)} new cols, {pos:,} rows)")


# ---------------------------------------------------------------------------
# Config-driven orchestration wrapper
# ---------------------------------------------------------------------------

def run_topics8(cfg) -> None:
    """Run the full topics8 stage: 10km->1km then 1km->100m.

    Resolves paths from cfg.work_dir canonical names.
    Honors cfg.mode=='subset' via cleancensus.stages.build_subset_parents.
    """
    from cleancensus.stages import build_subset_parents

    work_dir = cfg.work_dir
    work_dir.mkdir(parents=True, exist_ok=True)

    # the ages stage writes parquet; legacy gate runs used T:-era pickles —
    # names.resolve picks the new name, then any legacy alias (incl. .pickle)
    df10_path = names.resolve(work_dir, names.work("ages", "10km"))
    df1_pickle = names.resolve(work_dir, names.work("ages", "1km"))
    path_100 = names.resolve(work_dir, names.work("gender", "100m"))
    out_1 = work_dir / names.work("topics8", "1km")
    out_100 = work_dir / names.work("topics8", "100m")

    log.info(f"work_dir={work_dir}")

    # NOTE: no internal skip-if-exists here. The pipeline runner already gates this
    # stage via is_complete()/--force; an internal `if not out.exists()` guard would
    # silently IGNORE --force and reuse stale outputs (it did, masking a regression on
    # 2026-06-13). When the pipeline decides to run topics8, always rebuild both passes.

    # 1km pass
    log.info("running 1km pass ...")
    run_topics8_1km(df10_path, df1_pickle, out_1)

    # 100m pass
    parents = build_subset_parents(cfg) if cfg.mode == "subset" else None

    if parents is not None:
        subset_out = out_100.with_name(out_100.stem + "_SUBSET.parquet")
        log.info(f"running 100m subset pass -> {subset_out}")
        run_topics8_100m(out_1, path_100, subset_out, parents=parents)
    else:
        log.info("running 100m national pass ...")
        run_topics8_100m(out_1, path_100, out_100, parents=None)

    log.info("done.")
