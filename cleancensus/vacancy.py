"""Derive and harmonize dwelling vacancy (Leerstand) as a synthetic 2-category
topic from the Leerstandsquote ratio, anchored to the harmonized dwelling totals
(universe A: Wohnungen nach Zahl der Raeume).

Port of the tenure.py architecture, adapted for vacancy.
Numerics mirror tenure exactly (same signal rule: quote > 0 = signal).

Universe note: Zensus 2022 defines Leerstandsquote on dwellings in buildings
with residential space (universe B, ~42.5M). The anchor used here is universe A
(Wohnungen nach Zahl der Raeume, ~41.8M). Difference is ~3%; occupied+vacant
sum to universe A by construction. Official Zensus 2022 vacancy is 4.3% of
universe B; expected plausible range anchored to universe A is [3.5%, 5.5%].

In the new pipeline, vacancy extends the SAME version files (cfg.out_1 / cfg.out_100)
rather than writing separate outputs.

100m streaming strategy (avoid reading and writing the same file):
  National mode: stream cfg.out_100 -> .tmp.parquet, then os.replace to cfg.out_100.
  Subset mode:   read/mutate/overwrite the _SUBSET.parquet frame in memory.
"""
from __future__ import annotations

import os

import numpy as np
import pandas as pd

from cleancensus.harmonization import TopicSpec, BLEND_STD, downscale_topic, impute_orphan_rows_100m
from cleancensus.stages import DOWNSCALE_KW

# Column name constants (single source of truth for both levels)
QUOTE_1 = "Leerstandsquote_Leerstandsquote_1km-Gitter"
QUOTE_100 = "Leerstandsquote_Leerstandsquote_100m-Gitter"
DWG_ADJ_1 = "Insgesamt_Wohnungen_Wohnungen_nach_Zahl_der_Raeume_1km-Gitter_adj"
DWG_ADJ_100 = "Insgesamt_Wohnungen_Wohnungen_nach_Zahl_der_Raeume_100m-Gitter_adj"
OCC_1, VAC_1 = "BewohntWhg_Leerstand_1km-Gitter", "LeerstehendWhg_Leerstand_1km-Gitter"
OCC_100, VAC_100 = "BewohntWhg_Leerstand_100m-Gitter", "LeerstehendWhg_Leerstand_100m-Gitter"

SPEC = TopicSpec(
    name="Whg_Leerstand",
    parent_cat_cols=[OCC_1, VAC_1],
    child_cat_cols=[OCC_100, VAC_100],
    child_row_total_col=DWG_ADJ_100,
    alpha=0.90,
    blend=BLEND_STD,
)


def build_parent_vacancy(df1: pd.DataFrame) -> pd.DataFrame:
    """Derive occupied/vacant dwelling counts at 1km. Missing quotes (==0) with
    dwellings get the dwelling-weighted mean quote of their 10km group
    (national mean as last resort)."""
    q = pd.to_numeric(df1[QUOTE_1], errors="coerce").fillna(0.0).clip(0.0, 100.0)
    dwg = pd.to_numeric(df1[DWG_ADJ_1], errors="coerce").fillna(0.0)

    missing = (q <= 0) & (dwg > 0)
    have = (q > 0) & (dwg > 0)
    nat_mean = float((q[have] * dwg[have]).sum() / max(dwg[have].sum(), 1e-9))

    g10 = df1["GITTER_ID_10km"].astype(str).str.strip()
    grp_num = (q.where(have, 0.0) * dwg.where(have, 0.0)).groupby(g10).sum()
    grp_den = dwg.where(have, 0.0).groupby(g10).sum()
    grp_mean = grp_num / grp_den.replace(0, np.nan)

    fill = g10.map(grp_mean)
    n_natfill = int((missing & fill.isna()).sum())
    fill = fill.fillna(nat_mean)
    q_eff = q.where(~missing, fill)

    print(
        f"[vacancy-1km] inhabited={int((dwg > 0).sum()):,} | quote present={int(have.sum()):,} "
        f"| filled from 10km group={int(missing.sum()) - n_natfill:,} "
        f"| filled national mean={n_natfill:,} (nat mean={nat_mean:.1f}%)"
    )

    df1[VAC_1] = (q_eff / 100.0 * dwg).astype(np.float32)
    df1[OCC_1] = (dwg - df1[VAC_1]).clip(lower=0).astype(np.float32)
    return df1


def run_vacancy(cfg) -> None:
    """Add occupied/vacant dwelling columns to cfg.out_1 and cfg.out_100.

    Reads cfg.out_1, adds the two vacancy columns, overwrites cfg.out_1.
    For the 100m file:
      - National mode: streams cfg.out_100 -> .tmp.parquet, then replaces in place.
      - Subset mode:   reads/mutates/overwrites the _SUBSET.parquet frame.
    """
    # --- 1km ---
    df1 = pd.read_parquet(cfg.out_1)
    df1["GITTER_ID_1km"] = df1["GITTER_ID_1km"].astype(str).str.strip()
    df1 = build_parent_vacancy(df1)
    df1.to_parquet(cfg.out_1, index=False)
    print(f"[vacancy] wrote {cfg.out_1} cols={len(df1.columns)}")

    # --- 100m ---
    if cfg.mode == "subset":
        subset_path = cfg.out_100.with_name(cfg.out_100.stem + "_SUBSET.parquet")
        df100 = pd.read_parquet(subset_path).reset_index(drop=True)
        df100["GITTER_ID_1km"] = df100["GITTER_ID_1km"].astype(str).str.strip()
        df100["is_orphan"] = df100["is_orphan"].astype(bool)

        # QUOTE_100 and DWG_ADJ_100 are not in the SUBSET parquet (stage_b only
        # writes the topic columns it processed). Read from the original path_100,
        # filtered to the same parent set.
        p_1km_sub = set(df100["GITTER_ID_1km"].unique())
        df_src = pd.read_parquet(
            cfg.path_100, columns=["GITTER_ID_1km", QUOTE_100, DWG_ADJ_100]
        )
        df_src["GITTER_ID_1km"] = df_src["GITTER_ID_1km"].astype(str).str.strip()
        df_src = df_src[df_src["GITTER_ID_1km"].isin(p_1km_sub)].reset_index(drop=True)
        df100[QUOTE_100] = df_src[QUOTE_100].values
        df100[DWG_ADJ_100] = df_src[DWG_ADJ_100].values

        q = pd.to_numeric(df100[QUOTE_100], errors="coerce").fillna(0.0).clip(0.0, 100.0)
        dwg = pd.to_numeric(df100[DWG_ADJ_100], errors="coerce").fillna(0.0)
        sig = q > 0
        n_nosig = int(((~sig) & (dwg > 0)).sum())
        print(
            f"[vacancy-100m] inhabited={int((dwg > 0).sum()):,} "
            f"| local signal={int((sig & (dwg > 0)).sum()):,} "
            f"| no signal (parent-share fill)={n_nosig:,}"
        )
        df100[VAC_100] = np.where(sig, q / 100.0 * dwg, 0.0).astype(np.float32)
        df100[OCC_100] = np.where(sig, (dwg - df100[VAC_100]).clip(lower=0), 0.0).astype(np.float32)

        p_1km = set(df1["GITTER_ID_1km"].unique())
        df100["is_orphan"] = df100["is_orphan"] | ~df100["GITTER_ID_1km"].isin(p_1km)
        df100_ok = df100.loc[~df100["is_orphan"]].copy()
        df1_ok = df1.loc[df1["GITTER_ID_1km"].isin(df100_ok["GITTER_ID_1km"])].copy()

        res = downscale_topic(
            parent_df=df1_ok,
            child_df=df100_ok,
            parent_id_col="GITTER_ID_1km",
            child_parent_id_col="GITTER_ID_1km",
            spec=SPEC,
            **DOWNSCALE_KW,
        )
        for c in SPEC.child_cat_cols:
            df100.loc[df100_ok.index, c] = res[c].values.astype(np.float32)

        impute_orphan_rows_100m(
            df=df100,
            specs=[SPEC],
            orphan_flag_col="is_orphan",
            dtype_out=np.float32,
            verbose=True,
        )
        df100.to_parquet(subset_path, index=False)
        print(f"[vacancy] wrote subset {subset_path} (+2 cols, {len(df100):,} rows)")
        return

    # National mode: read the needed columns from cfg.out_100, then stream append
    import pyarrow as pa
    import pyarrow.dataset as ds
    import pyarrow.parquet as pq

    cols = ["GITTER_ID_1km", "is_orphan", QUOTE_100, DWG_ADJ_100]
    df100 = pd.read_parquet(cfg.out_100, columns=cols).reset_index(drop=True)
    df100["GITTER_ID_1km"] = df100["GITTER_ID_1km"].astype(str).str.strip()
    df100["is_orphan"] = df100["is_orphan"].astype(bool)

    q = pd.to_numeric(df100[QUOTE_100], errors="coerce").fillna(0.0).clip(0.0, 100.0)
    dwg = pd.to_numeric(df100[DWG_ADJ_100], errors="coerce").fillna(0.0)
    sig = q > 0
    n_nosig = int(((~sig) & (dwg > 0)).sum())
    print(
        f"[vacancy-100m] inhabited={int((dwg > 0).sum()):,} "
        f"| local signal={int((sig & (dwg > 0)).sum()):,} "
        f"| no signal (parent-share fill)={n_nosig:,}"
    )
    df100[VAC_100] = np.where(sig, q / 100.0 * dwg, 0.0).astype(np.float32)
    df100[OCC_100] = np.where(sig, (dwg - df100[VAC_100]).clip(lower=0), 0.0).astype(np.float32)

    p_1km = set(df1["GITTER_ID_1km"].unique())
    df100["is_orphan"] = df100["is_orphan"] | ~df100["GITTER_ID_1km"].isin(p_1km)
    df100_ok = df100.loc[~df100["is_orphan"]].copy()
    df1_ok = df1.loc[df1["GITTER_ID_1km"].isin(df100_ok["GITTER_ID_1km"])].copy()

    res = downscale_topic(
        parent_df=df1_ok,
        child_df=df100_ok,
        parent_id_col="GITTER_ID_1km",
        child_parent_id_col="GITTER_ID_1km",
        spec=SPEC,
        **DOWNSCALE_KW,
    )
    for c in SPEC.child_cat_cols:
        df100.loc[df100_ok.index, c] = res[c].values.astype(np.float32)

    impute_orphan_rows_100m(
        df=df100,
        specs=[SPEC],
        orphan_flag_col="is_orphan",
        dtype_out=np.float32,
        verbose=True,
    )

    # Stream cfg.out_100 -> tmp file, then atomically replace
    tmp_path = cfg.out_100.with_suffix(".tmp.parquet")
    dataset = ds.dataset(cfg.out_100, format="parquet")
    keep_cols = list(dataset.schema.names)
    full_schema = pa.schema(
        list(dataset.schema)
        + [pa.field(OCC_100, pa.float32()), pa.field(VAC_100, pa.float32())]
    )
    writer, pos = None, 0
    scanner = dataset.scanner(columns=keep_cols, batch_size=1_000_000)
    for rb in scanner.to_reader():
        tbl = pa.Table.from_batches([rb])
        n = tbl.num_rows
        for c in (OCC_100, VAC_100):
            tbl = tbl.append_column(
                c,
                pa.array(df100[c].iloc[pos : pos + n].to_numpy(), type=pa.float32()),
            )
        tbl = tbl.select([f.name for f in full_schema])
        if writer is None:
            writer = pq.ParquetWriter(tmp_path, full_schema)
        writer.write_table(tbl)
        pos += n
    if writer:
        writer.close()
    assert pos == len(df100), f"row mismatch: streamed {pos} vs frame {len(df100)}"
    os.replace(tmp_path, cfg.out_100)
    print(f"[vacancy] wrote {cfg.out_100} (+2 cols, {pos:,} rows)")


def check_vacancy(cfg) -> int:
    """Invariant checks on vacancy columns.

    Checks: occupied+vacant == DWG_adj (0 cells > 0.5), national vacancy share
    in [0.03, 0.06] (national mode only), no NaN/negatives, 1km margin echo.
    Orphan deviations are info-only, not failures.
    """
    fail = 0

    def chk(label, cond, detail=""):
        nonlocal fail
        ok = bool(cond)
        if not ok:
            fail += 1
        print(f"[{'OK ' if ok else 'FAIL'}] {label} {detail}")

    if cfg.mode == "subset":
        path_100 = cfg.out_100.with_name(cfg.out_100.stem + "_SUBSET.parquet")
    else:
        path_100 = cfg.out_100

    df = pd.read_parquet(
        path_100,
        columns=[OCC_100, VAC_100, DWG_ADJ_100, "is_orphan"],
    )

    s = df[OCC_100] + df[VAC_100]
    d = (s - df[DWG_ADJ_100]).abs()
    chk(
        "occupied+vacant == DWG_adj",
        int((d > 0.5).sum()) == 0,
        f"max|d|={d.max():.4f} cells>0.5={(d > 0.5).sum()}",
    )

    # Orphan tolerance: report orphan deviations but don't fail on them
    is_orphan = df["is_orphan"].astype(bool)
    d_nonorphan = d[~is_orphan]
    n_orphan_dev = int((d[is_orphan] > 0.5).sum())
    if n_orphan_dev:
        print(
            f"[INFO] orphan cells with |occupied+vacant - DWG_adj| > 0.5: "
            f"{n_orphan_dev} (benign artifact, not counted as failure)"
        )
    chk(
        "occupied+vacant == DWG_adj (non-orphan)",
        int((d_nonorphan > 0.5).sum()) == 0,
        f"max|d|={d_nonorphan.max():.4f}",
    )

    if cfg.mode == "national":
        rate = float(df[VAC_100].sum() / max(df[DWG_ADJ_100].sum(), 1e-9))
        chk(
            "national vacancy share in [0.03, 0.06]",
            0.03 <= rate <= 0.06,
            f"rate={rate:.4f}",
        )

    sub = df[[OCC_100, VAC_100]]
    chk("no NaN", int(sub.isna().sum().sum()) == 0)
    chk("no negatives", float(sub.min().min()) >= 0)

    # 1km margin echo
    df1 = pd.read_parquet(cfg.out_1, columns=["GITTER_ID_1km", VAC_1])
    vac100 = pd.read_parquet(path_100, columns=["GITTER_ID_1km", VAC_100])
    g = vac100.groupby(vac100["GITTER_ID_1km"].astype(str).str.strip())[VAC_100].sum()
    m = df1.set_index(df1["GITTER_ID_1km"].astype(str).str.strip())[VAC_1]
    joined = pd.concat([g, m], axis=1, join="inner")
    dd = (joined.iloc[:, 0] - joined.iloc[:, 1]).abs()
    chk(
        "1km vacant margin (echo)",
        float(dd.quantile(0.999)) < 5.0,
        f"p99.9|d|={dd.quantile(0.999):.3f} max|d|={dd.max():.3f} parents={len(joined):,}",
    )

    print(f"\n{fail} failures")
    return fail
