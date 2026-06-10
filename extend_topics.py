"""Extend the prepared census cell files with newly harmonized topics.

Usage:
  uv run python extend_topics.py stage_a [--topics NAME ...]
  uv run python extend_topics.py stage_b [--topics NAME ...] [--parents-csv FILE]

Default topic set = new_topics.MID_CONTROLLABLE_DEFAULT (Whg_Gebaeudetyp,
HH_Seniorenstatus) — the only topics directly controllable via MiD household data.
Pass --topics explicitly to run others from the catalog.

stage_a: 10km -> 1km, writes OUT_1_V2.
stage_b: 1km(v2) -> 100m, writes OUT_100_V2 (streamed). --parents-csv limits to a
         subset of GITTER_ID_1km parents (fast validation run, e.g. ZGB).
"""
from __future__ import annotations
import argparse
import sys

import numpy as np
import pandas as pd
from tqdm import tqdm

from harmonization import (
    normalize_parent_categories_for_specs, apply_adj_for_all_topics,
    downscale_topic, impute_orphan_rows_100m,
)
from new_topics import build_new_topic_specs, MID_CONTROLLABLE_DEFAULT
from paths import PATH_10, PATH_1, PATH_100, OUT_1_V2, OUT_100_V2

DOWNSCALE_KW = dict(inner_passes=10, outer_iters=2, rake_tol=1e-11,
                    rake_max_iter=1000, validate_row_tol=2e-4, verbose=False)


def stage_a(names):
    specs = build_new_topic_specs("1km", names=names)
    print(f"[stage_a] {len(specs)} topics: {[s.name for s in specs]}")

    df10 = pd.read_pickle(PATH_10).reset_index(drop=False)
    df1 = pd.read_parquet(PATH_1)
    for df in (df10, df1):
        df.replace([np.inf, -np.inf], np.nan, inplace=True)
        df.fillna(0, inplace=True)
    df10["GITTER_ID_10km"] = df10["GITTER_ID_10km"].astype(str).str.strip()
    df1["GITTER_ID_10km"] = df1["GITTER_ID_10km"].astype(str).str.strip()
    df1["GITTER_ID_1km"] = df1["GITTER_ID_1km"].astype(str).str.strip()

    # identical sequence to the original run:
    normalize_parent_categories_for_specs(parent_df=df10, specs=specs,
                                          child_level="1km", verbose=True)
    specs = apply_adj_for_all_topics(
        parent_df=df10, child_df=df1,
        parent_id_col="GITTER_ID_10km", child_parent_id_col="GITTER_ID_10km",
        specs=specs, verbose=True)

    for spec in tqdm(specs, desc="Topics 1km"):
        res = downscale_topic(parent_df=df10, child_df=df1,
                              parent_id_col="GITTER_ID_10km",
                              child_parent_id_col="GITTER_ID_10km",
                              spec=spec, **DOWNSCALE_KW)
        for c in spec.child_cat_cols:
            df1[c] = res[c].values

    df1.to_parquet(OUT_1_V2, index=False)
    print(f"[stage_a] wrote {OUT_1_V2} cols={len(df1.columns)}")


def stage_b(names, parents_csv=None):
    import pyarrow as pa
    import pyarrow.dataset as ds
    import pyarrow.parquet as pq

    specs = build_new_topic_specs("100m", names=names)
    print(f"[stage_b] {len(specs)} topics: {[s.name for s in specs]}")

    df1 = pd.read_parquet(OUT_1_V2)
    df1["GITTER_ID_1km"] = df1["GITTER_ID_1km"].astype(str).str.strip()

    needed = {"GITTER_ID_1km", "is_orphan"}
    for spec in specs:
        needed.add(spec.child_row_total_col)
        needed.update(spec.child_cat_cols)
    df100_min = pd.read_parquet(PATH_100, columns=sorted(needed)).reset_index(drop=False)
    df100_min.replace([np.inf, -np.inf], np.nan, inplace=True)
    df100_min.fillna(0, inplace=True)
    for c in df100_min.columns:
        if pd.api.types.is_float_dtype(df100_min[c]):
            df100_min[c] = df100_min[c].astype(np.float32)
    df100_min["GITTER_ID_1km"] = df100_min["GITTER_ID_1km"].astype(str).str.strip()
    df100_min["is_orphan"] = df100_min["is_orphan"].astype(bool)

    if parents_csv:  # fast validation subset (e.g. ZGB)
        keep = set(pd.read_csv(parents_csv, header=None)[0].astype(str).str.strip())
        df1 = df1[df1["GITTER_ID_1km"].isin(keep)].copy()
        df100_min = df100_min[df100_min["GITTER_ID_1km"].isin(keep)].copy()
        df100_min.reset_index(drop=True, inplace=True)
        print(f"[stage_b] subset: {len(df1)} parents, {len(df100_min)} cells")

    # orphan = 1km parent not present (flag already in file; recompute defensively, OR them)
    p_1km = set(df1["GITTER_ID_1km"].unique())
    df100_min["is_orphan"] = df100_min["is_orphan"] | ~df100_min["GITTER_ID_1km"].isin(p_1km)
    df100_ok = df100_min.loc[~df100_min["is_orphan"]].copy()
    df1_ok = df1.loc[df1["GITTER_ID_1km"].isin(df100_ok["GITTER_ID_1km"])].copy()

    specs = apply_adj_for_all_topics(
        parent_df=df1_ok, child_df=df100_ok,
        parent_id_col="GITTER_ID_1km", child_parent_id_col="GITTER_ID_1km",
        specs=specs, verbose=True)
    adj_total_cols = [s.child_row_total_col for s in specs]
    for col in adj_total_cols:
        df100_min.loc[df100_ok.index, col] = df100_ok[col].astype(np.float32).values

    for spec in tqdm(specs, desc="Topics 100m"):
        res = downscale_topic(parent_df=df1_ok, child_df=df100_ok,
                              parent_id_col="GITTER_ID_1km",
                              child_parent_id_col="GITTER_ID_1km",
                              spec=spec, **DOWNSCALE_KW)
        for c in spec.child_cat_cols:
            df100_min.loc[df100_ok.index, c] = res[c].values.astype(np.float32)

    # orphans: the original pipeline fixed them in a separate pass ("happyorphans");
    # here is_orphan exists from the start, so run the imputation inline.
    # NOTE: orphan *_adj totals stay at the raw Insgesamt value (no parent to anchor to);
    # fill them so every row has a defined total before imputing categories.
    for spec in specs:
        raw_tot = spec.child_row_total_col[:-len("_adj")]
        mask = df100_min["is_orphan"]
        df100_min.loc[mask, spec.child_row_total_col] = df100_min.loc[mask, raw_tot].values
    impute_orphan_rows_100m(df=df100_min, specs=specs, orphan_flag_col="is_orphan",
                            dtype_out=np.float32, verbose=True)

    if parents_csv:
        out = OUT_100_V2.with_name(OUT_100_V2.stem + "_SUBSET.parquet")
        df100_min.to_parquet(out, index=False)
        print(f"[stage_b] subset frame written to {out} (no streaming on subset runs)")
        return

    # ---- stream-append to the full file (pattern identical to the notebook) ----
    dataset = ds.dataset(PATH_100, format="parquet")
    keep_cols = list(dataset.schema.names)  # keep ALL original columns

    new_cols = []
    for spec in specs:
        new_cols.append(spec.child_row_total_col)
        new_cols.extend(spec.child_cat_cols)

    base_fields = [f for f in dataset.schema]
    extra_fields = [pa.field(c, pa.float32()) for c in new_cols if c not in keep_cols]
    full_schema = pa.schema(base_fields + extra_fields)

    writer, pos, batch_size = None, 0, 1_000_000
    scanner = dataset.scanner(columns=keep_cols, batch_size=batch_size)
    for rb in scanner.to_reader():
        tbl = pa.Table.from_batches([rb])
        n = tbl.num_rows
        combined = tbl
        for c in new_cols:
            in_schema = c in combined.schema.names
            expected_type = combined.schema.field(c).type if in_schema else pa.float32()
            arr = pa.array(df100_min[c].iloc[pos:pos + n].to_numpy(), type=expected_type)
            if in_schema:
                combined = combined.set_column(combined.schema.get_field_index(c), c, arr)
            else:
                combined = combined.append_column(c, arr)
        combined = combined.select([f.name for f in full_schema])
        if writer is None:
            writer = pq.ParquetWriter(OUT_100_V2, full_schema)
        writer.write_table(combined)
        pos += n
    if writer:
        writer.close()
    print(f"[stage_b] wrote {OUT_100_V2} (+{len(extra_fields)} new cols, {pos:,} rows)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("stage", choices=["stage_a", "stage_b"])
    ap.add_argument("--topics", nargs="*", default=list(MID_CONTROLLABLE_DEFAULT),
                    help="topic names from new_topics.RAW_TOPICS catalog")
    ap.add_argument("--parents-csv", default=None,
                    help="optional CSV with one GITTER_ID_1km per line (stage_b subset run)")
    args = ap.parse_args()
    if args.stage == "stage_a":
        stage_a(args.topics)
    else:
        stage_b(args.topics, args.parents_csv)


if __name__ == "__main__":
    sys.exit(main())
