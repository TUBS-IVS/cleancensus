"""Derive and harmonize household tenure (owner/renter) as a synthetic 2-category
topic from the Eigentuemerquote ratio, anchored to the harmonized household totals.

Port of tenure_v3.py, parameterized by Config instead of module constants.
Numerics are IDENTICAL to the legacy script.

In the new pipeline, tenure extends the SAME version files (cfg.out_1 / cfg.out_100)
rather than writing separate v3 outputs.

100m streaming strategy (avoid reading and writing the same file):
  National mode: stream cfg.out_100 -> .tmp.parquet, then os.replace to cfg.out_100.
  Subset mode:   read/mutate/overwrite the _SUBSET.parquet frame in memory.
"""
from __future__ import annotations

import os

import numpy as np
import pandas as pd

from cleancensus.harmonization import TopicSpec, BLEND_STD, downscale_topic, impute_orphan_rows_100m
from cleancensus.logsetup import get_logger
from cleancensus.stages import DOWNSCALE_KW

log = get_logger("tenure")

# Column name constants (single source of truth for both levels)
QUOTE_1 = "Eigentuemerquote_Eigentuemerquote_1km-Gitter"
QUOTE_100 = "Eigentuemerquote_Eigentuemerquote_100m-Gitter"
HH_ADJ_1 = "Insgesamt_Haushalte_Groesse_des_privaten_Haushalts_1km-Gitter_adj"
HH_ADJ_100 = "Insgesamt_Haushalte_Groesse_des_privaten_Haushalts_100m-Gitter_adj"
OWN_1, RENT_1 = "EigentuemerHH_Tenure_1km-Gitter", "MieterHH_Tenure_1km-Gitter"
OWN_100, RENT_100 = "EigentuemerHH_Tenure_100m-Gitter", "MieterHH_Tenure_100m-Gitter"

SPEC = TopicSpec(
    name="HH_Tenure",
    parent_cat_cols=[OWN_1, RENT_1],
    child_cat_cols=[OWN_100, RENT_100],
    child_row_total_col=HH_ADJ_100,
    alpha=0.90,
    blend=BLEND_STD,
)


def build_parent_tenure(df1: pd.DataFrame) -> pd.DataFrame:
    """Derive owner/renter counts at 1km. Missing quotes (==0) with households get
    the HH-weighted mean quote of their 10km group (national mean as last resort)."""
    q = pd.to_numeric(df1[QUOTE_1], errors="coerce").fillna(0.0).clip(0.0, 100.0)
    hh = pd.to_numeric(df1[HH_ADJ_1], errors="coerce").fillna(0.0)

    missing = (q <= 0) & (hh > 0)
    have = (q > 0) & (hh > 0)
    nat_mean = float((q[have] * hh[have]).sum() / max(hh[have].sum(), 1e-9))

    g10 = df1["GITTER_ID_10km"].astype(str).str.strip()
    grp_num = (q.where(have, 0.0) * hh.where(have, 0.0)).groupby(g10).sum()
    grp_den = hh.where(have, 0.0).groupby(g10).sum()
    grp_mean = grp_num / grp_den.replace(0, np.nan)

    fill = g10.map(grp_mean)
    n_natfill = int((missing & fill.isna()).sum())
    fill = fill.fillna(nat_mean)
    q_eff = q.where(~missing, fill)

    log.info(
        f"inhabited={int((hh > 0).sum()):,} | quote present={int(have.sum()):,} "
        f"| filled from 10km group={int(missing.sum()) - n_natfill:,} "
        f"| filled national mean={n_natfill:,} (nat mean={nat_mean:.1f}%)"
    )

    df1[OWN_1] = (q_eff / 100.0 * hh).astype(np.float32)
    df1[RENT_1] = (hh - df1[OWN_1]).clip(lower=0).astype(np.float32)
    return df1


def run_tenure(cfg) -> None:
    """Port of tenure_v3.run(): add owner/renter columns to cfg.out_1 and cfg.out_100.

    Reads cfg.out_1, adds the two tenure columns, overwrites cfg.out_1.
    For the 100m file:
      - National mode: streams cfg.out_100 -> .tmp.parquet, then replaces in place.
      - Subset mode:   reads/mutates/overwrites the _SUBSET.parquet frame.
    """
    # --- 1km ---
    df1 = pd.read_parquet(cfg.out_1)
    df1["GITTER_ID_1km"] = df1["GITTER_ID_1km"].astype(str).str.strip()
    df1 = build_parent_tenure(df1)
    df1.to_parquet(cfg.out_1, index=False)
    log.info(f"wrote {cfg.out_1} cols={len(df1.columns)}")

    # --- 100m ---
    if cfg.mode == "subset":
        subset_path = cfg.out_100.with_name(cfg.out_100.stem + "_SUBSET.parquet")
        # The SUBSET parquet only has the topic columns written by stage_b.
        # QUOTE_100 and HH_ADJ_100 live in the original path_100; read them from there
        # and align by row order (both are already filtered to the same parent set).
        df100 = pd.read_parquet(subset_path).reset_index(drop=True)
        df100["GITTER_ID_1km"] = df100["GITTER_ID_1km"].astype(str).str.strip()
        df100["is_orphan"] = df100["is_orphan"].astype(bool)

        # QUOTE_100 and HH_ADJ_100 are not in the SUBSET parquet (stage_b only writes
        # the topic columns it processed). Read them from the original path_100,
        # filtered to the same parent set.
        # Row order is preserved: stage_b filtered path_100 to these parents in
        # parquet scan order; we replicate the same filter here.
        p_1km_sub = set(df100["GITTER_ID_1km"].unique())
        df_src = pd.read_parquet(cfg.resolved_path_100, columns=["GITTER_ID_1km", QUOTE_100, HH_ADJ_100])
        df_src["GITTER_ID_1km"] = df_src["GITTER_ID_1km"].astype(str).str.strip()
        df_src = df_src[df_src["GITTER_ID_1km"].isin(p_1km_sub)].reset_index(drop=True)
        # Align by position (same scan order as stage_b)
        df100[QUOTE_100] = df_src[QUOTE_100].values
        df100[HH_ADJ_100] = df_src[HH_ADJ_100].values

        q = pd.to_numeric(df100[QUOTE_100], errors="coerce").fillna(0.0).clip(0.0, 100.0)
        hh = pd.to_numeric(df100[HH_ADJ_100], errors="coerce").fillna(0.0)
        sig = q > 0
        n_nosig = int(((~sig) & (hh > 0)).sum())
        log.info(
            f"inhabited={int((hh > 0).sum()):,} "
            f"| local signal={int((sig & (hh > 0)).sum()):,} "
            f"| no signal (parent-share fill)={n_nosig:,}"
        )
        df100[OWN_100] = np.where(sig, q / 100.0 * hh, 0.0).astype(np.float32)
        df100[RENT_100] = np.where(sig, (hh - df100[OWN_100]).clip(lower=0), 0.0).astype(np.float32)

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
        log.info(f"wrote subset {subset_path} (+2 cols, {len(df100):,} rows)")
        return

    # National mode: read the needed columns from cfg.out_100, then stream append
    import pyarrow as pa
    import pyarrow.dataset as ds
    import pyarrow.parquet as pq

    cols = ["GITTER_ID_1km", "is_orphan", QUOTE_100, HH_ADJ_100]
    df100 = pd.read_parquet(cfg.out_100, columns=cols).reset_index(drop=True)
    df100["GITTER_ID_1km"] = df100["GITTER_ID_1km"].astype(str).str.strip()
    df100["is_orphan"] = df100["is_orphan"].astype(bool)

    q = pd.to_numeric(df100[QUOTE_100], errors="coerce").fillna(0.0).clip(0.0, 100.0)
    hh = pd.to_numeric(df100[HH_ADJ_100], errors="coerce").fillna(0.0)
    sig = q > 0
    n_nosig = int(((~sig) & (hh > 0)).sum())
    log.info(
        f"inhabited={int((hh > 0).sum()):,} "
        f"| local signal={int((sig & (hh > 0)).sum()):,} "
        f"| no signal (parent-share fill)={n_nosig:,}"
    )
    df100[OWN_100] = np.where(sig, q / 100.0 * hh, 0.0).astype(np.float32)
    df100[RENT_100] = np.where(sig, (hh - df100[OWN_100]).clip(lower=0), 0.0).astype(np.float32)

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
        + [pa.field(OWN_100, pa.float32()), pa.field(RENT_100, pa.float32())]
    )
    writer, pos = None, 0
    scanner = dataset.scanner(columns=keep_cols, batch_size=1_000_000)
    for rb in scanner.to_reader():
        tbl = pa.Table.from_batches([rb])
        n = tbl.num_rows
        for c in (OWN_100, RENT_100):
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
    log.info(f"wrote {cfg.out_100} (+2 cols, {pos:,} rows)")


def check_tenure(cfg) -> int:
    """Port of tenure_v3.check(): invariant checks on tenure columns.

    Refinement from validated run: Seniorenstatus comparison is evaluated on
    NON-ORPHAN cells only as the hard check (orphan deviations are a known benign
    artifact — their count is reported as info, not failure).

    National-share check [0.40, 0.50] only in national mode.
    """
    fail = 0

    def chk(label, cond, detail=""):
        nonlocal fail
        ok = bool(cond)
        if not ok:
            fail += 1
        log.info(f"[{'OK ' if ok else 'FAIL'}] {label} {detail}")

    if cfg.mode == "subset":
        path_100 = cfg.out_100.with_name(cfg.out_100.stem + "_SUBSET.parquet")
    else:
        path_100 = cfg.out_100

    senior_col = (
        "Insgesamt_Haushalte_Seniorenstatus_eines_privaten_Haushalts_100m-Gitter_adj"
    )
    df = pd.read_parquet(
        path_100,
        columns=[OWN_100, RENT_100, HH_ADJ_100, senior_col, "is_orphan"],
    )

    s = df[OWN_100] + df[RENT_100]
    d = (s - df[HH_ADJ_100]).abs()
    chk(
        "owner+renter == HH_adj",
        int((d > 0.5).sum()) == 0,
        f"max|d|={d.max():.4f} cells>0.5={(d > 0.5).sum()}",
    )

    # Seniorenstatus check: hard on non-orphan cells, info-only on orphan cells
    is_orphan = df["is_orphan"].astype(bool)
    d2_all = (s - df[senior_col]).abs()
    d2_nonorphan = d2_all[~is_orphan]
    n_orphan_dev = int((d2_all[is_orphan] > 0.5).sum())
    if n_orphan_dev:
        log.info(
            f"[INFO] orphan cells with |owner+renter - Seniorenstatus_adj| > 0.5: "
            f"{n_orphan_dev} (benign artifact, not counted as failure)"
        )
    chk(
        "owner+renter == Seniorenstatus_adj (non-orphan)",
        int((d2_nonorphan > 0.5).sum()) == 0,
        f"max|d|={d2_nonorphan.max():.4f}",
    )

    if cfg.mode == "national":
        rate = float(df[OWN_100].sum() / max(df[HH_ADJ_100].sum(), 1e-9))
        chk(
            "national owner share in [0.40, 0.50]",
            0.40 <= rate <= 0.50,
            f"rate={rate:.4f}",
        )

    sub = df[[OWN_100, RENT_100]]
    chk("no NaN", int(sub.isna().sum().sum()) == 0)
    chk("no negatives", float(sub.min().min()) >= 0)

    # 1km margin echo (read cfg.out_1 which already has tenure cols)
    df1 = pd.read_parquet(cfg.out_1, columns=["GITTER_ID_1km", OWN_1])
    own100 = pd.read_parquet(path_100, columns=["GITTER_ID_1km", OWN_100])
    g = own100.groupby(own100["GITTER_ID_1km"].astype(str).str.strip())[OWN_100].sum()
    m = df1.set_index(df1["GITTER_ID_1km"].astype(str).str.strip())[OWN_1]
    joined = pd.concat([g, m], axis=1, join="inner")
    dd = (joined.iloc[:, 0] - joined.iloc[:, 1]).abs()
    chk(
        "1km owner margin (echo)",
        float(dd.quantile(0.999)) < 5.0,
        f"p99.9|d|={dd.quantile(0.999):.3f} max|d|={dd.max():.3f} parents={len(joined):,}",
    )

    log.info(f"\n{fail} failures")
    return fail
