# Vacancy (Leerstand) Derived Topic Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a derived 2-category topic (occupied / vacant dwellings) to the cleancensus pipeline, modeled identically to the existing `tenure.py` architecture.

**Architecture:** A new `cleancensus/vacancy.py` mirrors `tenure.py` exactly: derive occupied/vacant counts at 1km from `Leerstandsquote` × harmonized dwelling totals, trust-blend downscale 1km→100m, orphan-impute, stream-append in national mode. Config gate `derived_vacancy` (default false). Stage `vacancy` is inserted after `tenure` in the registry.

**Tech Stack:** Python, pandas, numpy, pyarrow; same `TopicSpec / downscale_topic / impute_orphan_rows_100m` from `cleancensus/harmonization.py`; `DOWNSCALE_KW` from `cleancensus/stages.py`.

---

## Pre-work investigation findings (already done — do NOT re-run)

**Ratio columns confirmed present:**
- 1km: `Leerstandsquote_Leerstandsquote_1km-Gitter` — present in `data/inputs/cells_1km_with_binneds.parquet`
- 100m: `Leerstandsquote_Leerstandsquote_100m-Gitter` — present in the 100m prepared input
- Both: `marktaktive_Leerstandsquote_*` also present (informational only, not used)

**Anchor column confirmed present at both levels (with `_adj`):**
- `Insgesamt_Wohnungen_Wohnungen_nach_Zahl_der_Raeume_1km-Gitter_adj` (1km total: 41,806,842)
- `Insgesamt_Wohnungen_Wohnungen_nach_Zahl_der_Raeume_100m-Gitter_adj` (100m total: 41,803,912)

**Signal-rule investigation (1km):**
- Rows with quote > 0: 91,775
- Rows with quote == 0 & dwellings > 0: 105,105 (no signal → use parent shares)
- Rows with quote == 0 & dwellings == 0: 15,878 (both zero → all zero)
- Weighted national quote (signal cells): 4.26% — within expected [3.5%, 5.5%] range

**Signal-rule investigation (100m):**
- Rows with quote > 0: 265,235
- Rows with quote == 0 & dwellings > 0: 2,340,987
- Rows with quote == 0 & dwellings == 0: 542,260

**Universe note:** Zensus defines Leerstandsquote on universe B (~42.5M dwellings, buildings with residential space); anchor is universe A (~41.8M, Wohnungen nach Zahl der Räume). Difference ~3%. Document in module docstring.

**1km source decision:** `Leerstandsquote_Leerstandsquote_1km-Gitter` is ALREADY present in `data/inputs/cells_1km_with_binneds.parquet`. No need to derive from 100m or look in work files.

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `cleancensus/vacancy.py` | Create | Vacancy derivation: `build_parent_vacancy`, `run_vacancy`, `check_vacancy` |
| `cleancensus/config.py` | Modify | Add `derived_vacancy: bool` field; add to `load_config` |
| `cleancensus/pipeline.py` | Modify | Add `vacancy` stage after `tenure`; wire `_run_vacancy`, `_vacancy_complete`, update `STAGE_NAMES` |
| `config.example.toml` | Modify | Add `derived_vacancy = false` comment line |
| `tests/test_vacancy.py` | Create | Unit tests: arithmetic, signal rule, config default, stage order |
| `tests/test_pipeline.py` | Modify | Update `test_registry_order_and_completeness` to include `vacancy` |
| `tests/test_config.py` | Modify | Add `derived_vacancy` default false test |

---

## Task 1: Create `cleancensus/vacancy.py`

**Files:**
- Create: `cleancensus/vacancy.py`

- [ ] **Step 1: Write `cleancensus/vacancy.py`**

```python
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
```

- [ ] **Step 2: Verify file was created**

```powershell
Test-Path "cleancensus/vacancy.py"
```

Expected: `True`

---

## Task 2: Wire Config (`cleancensus/config.py`)

**Files:**
- Modify: `cleancensus/config.py` (lines 17, 163-168)

- [ ] **Step 1: Add `derived_vacancy` field to the `Config` dataclass**

In `cleancensus/config.py`, find:
```python
    derived_tenure: bool
```
Replace with:
```python
    derived_tenure: bool
    derived_vacancy: bool
```

- [ ] **Step 2: Wire `derived_vacancy` in `load_config`**

In `cleancensus/config.py`, find:
```python
        derived_tenure=bool(harmonize.get("derived_tenure", False)),
```
Replace with:
```python
        derived_tenure=bool(harmonize.get("derived_tenure", False)),
        derived_vacancy=bool(harmonize.get("derived_vacancy", False)),
```

---

## Task 3: Wire Pipeline (`cleancensus/pipeline.py`)

**Files:**
- Modify: `cleancensus/pipeline.py`

- [ ] **Step 1: Add `_vacancy_complete` helper function**

In `cleancensus/pipeline.py`, find:
```python
def _tenure_complete(cfg: Config) -> bool:
    import pyarrow.parquet as pq

    out100 = _final_100m_path(cfg)
    if not out100.exists():
        return False
    names = set(pq.ParquetFile(out100).schema_arrow.names)
    return "EigentuemerHH_Tenure_100m-Gitter" in names
```
Replace with (add the new function immediately after the existing one):
```python
def _tenure_complete(cfg: Config) -> bool:
    import pyarrow.parquet as pq

    out100 = _final_100m_path(cfg)
    if not out100.exists():
        return False
    names = set(pq.ParquetFile(out100).schema_arrow.names)
    return "EigentuemerHH_Tenure_100m-Gitter" in names


def _vacancy_complete(cfg: Config) -> bool:
    import pyarrow.parquet as pq

    out100 = _final_100m_path(cfg)
    if not out100.exists():
        return False
    names = set(pq.ParquetFile(out100).schema_arrow.names)
    return "BewohntWhg_Leerstand_100m-Gitter" in names
```

- [ ] **Step 2: Add `vacancy` stage entry to `REGISTRY` tuple**

In `cleancensus/pipeline.py`, find:
```python
    Stage("tenure", "derive owner/renter households from Eigentuemerquote",
          lambda cfg: cfg.derived_tenure, None, _tenure_complete),  # run set below
    Stage("sanity", "invariant checks on the produced output",
```
Replace with:
```python
    Stage("tenure", "derive owner/renter households from Eigentuemerquote",
          lambda cfg: cfg.derived_tenure, None, _tenure_complete),  # run set below
    Stage("vacancy", "derive occupied/vacant dwellings from Leerstandsquote",
          lambda cfg: cfg.derived_vacancy, None, _vacancy_complete),  # run set below
    Stage("sanity", "invariant checks on the produced output",
```

- [ ] **Step 3: Add `_run_vacancy` function and wire it into `_RUN`**

In `cleancensus/pipeline.py`, find:
```python
def _run_tenure(cfg: Config):
    from cleancensus.tenure import run_tenure
    run_tenure(cfg)
```
Replace with:
```python
def _run_tenure(cfg: Config):
    from cleancensus.tenure import run_tenure
    run_tenure(cfg)


def _run_vacancy(cfg: Config):
    from cleancensus.vacancy import run_vacancy
    run_vacancy(cfg)
```

In `cleancensus/pipeline.py`, find:
```python
    "tenure": _run_tenure,
    "sanity": _run_sanity,
```
Replace with:
```python
    "tenure": _run_tenure,
    "vacancy": _run_vacancy,
    "sanity": _run_sanity,
```

- [ ] **Step 4: Wire `_vacancy_complete` into `_IS_COMPLETE`**

In `cleancensus/pipeline.py`, find (it's inside the `_IS_COMPLETE` dict literal at the bottom):
```python
    "regiostar": _regiostar_complete,
}
```
Replace with:
```python
    "regiostar": _regiostar_complete,
    "vacancy": _vacancy_complete,
}
```

---

## Task 4: Update `config.example.toml`

**Files:**
- Modify: `config.example.toml`

- [ ] **Step 1: Add `derived_vacancy` line**

In `config.example.toml`, find:
```toml
derived_tenure = true          # owner/renter households derived from Eigentuemerquote
```
Replace with:
```toml
derived_tenure = true          # owner/renter households derived from Eigentuemerquote
derived_vacancy = false        # occupied/vacant dwellings derived from Leerstandsquote (universe A anchor, ~3% below official B)
```

---

## Task 5: Write tests (`tests/test_vacancy.py`)

**Files:**
- Create: `tests/test_vacancy.py`

- [ ] **Step 1: Create `tests/test_vacancy.py`**

```python
"""Unit tests for cleancensus/vacancy.py.

Tests cover:
- Derivation arithmetic at 1km (clip, signal rule, occupied+vacant == anchor)
- Signal rule: quote==0 & dwellings>0 yields zeros (parent-share fill handled downstream)
- Config: derived_vacancy defaults to False
- Stage order: vacancy appears after tenure, before sanity in STAGE_NAMES
"""
import textwrap

import numpy as np
import pandas as pd
import pytest

from cleancensus.vacancy import (
    build_parent_vacancy,
    QUOTE_1,
    DWG_ADJ_1,
    OCC_1,
    VAC_1,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_df1(quotes, dwg_adj, g10=None):
    """Build a minimal 1km DataFrame for build_parent_vacancy."""
    n = len(quotes)
    return pd.DataFrame({
        "GITTER_ID_1km": [f"1kmN{i}E{i}" for i in range(n)],
        "GITTER_ID_10km": g10 if g10 is not None else ["10kmA"] * n,
        QUOTE_1: quotes,
        DWG_ADJ_1: dwg_adj,
    })


# ---------------------------------------------------------------------------
# Arithmetic tests
# ---------------------------------------------------------------------------

def test_basic_derivation():
    """quote=10 & dwg=100 -> vacant=10, occupied=90."""
    df = _make_df1(quotes=[10.0], dwg_adj=[100.0])
    result = build_parent_vacancy(df)
    assert float(result[VAC_1].iloc[0]) == pytest.approx(10.0, abs=0.01)
    assert float(result[OCC_1].iloc[0]) == pytest.approx(90.0, abs=0.01)


def test_sum_equals_anchor():
    """occupied + vacant == DWG_adj for all rows."""
    quotes = [0.0, 5.0, 10.0, 50.0, 0.0]
    dwg = [0.0, 200.0, 100.0, 50.0, 300.0]
    df = _make_df1(quotes=quotes, dwg_adj=dwg)
    result = build_parent_vacancy(df)
    total = result[OCC_1] + result[VAC_1]
    adj = pd.to_numeric(result[DWG_ADJ_1], errors="coerce").fillna(0.0)
    np.testing.assert_allclose(total.values, adj.values, atol=0.1)


def test_quote_clipped_above_100():
    """quote > 100 is clipped to 100; vacant <= dwg always."""
    df = _make_df1(quotes=[150.0], dwg_adj=[100.0])
    result = build_parent_vacancy(df)
    assert float(result[VAC_1].iloc[0]) <= float(result[DWG_ADJ_1].iloc[0]) + 0.01
    assert float(result[OCC_1].iloc[0]) >= -0.01


def test_zero_dwellings_yields_zero():
    """quote=5 & dwg=0 -> both occupied and vacant are 0."""
    df = _make_df1(quotes=[5.0], dwg_adj=[0.0])
    result = build_parent_vacancy(df)
    assert float(result[VAC_1].iloc[0]) == pytest.approx(0.0, abs=0.01)
    assert float(result[OCC_1].iloc[0]) == pytest.approx(0.0, abs=0.01)


def test_signal_rule_zero_quote_with_dwellings():
    """quote==0 & dwg>0 -> no local signal; group-mean fill is applied.
    With a single 10km group, the fill uses the group mean of the signal cells."""
    # Cell 0: has signal (quote=10, dwg=100)
    # Cell 1: no signal (quote=0, dwg=50) -> gets group mean fill
    df = _make_df1(
        quotes=[10.0, 0.0],
        dwg_adj=[100.0, 50.0],
        g10=["10kmA", "10kmA"],
    )
    result = build_parent_vacancy(df)
    # Group mean = 10.0 (only cell 0 has signal)
    # Cell 1: vacant = 10.0/100 * 50 = 5.0
    assert float(result[VAC_1].iloc[1]) == pytest.approx(5.0, abs=0.1)
    assert float(result[OCC_1].iloc[1]) == pytest.approx(45.0, abs=0.1)


def test_no_negatives():
    """Occupied (dwg - vacant) is always clipped to >= 0."""
    # Even if due to float error the subtraction would go negative, clip guards it.
    quotes = [100.0, 99.9, 0.1, 50.0]
    dwg = [100.0, 100.0, 100.0, 0.0]
    df = _make_df1(quotes=quotes, dwg_adj=dwg)
    result = build_parent_vacancy(df)
    assert float(result[OCC_1].min()) >= -0.01


def test_output_dtype_float32():
    """Output columns are float32."""
    df = _make_df1(quotes=[4.3], dwg_adj=[1000.0])
    result = build_parent_vacancy(df)
    assert result[VAC_1].dtype == np.float32
    assert result[OCC_1].dtype == np.float32


# ---------------------------------------------------------------------------
# Config wiring
# ---------------------------------------------------------------------------

def test_derived_vacancy_default_false(tmp_path):
    """derived_vacancy defaults to False when not set in config."""
    p = tmp_path / "config.toml"
    p.write_text("", encoding="utf-8")
    from cleancensus.config import load_config
    cfg = load_config(p)
    assert cfg.derived_vacancy is False


def test_derived_vacancy_can_be_enabled(tmp_path):
    """derived_vacancy=true in [harmonize] is parsed correctly."""
    p = tmp_path / "config.toml"
    p.write_text(textwrap.dedent("""
        [harmonize]
        derived_vacancy = true
    """), encoding="utf-8")
    from cleancensus.config import load_config
    cfg = load_config(p)
    assert cfg.derived_vacancy is True


# ---------------------------------------------------------------------------
# Stage order
# ---------------------------------------------------------------------------

def test_stage_order_vacancy_after_tenure_before_sanity():
    from cleancensus.pipeline import STAGE_NAMES
    names = list(STAGE_NAMES)
    assert "vacancy" in names
    assert names.index("vacancy") > names.index("tenure")
    assert names.index("vacancy") < names.index("sanity")


def test_registry_includes_vacancy():
    from cleancensus.pipeline import STAGE_NAMES
    assert STAGE_NAMES == (
        "merge", "totals", "ages", "gemeinde", "gender", "topics8",
        "aggs", "regiostar", "extend", "tenure", "vacancy", "sanity",
    )
```

---

## Task 6: Update existing tests

**Files:**
- Modify: `tests/test_pipeline.py`
- Modify: `tests/test_config.py`

- [ ] **Step 1: Update `test_registry_order_and_completeness` in `tests/test_pipeline.py`**

In `tests/test_pipeline.py`, find:
```python
def test_registry_order_and_completeness():
    assert STAGE_NAMES == (
        "merge", "totals", "ages", "gemeinde", "gender", "topics8",
        "aggs", "regiostar", "extend", "tenure", "sanity",
    )
    # implemented stages (R3: merge+totals; R4: ages; R5: gemeinde+gender; R6: aggs+regiostar+topics8+extend)
    impl = {s.name: s.implemented for s in REGISTRY}
    assert impl["merge"]    # R3: z22data ingest path
    assert impl["totals"]   # R3: population totals collapse + adjust
    assert impl["ages"]     # R4: single-year age decomposition
    assert impl["gemeinde"] # R5: Gemeinde/ARS join
    assert impl["gender"]   # R5: male/female split + orphan backfill
    assert impl["extend"] and impl["tenure"] and impl["sanity"]
    assert impl["topics8"] and impl["aggs"] and impl["regiostar"]
```
Replace with:
```python
def test_registry_order_and_completeness():
    assert STAGE_NAMES == (
        "merge", "totals", "ages", "gemeinde", "gender", "topics8",
        "aggs", "regiostar", "extend", "tenure", "vacancy", "sanity",
    )
    # implemented stages (R3: merge+totals; R4: ages; R5: gemeinde+gender; R6: aggs+regiostar+topics8+extend)
    impl = {s.name: s.implemented for s in REGISTRY}
    assert impl["merge"]    # R3: z22data ingest path
    assert impl["totals"]   # R3: population totals collapse + adjust
    assert impl["ages"]     # R4: single-year age decomposition
    assert impl["gemeinde"] # R5: Gemeinde/ARS join
    assert impl["gender"]   # R5: male/female split + orphan backfill
    assert impl["extend"] and impl["tenure"] and impl["vacancy"] and impl["sanity"]
    assert impl["topics8"] and impl["aggs"] and impl["regiostar"]
```

Also update `test_default_plan_only_extend_runs` to check vacancy is disabled:

In `tests/test_pipeline.py`, find:
```python
    assert actions["tenure"] == "skip-disabled"
    assert actions["sanity"] == "run"
```
Replace with:
```python
    assert actions["tenure"] == "skip-disabled"
    assert actions["vacancy"] == "skip-disabled"
    assert actions["sanity"] == "run"
```

Also update `test_producer_stages_constant_matches_registry`:

In `tests/test_pipeline.py`, find:
```python
    assert "tenure" not in PRODUCER_STAGES and "sanity" not in PRODUCER_STAGES
```
Replace with:
```python
    assert "tenure" not in PRODUCER_STAGES
    assert "vacancy" not in PRODUCER_STAGES
    assert "sanity" not in PRODUCER_STAGES
```

- [ ] **Step 2: Add `derived_vacancy` default test to `tests/test_config.py`**

In `tests/test_config.py`, find:
```python
def test_defaults(tmp_path):
    cfg = load_config(_write(tmp_path, ""))
    assert cfg.topics == ["Whg_Gebaeudetyp", "HH_Seniorenstatus"]
    assert cfg.mode == "national"
    assert cfg.sanity == "fail"
    assert cfg.derived_tenure is False
    assert cfg.version_tag == "v2"
    assert cfg.out_1.name == "cells_1km_with_binneds_v2.parquet"
```
Replace with:
```python
def test_defaults(tmp_path):
    cfg = load_config(_write(tmp_path, ""))
    assert cfg.topics == ["Whg_Gebaeudetyp", "HH_Seniorenstatus"]
    assert cfg.mode == "national"
    assert cfg.sanity == "fail"
    assert cfg.derived_tenure is False
    assert cfg.derived_vacancy is False
    assert cfg.version_tag == "v2"
    assert cfg.out_1.name == "cells_1km_with_binneds_v2.parquet"
```

---

## Task 7: Run tests to verify all pass

- [ ] **Step 1: Run the full test suite**

```powershell
uv run --no-sync pytest -q
```

Expected: all tests pass (171+ before adding tests; now 171+ new tests from test_vacancy.py). No failures. Note: some tests requiring actual data files may be skipped — that is expected.

- [ ] **Step 2: Run just the new vacancy tests**

```powershell
uv run --no-sync pytest tests/test_vacancy.py -v
```

Expected: all tests PASS.

- [ ] **Step 3: Run pipeline tests to confirm STAGE_NAMES updated**

```powershell
uv run --no-sync pytest tests/test_pipeline.py tests/test_config.py -v
```

Expected: all PASS.

---

## Task 8: ZGB Subset Validation Run

- [ ] **Step 1: Write temporary config file**

Create `data/work/config_vaczgb_temp.toml` with content:

```toml
[data]
inputs_dir  = "data/inputs"
outputs_dir = "data/outputs"
version_tag = "vaczgb"

[harmonize]
topics = ["HH_Seniorenstatus"]
derived_tenure = false
derived_vacancy = true

[scope]
mode = "subset"
ars_prefixes = ["03101", "03102", "03103", "03151", "03153", "03154", "03157", "03158"]

[run]
sanity = "warn"
write_manifest = false
```

- [ ] **Step 2: Run the pipeline with the temp config**

```powershell
uv run --no-sync cleancensus --config data/work/config_vaczgb_temp.toml
```

Expected output to include lines like:
```
[pipeline] vacancy: run
[vacancy-1km] inhabited=... | quote present=... | filled from 10km group=... | filled national mean=...
[vacancy-100m] inhabited=... | local signal=... | no signal (parent-share fill)=...
[vacancy] wrote subset ... (+2 cols, ... rows)
[OK ] occupied+vacant == DWG_adj ...
[OK ] occupied+vacant == DWG_adj (non-orphan) ...
[OK ] no NaN
[OK ] no negatives
[OK ] 1km vacant margin (echo) ...
0 failures
```

Note: The subset national vacancy share check is NOT run (only triggered in national mode). Inspect the subset vacancy rate manually:

```powershell
uv run --no-sync python -c "
import pandas as pd
from pathlib import Path

stem = 'cells_100m_with_gender_backf_binneds_happyorphans_with_aggs_regiostar_vaczgb'
p = Path('data/outputs') / (stem + '_SUBSET.parquet')
df = pd.read_parquet(p, columns=['BewohntWhg_Leerstand_100m-Gitter', 'LeerstehendWhg_Leerstand_100m-Gitter', 'Insgesamt_Wohnungen_Wohnungen_nach_Zahl_der_Raeume_100m-Gitter_adj'])
occ = df['BewohntWhg_Leerstand_100m-Gitter'].sum()
vac = df['LeerstehendWhg_Leerstand_100m-Gitter'].sum()
tot = df['Insgesamt_Wohnungen_Wohnungen_nach_Zahl_der_Raeume_100m-Gitter_adj'].sum()
print(f'Occupied: {occ:.0f}, Vacant: {vac:.0f}, Total anchor: {tot:.0f}')
print(f'Subset vacancy rate: {vac/(occ+vac)*100:.2f}%')
print(f'occ+vac: {occ+vac:.0f} vs anchor: {tot:.0f} (diff: {abs(occ+vac-tot):.1f})')
"
```

- [ ] **Step 3: Delete temp config and vaczgb outputs**

```powershell
Remove-Item "data/work/config_vaczgb_temp.toml"
Get-ChildItem "data/outputs" -Filter "*vaczgb*" | Remove-Item
```

Verify cleanup:

```powershell
Get-ChildItem "data/outputs" -Filter "*vaczgb*"
```

Expected: no output (empty).

---

## Task 9: Commit

- [ ] **Step 1: Stage all changed files**

```powershell
git add cleancensus/vacancy.py cleancensus/config.py cleancensus/pipeline.py config.example.toml tests/test_vacancy.py tests/test_pipeline.py tests/test_config.py
```

- [ ] **Step 2: Commit**

```powershell
git commit -m "feat: vacancy (Leerstand) derived topic — occupied/vacant dwellings anchored to harmonized dwelling totals (P3)"
```

Expected: commit succeeds, all pre-commit hooks pass.

---

## Self-Review Checklist

**Spec coverage:**
- [x] Ratios: `Leerstandsquote_Leerstandsquote_{1km,100m}-Gitter` — investigated, confirmed present, used
- [x] Anchor: `Insgesamt_Wohnungen_Wohnungen_nach_Zahl_der_Raeume_*_adj` — confirmed present at both levels
- [x] Universe A vs B documented in module docstring
- [x] Signal rule: same as tenure (quote>0 = signal) — confirmed valid from investigation (4.26% weighted national rate)
- [x] New columns: `BewohntWhg_Leerstand_{1km,100m}-Gitter`, `LeerstehendWhg_Leerstand_{1km,100m}-Gitter`
- [x] Config: `derived_vacancy = false` default, wired in Config dataclass + load_config + config.example.toml
- [x] Pipeline: stage `vacancy` after `tenure`, before `sanity`
- [x] check_vacancy: occupied+vacant == anchor_adj, national rate [0.03, 0.06], no NaN/negatives, 1km echo
- [x] ZGB validation run with temp config, paste log, delete afterward
- [x] tests/test_vacancy.py: arithmetic, clip, signal rule, config default, stage order
- [x] test_pipeline.py / test_config.py updated

**Placeholder scan:** No TBD, no "add appropriate..." patterns found.

**Type consistency:**
- `OCC_1`, `VAC_1`, `OCC_100`, `VAC_100` constants defined once in `vacancy.py` and imported in tests
- `SPEC` uses same constant names
- `DWG_ADJ_100` is the `child_row_total_col` in SPEC — matches what `check_vacancy` reads
- `_vacancy_complete` checks for `"BewohntWhg_Leerstand_100m-Gitter"` which equals `OCC_100` — consistent
