# Harmonize Building & Extra Census Topics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the prepared Zensus-2022 100m cell parquet with harmonized (`*_adj`-consistent) topics that are directly controllable via MiD household data — default scope: Wohnungen nach Gebäudetyp (`haustyp`) + Seniorenstatus (`HP_ALTER_1..6`) — using the exact same hierarchical trust-blended IPF method already applied to the 8 existing topics. All other un-harmonized topics remain available as an opt-in catalog.

**Architecture:** The proven machinery lives in `other_binned_data.ipynb` cell 1 (TrustBlend → normalize 10km cats → `make_child_totals_adj` → `downscale_topic` raking → orphan imputation → streamed parquet append). We extract it verbatim into an importable module, add a declarative spec table for the new topics, and run the same two-stage cascade 10km→1km→100m. Output = additive new columns on top of the existing files (`*_v2.parquet`); nothing existing is modified, so all downstream popsim consumers keep working unchanged.

**Tech Stack:** Python 3.13 (uv project `cleancensus`), pandas, numpy, pyarrow (streaming writer), tqdm, pytest (new dev dep).

---

## Background / verified facts (2026-06-10)

- `eqasim-data/.../cells/zensus2022_grid_100m_de_prepared.parquet` is a byte-identical rename of `T:\petre\UCFL\Synthetic Population\popsimprep_NI_260128\inputs\cells_100m_with_gender_backf_binneds_happyorphans_with_aggs_regiostar.parquet` (7,718,813,319 bytes, 3,148,482 rows × 570 cols, 4 row groups, arrow 23.0.0).
- 9 `*_adj` totals exist (POP_TOTAL + 8 topics). For each existing topic, sum(categories) == `*_adj` total holds **exactly** (0 cells off across 3.15M rows).
- Inputs for the cascade all exist:
  - 10km: `T:\petre\UCFL\Synthetic Population\Zensus\merged\df10_with_single_years.pickle` (3,824 rows × 346 cols)
  - 1km: `T:\petre\UCFL\Synthetic Population\Zensus\with_other_binned_data\cells_1km_with_binneds.parquet` (348 cols, has the 1km `*_adj` totals from the previous run)
  - 100m: the prepared parquet above (has `GITTER_ID_1km`, `is_orphan`)
- All new topics exist at all three levels (10km / 1km / 100m) with identical naming except the `_<level>-Gitter` suffix.
- **Universe map** (global sums, raw):
  - Gebäude universe = 19,116,274 — identical per cell across Gebäudetyp/AnzahlWohnungen/Baujahr topics (verified per cell, 0 off); Heizungsart(Gebäude) shares it and is ALREADY harmonized (`_adj` exists, sum 19,953,844).
  - Wohnungen universe A = 41,235,170 (Räume, Fläche — already `_adj`, per-cell equal).
  - Wohnungen universe B = 42,507,505 (Wohnung_Gebaeudetyp_Groesse and Heizungsart(6 cats, Wohnungen) — both un-harmonized, **different universe than A** — do NOT anchor them to the Räume `_adj`).
  - Haushalte universe: Groesse_des_privaten_Haushalts + Typ_priv_HH_Lebensform already `_adj`; Seniorenstatus + Typ_priv_HH_Familie are not.
  - Personen universe: Familienstand/Geburtsland already `_adj` (≈ POP_TOTAL_100m_adj); Staatsangehoerigkeit(2/6/4 cats) + Religion are not.
  - Familien universe: Grosse_Kernfamilie + Typ_der_Kernfamilie are not harmonized (own totals).
- Ratio/average columns (Eigentuemerquote, durchschnMieteQM, Durchschnittsalter, DurchschnHHGroesse, Flaeche je Bewohner/Wohnung, Anteil*) are NOT counts → cannot be raked; they stay as-is.

## Scope decision (MiD-checked, 2026-06-10)

**User rule:** only harmonize topics that can be controlled DIRECTLY via the MiD household
data AND were collected for ALL households (Grundgesamtheit rule, see
`eqasim-bs/.claude/worktrees/popsim-g5/docs/data/MID2023_HANDBOOK_REFERENCE.md` §3).

MiD ground truth (checked against the actual ZGB delivery headers `MiD2023_Haushalte.csv` /
`MiD2023_Personen.csv` and `MiD2023_Codepläne_B1_Standard_v1.1.xlsx`, sheet Haushalte):

| Census topic | MiD household variable | Verdict |
|---|---|---|
| Wohnung_Gebaeudetyp_Groesse (10) | `haustyp` — GEOCODED (Raumbezug Siedlungsblock), all HH: 1=Ein-/Zweifamilienhaus, 2=Mehrfamilienhaus, 3=Geschosswohnungsbau, 4=sonstiges, 95=nicht zuzuordnen | **HARMONIZE (default)** — crosswalk: haustyp 1 ↔ {FreiEFH, EFH_DHH, EFH_Reihenhaus, Freist_ZFH, ZFH_DHH, ZFH_Reihenhaus}; 2+3 ↔ {MFH_3bis6, MFH_7bis12, MFH_13undmehr}; 4 ↔ AndererGebaeudetyp |
| Seniorenstatus (3) | `HP_ALTER_1..6` — household interview, ages of ALL members (H_GR is capped at 6 in MiD) → nur/mit/ohne Senioren (65+) exactly derivable | **HARMONIZE (default)** |
| HH-Größe categories | `H_GR` | already `_adj` — no harmonization needed; control add is an eqasim-side change |
| Eigentum/Miete | `H_MIETE` (asked, all private HH) | census has only the Eigentuemerquote RATIO, no count topic → nothing to harmonize; tenure goes via the existing eqasim spec |
| Geb_Gebaeudetyp / AnzahlWohnungen / Baujahr / Geb-Energieträger | — (no building-level MiD vars) | **skip (opt-in only)** |
| Heizungsart (Wohnungen) | — (no heating var in MiD) | **skip (opt-in only)** |
| Typ_priv_HH_Familie | no `hhtyp` in our delivery; only heuristic from HP_ALTER/HP_SEX counts | **skip (opt-in only)** |
| Staatsangehörigkeit / Religion / Kernfamilie | no P_STAAT (only `migration` proxy), no religion, no family vars | **skip (opt-in only)** |

Default run scope = `MID_CONTROLLABLE_DEFAULT = ("Whg_Gebaeudetyp", "HH_Seniorenstatus")`
→ 13 category columns + 2 `_adj` totals = 15 new columns. The full spec table (all topics)
stays in `new_topics.py` as an opt-in catalog via `--topics`.

Runtime expectation: 10km→1km is minutes; 1km→100m is the heavy stage (the original
8-topic national run took hours; 2 topics ≈ 1–2 h). Plan includes a fast ZGB-subset
validation run before the full national run.

---

## File Structure

The two canonical inputs are imported from `C:\Users\bienzeisler\Downloads\` into a clean,
gitignored `data/` tree inside the repo. Scripts only (the existing Jupyter notebooks stay
untouched — they are the colleague's original pipeline and the method reference).

```
cleancensus/
  paths.py                  # NEW – single source of truth for all data paths (repo-relative)
  harmonization.py          # NEW – verbatim extraction of notebook cell-1 functions (no behavior change)
  new_topics.py             # NEW – declarative spec catalog (default = MID_CONTROLLABLE_DEFAULT)
  extend_topics.py          # NEW – driver: stage A (10km→1km → 1km v2) + stage B (1km→100m → 100m v2)
  sanity_extend.py          # NEW – post-run invariant checks (row sums, universe equality, global sums, nulls)
  tests/
    test_harmonization.py   # NEW – characterization tests of the extracted machinery (synthetic fixtures)
    test_new_topics.py      # NEW – spec table validated against the real file schemas (skip if data absent)
  data/                     # NEW – gitignored
    inputs/
      cells_1km_with_binneds.parquet                                        # moved from Downloads (190 MB)
      cells_100m_with_gender_backf_binneds_happyorphans_with_aggs_regiostar.parquet  # moved from Downloads (7.7 GB)
      df10_with_single_years.pickle                                         # copied once from T:\ (small, 3,824 rows)
    outputs/
      cells_1km_with_binneds_v2.parquet                                     # stage A result
      cells_100m_..._regiostar_v2.parquet                                   # stage B result
  README.md                 # NEW – GitHub-ready project description (Task 9)
  *.ipynb                   # UNTOUCHED – original notebook pipeline (reference)
```

`paths.py` (created in Task 0b; everything imports from here):

```python
from pathlib import Path

REPO = Path(__file__).resolve().parent
DATA_IN = REPO / "data" / "inputs"
DATA_OUT = REPO / "data" / "outputs"

PATH_10 = DATA_IN / "df10_with_single_years.pickle"
PATH_1 = DATA_IN / "cells_1km_with_binneds.parquet"
PATH_100 = DATA_IN / "cells_100m_with_gender_backf_binneds_happyorphans_with_aggs_regiostar.parquet"
OUT_1_V2 = DATA_OUT / "cells_1km_with_binneds_v2.parquet"
OUT_100_V2 = DATA_OUT / "cells_100m_with_gender_backf_binneds_happyorphans_with_aggs_regiostar_v2.parquet"
```

---

### Task 0: Dev tooling (pytest)

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Add pytest as dev dependency**

Run: `uv add --dev pytest`
Expected: `pyproject.toml` gains `[dependency-groups] dev = ["pytest>=8"]` (uv default group) and `uv.lock` updates.

- [ ] **Step 2: Verify pytest runs (no tests yet)**

Run: `uv run pytest --collect-only -q`
Expected: `no tests ran` / collected 0 items, exit code 5 (acceptable — repo has no tests yet).

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "chore: add pytest dev dependency"
```

---

### Task 0b: Data import & clean layout

**Files:**
- Create: `paths.py` (content exactly as in File Structure above)
- Create: `.gitignore` entries
- Move/copy data into `data/`

- [ ] **Step 1: Create the data tree and .gitignore**

```bash
mkdir -p data/inputs data/outputs
```

Append to `.gitignore` (create if absent):

```
data/
*.parquet
*.pickle
zgb_parents.csv
stage_b_national.log
_cell*.py
.idea/
```

- [ ] **Step 2: Move the Downloads inputs (same volume → instant) and copy the 10km pickle from T:**

```powershell
Move-Item "C:\Users\bienzeisler\Downloads\cells_1km_with_binneds.parquet" "data\inputs\"
Move-Item "C:\Users\bienzeisler\Downloads\cells_100m_with_gender_backf_binneds_happyorphans_with_aggs_regiostar.parquet" "data\inputs\"
Copy-Item "T:\petre\UCFL\Synthetic Population\Zensus\merged\df10_with_single_years.pickle" "data\inputs\"
```

- [ ] **Step 3: Create `paths.py`** (verbatim from the File Structure section).

- [ ] **Step 4: Verify the imports are intact**

```python
# uv run python - <<'PY'
import pyarrow.parquet as pq
import pandas as pd
from paths import PATH_10, PATH_1, PATH_100
md100 = pq.ParquetFile(PATH_100).metadata
md1 = pq.ParquetFile(PATH_1).metadata
df10 = pd.read_pickle(PATH_10)
assert (md100.num_rows, md100.num_columns) == (3148482, 570), (md100.num_rows, md100.num_columns)
# NOTE: the Downloads 1km file has 256 cols = the T: version (348) minus the 101
# single-year AGE_* columns — irrelevant for topic harmonization. Verified 2026-06-10.
assert md1.num_columns == 256, md1.num_columns
assert len(df10) == 3824, len(df10)
print("inputs OK:", md100.num_rows, "x", md100.num_columns, "|", md1.num_rows, "x", md1.num_columns, "|", len(df10))
PY
```
Expected: `inputs OK: 3148482 x 570 | 212k-ish x 348 | 3824`.

- [ ] **Step 5: Verify git sees NO data files**

Run: `git status --porcelain`
Expected: only `paths.py`, `.gitignore` (and plan doc) listed — no parquet/pickle.

- [ ] **Step 6: Commit**

```bash
git add paths.py .gitignore
git commit -m "feat: repo-relative data layout + gitignored data tree, canonical inputs imported"
```

---

### Task 1: Extract the proven machinery into `harmonization.py`

The notebook's cell 1 is the reference implementation already validated by the existing 8 topics. Extract it **verbatim** (functions only, not the `__main__` block) so the driver and tests can import it. No edits to logic.

**Files:**
- Create: `harmonization.py`
- Source: `other_binned_data.ipynb` code cell index 1 (the cell starting with `# -*- coding: utf-8 -*-` / docstring "Generic hierarchical downscaling for NON-AGE categorical vectors")

- [ ] **Step 1: Extract cell 1 to a module file**

```python
# run as: uv run python - <<'PY'  (or save as scripts/_extract.py and run once)
import json, io, re
nb = json.load(open("other_binned_data.ipynb", encoding="utf-8"))
src = "".join(nb["cells"][1]["source"])
# keep everything BEFORE the __main__ runner block
cut = src.index('if __name__ == "__main__":')
header = (
    '"""Verbatim extraction of other_binned_data.ipynb cell 1 (machinery only).\n'
    'Do NOT edit logic here; this is the reference implementation already used\n'
    'for the 8 existing harmonized topics. Driver: extend_topics.py\n"""\n'
)
io.open("harmonization.py", "w", encoding="utf-8").write(header + src[:cut])
print("written", len(src[:cut]), "chars")
PY
```

Expected: `harmonization.py` created, ~30 KB, containing `TrustBlend`, `rake_to_margins`, `make_child_totals_adj`, `TopicSpec`, `_assert_topic_columns`, `_apply_topic_trust_blend`, `downscale_topic`, `levelize`, `_make_topic_prior_shares`, `normalize_parent_categories_for_specs`, `BLEND_STRONG/STD/WEAK`, `build_topic_specs_for_level`, `_require_parent_adj_for_child_total`, `apply_adj_for_all_topics`, `impute_orphan_rows_100m`.

- [ ] **Step 2: Verify it imports cleanly**

Run: `uv run python -c "import harmonization as h; print([n for n in ['TrustBlend','rake_to_margins','make_child_totals_adj','TopicSpec','downscale_topic','levelize','normalize_parent_categories_for_specs','apply_adj_for_all_topics','impute_orphan_rows_100m'] if not hasattr(h,n)])"`
Expected: `[]`

- [ ] **Step 3: Commit**

```bash
git add harmonization.py
git commit -m "feat: extract harmonization machinery from other_binned_data notebook (verbatim)"
```

---

### Task 2: Characterization tests for the machinery

These pin the behavior we rely on, using tiny synthetic fixtures. (The machinery already exists, so these are write-test→run-green characterization tests, not red-first TDD.)

**Files:**
- Create: `conftest.py` (empty — makes pytest put the repo root on `sys.path` so tests import the root modules)
- Create: `tests/test_harmonization.py`

- [ ] **Step 0: Create empty `conftest.py` at repo root**

```bash
touch conftest.py
```

- [ ] **Step 1: Write the tests**

```python
import numpy as np
import pandas as pd
import pytest

from harmonization import (
    TrustBlend, TopicSpec, rake_to_margins, make_child_totals_adj,
    downscale_topic, impute_orphan_rows_100m,
)


def test_rake_to_margins_hits_both_margins():
    X = np.array([[1.0, 1.0], [1.0, 1.0]])
    rows = np.array([10.0, 30.0])
    cols = np.array([15.0, 25.0])
    rake_to_margins(X, row_targets=rows, col_targets=cols)
    np.testing.assert_allclose(X.sum(axis=1), rows, atol=1e-8)
    np.testing.assert_allclose(X.sum(axis=0), cols, atol=1e-8)


def test_make_child_totals_adj_scales_group_to_parent():
    parent = pd.DataFrame({"PID": ["A"], "tot_adj": [100.0]})
    child = pd.DataFrame({"PID": ["A", "A"], "tot": [30.0, 50.0]})
    make_child_totals_adj(
        parent_df=parent, child_df=child,
        parent_id_col="PID", child_parent_id_col="PID",
        parent_adj_col="tot_adj", child_total_col="tot", out_col="tot_adj",
    )
    assert child["tot_adj"].sum() == pytest.approx(100.0)
    # shape preserved: 30/80 vs 50/80
    np.testing.assert_allclose(child["tot_adj"].values, [37.5, 62.5])


def test_make_child_totals_adj_equal_split_when_child_sum_zero():
    parent = pd.DataFrame({"PID": ["A"], "tot_adj": [10.0]})
    child = pd.DataFrame({"PID": ["A", "A"], "tot": [0.0, 0.0]})
    make_child_totals_adj(
        parent_df=parent, child_df=child,
        parent_id_col="PID", child_parent_id_col="PID",
        parent_adj_col="tot_adj", child_total_col="tot", out_col="tot_adj",
    )
    np.testing.assert_allclose(child["tot_adj"].values, [5.0, 5.0])


def _tiny_topic_frames():
    # one 1km parent with 2 categories, three 100m children
    parent = pd.DataFrame({
        "GITTER_ID_1km": ["P1"],
        "cat_a_1km": [60.0], "cat_b_1km": [40.0],
    })
    child = pd.DataFrame({
        "GITTER_ID_1km": ["P1", "P1", "P1"],
        "cat_a_100m": [10.0, 0.0, 5.0],
        "cat_b_100m": [0.0, 8.0, 5.0],
        "tot_adj":    [40.0, 30.0, 30.0],   # sums to parent total 100
    })
    spec = TopicSpec(
        name="tiny",
        parent_cat_cols=["cat_a_1km", "cat_b_1km"],
        child_cat_cols=["cat_a_100m", "cat_b_100m"],
        child_row_total_col="tot_adj",
        alpha=0.85, blend=TrustBlend(w_min=0.4, t_pc=5.0),
    )
    return parent, child, spec


def test_downscale_topic_satisfies_row_and_col_margins():
    parent, child, spec = _tiny_topic_frames()
    res = downscale_topic(
        parent_df=parent, child_df=child,
        parent_id_col="GITTER_ID_1km", child_parent_id_col="GITTER_ID_1km",
        spec=spec,
    )
    np.testing.assert_allclose(
        res[spec.child_cat_cols].sum(axis=1).values, child["tot_adj"].values, rtol=1e-6)
    np.testing.assert_allclose(
        res[spec.child_cat_cols].sum(axis=0).values, [60.0, 40.0], atol=1e-2)
    assert (res.values >= 0).all()


def test_impute_orphan_rows_scales_signal_to_total():
    df = pd.DataFrame({
        "is_orphan":  [False, False, True, True],
        "cat_a_100m": [60.0, 30.0, 1.0, 0.0],
        "cat_b_100m": [20.0, 10.0, 1.0, 0.0],
        "tot_adj":    [80.0, 40.0, 10.0, 6.0],
    })
    spec = TopicSpec(
        name="tiny", parent_cat_cols=["x", "y"],
        child_cat_cols=["cat_a_100m", "cat_b_100m"],
        child_row_total_col="tot_adj",
    )
    impute_orphan_rows_100m(df, specs=[spec], orphan_flag_col="is_orphan", verbose=False)
    # orphan with signal: scaled 1:1 -> 5/5
    np.testing.assert_allclose(df.loc[2, ["cat_a_100m", "cat_b_100m"]].values.astype(float), [5.0, 5.0])
    # orphan without signal: prior from non-orphans (90:30 = 3:1) -> 4.5/1.5
    np.testing.assert_allclose(df.loc[3, ["cat_a_100m", "cat_b_100m"]].values.astype(float), [4.5, 1.5], rtol=1e-5)
```

- [ ] **Step 2: Run the tests**

Run: `uv run pytest tests/test_harmonization.py -v`
Expected: 5 passed. If `test_downscale_topic_satisfies_row_and_col_margins` fails on the column-margin tolerance, loosen `atol` to `1e-1` ONLY for the column assert (the trust-blend deliberately allows small parent-margin slack; row totals are the hard constraint) and note it in the test docstring.

- [ ] **Step 3: Commit**

```bash
git add tests/test_harmonization.py
git commit -m "test: characterization tests for harmonization machinery"
```

---

### Task 3: Declarative spec table for the new topics (`new_topics.py`)

Exact column names below were read from the real schemas (100m parquet / 1km parquet / 10km pickle) on 2026-06-10. They follow the notebook convention: define 10km names, derive 1km/100m via `levelize`.

**Files:**
- Create: `new_topics.py`
- Test: `tests/test_new_topics.py`

- [ ] **Step 1: Write `new_topics.py`**

```python
"""Spec table for the additional topics to harmonize (extends the original 8).

Naming convention identical to other_binned_data.ipynb: base names carry the
10km suffix; levelize() swaps the suffix per level. Each topic keeps its OWN
total chain (universes differ; see plan Background)."""
from harmonization import TopicSpec, TrustBlend, levelize, BLEND_STD

# tier -> list of (name, total_col_10km, [category_cols_10km], alpha)
RAW_TOPICS = {
    1: [
        ("Geb_Gebaeudetyp",
         "Insgesamt_Gebaeude_Geb_Gebaeudetyp_Groesse_10km-Gitter",
         ["FreiEFH_Geb_Gebaeudetyp_Groesse_10km-Gitter",
          "EFH_DHH_Geb_Gebaeudetyp_Groesse_10km-Gitter",
          "EFH_Reihenhaus_Geb_Gebaeudetyp_Groesse_10km-Gitter",
          "Freist_ZFH_Geb_Gebaeudetyp_Groesse_10km-Gitter",
          "ZFH_DHH_Geb_Gebaeudetyp_Groesse_10km-Gitter",
          "ZFH_Reihenhaus_Geb_Gebaeudetyp_Groesse_10km-Gitter",
          "MFH_3bis6Wohnungen_Geb_Gebaeudetyp_Groesse_10km-Gitter",
          "MFH_7bis12Wohnungen_Geb_Gebaeudetyp_Groesse_10km-Gitter",
          "MFH_13undmehrWohnungen_Geb_Gebaeudetyp_Groesse_10km-Gitter",
          "AndererGebaeudetyp_Geb_Gebaeudetyp_Groesse_10km-Gitter"], 0.85),
        ("Geb_AnzahlWohnungen",
         "Insgesamt_Gebaeude_Gebaeude_nach_Anzahl_der_Wohnungen_10km-Gitter",
         ["1_Wohnung_Gebaeude_nach_Anzahl_der_Wohnungen_10km-Gitter",
          "2_Wohnungen_Gebaeude_nach_Anzahl_der_Wohnungen_10km-Gitter",
          "3bis6_Wohnungen_Gebaeude_nach_Anzahl_der_Wohnungen_10km-Gitter",
          "7bis12_Wohnungen_Gebaeude_nach_Anzahl_der_Wohnungen_10km-Gitter",
          "13undmehr_Wohnungen_Gebaeude_nach_Anzahl_der_Wohnungen_10km-Gitter"], 0.85),
        ("Geb_Baujahr",
         "Insgesamt_Gebaeude_Gebaeude_nach_Baujahr_in_MZ_Klassen_10km-Gitter",
         ["Vor1919_Gebaeude_nach_Baujahr_in_MZ_Klassen_10km-Gitter",
          "a1919bis1948_Gebaeude_nach_Baujahr_in_MZ_Klassen_10km-Gitter",
          "a1949bis1978_Gebaeude_nach_Baujahr_in_MZ_Klassen_10km-Gitter",
          "a1979bis1990_Gebaeude_nach_Baujahr_in_MZ_Klassen_10km-Gitter",
          "a1991bis2000_Gebaeude_nach_Baujahr_in_MZ_Klassen_10km-Gitter",
          "a2001bis2010_Gebaeude_nach_Baujahr_in_MZ_Klassen_10km-Gitter",
          "a2011bis2019_Gebaeude_nach_Baujahr_in_MZ_Klassen_10km-Gitter",
          "a2020undspaeter_Gebaeude_nach_Baujahr_in_MZ_Klassen_10km-Gitter"], 0.85),
        ("Geb_Energietraeger",
         "Insgesamt_Energietraeger_Gebaeude_nach_Energietraeger_der_Heizung_10km-Gitter",
         ["Gas_Gebaeude_nach_Energietraeger_der_Heizung_10km-Gitter",
          "Heizoel_Gebaeude_nach_Energietraeger_der_Heizung_10km-Gitter",
          "Holz_Holzpellets_Gebaeude_nach_Energietraeger_der_Heizung_10km-Gitter",
          "Biomasse_Biogas_Gebaeude_nach_Energietraeger_der_Heizung_10km-Gitter",
          "Solar_Geothermie_Waermepumpen_Gebaeude_nach_Energietraeger_der_Heizung_10km-Gitter",
          "Strom_Gebaeude_nach_Energietraeger_der_Heizung_10km-Gitter",
          "Kohle_Gebaeude_nach_Energietraeger_der_Heizung_10km-Gitter",
          "Fernwaerme_Gebaeude_nach_Energietraeger_der_Heizung_10km-Gitter",
          "kein_Energietraeger_Gebaeude_nach_Energietraeger_der_Heizung_10km-Gitter"], 0.85),
        ("Whg_Gebaeudetyp",
         "Insgesamt_Wohnungen_Wohnung_Gebaeudetyp_Groesse_10km-Gitter",
         ["FreiEFH_Wohnung_Gebaeudetyp_Groesse_10km-Gitter",
          "EFH_DHH_Wohnung_Gebaeudetyp_Groesse_10km-Gitter",
          "EFH_Reihenhaus_Wohnung_Gebaeudetyp_Groesse_10km-Gitter",
          "Freist_ZFH_Wohnung_Gebaeudetyp_Groesse_10km-Gitter",
          "ZFH_DHH_Wohnung_Gebaeudetyp_Groesse_10km-Gitter",
          "ZFH_Reihenhaus_Wohnung_Gebaeudetyp_Groesse_10km-Gitter",
          "MFH_3bis6Wohnungen_Wohnung_Gebaeudetyp_Groesse_10km-Gitter",
          "MFH_7bis12Wohnungen_Wohnung_Gebaeudetyp_Groesse_10km-Gitter",
          "MFH_13undmehrWohnungen_Wohnung_Gebaeudetyp_Groesse_10km-Gitter",
          "AndererGebaeudetyp_Wohnung_Gebaeudetyp_Groesse_10km-Gitter"], 0.85),
        ("Whg_Heizungsart",
         "Insgesamt_Heizungsart_Heizungsart_10km-Gitter",
         ["Fernheizung_Heizungsart_10km-Gitter",
          "Etagenheizung_Heizungsart_10km-Gitter",
          "Blockheizung_Heizungsart_10km-Gitter",
          "Zentralheizung_Heizungsart_10km-Gitter",
          "Einzel_Mehrraumoefen_Heizungsart_10km-Gitter",
          "keine_Heizung_Heizungsart_10km-Gitter"], 0.85),
    ],
    2: [
        ("HH_Seniorenstatus",
         "Insgesamt_Haushalte_Seniorenstatus_eines_privaten_Haushalts_10km-Gitter",
         ["HH_nurSenioren_Seniorenstatus_eines_privaten_Haushalts_10km-Gitter",
          "HH_mitSenioren_Seniorenstatus_eines_privaten_Haushalts_10km-Gitter",
          "HH_ohneSenioren_Seniorenstatus_eines_privaten_Haushalts_10km-Gitter"], 0.90),
        ("HH_Familientyp",
         "Insgesamt_Haushalte_Typ_priv_HH_Familie_10km-Gitter",
         ["EinpersHH_SingleHH_Typ_priv_HH_Familie_10km-Gitter",
          "Paare_ohneKind_Typ_priv_HH_Familie_10km-Gitter",
          "Paare_mitKind_Typ_priv_HH_Familie_10km-Gitter",
          "Alleinerziehende_Typ_priv_HH_Familie_10km-Gitter",
          "MehrpersHHohneKernfam_Typ_priv_HH_Familie_10km-Gitter"], 0.90),
        ("Pers_Staatsangehoerigkeit",
         "Insgesamt_Bevoelkerung_Staatsangehoerigkeit_10km-Gitter",
         ["Deutschland_Staatsangehoerigkeit_10km-Gitter",
          "Ausland_Sonstige_Staatsangehoerigkeit_10km-Gitter"], 0.90),
    ],
    3: [
        ("Pers_StaatsangGruppen",
         "Insgesamt_Bevoelkerung_Staatsangehoerigkeit_Gruppen_10km-Gitter",
         ["Deutschland_Staatsangehoerigkeit_Gruppen_10km-Gitter",
          "Ausland_Sonstige_Staatsangehoerigkeit_Gruppen_10km-Gitter",
          "EU27_Land_Staatsangehoerigkeit_Gruppen_10km-Gitter",
          "Sonstiges_Europa_Staatsangehoerigkeit_Gruppen_10km-Gitter",
          "Sonstige_Welt_Staatsangehoerigkeit_Gruppen_10km-Gitter",
          "Sonstige_Staatsangehoerigkeit_Gruppen_10km-Gitter"], 0.85),
        ("Pers_ZahlStaatsang",
         "Insgesamt_Bevoelkerung_Zahl_der_Staatsangehoerigkeiten_10km-Gitter",
         ["EineStaatsang_Zahl_der_Staatsangehoerigkeiten_10km-Gitter",
          "Mehrere_deutsch_und_auslaendisch_Zahl_der_Staatsangehoerigkeiten_10km-Gitter",
          "Mehrere_nur_auslaendisch_Zahl_der_Staatsangehoerigkeiten_10km-Gitter",
          "Nicht_bekannt_Zahl_der_Staatsangehoerigkeiten_10km-Gitter"], 0.85),
        ("Pers_Religion",
         "Insgesamt_Bevoelkerung_Religion_10km-Gitter",
         ["Roemisch_katholisch_Religion_10km-Gitter",
          "Evangelisch_Religion_10km-Gitter",
          "Sonstige_keine_ohneAngabe_Religion_10km-Gitter"], 0.85),
        ("Fam_Groesse",
         "Insgesamt_Familien_Grosse_Kernfamilie_bis6undmehrPers_10km-Gitter",
         ["a2Personen_Grosse_Kernfamilie_bis6undmehrPers_10km-Gitter",
          "a3Personen_Grosse_Kernfamilie_bis6undmehrPers_10km-Gitter",
          "a4Personen_Grosse_Kernfamilie_bis6undmehrPers_10km-Gitter",
          "a5Personen_Grosse_Kernfamilie_bis6undmehrPers_10km-Gitter",
          "a6Pers_und_mehr_Grosse_Kernfamilie_bis6undmehrPers_10km-Gitter"], 0.85),
        ("Fam_TypNachKindern",
         "Insgesamt_Familie_Typ_der_Kernfamilie_nach_Kindern_10km-Gitter",
         ["Ehep_ohneKind_Typ_der_Kernfamilie_nach_Kindern_10km-Gitter",
          "Ehep_mind_1Kind_unter18_Typ_der_Kernfamilie_nach_Kindern_10km-Gitter",
          "Ehep_Kinder_ab18_Typ_der_Kernfamilie_nach_Kindern_10km-Gitter",
          "EingetrLP_ohneKind_Typ_der_Kernfamilie_nach_Kindern_10km-Gitter",
          "EingetrLP_mind_1Kind_unter18_Typ_der_Kernfamilie_nach_Kindern_10km-Gitter",
          "EingetrLP_Kinder_ab18_Typ_der_Kernfamilie_nach_Kindern_10km-Gitter",
          "NichtehelLG_ohneKind_Typ_der_Kernfamilie_nach_Kindern_10km-Gitter",
          "NichtehelLG_mind_1Kind_unter18_Typ_der_Kernfamilie_nach_Kindern_10km-Gitter",
          "NichtehelLG_Kinder_ab18_Typ_der_Kernfamilie_nach_Kindern_10km-Gitter",
          "Vater_mind_1Kind_unter18_Typ_der_Kernfamilie_nach_Kindern_10km-Gitter",
          "Vater_Kinder_ab18_Typ_der_Kernfamilie_nach_Kindern_10km-Gitter",
          "Mutter_mind_1Kind_unter18_Typ_der_Kernfamilie_nach_Kindern_10km-Gitter",
          "Mutter_Kinder_ab18_Typ_der_Kernfamilie_nach_Kindern_10km-Gitter"], 0.85),
    ],
}

DEFAULT_TIERS = (1, 2)

# The only topics controllable DIRECTLY via MiD household data collected for ALL
# households (haustyp = geocoded building type; HP_ALTER_1..6 = member ages).
# Everything else in RAW_TOPICS is an opt-in catalog (--topics).
MID_CONTROLLABLE_DEFAULT = ("Whg_Gebaeudetyp", "HH_Seniorenstatus")


def build_new_topic_specs(level: str, tiers=DEFAULT_TIERS, names=None):
    """Mirror of build_topic_specs_for_level for the NEW topics.

    level: "1km" (parent 10km) or "100m" (parent 1km).
    names: optional explicit topic-name subset (overrides tiers).
    """
    specs = []
    for tier, topics in RAW_TOPICS.items():
        for name, tot_10, cats_10, alpha in topics:
            if names is not None:
                if name not in names:
                    continue
            elif tier not in tiers:
                continue
            if level == "1km":
                parent_cols, child_cols = cats_10, levelize(cats_10, "1km")
                child_total = tot_10.replace("_10km-Gitter", "_1km-Gitter")
            elif level == "100m":
                parent_cols, child_cols = levelize(cats_10, "1km"), levelize(cats_10, "100m")
                child_total = tot_10.replace("_10km-Gitter", "_100m-Gitter")
            else:
                raise ValueError(f"Unknown level: {level}")
            specs.append(TopicSpec(
                name=name, parent_cat_cols=parent_cols, child_cat_cols=child_cols,
                child_row_total_col=child_total, alpha=alpha, blend=BLEND_STD,
            ))
    return specs
```

- [ ] **Step 2: Write the schema-validation test**

```python
# tests/test_new_topics.py
import os
import pytest

from new_topics import RAW_TOPICS, build_new_topic_specs
from paths import PATH_10, PATH_1, PATH_100


def test_spec_shapes_consistent():
    for tier, topics in RAW_TOPICS.items():
        for name, tot, cats, alpha in topics:
            assert tot.endswith("_10km-Gitter"), name
            assert all(c.endswith("_10km-Gitter") for c in cats), name
            assert len(set(cats)) == len(cats), f"dup cats in {name}"
    s1 = build_new_topic_specs("1km", tiers=(1, 2, 3))
    s100 = build_new_topic_specs("100m", tiers=(1, 2, 3))
    assert len(s1) == len(s100) == sum(len(v) for v in RAW_TOPICS.values())
    for a, b in zip(s1, s100):
        assert len(a.parent_cat_cols) == len(a.child_cat_cols)
        assert len(b.parent_cat_cols) == len(b.child_cat_cols)


@pytest.mark.skipif(not os.path.exists(PATH_100), reason="prepared 100m parquet not reachable")
def test_specs_exist_in_100m_schema():
    import pyarrow.parquet as pq
    cols = set(f.name for f in pq.ParquetFile(PATH_100).schema_arrow)
    for spec in build_new_topic_specs("100m", tiers=(1, 2, 3)):
        assert spec.child_row_total_col in cols, spec.name
        missing = [c for c in spec.child_cat_cols if c not in cols]
        assert not missing, f"{spec.name}: {missing}"


@pytest.mark.skipif(not os.path.exists(PATH_1), reason="1km parquet not reachable")
def test_specs_exist_in_1km_schema():
    import pyarrow.parquet as pq
    cols = set(f.name for f in pq.ParquetFile(PATH_1).schema_arrow)
    for spec in build_new_topic_specs("100m", tiers=(1, 2, 3)):  # 100m specs -> parents are 1km cols
        missing = [c for c in spec.parent_cat_cols if c not in cols]
        assert not missing, f"{spec.name}: {missing}"
        # the 1km total needed by apply_adj at the 100m stage:
        assert spec.child_row_total_col.replace("_100m-Gitter", "_1km-Gitter") in cols, spec.name


@pytest.mark.skipif(not os.path.exists(PATH_10), reason="10km pickle not reachable")
def test_specs_exist_in_10km_frame():
    import pandas as pd
    cols = set(pd.read_pickle(PATH_10).reset_index().columns)
    for spec in build_new_topic_specs("1km", tiers=(1, 2, 3)):
        assert spec.child_row_total_col.replace("_1km-Gitter", "_10km-Gitter") in cols, spec.name
        missing = [c for c in spec.parent_cat_cols if c not in cols]
        assert not missing, f"{spec.name}: {missing}"
```

- [ ] **Step 3: Run the tests**

Run: `uv run pytest tests/test_new_topics.py -v`
Expected: 4 passed (or 1 passed + 3 skipped if T:/eqasim paths are unreachable from the test machine — they were reachable on 2026-06-10).

- [ ] **Step 4: Commit**

```bash
git add new_topics.py tests/test_new_topics.py
git commit -m "feat: declarative spec table for new building/household/nationality topics"
```

---

### Task 4: Driver stage A — 10km→1km (`extend_topics.py`, part 1)

Mirrors the notebook `__main__` 10km→1km block exactly, but only for the NEW specs, and writes `cells_1km_with_binneds_v2.parquet` (= old file + new `*_adj` totals + new downscaled categories).

**Files:**
- Create: `extend_topics.py`

- [ ] **Step 1: Write the driver (both stages in one file; stage B body comes in Task 5)**

```python
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
        stage_b(args.topics, args.parents_csv)  # Task 5


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Smoke-test stage A wiring on ONE small topic**

Run: `uv run python extend_topics.py stage_a --topics HH_Seniorenstatus`
Expected: `[norm] 'HH_Seniorenstatus' rows=3,824 | max rel.err=...`, `[adj] Created Insgesamt_Haushalte_Seniorenstatus_eines_privaten_Haushalts_1km-Gitter_adj`, progress bar over ~3.8k parents, then `wrote ...cells_1km_with_binneds_v2.parquet`. Runtime: a few minutes.

- [ ] **Step 3: Sanity-check the smoke output**

```python
# uv run python - <<'PY'
import pandas as pd, numpy as np
df = pd.read_parquet(r"T:\petre\UCFL\Synthetic Population\Zensus\with_other_binned_data\cells_1km_with_binneds_v2.parquet",
                     columns=["Insgesamt_Haushalte_Seniorenstatus_eines_privaten_Haushalts_1km-Gitter_adj",
                              "HH_nurSenioren_Seniorenstatus_eines_privaten_Haushalts_1km-Gitter",
                              "HH_mitSenioren_Seniorenstatus_eines_privaten_Haushalts_1km-Gitter",
                              "HH_ohneSenioren_Seniorenstatus_eines_privaten_Haushalts_1km-Gitter"])
s = df.iloc[:, 1:].sum(axis=1)
rel = (s - df.iloc[:, 0]).abs() / df.iloc[:, 0].clip(lower=1.0)
print("rows:", len(df), "max rel.err:", rel.max())
assert rel.max() < 2e-4
PY
```
Expected: `max rel.err` < 2e-4.

- [ ] **Step 4: Commit**

```bash
git add extend_topics.py
git commit -m "feat: stage A driver (10km->1km) for new topics"
```

---

### Task 5: Driver stage B — 1km→100m streamed (`extend_topics.py`, part 2)

Mirrors the notebook's memory-safe 100m block: load only needed columns, `apply_adj_for_all_topics` against the 1km v2 parents, downscale per topic, impute orphans inline (the original run did this in a separate "happyorphans" pass; the `is_orphan` flag already exists in the prepared file), then stream-append the new columns to the full 7.7 GB parquet.

**Files:**
- Modify: `extend_topics.py` (add `stage_b`)

- [ ] **Step 1: Add `stage_b` to `extend_topics.py`**

```python
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
```

- [ ] **Step 2: Verify the module still imports and args parse**

Run: `uv run python -c "import extend_topics; print('ok')"` and `uv run python extend_topics.py stage_b --help`
Expected: `ok`; help text shows `--parents-csv`.

- [ ] **Step 3: Commit**

```bash
git add extend_topics.py
git commit -m "feat: stage B driver (1km->100m streamed) with orphan imputation and subset mode"
```

---

### Task 6: Sanity checker (`sanity_extend.py`)

Mirrors notebook cell 3's role: hard invariants over the v2 outputs. Must pass before the v2 file is handed to eqasim.

**Files:**
- Create: `sanity_extend.py`

- [ ] **Step 1: Write the checker**

```python
"""Invariant checks for the extended (v2) cell files. Exit code 0 = all pass.

Usage: uv run python sanity_extend.py [--topics NAME ...] [--path-100 OVERRIDE]
"""
from __future__ import annotations
import argparse
import sys

import numpy as np
import pandas as pd

from new_topics import build_new_topic_specs, MID_CONTROLLABLE_DEFAULT
from paths import PATH_10, OUT_100_V2

FAIL = 0


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
        need.add(s.child_row_total_col)          # *_adj
        need.add(s.child_row_total_col[:-4])     # raw Insgesamt
        need.update(s.child_cat_cols)
    # cross-universe anchors already in the file:
    anchors = [
        "Insgesamt_Heizungsart_Gebaeude_nach_ueberwiegender_Heizungsart_100m-Gitter_adj",
        "Insgesamt_Haushalte_Groesse_des_privaten_Haushalts_100m-Gitter_adj",
        "POP_TOTAL_100m_adj",
    ]
    need.update(anchors)
    df = pd.read_parquet(args.path_100, columns=sorted(need))
    n = len(df)
    print(f"rows: {n:,}")

    # 1) per-topic: sum(categories) == *_adj total (the core harmonization invariant)
    for s in specs:
        cats = df[s.child_cat_cols].sum(axis=1)
        d = (cats - df[s.child_row_total_col]).abs()
        check(f"{s.name}: sum(cats)==adj", int((d > 0.5).sum()) == 0,
              f"max|d|={d.max():.4f} cells>0.5={(d > 0.5).sum()}")

    # 2) universe equality of *_adj totals across topics that share a universe
    def pair(a, b, label, tol=0.5):
        d = (df[a] - df[b]).abs()
        check(label, int((d > tol).sum()) == 0, f"max|d|={d.max():.4f}")

    by_name = {s.name: s for s in specs}
    if {"Geb_Gebaeudetyp", "Geb_AnzahlWohnungen"} <= by_name.keys():
        pair(by_name["Geb_Gebaeudetyp"].child_row_total_col,
             by_name["Geb_AnzahlWohnungen"].child_row_total_col, "Gebaeude adj: Typ==AnzWhg")
    if {"Geb_Gebaeudetyp", "Geb_Baujahr"} <= by_name.keys():
        pair(by_name["Geb_Gebaeudetyp"].child_row_total_col,
             by_name["Geb_Baujahr"].child_row_total_col, "Gebaeude adj: Typ==Baujahr")
    if "Geb_Gebaeudetyp" in by_name:
        pair(by_name["Geb_Gebaeudetyp"].child_row_total_col, anchors[0],
             "Gebaeude adj: new==existing Heizungsart(Geb) adj", tol=1.0)
    if {"Whg_Gebaeudetyp", "Whg_Heizungsart"} <= by_name.keys():
        pair(by_name["Whg_Gebaeudetyp"].child_row_total_col,
             by_name["Whg_Heizungsart"].child_row_total_col, "Wohnungen-B adj: Typ==Heizungsart")
    if "HH_Seniorenstatus" in by_name:
        pair(by_name["HH_Seniorenstatus"].child_row_total_col, anchors[1],
             "Haushalte adj: Seniorenstatus==HH_Groesse", tol=1.0)
    if "Pers_Staatsangehoerigkeit" in by_name:
        pair(by_name["Pers_Staatsangehoerigkeit"].child_row_total_col, anchors[2],
             "Personen adj: Staatsang==POP_TOTAL", tol=1.0)

    # 3) global mass: 100m adj sum vs 10km raw national sum per topic (within 2%)
    df10 = pd.read_pickle(PATH_10).reset_index(drop=False)
    for s in build_new_topic_specs("1km", names=args.topics):
        tot10 = s.child_row_total_col.replace("_1km-Gitter", "_10km-Gitter")
        nat = pd.to_numeric(df10[tot10], errors="coerce").fillna(0).sum()
        got = df[by_name[s.name].child_row_total_col].sum() if s.name in by_name else np.nan
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
```

- [ ] **Step 2: Verify it imports and fails gracefully without the v2 file**

Run: `uv run python -c "import sanity_extend; print('ok')"`
Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add sanity_extend.py
git commit -m "feat: post-run sanity checker for extended topics"
```

---

### Task 7: Fast validation run (ZGB subset) before the national run

The 1km→100m stage on all 3.15M cells takes hours; validate the whole chain on the ~2.4k ZGB 1km parents (~44k cells) first.

**Files:**
- Create: `zgb_parents.csv` (generated, not committed — add to .gitignore if absent)

- [ ] **Step 1: Run full stage A (default MiD-controllable scope, national — this stage is cheap)**

Run: `uv run python extend_topics.py stage_a`
Expected: 2 topics (Whg_Gebaeudetyp, HH_Seniorenstatus), ~3.8k parents each, finishes in minutes, writes `cells_1km_with_binneds_v2.parquet`.

- [ ] **Step 2: Build the ZGB parent list (ARS prefixes of the 8 ZGB Kreise, same rule as eqasim filter_zgb_cells)**

```python
# uv run python - <<'PY'
import pandas as pd
from paths import PATH_100
ZGB = ("03101", "03102", "03151", "03153", "03154", "03157", "03158", "03103")
df = pd.read_parquet(PATH_100, columns=["GITTER_ID_1km", "Kreis", "Land", "Regierungsbezirk"])
# Kreis key = Land(2)+RB(1)+Kreis(2) -> compare against 5-digit ARS prefixes
ars5 = (df["Land"].astype("Int64").astype(str).str.zfill(2)
        + df["Regierungsbezirk"].astype("Int64").astype(str).str.zfill(1)
        + df["Kreis"].astype("Int64").astype(str).str.zfill(2))
keep = df.loc[ars5.isin(ZGB), "GITTER_ID_1km"].drop_duplicates()
keep.to_csv("zgb_parents.csv", index=False, header=False)
print("ZGB 1km parents:", len(keep))
PY
```
Expected: ~2,400 parents (memory reference: 2,410). If the Land/RB/Kreis composition does not yield 5-digit ARS (check a few rows first), fall back to: take `GITTER_ID_1km` values from the eqasim popsim cache (braunschweig.popsim.cells output) instead.

- [ ] **Step 3: Run stage B on the subset**

Run: `uv run python extend_topics.py stage_b --parents-csv zgb_parents.csv`
Expected: `subset: ~2,400 parents, ~44,000 cells`, per-topic progress, orphan log lines, writes `..._prepared_v2_SUBSET.parquet`. Runtime: minutes.

- [ ] **Step 4: Sanity-check the subset**

Run: `uv run python sanity_extend.py --path-100 "data/outputs/cells_100m_with_gender_backf_binneds_happyorphans_with_aggs_regiostar_v2_SUBSET.parquet"`
Expected: all per-topic `sum(cats)==adj` checks OK; universe-equality checks OK. The "national mass" checks will FAIL on a subset by construction — ignore those lines here (they compare against national 10km sums).

- [ ] **Step 5: Review checkpoint — STOP and show the sanity output to the user before the national run.**

- [ ] **Step 6: Commit (scripts only, never data)**

```bash
git add .gitignore   # ensure zgb_parents.csv + *.parquet ignored
git commit -m "chore: ignore generated subset artifacts"
```

---

### Task 8: Full national run + final validation + handoff

- [ ] **Step 1: Run stage B nationally (multi-hour job — run in background)**

Run: `uv run python extend_topics.py stage_b 2>&1 | tee stage_b_national.log`
Expected: 2 topic progress bars over ~212k parents; `Diffcouter`/`Parent sum 0` echo lines per topic (mirroring the original run); final line `wrote ...zensus2022_grid_100m_de_prepared_v2.parquet (+15 new cols, 3,148,482 rows)`. Runtime ≈ 1–2 h.

- [ ] **Step 2: Run the full sanity check**

Run: `uv run python sanity_extend.py`
Expected: `0 failures`. Every per-topic invariant, universe equality, national mass within 2%, no NaN/negatives.

- [ ] **Step 3: Spot-compare before/after distributions (national, one building topic)**

```python
# uv run python - <<'PY'
import pandas as pd
from paths import PATH_100, OUT_100_V2
cats = ["FreiEFH_Wohnung_Gebaeudetyp_Groesse_100m-Gitter",
        "MFH_3bis6Wohnungen_Wohnung_Gebaeudetyp_Groesse_100m-Gitter",
        "AndererGebaeudetyp_Wohnung_Gebaeudetyp_Groesse_100m-Gitter",
        "HH_nurSenioren_Seniorenstatus_eines_privaten_Haushalts_100m-Gitter"]
a = pd.read_parquet(PATH_100, columns=cats).sum()
b = pd.read_parquet(OUT_100_V2, columns=cats).sum()
print(pd.DataFrame({"raw": a, "harmonized": b, "ratio": b / a}))
PY
```
Expected: ratios in a plausible band (~0.95–1.10, same magnitude as the existing Heizungsart adjustment 19.12M→19.95M ≈ 1.04). Large deviations (>1.2) on any category = investigate before handoff.

- [ ] **Step 4: Handoff notes (do NOT silently replace any v1 file)**

1. All v1 inputs stay untouched in `data/inputs/`; v2 outputs live in `data/outputs/`.
2. Distribution of the v2 100m file to consumers is MANUAL (ask user first):
   - eqasim-bs: copy as `eqasim-data/data/braunschweig/popsim/cells/zensus2022_grid_100m_de_prepared_v2.parquet` (keep v1), then update `eqasim-bs docs/population/DATA_LAYOUT.md` (name, origin = this plan, +15 columns).
   - T: mirror: `T:\petre\UCFL\Synthetic Population\popsimprep_NI_260128\inputs\` (per data-organization convention).
3. The eqasim-bs consumer switch (pointing popsim at v2 + adding the haustyp/Seniorenstatus controls) is a SEPARATE change on branch `feature/population-method-workflows`, governed by the existing spec `docs/superpowers/specs/2026-06-09-building-type-tenure-controls-design.md` and its measure-gain gate.

- [ ] **Step 5: Final commit**

```bash
git add -A   # scripts/docs only — data/ is gitignored
git commit -m "feat: harmonized Whg-Gebaeudetyp + Seniorenstatus topics (national run complete)"
```

---

### Task 9: GitHub-ready project polish

The repo goes public/shared: README, clean structure, notebooks untouched, no data committed. Do NOT push — committing locally is fine, pushing needs explicit user confirmation.

**Files:**
- Create: `README.md`
- Verify: `.gitignore`, `git status` clean of data

- [ ] **Step 1: Write `README.md`**

```markdown
# cleancensus

Preparation and harmonization of the German **Zensus 2022 grid data** (100m / 1km / 10km)
into consistent, analysis-ready cell tables — the spatial backbone for synthetic
population generation (PopulationSim / eqasim).

## What it does

The raw Zensus 2022 grid tables are perturbed for disclosure control: category counts do
not sum to the published totals, and the three grid levels disagree with each other. This
repo makes them consistent:

1. **Merge** all Zensus 2022 grid CSVs per level (10km / 1km / 100m).
2. **Adjust totals** across levels (IPF): population totals at each level are reconciled
   against the coarser level.
3. **Downscale topics** (`other_binned_data` method): per categorical topic
   (e.g. marital status, household size, dwelling size), a trust-blended IPF rakes the
   100m category vectors so that per cell `sum(categories) == adjusted total` and the
   1km category margins are respected. Adjusted totals get an `_adj` suffix.
4. **Orphan handling**: 100m cells without a 1km parent get prior-based imputation.
5. **Single-year ages + gender**: separate pipeline (`ages.ipynb`, `gender.ipynb`)
   produces `AGE_0..`, `M_AGE_*`, `F_AGE_*` columns.

## Repository layout

| Path | What |
|---|---|
| `*.ipynb` | Original pipeline notebooks (reference implementation; run history preserved) |
| `harmonization.py` | The downscaling machinery, extracted verbatim from `other_binned_data.ipynb` |
| `new_topics.py` | Spec catalog of additional topics; default scope = topics controllable via MiD household data (`Whg_Gebaeudetyp`, `HH_Seniorenstatus`) |
| `extend_topics.py` | Driver: `stage_a` (10km→1km), `stage_b` (1km→100m, streamed over the 7.7 GB file) |
| `sanity_extend.py` | Post-run invariant checks (exit code 0 = pass) |
| `paths.py` | Single source of truth for data locations (repo-relative, `data/` is gitignored) |
| `tests/` | pytest suite (synthetic fixtures + schema validation against the real files) |
| `data/inputs/`, `data/outputs/` | Local only, never committed |

## Usage

```bash
uv sync                                  # install deps (Python >= 3.13)
uv run pytest                            # tests
uv run python extend_topics.py stage_a   # 10km -> 1km (minutes)
uv run python extend_topics.py stage_b   # 1km -> 100m (national: ~1-2 h)
uv run python sanity_extend.py           # invariants; 0 failures required
```

Subset validation run (e.g. ZGB region) before a national run:
`extend_topics.py stage_b --parents-csv zgb_parents.csv`.

Other topics from the catalog: `--topics Geb_Baujahr Pers_Religion ...`
(see `new_topics.RAW_TOPICS`; default deliberately covers only what MiD household
data can control as PopulationSim targets).

## Data

Inputs are NOT in this repo (size + Zensus licensing). Required in `data/inputs/`:

| File | Source |
|---|---|
| `df10_with_single_years.pickle` | 10km merged Zensus tables (from `data_prep.ipynb`) |
| `cells_1km_with_binneds.parquet` | 1km cells incl. previous harmonization run |
| `cells_100m_with_gender_backf_binneds_happyorphans_with_aggs_regiostar.parquet` | the prepared 100m cell table (3.15M cells × 570 cols, all Germany) |

Note: zero values in harmonized columns can be true zeros OR disclosure-suppressed
values filled with 0 — they are indistinguishable downstream.

## Method invariants (checked by `sanity_extend.py`)

- per topic: `sum(categories) == Insgesamt_*_adj` per cell (hard, < 0.5 abs)
- topics sharing a universe have per-cell identical `_adj` totals
- national mass per topic within 2% of the 10km raw total
- no NaN / negatives in produced columns
```

- [ ] **Step 2: Verify repo state**

Run: `git status --porcelain` and `git check-ignore data/inputs -v && echo IGNORED`
Expected: no `data/` entries in status; `IGNORED` printed.

- [ ] **Step 3: Run the full test suite one last time**

Run: `uv run pytest -q`
Expected: all green (≈ 9+ passed).

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: GitHub-ready README"
```

(Pushing to origin requires explicit user confirmation — do not push.)

---

## Out of scope (tracked elsewhere)

- Wiring new controls into PopulationSim configs (eqasim-bs; building-type/tenure spec with measure-gain gate; controls = add reliable few + validate, not more=better). Seed expressions for the two new controls: `households.haustyp == 1` ↔ EFH/ZFH category group, `haustyp in (2,3)` ↔ MFH group, `haustyp == 4` ↔ sonstiges (handle 95 = nicht zuzuordnen observably); Seniorenstatus flags precomputed onto the households seed from `HP_ALTER_1..6` (treat 2xx/3xx/9xx missing codes per the MiD handbook missing-code rule).
- Adding HH-size-category controls (`H_GR` ↔ already-harmonized Groesse_des_privaten_Haushalts categories) — zero harmonization work, pure eqasim-side control add.
- MiD seed-availability check: DONE 2026-06-10 (see Scope decision table) — result is the reduced default scope.
- Ratio columns (Eigentuemerquote, Nettokaltmiete, …): usable as stratification/inputs as-is; tenure goes via the MiD `H_MIETE`-based design from the existing spec.
- Age topics (10er/5er classes): intentionally untouched — superseded by the single-year AGE_*/M_/F_ pipeline.
```
