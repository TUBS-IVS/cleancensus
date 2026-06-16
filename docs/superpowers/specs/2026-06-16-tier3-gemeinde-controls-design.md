---
title: Tier-3 Gemeinde/Kreis PopulationSim controls — employment + education
date: 2026-06-16
status: Draft — awaiting user review
repos: cleancensus (table generation + import) + eqasim-bs (attributes, catalog, gate)
---

# Tier-3 controls — design

## Goal

Add **employment** and **education** as PopulationSim controls (Tier-3), fitted at **Kreis**
geography, after the Tier-0–2 controls (age×sex, household size/type, tenure, building_type).
Three controls: `employed` (binary), `schulabschluss` (3-class), `beruflabschluss` (3-class).

## Feasibility (verified by spike, 2026-06-16)

- **employment — ready.** `employed` is already derived in popsim (`attributes.map_employed`
  from MiD `P_TAET`). Zensus Erwerbsstatus Kreis marginals are **0% suppressed** (BS/SZ/WOB
  kreisfrei → Kreis == Stadt; the 5 surrounding Landkreise have exact Kreis rows).
- **education — confirmed present in MiD.** The raw `MiD2023_Personen.csv` carries
  `bildung1` (school) and `bildung2` (vocational), already in the donor frame (`load_seed`
  reads the full CSV; they were simply unused). Observed value counts (national MiD):
  - `bildung1`: 1:51,793 · 2:58,083 · 3:92,189 · 4:208,278 · 5:8,712 · 9:1,924 (k.A.)
    → **5 substantive levels** (the `GEMEINDE_CONTROLS.md` doc assumed 4 — crosswalk must be
    re-derived from the MiD 2023 Codeplan B1, validated against this distribution).
  - `bildung2`: 1:164,631 · 2:114,785 · 3:21,427 · 4:8,220 · 5:44,299 · 9:2,635 ·
    **206:24,568 · 402:40,414** → 5 substantive + structural **206 (proxy) / 402 (children)**.
    The 206/402 codes confirm the control **universe is persons 15+** — exactly the Zensus
    Schulabschluss/berufl. universe; those rows are excluded from the control.
  - (`bildung`, a combined 6-level variable, also exists — a possible single-variable
    alternative; see Open items.)
- **students — NOT a control** (decision): no residence-based Zensus marginal isolates
  enrolled Studierende (only place-of-study Hochschulstatistik, wrong geography), and student
  status is largely pinned by the age control. Kept as the existing `studies`/`student`
  attribute (`P_TAET ∈ {8,9,10}`), not fitted.

## Design

### Universe & geography
- **Universe:** persons **15+** (drop MiD structural codes 206/402; matches the Zensus 15+
  education/Erwerbsstatus universe).
- **Geography:** **Kreis** (exact). Gemeinde-level (`--fill harmonize`, estimated) is a
  **non-goal for v1** — added later only if a measure-gain check on the 5 Landkreise justifies
  the extra resolution.

### The three controls (coarse — collinearity-safe per the overspec warning)
1. **`employed`** — binary (Erwerbstätig vs not).
   - Census: `ERWERBSTAT_KURZ_STP__11` (Erwerbstätige) vs (total 15+ − Erwerbstätige).
   - MiD: existing `employed`. **Open:** align `employed` (currently `P_TAET ∈ 1..7`) to the
     Zensus *Erwerbstätige* (ILO employed) definition — verify whether 1..7 == Erwerbstätige or
     needs narrowing (e.g. exclude code 7 freiwilliger Wehrdienst). Decide in the plan.
2. **`schulabschluss`** — 3-class `{low, mid, high}` from `bildung1`.
   - Census (`SCHULABS`): `__21`+`__22`+`__3` → low (Haupt/POS/ohne); `__23` → mid (Mittlere
     Reife); `__24` → high (Hochschulreife). `__1` (noch in schulischer Ausbildung) → folded
     into the universe per its completed level, or excluded (decide via codebook).
   - MiD: `bildung1` codes → the same 3 classes (codebook-grounded; validated vs the observed
     distribution above). k.A. (9) → existing item-nonresponse imputation policy.
3. **`beruflabschluss`** — 3-class `{none, vocational, tertiary}` from `bildung2`.
   - Census (`BERUFABS`): `__11`+`__12`+`__13` → vocational (Lehre/Fachschule); `__14`+`__15`+
     `__16`+`__17` → tertiary (Bachelor/Master/Diplom/Promotion); `__2` → none.
   - MiD: `bildung2` codes → the same 3 classes; structural 206/402 → excluded (15+); k.A. (9)
     → imputation policy.

### Components (units, by repo)
- **cleancensus** — `gemeinde_controls` (parser exists): generate the `kreis_erwerbsstatus`,
  `kreis_schulabschluss`, `kreis_berufl_abschluss` parquets (`--gemeinde-controls`), then a
  documented **import** to the canonical eqasim-data controls path (like the prior Familientyp
  import). No new cleancensus parsing code expected — verify the 3 kreis tables cover the 8 ZGB
  Kreise.
- **eqasim `attributes.py`** — add `map_schulabschluss(bildung1)` and
  `map_beruflabschluss(bildung2)` (codebook-grounded dicts, like `SPC_BY_P_BKAT`); `employed`
  exists. Each returns the coarse class; 206/402 → NaN (excluded); 9 → imputed.
- **eqasim `control_spec.py`** — three new `CatalogControl`s (geography=`Kreis`,
  `census_source` = the imported kreis tables with a multi-column aggregation into the coarse
  classes — reuse the `building_type` 3-class aggregation capability; per-seed expr = **MiD
  only**, ENTD drops via `controls_for_seed`, logged). Tier label **tier3**.
- **measure-gain gate** — add controls **one at a time** (`employed` → `schulabschluss` →
  `beruflabschluss`); score with `popsim_validation` (realized-vs-target SRMSE / coverage /
  grade) **plus** IPF convergence rate and max household-weight ratio; **drop any control that
  doesn't improve** (the doc's anti-overspec rule). Document the kept set.

### Data flow
Kreis census marginals (imported) + MiD-derived 15+ person classes → `CatalogControl` →
`build_controls_df` → PopulationSim IPF → `popsim_validation` report.

### Error handling
- Suppression: Erwerbsstatus Kreis 0%; Schulabschluss/berufl. Kreis residue (~0.8% / ~3.9%,
  fine gender×Promotion splits) — affected Kreis cells with no target fall back to no-control
  for that cell (coarse 3-class aggregation largely avoids the fine-split suppression).
- Missing: k.A. (9) → existing group-wise item-nonresponse imputation; structural 206/402 →
  excluded from the control universe (present on the frame for reference).
- ENTD seed: education/employment controls not expressible → dropped with a log line (no
  silent fallback).

## Testing
- Attribute mappers: codebook cases for `bildung1`/`bildung2` → 3 classes; 206/402 → NaN; 9 → imputed.
- `CatalogControl` rendering per seed (MiD renders 3; ENTD drops them, logged); tier0 stays
  byte-identical (empty aggregation_map guard).
- Measure-gain: validation grades improve for kept controls; convergence + max weight ratio logged.
- End-to-end: a single-Kreis run (e.g. 03101) with tier0–3, baseline guard green.

## Non-goals (v1)
- Gemeinde-level (`--fill`) controls; **Studierende** control; education granularity beyond
  3-class; ENTD education/employment controls; any change to the income or spatial-tilt layers.

## Open items (resolve in the plan)
1. **MiD codebook crosswalk** for `bildung1` (5 codes) and `bildung2` (5 codes) → the 3 classes,
   validated against the observed distributions above. Decide `bildung1=__1` (still-in-school)
   handling. Evaluate the combined `bildung` (6-level) variable as a single-source alternative.
2. **`employed` ↔ Erwerbstätige (ILO)** definitional alignment (P_TAET 1..7 vs the census
   Erwerbstätige category).
3. Bildung Kreis suppression residue handling under the coarse aggregation.
4. Confirm the 3 `kreis_*` tables cover all 8 ZGB Kreise after generation.
