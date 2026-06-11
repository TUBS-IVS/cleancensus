"""Config-driven stage functions: stage_a (10km -> 1km) and stage_b (1km -> 100m).

Port of extend_topics.py, parameterized by Config instead of module constants.
Numerics are IDENTICAL to the legacy script.
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd

from cleancensus.harmonization import (
    normalize_parent_categories_for_specs,
    apply_adj_for_all_topics,
    downscale_topic,
    impute_orphan_rows_100m,
)
from cleancensus.progress import progress_iter
from cleancensus.topics import build_new_topic_specs

DOWNSCALE_KW = dict(
    inner_passes=10,
    outer_iters=2,
    rake_tol=1e-11,
    rake_max_iter=1000,
    validate_row_tol=2e-4,
    verbose=False,
)


def load_frame(path) -> "pd.DataFrame":
    """Load a DataFrame from path, dispatching on file suffix.

    Supports .parquet (pd.read_parquet) and .pickle / .pkl (pd.read_pickle).
    Raises ValueError for unrecognised suffixes.
    """
    from pathlib import Path
    p = Path(path)
    suffix = p.suffix.lower()
    if suffix == ".parquet":
        return pd.read_parquet(p)
    if suffix in (".pickle", ".pkl"):
        return pd.read_pickle(p)
    raise ValueError(f"load_frame: unrecognised file suffix {suffix!r} for {p}")


def build_subset_parents(cfg) -> "set[str] | None":
    """Return the set of GITTER_ID_1km parent ids for the configured ARS prefixes.

    Returns None for mode='national' (no filtering needed).
    For mode='subset', reads the 100m file and builds ARS-5 codes from
    Land (zfill 2) + Regierungsbezirk (zfill 1) + Kreis (zfill 2).
    """
    if cfg.mode == "national":
        return None

    df = pd.read_parquet(
        cfg.resolved_path_100,
        columns=["GITTER_ID_1km", "Kreis", "Land", "Regierungsbezirk"],
    )
    ars5 = (
        df["Land"].astype("Int64").astype(str).str.zfill(2)
        + df["Regierungsbezirk"].astype("Int64").astype(str).str.zfill(1)
        + df["Kreis"].astype("Int64").astype(str).str.zfill(2)
    )
    keep = ars5.isin(set(cfg.ars_prefixes))
    parents = set(df.loc[keep, "GITTER_ID_1km"].astype(str).str.strip().unique())
    print(f"[subset] ARS prefixes={cfg.ars_prefixes} -> {len(parents):,} parent 1km cells")
    return parents


def run_stage_a(cfg) -> None:
    """Port of stage_a: downscale 10km -> 1km, writes cfg.out_1."""
    specs = build_new_topic_specs("1km", names=cfg.topics)
    print(f"[stage_a] {len(specs)} topics: {[s.name for s in specs]}")
    if not specs:
        sys.exit("[stage_a] no specs matched topics; aborting")

    df10 = load_frame(cfg.resolved_path_10).reset_index(drop=False)
    df1 = load_frame(cfg.resolved_path_1)
    for df in (df10, df1):
        df.replace([np.inf, -np.inf], np.nan, inplace=True)
        df.fillna(0, inplace=True)
    df10["GITTER_ID_10km"] = df10["GITTER_ID_10km"].astype(str).str.strip()
    df1["GITTER_ID_10km"] = df1["GITTER_ID_10km"].astype(str).str.strip()
    df1["GITTER_ID_1km"] = df1["GITTER_ID_1km"].astype(str).str.strip()

    normalize_parent_categories_for_specs(
        parent_df=df10, specs=specs, child_level="1km", verbose=True
    )
    specs = apply_adj_for_all_topics(
        parent_df=df10,
        child_df=df1,
        parent_id_col="GITTER_ID_10km",
        child_parent_id_col="GITTER_ID_10km",
        specs=specs,
        verbose=True,
    )

    for spec in progress_iter(specs, "stage_a/topics-1km", total=len(specs)):
        res = downscale_topic(
            parent_df=df10,
            child_df=df1,
            parent_id_col="GITTER_ID_10km",
            child_parent_id_col="GITTER_ID_10km",
            spec=spec,
            **DOWNSCALE_KW,
        )
        for c in spec.child_cat_cols:
            df1[c] = res[c].values.astype(np.float32)

    cfg.outputs_dir.mkdir(parents=True, exist_ok=True)
    df1.to_parquet(cfg.out_1, index=False)
    print(f"[stage_a] wrote {cfg.out_1} cols={len(df1.columns)}")


def run_stage_b(cfg) -> None:
    """Port of stage_b: downscale 1km -> 100m, writes cfg.out_100 (or _SUBSET).

    For national mode: streams from cfg.resolved_path_100 and writes cfg.out_100.
    For subset mode: filters in-memory and writes cfg.out_100.with_name(..._SUBSET.parquet).
    """
    import pyarrow as pa
    import pyarrow.dataset as ds
    import pyarrow.parquet as pq

    specs = build_new_topic_specs("100m", names=cfg.topics)
    print(f"[stage_b] {len(specs)} topics: {[s.name for s in specs]}")
    if not specs:
        sys.exit("[stage_b] no specs matched topics; aborting")

    df1 = pd.read_parquet(cfg.out_1)
    df1["GITTER_ID_1km"] = df1["GITTER_ID_1km"].astype(str).str.strip()

    needed = {"GITTER_ID_1km", "is_orphan"}
    for spec in specs:
        needed.add(spec.child_row_total_col)
        needed.update(spec.child_cat_cols)
    df100_min = (
        pd.read_parquet(cfg.resolved_path_100, columns=sorted(needed))
        .reset_index(drop=True)
    )
    df100_min.replace([np.inf, -np.inf], np.nan, inplace=True)
    df100_min.fillna(0, inplace=True)
    for c in df100_min.columns:
        if pd.api.types.is_float_dtype(df100_min[c]):
            df100_min[c] = df100_min[c].astype(np.float32)
    df100_min["GITTER_ID_1km"] = df100_min["GITTER_ID_1km"].astype(str).str.strip()
    df100_min["is_orphan"] = df100_min["is_orphan"].astype(bool)

    # Subset filter: build parent set and restrict both frames
    parents = build_subset_parents(cfg)
    if parents is not None:
        df1 = df1[df1["GITTER_ID_1km"].isin(parents)].copy()
        df100_min = df100_min[df100_min["GITTER_ID_1km"].isin(parents)].copy()
        df100_min.reset_index(drop=True, inplace=True)
        print(f"[stage_b] subset: {len(df1)} parents, {len(df100_min)} cells")

    # orphan: the flag already exists; recompute defensively (OR them)
    p_1km = set(df1["GITTER_ID_1km"].unique())
    df100_min["is_orphan"] = df100_min["is_orphan"] | ~df100_min["GITTER_ID_1km"].isin(p_1km)
    df100_ok = df100_min.loc[~df100_min["is_orphan"]].copy()
    df1_ok = df1.loc[df1["GITTER_ID_1km"].isin(df100_ok["GITTER_ID_1km"])].copy()

    if df100_ok.empty:
        sys.exit("[stage_b] no non-orphan cells matched; aborting")

    specs = apply_adj_for_all_topics(
        parent_df=df1_ok,
        child_df=df100_ok,
        parent_id_col="GITTER_ID_1km",
        child_parent_id_col="GITTER_ID_1km",
        specs=specs,
        verbose=True,
    )
    adj_total_cols = [s.child_row_total_col for s in specs]
    for col in adj_total_cols:
        df100_min.loc[df100_ok.index, col] = df100_ok[col].astype(np.float32).values

    for spec in progress_iter(specs, "stage_b/topics-100m", total=len(specs)):
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

    # Orphan raw-fill: _adj totals stay at raw Insgesamt value; fill before imputing
    for spec in specs:
        raw_tot = spec.child_row_total_col[: -len("_adj")]
        mask = df100_min["is_orphan"]
        df100_min.loc[mask, spec.child_row_total_col] = df100_min.loc[mask, raw_tot].values
    impute_orphan_rows_100m(
        df=df100_min,
        specs=specs,
        orphan_flag_col="is_orphan",
        dtype_out=np.float32,
        verbose=True,
    )

    cfg.outputs_dir.mkdir(parents=True, exist_ok=True)

    if parents is not None:
        # Subset mode: write the SUBSET frame directly (no streaming)
        out = cfg.out_100.with_name(cfg.out_100.stem + "_SUBSET.parquet")
        df100_min.to_parquet(out, index=False)
        print(f"[stage_b] subset frame written to {out} (no streaming on subset runs)")
        return

    # National mode: stream-append to the full file
    dataset = ds.dataset(cfg.resolved_path_100, format="parquet")
    keep_cols = list(dataset.schema.names)

    new_cols = []
    for spec in specs:
        new_cols.append(spec.child_row_total_col)
        new_cols.extend(spec.child_cat_cols)

    base_fields = [f for f in dataset.schema]
    extra_fields = [
        pa.field(c, pa.float32()) for c in new_cols if c not in keep_cols
    ]
    full_schema = pa.schema(base_fields + extra_fields)

    writer, pos, batch_size = None, 0, 1_000_000
    scanner = dataset.scanner(columns=keep_cols, batch_size=batch_size)
    # Approximate total batches from row-group metadata (best-effort)
    try:
        _n_rg = sum(
            pq.ParquetFile(f).metadata.num_row_groups
            for f in dataset.files
        )
    except Exception:
        _n_rg = None
    for rb in progress_iter(scanner.to_reader(), "stage_b/stream-write", total=_n_rg):
        tbl = pa.Table.from_batches([rb])
        n = tbl.num_rows
        combined = tbl
        for c in new_cols:
            in_schema = c in combined.schema.names
            expected_type = (
                combined.schema.field(c).type if in_schema else pa.float32()
            )
            arr = pa.array(
                df100_min[c].iloc[pos : pos + n].to_numpy(), type=expected_type
            )
            if in_schema:
                combined = combined.set_column(
                    combined.schema.get_field_index(c), c, arr
                )
            else:
                combined = combined.append_column(c, arr)
        combined = combined.select([f.name for f in full_schema])
        if writer is None:
            writer = pq.ParquetWriter(cfg.out_100, full_schema)
        writer.write_table(combined)
        pos += n
    if writer:
        writer.close()
    assert pos == len(df100_min), (
        f"row mismatch: streamed {pos} vs frame {len(df100_min)}"
    )
    print(
        f"[stage_b] wrote {cfg.out_100} (+{len(extra_fields)} new cols, {pos:,} rows)"
    )
