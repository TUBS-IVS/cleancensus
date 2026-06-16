# Tier-3 Gemeinde/Kreis Controls Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `employed` + `schulabschluss` + `beruflabschluss` as **Kreis**-geography PopulationSim controls (Tier-3), MiD-only, measure-gain gated.

**Architecture:** cleancensus generates + imports the Kreis marginal tables; eqasim derives the three person attributes from MiD (`P_TAET`/`bildung1`/`bildung2`), adds a `tier3_controls()` catalog block (KREIS geography), wires KREIS-geography census sourcing, and gates each control through `popsim_validation`.

**Tech Stack:** Python 3, pandas, PopulationSim; cleancensus tests via `uv run pytest`; eqasim tests via `uv run pytest` (test-only env). ANSI-free.

**Spec:** `docs/superpowers/specs/2026-06-16-tier3-gemeinde-controls-design.md`
**Repos:** cleancensus (Phase 1) + eqasim-bs (Phases 2-4, on a fresh branch off `origin/main`).

---

## File Structure

- **cleancensus** — `cleancensus/gemeinde_controls.py` (exists; generation), no code change expected; a documented import step into eqasim-data.
- **eqasim `braunschweig/popsim/attributes.py`** — add `map_schulabschluss` + `map_beruflabschluss`; align `map_employed`.
- **eqasim `braunschweig/popsim/control_spec.py`** — add `_TIER3_*_ENTRIES` + `tier3_controls()`; extend `full_catalog`.
- **eqasim `braunschweig/popsim/<controls-builder>`** (stage.py / prepared_cells.py / folders.py) — KREIS-geography census sourcing (Task 3.0; exact module confirmed by the spike).
- **eqasim `braunschweig/analysis/popsim_validation/`** — register the 3 controls.
- **Tests:** `tests/test_popsim_education_attributes.py`, `tests/test_popsim_tier3_controls.py`.

---

## Phase 1 — cleancensus: generate + import the Kreis tables

### Task 1.1: Generate the Kreis control tables + verify ZGB coverage

**Files:** none (run + verify)

- [ ] **Step 1:** Generate the tables.
  Run: `uv run cleancensus --config config_e2e.toml --gemeinde-controls`
  Expected: writes `data/outputs/gemeinde_controls/{kreis_erwerbsstatus,kreis_schulabschluss,kreis_berufl_abschluss}.parquet` (and the Gemeinde-level ones). Log lines report per-table coverage.

- [ ] **Step 2:** Verify the 8 ZGB Kreise are present + unsuppressed for employment.
```python
import pandas as pd
ARS = {"03101","03102","03103","03151","03153","03154","03157","03158"}  # BS/SZ/WOB + 5 LK
df = pd.read_parquet("data/outputs/gemeinde_controls/kreis_erwerbsstatus.parquet")
k = df[df["ARS"].astype(str).str[:5].isin(ARS)]
assert set(k["ARS"].astype(str).str[:5]) == ARS, sorted(set(k["ARS"].astype(str).str[:5]))
assert k["ERWERBSTAT_KURZ_STP__11"].notna().all()  # Erwerbstätige present for all 8
print(k[["ARS","Name","ERWERBSTAT_KURZ_STP","ERWERBSTAT_KURZ_STP__11"]])
```
  Expected: 8 Kreise, all with a non-null Erwerbstätige count. (Repeat the notna check for `SCHULABS_STP__24` and `BERUFABS_AUSF_STP__1`; note any Bildung Kreis-cell suppression for the design's coarse aggregation.)

### Task 1.2: Import the Kreis tables to eqasim-data

**Files:** none (documented copy + provenance)

- [ ] **Step 1:** Copy the 3 `kreis_*.parquet` into the canonical eqasim-data controls path (the same location the Familientyp import used; confirm via the eqasim config key for Gemeinde/Kreis controls). Record the source commit + date in the eqasim `DATA_LAYOUT` note (provenance, like the prior import).
- [ ] **Step 2:** Commit the provenance note on the cleancensus branch.
```bash
git add docs/  # provenance note if added here
git commit -m "docs(tier3): record Kreis control-table generation + eqasim import provenance"
```

---

## Phase 2 — eqasim: MiD education + employment attributes

*(On the eqasim branch. Pattern mirror: the existing `SPC_BY_P_BKAT` dict + `logging.getLogger(__name__)` + `.map(...).fillna(...)` in `attributes.py`.)*

### Task 2.0: Confirm the MiD bildung crosswalk from the Codeplan

**Files:** none (codebook confirmation → fills the dicts in 2.1/2.2)

- [ ] **Step 1:** Read the MiD 2023 Codeplan B1 entries for `bildung1` and `bildung2`; record code→label. Validate against the measured national distribution (anchor):
  `bildung1`: 1:51793 · 2:58083 · 3:92189 · 4:208278 · 5:8712 · 9:1924 ·
  `bildung2`: 1:164631 · 2:114785 · 3:21427 · 4:8220 · 5:44299 · 9:2635 · 206:24568 · 402:40414.
- [ ] **Step 2:** Fill `SCHULABS_BY_BILDUNG1` (→ low/mid/high) and `BERUFABS_BY_BILDUNG2` (→ none/vocational/tertiary) in 2.1/2.2 with the confirmed codes. The provisional mappings below are the starting point — overwrite if the Codeplan disagrees.

### Task 2.1: `map_schulabschluss` (bildung1 → 3-class)

**Files:** Modify `braunschweig/popsim/attributes.py`; Test `tests/test_popsim_education_attributes.py`

- [ ] **Step 1: Failing test**
```python
import pandas as pd
from braunschweig.popsim.attributes import map_schulabschluss

def test_schulabschluss_three_class():
    persons = pd.DataFrame({"bildung1": [1, 3, 4, 5, 9]})
    out = map_schulabschluss(persons.copy())
    # provisional codebook mapping (Task 2.0 confirms): 1/2 low, 3 mid, 4 high, 5 low(ohne), 9 -> NaN
    assert list(out["schulabschluss"].fillna("NA")) == ["low", "mid", "high", "low", "NA"]
```
- [ ] **Step 2: Run** `uv run pytest tests/test_popsim_education_attributes.py::test_schulabschluss_three_class -v` → FAIL (function undefined).
- [ ] **Step 3: Implement** (append to `attributes.py`)
```python
# MiD bildung1 (Schulabschluss) -> 3-class {low, mid, high}. Codes per MiD 2023
# Codeplan B1 (confirmed in Task 2.0); validated vs the national distribution.
SCHULABS_BY_BILDUNG1 = {1: "low", 2: "low", 3: "mid", 4: "high", 5: "low"}  # 9 (k.A.) -> NaN

def map_schulabschluss(persons):
    """Add a 3-class ``schulabschluss`` {low, mid, high} from MiD ``bildung1``.
    k.A. (9) -> NaN (handled by the item-nonresponse imputation policy)."""
    import logging
    logger = logging.getLogger(__name__)
    out = persons.copy()
    mapped = out["bildung1"].map(SCHULABS_BY_BILDUNG1)
    n_na = int(mapped.isna().sum())
    logger.info("schulabschluss: %d/%d persons unmapped (k.A.) -> imputed downstream",
                n_na, len(out))
    out["schulabschluss"] = mapped
    return out
```
- [ ] **Step 4: Run** the test → PASS.
- [ ] **Step 5: Commit** `git add -A && git commit -m "feat(popsim): map_schulabschluss (MiD bildung1 -> 3-class)"`

### Task 2.2: `map_beruflabschluss` (bildung2 → 3-class, exclude 206/402)

**Files:** Modify `braunschweig/popsim/attributes.py`; Test `tests/test_popsim_education_attributes.py`

- [ ] **Step 1: Failing test**
```python
from braunschweig.popsim.attributes import map_beruflabschluss

def test_beruflabschluss_excludes_structural():
    persons = pd.DataFrame({"bildung2": [1, 4, 5, 9, 206, 402]})
    out = map_beruflabschluss(persons.copy())
    # 1 vocational, 4 tertiary, 5 none, 9 -> NaN(impute), 206/402 -> NaN(15+ exclude)
    assert list(out["beruflabschluss"].fillna("NA")) == ["vocational","tertiary","none","NA","NA","NA"]
```
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement**
```python
# MiD bildung2 (berufl. Abschluss) -> 3-class {none, vocational, tertiary}. Structural
# 206 (proxy) / 402 (children) and 9 (k.A.) -> NaN (excluded from the 15+ control universe
# / imputed). Codes per MiD 2023 Codeplan B1 (confirmed Task 2.0).
BERUFABS_BY_BILDUNG2 = {1: "vocational", 2: "vocational", 3: "tertiary",
                        4: "tertiary", 5: "none"}  # 9/206/402 -> NaN

def map_beruflabschluss(persons):
    """Add a 3-class ``beruflabschluss`` {none, vocational, tertiary} from MiD ``bildung2``.
    Structural 206/402 + k.A. 9 -> NaN (excluded / imputed)."""
    import logging
    logger = logging.getLogger(__name__)
    out = persons.copy()
    out["beruflabschluss"] = out["bildung2"].map(BERUFABS_BY_BILDUNG2)
    logger.info("beruflabschluss: %d/%d unmapped (k.A./structural 206/402) -> excluded/imputed",
                int(out["beruflabschluss"].isna().sum()), len(out))
    return out
```
- [ ] **Step 4: Run** → PASS. **Step 5: Commit** `feat(popsim): map_beruflabschluss (MiD bildung2 -> 3-class, 15+)`

### Task 2.3: Align `employed` to Zensus Erwerbstätige

**Files:** Modify `braunschweig/popsim/attributes.py` (`EMPLOYED_TAET` / `map_employed`); Test `tests/test_popsim_education_attributes.py`

- [ ] **Step 1:** Confirm from the Codeplan whether Zensus *Erwerbstätige* == MiD `P_TAET ∈ {1..7}` or excludes code 7 (freiwilliger Wehrdienst). Record the decision inline.
- [ ] **Step 2: Failing test** asserting the chosen set (example keeps 1..6 employed, 7 excluded — adjust per Step 1):
```python
from braunschweig.popsim.attributes import map_employed
def test_employed_matches_erwerbstaetige():
    persons = pd.DataFrame({"P_TAET":[1,6,7,11], "alter_gr1":[3,3,3,3]})
    out = map_employed(persons.copy())
    assert list(out["employed"]) == [True, True, False, False]  # if 7 excluded
```
- [ ] **Step 3:** Adjust `EMPLOYED_TAET` accordingly (or leave 1..7 if Step 1 confirms it). **Step 4: Run** → PASS. **Step 5: Commit.**

### Task 2.4: Wire the new mappers into the attribute pipeline

**Files:** Modify the popsim attribute-assembly call site (where `map_employed` etc. are invoked — `assembly.py` or `attributes.py` orchestrator).

- [ ] **Step 1:** Add `map_schulabschluss(...)` + `map_beruflabschluss(...)` to the same pipeline that calls `map_employed`. **Step 2:** Run `uv run pytest tests/test_popsim_socioprofessional.py tests/test_spc_attribute.py tests/test_popsim_education_attributes.py -q` → all green. **Step 3: Commit.**

---

## Phase 3 — eqasim: Tier-3 catalog controls (KREIS geography)

### Task 3.0: KREIS-geography census sourcing (spike + wire)

**Files:** `braunschweig/popsim/control_spec.py` (GEO_KREIS exists), `braunschweig/popsim/folders.py` (geography handling — the in-sync note at control_spec.py:56), the controls builder (`stage.py build_controls_df` / `prepared_cells.py`).

- [ ] **Step 1 (spike):** Read `folders.py` geography handling + the controls builder (`build_controls_df` / `build_control_totals` / `prepared_cells.add_aggregated_controls`). Determine how cell-level (`ZENSUS100m/1km`) marginals are sourced today, and what's missing to source a **KREIS** marginal from the imported `kreis_*` tables joined on `ARS[:5]` via the cell→Kreis cross-walk. Write findings as a 10-line comment block in the PR description.
- [ ] **Step 2:** Implement KREIS sourcing: for `geography == GEO_KREIS`, resolve each control's `census_source` columns from the imported Kreis table (keyed by Kreis ARS), emit the per-Kreis target. Reuse `build_aggregation_map` for multi-column coarse classes (e.g. school `high` = `SCHULABS_STP__24`; vocational = sum of `BERUFABS_AUSF_STP__11/12/13`). Add a focused unit test with a 2-Kreis synthetic table asserting the rendered per-Kreis targets.
- [ ] **Step 3:** Run the new sourcing test → PASS. **Step 4: Commit** `feat(popsim): KREIS-geography census sourcing for Tier-3`.

### Task 3.1: `tier3_controls()` catalog block

**Files:** Modify `braunschweig/popsim/control_spec.py`; Test `tests/test_popsim_tier3_controls.py`

- [ ] **Step 1: Failing test**
```python
from braunschweig.popsim.control_spec import tier3_controls, GEO_KREIS, controls_for_seed

def test_tier3_controls_kreis_mid_only():
    cat = tier3_controls()
    names = {c.name for c in cat}
    assert {"employed","schulabschluss_low","schulabschluss_mid","schulabschluss_high",
            "beruflabschluss_none","beruflabschluss_vocational","beruflabschluss_tertiary"} <= names
    assert all(c.geography == GEO_KREIS for c in cat)
    assert all(c.seed_table == "persons" for c in cat)
    # MiD expresses all; ENTD drops all (entd=None)
    assert len(controls_for_seed(cat, "mid")) == len(cat)
    assert len(controls_for_seed(cat, "entd")) == 0
```
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** (append to `control_spec.py`, mirroring `tier2_controls`)
```python
# Tier-3 person-level controls at KREIS geography (MiD-only; ENTD=None -> dropped).
# census_source names the imported Kreis-table columns (cleancensus gemeinde_controls).
_TIER3_ENTRIES = (
    # (name, census_source cols, mid expression)
    ("employed", ("ERWERBSTAT_KURZ_STP__11",), "(persons.employed == True)"),
    ("schulabschluss_low",  ("SCHULABS_STP__21","SCHULABS_STP__22","SCHULABS_STP__3"),
     "(persons.schulabschluss == 'low')"),
    ("schulabschluss_mid",  ("SCHULABS_STP__23",), "(persons.schulabschluss == 'mid')"),
    ("schulabschluss_high", ("SCHULABS_STP__24",), "(persons.schulabschluss == 'high')"),
    ("beruflabschluss_none", ("BERUFABS_AUSF_STP__2",), "(persons.beruflabschluss == 'none')"),
    ("beruflabschluss_vocational",
     ("BERUFABS_AUSF_STP__11","BERUFABS_AUSF_STP__12","BERUFABS_AUSF_STP__13"),
     "(persons.beruflabschluss == 'vocational')"),
    ("beruflabschluss_tertiary",
     ("BERUFABS_AUSF_STP__14","BERUFABS_AUSF_STP__15","BERUFABS_AUSF_STP__16","BERUFABS_AUSF_STP__17"),
     "(persons.beruflabschluss == 'tertiary')"),
)

def tier3_controls() -> List[CatalogControl]:
    """Tier-3: employment + education controls at KREIS geography (MiD-only).

    7 controls (1 employed + 3 schulabschluss + 3 beruflabschluss), each at GEO_KREIS,
    persons table. ENTD cannot express them (entd=None -> dropped by controls_for_seed).
    Multi-column census_source classes are materialised via build_aggregation_map.
    """
    catalog: List[CatalogControl] = []
    for name, source_cols, mid_expr in _TIER3_ENTRIES:
        catalog.append(
            CatalogControl(
                name=name, geography=GEO_KREIS, seed_table=SEED_TABLE_PERSONS,
                importance=1000, census_source=source_cols,
                seed_expressions={"mid": mid_expr, "entd": None},
            )
        )
    return catalog
```
- [ ] **Step 4: Run** → PASS. **Step 5: Commit** `feat(popsim): tier3_controls (employment + education, KREIS, MiD-only)`

### Task 3.2: Wire `tier3` into `full_catalog`

**Files:** Modify `braunschweig/popsim/control_spec.py` (`full_catalog`); Test `tests/test_popsim_tier3_controls.py`

- [ ] **Step 1: Failing test**
```python
from braunschweig.popsim.control_spec import full_catalog
def test_full_catalog_includes_tier3():
    base = {c.name for c in full_catalog(("tier0",))}
    with3 = {c.name for c in full_catalog(("tier0","tier3"))}
    assert "employed" in with3 and "employed" not in base
```
- [ ] **Step 2: Run** → FAIL. **Step 3:** add `if "tier3" in include_tiers: catalog.extend(tier3_controls())` to `full_catalog` (+ update its docstring). **Step 4: Run** → PASS. **Step 5: Commit.**

---

## Phase 4 — eqasim: measure-gain gate

### Task 4.1: Register the 3 controls in popsim_validation

**Files:** Modify `braunschweig/analysis/popsim_validation/` (the control registry); Test the existing validation test.

- [ ] **Step 1:** Add `employed`, `schulabschluss`, `beruflabschluss` to the realized-vs-target registry (target = the Kreis marginals; realized = synthetic population aggregated to Kreis). **Step 2:** Run the validation test suite → green. **Step 3: Commit.**

### Task 4.2: Gated run — add one control at a time

**Files:** none (run + record)

- [ ] **Step 1:** Single-Kreis run (03101) with `control_tiers: tier0,1,2` (baseline) → record SRMSE/coverage/grade + IPF convergence + max household-weight ratio.
- [ ] **Step 2:** Add `employed` only (`tier3` with just the employed control via a temporary filter) → re-run → record the delta. Keep if it improves.
- [ ] **Step 3:** Add `schulabschluss`, then `beruflabschluss`, one at a time; **drop any control whose addition does not improve fit** (RMSE improvement < ~2pp or convergence/weight-ratio degrades). Log the kept set.
- [ ] **Step 4:** Full-region validation run with the kept Tier-3 set; record grades. **Step 5:** PR on eqasim-bs origin.

---

## Self-Review

- **Spec coverage:** universe 15+ (2.2 excludes 206/402) ✓ · Kreis geography (3.0) ✓ · employed (2.3) ✓ · schulabschluss (2.1) ✓ · beruflabschluss (2.2) ✓ · CatalogControls MiD-only (3.1) ✓ · measure-gain gate (4.2) ✓ · cleancensus import (1.x) ✓ · students-not-a-control (no task — correct, it's a non-goal). All covered.
- **Residual investigation (flagged, not a lazy placeholder):** Task 2.0 (codebook code→class — provisional dicts given + validation anchors) and Task 3.0 (KREIS sourcing — named files + the cell→Kreis-join capability) are genuine spike-then-implement tasks; every other task is code-complete.
- **Type consistency:** `schulabschluss` values {low,mid,high}; `beruflabschluss` {none,vocational,tertiary}; `employed` bool — used identically in the mappers (2.1/2.2/2.3) and the control expressions (3.1). `tier3_controls`/`full_catalog("tier3")` names match across 3.1/3.2/4.1. ✓
- **YAGNI:** Gemeinde-level + Studierende + combined `bildung` are non-goals; only the 7 Kreis controls + the gate.
