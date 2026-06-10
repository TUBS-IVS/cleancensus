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
        raise NotImplementedError("stage_b lands in the next task")


if __name__ == "__main__":
    sys.exit(main())
