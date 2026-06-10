"""Derive and harmonize household tenure (owner/renter) as a synthetic 2-category
topic from the Eigentuemerquote ratio, anchored to the harmonized household totals.

The 10km grid has no quote column, so the cascade is 1km -> 100m only.
quote == 0 in the prepared files means "not published" (the raw data never holds a
true zero), so such cells carry NO local signal and receive parent shares via the
trust-blended IPF.

Usage:
  uv run python tenure_v3.py run     # build v3 files from the v2 outputs
  uv run python tenure_v3.py check   # invariant checks on the v3 output
"""
from __future__ import annotations
import argparse
import sys

import numpy as np
import pandas as pd

from harmonization import TopicSpec, BLEND_STD, downscale_topic, impute_orphan_rows_100m
from extend_topics import DOWNSCALE_KW
from paths import OUT_1_V2, OUT_100_V2, OUT_1_V3, OUT_100_V3

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
    alpha=0.90, blend=BLEND_STD,
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
    grp_mean = (grp_num / grp_den.replace(0, np.nan))

    fill = g10.map(grp_mean)
    n_natfill = int((missing & fill.isna()).sum())
    fill = fill.fillna(nat_mean)
    q_eff = q.where(~missing, fill)

    print(f"[tenure-1km] inhabited={int((hh > 0).sum()):,} | quote present={int(have.sum()):,} "
          f"| filled from 10km group={int(missing.sum()) - n_natfill:,} "
          f"| filled national mean={n_natfill:,} (nat mean={nat_mean:.1f}%)")

    df1[OWN_1] = (q_eff / 100.0 * hh).astype(np.float32)
    df1[RENT_1] = (hh - df1[OWN_1]).clip(lower=0).astype(np.float32)
    return df1


def run():
    df1 = pd.read_parquet(OUT_1_V2)
    df1["GITTER_ID_1km"] = df1["GITTER_ID_1km"].astype(str).str.strip()
    df1 = build_parent_tenure(df1)
    df1.to_parquet(OUT_1_V3, index=False)
    print(f"[tenure] wrote {OUT_1_V3} cols={len(df1.columns)}")

    cols = ["GITTER_ID_1km", "is_orphan", QUOTE_100, HH_ADJ_100]
    df100 = pd.read_parquet(OUT_100_V2, columns=cols).reset_index(drop=True)
    df100["GITTER_ID_1km"] = df100["GITTER_ID_1km"].astype(str).str.strip()
    df100["is_orphan"] = df100["is_orphan"].astype(bool)
    q = pd.to_numeric(df100[QUOTE_100], errors="coerce").fillna(0.0).clip(0.0, 100.0)
    hh = pd.to_numeric(df100[HH_ADJ_100], errors="coerce").fillna(0.0)
    sig = q > 0
    n_nosig = int(((~sig) & (hh > 0)).sum())
    print(f"[tenure-100m] inhabited={int((hh > 0).sum()):,} | local signal={int((sig & (hh > 0)).sum()):,} "
          f"| no signal (parent-share fill)={n_nosig:,}")
    df100[OWN_100] = np.where(sig, q / 100.0 * hh, 0.0).astype(np.float32)
    df100[RENT_100] = np.where(sig, (hh - df100[OWN_100]).clip(lower=0), 0.0).astype(np.float32)

    p_1km = set(df1["GITTER_ID_1km"].unique())
    df100["is_orphan"] = df100["is_orphan"] | ~df100["GITTER_ID_1km"].isin(p_1km)
    df100_ok = df100.loc[~df100["is_orphan"]].copy()
    df1_ok = df1.loc[df1["GITTER_ID_1km"].isin(df100_ok["GITTER_ID_1km"])].copy()

    res = downscale_topic(parent_df=df1_ok, child_df=df100_ok,
                          parent_id_col="GITTER_ID_1km",
                          child_parent_id_col="GITTER_ID_1km",
                          spec=SPEC, **DOWNSCALE_KW)
    for c in SPEC.child_cat_cols:
        df100.loc[df100_ok.index, c] = res[c].values.astype(np.float32)

    impute_orphan_rows_100m(df=df100, specs=[SPEC], orphan_flag_col="is_orphan",
                            dtype_out=np.float32, verbose=True)

    # stream v2 -> v3 with the two new columns appended
    import pyarrow as pa
    import pyarrow.dataset as ds
    import pyarrow.parquet as pq
    dataset = ds.dataset(OUT_100_V2, format="parquet")
    keep_cols = list(dataset.schema.names)
    full_schema = pa.schema(list(dataset.schema)
                            + [pa.field(OWN_100, pa.float32()), pa.field(RENT_100, pa.float32())])
    writer, pos = None, 0
    scanner = dataset.scanner(columns=keep_cols, batch_size=1_000_000)
    for rb in scanner.to_reader():
        tbl = pa.Table.from_batches([rb])
        n = tbl.num_rows
        for c in (OWN_100, RENT_100):
            tbl = tbl.append_column(c, pa.array(df100[c].iloc[pos:pos + n].to_numpy(), type=pa.float32()))
        tbl = tbl.select([f.name for f in full_schema])
        if writer is None:
            writer = pq.ParquetWriter(OUT_100_V3, full_schema)
        writer.write_table(tbl)
        pos += n
    if writer:
        writer.close()
    assert pos == len(df100), f"row mismatch: streamed {pos} vs frame {len(df100)}"
    print(f"[tenure] wrote {OUT_100_V3} (+2 cols, {pos:,} rows)")


def check():
    fail = 0

    def chk(label, cond, detail=""):
        nonlocal fail
        ok = bool(cond)
        if not ok:
            fail += 1
        print(f"[{'OK ' if ok else 'FAIL'}] {label} {detail}")

    df = pd.read_parquet(OUT_100_V3, columns=[OWN_100, RENT_100, HH_ADJ_100,
                                              "Insgesamt_Haushalte_Seniorenstatus_eines_privaten_Haushalts_100m-Gitter_adj"])
    s = df[OWN_100] + df[RENT_100]
    d = (s - df[HH_ADJ_100]).abs()
    chk("owner+renter == HH_adj", int((d > 0.5).sum()) == 0,
        f"max|d|={d.max():.4f} cells>0.5={(d > 0.5).sum()}")
    d2 = (s - df.iloc[:, 3]).abs()
    chk("owner+renter == Seniorenstatus_adj", int((d2 > 0.5).sum()) == 0,
        f"max|d|={d2.max():.4f}")
    rate = float(df[OWN_100].sum() / max(df[HH_ADJ_100].sum(), 1e-9))
    chk("national owner share in [0.40, 0.50]", 0.40 <= rate <= 0.50, f"rate={rate:.4f}")
    sub = df[[OWN_100, RENT_100]]
    chk("no NaN", int(sub.isna().sum().sum()) == 0)
    chk("no negatives", float(sub.min().min()) >= 0)

    df1 = pd.read_parquet(OUT_1_V3, columns=["GITTER_ID_1km", OWN_1])
    own100 = pd.read_parquet(OUT_100_V3, columns=["GITTER_ID_1km", OWN_100])
    g = own100.groupby(own100["GITTER_ID_1km"].astype(str).str.strip())[OWN_100].sum()
    m = df1.set_index(df1["GITTER_ID_1km"].astype(str).str.strip())[OWN_1]
    joined = pd.concat([g, m], axis=1, join="inner")
    dd = (joined.iloc[:, 0] - joined.iloc[:, 1]).abs()
    chk("1km owner margin (echo)", float(dd.quantile(0.999)) < 5.0,
        f"p99.9|d|={dd.quantile(0.999):.3f} max|d|={dd.max():.3f} parents={len(joined):,}")

    print(f"\n{fail} failures")
    return 1 if fail else 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["run", "check"])
    args = ap.parse_args()
    if args.mode == "run":
        run()
        return 0
    return check()


if __name__ == "__main__":
    sys.exit(main())
