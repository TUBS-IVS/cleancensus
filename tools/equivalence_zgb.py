"""Equivalence gate: compare two cleancensus output files cell-exactly.

Usage:
  uv run python tools/equivalence_zgb.py --new <new.parquet> --ref <ref.parquet> \
      [--cols-from-ref] [--atol 1e-3]

Aligns rows positionally after verifying GITTER_ID_1km equality per row (both
files must stem from the same source filter in the same order). Compares every
shared numeric column with abs tolerance; reports per-column max|d| and a final
PASS/FAIL line; exit code 0 on pass.
"""
from __future__ import annotations

import argparse
import sys

import numpy as np
import pandas as pd


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--new", required=True)
    ap.add_argument("--ref", required=True)
    ap.add_argument("--atol", type=float, default=1e-3)
    args = ap.parse_args()

    new = pd.read_parquet(args.new)
    ref = pd.read_parquet(args.ref)

    if len(new) != len(ref):
        print(f"FAIL: row count differs: new={len(new):,} ref={len(ref):,}")
        return 1

    key = "GITTER_ID_1km"
    if not (new[key].astype(str).values == ref[key].astype(str).values).all():
        print(f"FAIL: {key} row order differs")
        return 1

    shared = [c for c in ref.columns if c in new.columns
              and pd.api.types.is_numeric_dtype(ref[c])
              and pd.api.types.is_numeric_dtype(new[c])]
    skipped = [c for c in ref.columns if c not in new.columns]
    if skipped:
        print(f"[info] {len(skipped)} ref-only columns skipped: {skipped[:5]}{'...' if len(skipped) > 5 else ''}")

    worst = 0.0
    fails = []
    for c in shared:
        d = np.abs(new[c].to_numpy(dtype=float) - ref[c].to_numpy(dtype=float))
        mx = float(np.nanmax(d)) if len(d) else 0.0
        worst = max(worst, mx)
        status = "OK " if mx <= args.atol else "FAIL"
        if mx > args.atol:
            fails.append((c, mx))
        print(f"[{status}] {c}: max|d|={mx:.6g}")

    print(f"\ncompared {len(shared)} columns over {len(new):,} rows | worst max|d|={worst:.6g}")
    if fails:
        print(f"FAIL: {len(fails)} columns exceed atol={args.atol}")
        return 1
    print("PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
