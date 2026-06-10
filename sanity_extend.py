"""Invariant checks for the extended (v2) cell files. Exit code 0 = all pass.

Usage: uv run python sanity_extend.py [--topics NAME ...] [--path-100 OVERRIDE]

On a SUBSET file (--path-100 ..._SUBSET.parquet) the national-mass checks (#3)
fail by construction — they compare against national 10km sums; ignore them there.
"""
from __future__ import annotations
import argparse
import sys

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from new_topics import build_new_topic_specs, MID_CONTROLLABLE_DEFAULT
from paths import PATH_10, OUT_100_V2

FAIL = 0

ANCHOR_GEB_HEIZ = "Insgesamt_Heizungsart_Gebaeude_nach_ueberwiegender_Heizungsart_100m-Gitter_adj"
ANCHOR_HH_GROESSE = "Insgesamt_Haushalte_Groesse_des_privaten_Haushalts_100m-Gitter_adj"
ANCHOR_POP = "POP_TOTAL_100m_adj"


def check(label, cond, detail=""):
    global FAIL
    status = "OK " if cond else "FAIL"
    if not cond:
        FAIL += 1
    print(f"[{status}] {label} {detail}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--topics", nargs="*", default=list(MID_CONTROLLABLE_DEFAULT))
    ap.add_argument("--path-100", default=OUT_100_V2)
    args = ap.parse_args()

    specs = build_new_topic_specs("100m", names=args.topics)
    need = set()
    for s in specs:
        need.add(s.child_row_total_col + "_adj")
        need.add(s.child_row_total_col)
        need.update(s.child_cat_cols)

    anchors = [ANCHOR_GEB_HEIZ, ANCHOR_HH_GROESSE, ANCHOR_POP]

    # Determine which anchors are actually present in the file (subset runs omit them)
    avail = set(f.name for f in pq.ParquetFile(args.path_100).schema_arrow)
    missing_anchors = [a for a in anchors if a not in avail]
    for a in missing_anchors:
        print(f"[SKIP] anchor not in file (subset run?): {a}")
    anchors = [a for a in anchors if a in avail]
    need.difference_update(missing_anchors)
    need.update(anchors)

    # Pre-check: report missing required columns and remove them from need
    missing_cols = set()
    for c in sorted(need - avail):
        if c not in missing_anchors:
            check(f"column present: {c}", False)
            missing_cols.add(c)
    need -= missing_cols

    df = pd.read_parquet(args.path_100, columns=sorted(c for c in need if c in avail))
    n = len(df)
    print(f"rows: {n:,}")

    # 1) per-topic: sum(categories) == *_adj total (the core harmonization invariant)
    for s in specs:
        adj = s.child_row_total_col + "_adj"
        missing_topic_cols = [c for c in s.child_cat_cols + [adj] if c not in df.columns]
        if missing_topic_cols:
            check(f"{s.name}: sum(cats)==adj", False, f"missing columns: {missing_topic_cols}")
            continue
        cats = df[s.child_cat_cols].sum(axis=1)
        d = (cats - df[adj]).abs()
        check(f"{s.name}: sum(cats)==adj", int((d > 0.5).sum()) == 0,
              f"max|d|={d.max():.4f} cells>0.5={(d > 0.5).sum()}")

    # 2) universe equality of *_adj totals across topics that share a universe
    def pair(a, b, label, tol=0.5):
        d = (df[a] - df[b]).abs()
        check(label, int((d > tol).sum()) == 0, f"max|d|={d.max():.4f}")

    by_name = {s.name: s for s in specs}

    def adj_of(name):
        return by_name[name].child_row_total_col + "_adj"

    if {"Geb_Gebaeudetyp", "Geb_AnzahlWohnungen"} <= by_name.keys():
        pair(adj_of("Geb_Gebaeudetyp"), adj_of("Geb_AnzahlWohnungen"),
             "Gebaeude adj: Typ==AnzWhg")
    if {"Geb_Gebaeudetyp", "Geb_Baujahr"} <= by_name.keys():
        pair(adj_of("Geb_Gebaeudetyp"), adj_of("Geb_Baujahr"),
             "Gebaeude adj: Typ==Baujahr")
    if "Geb_Gebaeudetyp" in by_name and ANCHOR_GEB_HEIZ in df.columns:
        pair(adj_of("Geb_Gebaeudetyp"), ANCHOR_GEB_HEIZ,
             "Gebaeude adj: new==existing Heizungsart(Geb) adj", tol=1.0)
    if {"Whg_Gebaeudetyp", "Whg_Heizungsart"} <= by_name.keys():
        pair(adj_of("Whg_Gebaeudetyp"), adj_of("Whg_Heizungsart"),
             "Wohnungen-B adj: Typ==Heizungsart")
    if "HH_Seniorenstatus" in by_name and ANCHOR_HH_GROESSE in df.columns:
        pair(adj_of("HH_Seniorenstatus"), ANCHOR_HH_GROESSE,
             "Haushalte adj: Seniorenstatus==HH_Groesse", tol=1.0)
    if "Pers_Staatsangehoerigkeit" in by_name and ANCHOR_POP in df.columns:
        pair(adj_of("Pers_Staatsangehoerigkeit"), ANCHOR_POP,
             "Personen adj: Staatsang==POP_TOTAL", tol=1.0)

    # 3) global mass: 100m adj sum vs 10km raw national sum per topic (within 2%)
    df10 = pd.read_pickle(PATH_10).reset_index(drop=False)
    for s in build_new_topic_specs("1km", names=args.topics):
        adj_col = adj_of(s.name)
        if adj_col not in df.columns:
            check(f"{s.name}: national mass within 2%", False, f"missing columns: {adj_col}")
            continue
        tot10 = s.child_row_total_col.replace("_1km-Gitter", "_10km-Gitter")
        nat = pd.to_numeric(df10[tot10], errors="coerce").fillna(0).sum()
        got = df[adj_col].sum()
        rel = abs(got - nat) / max(nat, 1.0)
        check(f"{s.name}: national mass within 2%", rel < 0.02,
              f"100m={got:,.0f} 10km={nat:,.0f} rel={rel:.4f}")

    # 4) hygiene: no NaN/negative values in new columns
    sub = df[[c for s in specs for c in s.child_cat_cols]]
    check("no NaN in new categories", int(sub.isna().sum().sum()) == 0)
    check("no negatives in new categories", float(sub.min().min()) >= 0)

    print(f"\n{FAIL} failures")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
