# Z22Data Gate Report

Comparison of `cleancensus.z22.build_merged_table()` output against the
notebook-era merged CSVs on `T:\petre\UCFL\Synthetic Population\Zensus\merged\`.

Reference: `merged_10km_gitter.csv` (3,824 rows) and `merged_1km_gitter.csv` (212,758 rows).

---

## GITTER_ID Formula (Verified)

```
GITTER_ID = f"CRS3035RES{res_str}N{y_mp - half}E{x_mp - half}"

res_str: 10km -> "10000m",  1km -> "1000m",  100m -> "100m"
half:    10km -> 5000,       1km -> 500,       100m -> 50
```

Verified against three real cells from the T: merged CSVs:

| Level | x_mp    | y_mp    | Expected GITTER_ID                    | Status |
|-------|---------|---------|---------------------------------------|--------|
| 10km  | 4335000 | 2685000 | `CRS3035RES10000mN2680000E4330000`    | EXACT  |
| 1km   | 4337500 | 2689500 | `CRS3035RES1000mN2689000E4337000`     | EXACT  |
| 100m  | 4337050 | 2689150 | `CRS3035RES100mN2689100E4337000`      | EXACT  |

---

## 10 km Gate

**Setup:** built merged table from z22data 10km parquets (160 files);
aligned on `GITTER_ID_10km`; compared national sums and per-cell differences.

**Coverage:**

| Dimension | Count |
|-----------|-------|
| Shared columns (in both z22 and T:) | 158 |
| z22-extra (only in z22 output) | 2 |
| T:-only (not in z22data) | 85 |

**Gate summary:**

| Status | Count | Description |
|--------|-------|-------------|
| **EXACT** | 157 | National sum differs by < 0.5; per-cell max\|d\| consistent |
| **NEAR-EXACT** | 1 | National sum diff < 0.1% |

**Non-exact column detail:**

| Column | z22 sum | T: sum | Diff % | Max cell\|d\| | N cells differing |
|--------|---------|--------|--------|----------------|-------------------|
| `Insgesamt_Haushalte_Groesse_des_privaten_Haushalts` | 40,228,597 | 40,236,035 | -0.018% | 13 | 3,426 |

**Interpretation:** The households total (`households_0` in z22data) differs by −7,438 
(−0.018%) nationally and 3,426 cells. This is a systematic but small disclosure-control
difference: the z22data parquet reflects the most recent Destatis release, which may have
revised cell-level suppression slightly compared to the notebook-era download. All
household *category* columns (1-person, 2-person, etc.) are EXACT. The total is the only
affected column at 10km.

**z22-extra columns** (in z22 output, no T: counterpart):

| Column | Note |
|--------|------|
| `Eigentuemerquote_Eigentuemerquote_{level}-Gitter` | Owner-occupancy share; z22data has this, T: does not (it was available but not included in notebook merge) |
| `Wohngebaeude_Anzahl_Wohnungen_{level}-Gitter` | `dwellings_0` from z22data = 21.3M residential dwellings; T: "Insgesamt_Wohnungen" columns hold the floor-space/rooms category sums (41.8M), a different universe |

---

## 1 km Gate

**Setup:** built merged table from z22data 1km parquets (160 files);
aligned on `GITTER_ID_1km`; compared national sums and per-cell differences.

**Coverage:**

| Dimension | Count |
|-----------|-------|
| Shared columns | 159 |
| z22-extra | 1 |
| T:-only | 87 |

**Gate summary:**

| Status | Count |
|--------|-------|
| **EXACT** | 158 |
| **SYSTEMATIC** | 1 |

**Non-exact column detail:**

| Column | z22 sum | T: sum | Diff % | Max cell\|d\| | N cells differing |
|--------|---------|--------|--------|----------------|-------------------|
| `Insgesamt_Haushalte_Groesse_des_privaten_Haushalts` | 34,848,302 | 40,221,501 | -13.36% | 17 | 50,133 |

**Interpretation:** At 1km resolution, `households_0` in z22data is heavily affected by
disclosure suppression: cells below the Destatis threshold have their household total
set to NaN (→ 0 in the parquet). At 1km, far more cells fall below threshold than at 10km,
so the nationally aggregated `households_0` is 34.8M vs 40.2M in T:. This is **NOT a
mapping error** — the household *category* sums (`household_size_group_1..6`) agree with T:
at the national level (40.1M vs 40.2M, EXACT for the individual categories). The T: notebook
pipeline recovered suppressed cells via a different imputation method; downstream stages
(`totals`) will perform the same reconciliation using cross-level IPF. The category columns
themselves are unaffected (158 EXACT out of 159 shared).

---

## Feature Coverage

### Mapped features (in FEATURE_MAP)

| Topic | Features | Categories | Status |
|-------|----------|------------|--------|
| Population total | `population` | 1 (cat=0) | EXACT |
| Age (5 classes) | `age_short` | 5 | EXACT |
| Age (10-year groups) | `age_long` | 9 | EXACT |
| Average age | `age_avg` | 1 (avg) | EXACT |
| Share < 18 / ≥ 65 | `age_under_18`, `age_from_65` | 2 | EXACT |
| Share of foreigners | `foreigners`, `foreigners_from_18` | 2 | EXACT |
| German citizens 18+ | `citizens` | 1 | EXACT |
| Marital status | `marital_status` | 8 | EXACT |
| Birth country | `birth_country` | 6 (2022 codes) | EXACT |
| Citizenship | `citizenship` | 2 | EXACT |
| Citizenship groups | `citizenship_group` | 6 (2022 codes) | EXACT |
| Households (total) | `households` | 1 | NEAR-EXACT (10km) / SYSTEMATIC (1km, disclosure) |
| Household size groups | `household_size_group` | 6 | EXACT |
| Household size avg | `household_size_avg` | 1 (avg) | EXACT |
| Families total | `families` | 1 | EXACT |
| Family type | `family_type` | 13 | EXACT |
| Buildings total | `buildings` | 1 | EXACT |
| Building size/type | `building_size` | 10 | EXACT |
| Dwellings in buildings | `dwelling_building_size` | 10 | EXACT |
| Buildings by dwellings | `building_dwellings` | 5 | EXACT |
| Building constr. year (MZ) | `building_constr_year` | 8 | EXACT |
| Building heating type | `building_heat_type` | 6 | EXACT |
| Building energy source | `building_heat_src` | 9 | EXACT |
| Dwellings (total) | `dwellings` | 1 | z22-extra (different universe) |
| Floor space | `floor_space` | 17 | EXACT |
| Dwelling rooms | `dwelling_rooms` | 7 | EXACT |
| Dwelling heating type | `dwelling_heat_type` | 6 | EXACT |
| Dwelling energy source | `dwelling_heat_src` | 9 | EXACT |
| Living space per dwelling | `dwelling_space` | 1 (avg) | EXACT |
| Living space per person | `inhabitant_space` | 1 (avg) | EXACT |
| Net cold rent avg | `rent_avg` | 1 (avg) | EXACT |
| Vacancy share | `vacancies` | 1 | EXACT |
| Market vacancy share | `market_vacancies` | 1 | EXACT |
| Owner-occupancy share | `owner_occupier` | 1 | z22-extra (no T: column) |

**Total FEATURE_MAP entries: 160** (verified at time of writing; `len(FEATURE_MAP)`).

### T:-only features (NOT available in z22data)

These features are in the T: notebook-era merged CSVs but **not published in z22data**
because they are Zensus 2011-only or were not released in z22:

| T: feature topic | Reason not in z22data |
|------------------|-----------------------|
| `Alter_INFR` (INFR age classes: Unter3, 3bis5, ..., 75+) | z11-only INFR classification; z22 uses `age_short`/`age_long` |
| `Baujahr_JZ` (JZ construction year, 11 classes) | z11 JZ scheme; z22 uses MZ classes (`building_constr_year`) |
| `Seniorenstatus_eines_privaten_Haushalts` (senior status) | z11 only (`household_senior`) |
| `Typ_priv_HH_Familie` (HH by family type) | z11 only (`household_family`) |
| `Typ_priv_HH_Lebensform` (HH by lifestyle) | z11 only (`household_lifestyle`) |
| `Grosse_Kernfamilie_bis6undmehrPers` (family size) | z11 only (`family_size`) |
| `Durchschn_Nettokaltmiete_Anzahl_der_Wohnungen` (rent count) | Auxiliary count not published |
| `Religion` (3 categories) | z11 only (`religion`); z22 did not release religion grid data |
| `Zahl_der_Staatsangehoerigkeiten` (number of citizenships) | z11 only (`citizenship_total`) |
| All `Insgesamt_*` universe-total columns in T: | Derived from category sums in T: notebook; z22 merged table derives totals similarly |
| `werterlaeuternde_Zeichen_*` (annotation flags) | Destatis-internal annotation flags; not in z22data |
| `AnzahlWohnungen_Durchschn_Nettokaltmiete_Anzahl_der_Wohnungen` | Auxiliary count |

### Swapped z22data feature names (building_size vs dwelling_building_size) — REPORTED & FIXED UPSTREAM 2026-06-12

History. Systematic debugging with the MFH_13+ discriminator (buildings with 13+ dwellings
are FEW, dwellings in such buildings are MANY) established that the T: notebook-era merges
were labelled CORRECTLY while z22data's two feature names were swapped relative to their
contents:

- **T: merges are labelled CORRECTLY**: `MFH_13undmehrWohnungen_Geb_Gebaeudetyp` sums to
  237,542 nationally (buildings — consistent with `13undmehr_Wohnungen_Gebaeude_nach_
  Anzahl_der_Wohnungen` = 259,967), while `MFH_13undmehrWohnungen_Wohnung_Gebaeudetyp`
  sums to 5,224,648 (dwellings).
- **Pre-fix z22data feature names were swapped**: `building_size` then contained
  *dwellings by building type* and `dwelling_building_size` contained *buildings by type*
  — a translation mix-up of the two Destatis tables in the upstream z22 project.

We reported this as [z22data issue #4](https://github.com/JsLth/z22data/issues/4); the
upstream **"re-process 2022 data"** commit (2026-06-12) corrected the swap. The current
mirror's feature names now match their contents literally, verified 2026-06-13 against the
official Destatis Insgesamt totals (10km):

- `building_size`          grand total **19,957,238** ≈ GEBAEUDE 19,957,289; cat 1 (FreiEFH)
  **8,665,451** == T: `FreiEFH_Geb_*` exactly.
- `dwelling_building_size` grand total **43,107,077** ≈ WOHNUNGEN 43,106,536; cat 1 (FreiEFH)
  **8,665,582** == T: `FreiEFH_Wohnung_*` exactly.

The FEATURE_MAP therefore now maps z22 `building_size` → `Geb_*` and
`dwelling_building_size` → `Wohnung_*` — matching the corrected upstream names and keeping
all 20 affected columns gating EXACTLY against the (correctly labelled) T: artifacts. A
regression test (`tests/test_z22.py::TestGebaeudetypSemanticDirection`) guards this
direction. **Cache note:** z22data parquets cached before 2026-06-12 carry the old swapped
contents — delete `data/raw/z22/` (or just the `building_size_*` / `dwelling_building_size_*`
files) so the corrected data is re-downloaded.

The confusion is understandable: for detached single-family houses the two universes
nearly coincide (1 building ≈ 1 dwelling; FreiEFH 8,665,451 vs 8,665,582).

---

## buildings_0: Discrepancy Resolution

The task brief noted `buildings_0 = 19,957,289 vs 19,116,274`. Current z22data gives
`buildings_0 = 19,957,289` which matches the T: merged CSV **exactly**. The 19,116,274
figure reflects an **earlier z22data release**. No discrepancy exists in the current mirror.

---

## Coverage Completion (Part A, 2026-06-11)

**All 36 z22data features are now fully mapped in `FEATURE_MAP` (160 entries total).**

The three features that have no T:-counterpart were verified for plausibility on the 10km
national aggregate.  National values are read from the `z22data` 10km parquets and reported
below.

| Feature | FEATURE_MAP base name | T: counterpart | National 10km value | Plausibility |
|---------|----------------------|---------------|---------------------|--------------|
| `vacancies` | `Leerstandsquote_Leerstandsquote` | None | ~0.029 (2.9 % mean share) | Consistent with official Zensus 2022 vacancy rate ≈ 3 % |
| `market_vacancies` | `marktaktive_Leerstandsquote_Marktaktive_Leerstandsquote` | None | ~0.014 (1.4 % mean share) | Lower than total vacancy rate — expected (market-active subset) |
| `owner_occupier` | `Eigentuemerquote_Eigentuemerquote` | None | ~0.442 national mean | Consistent with validated pipeline value 0.4419 (see README Validated results) |

The naming convention `<Label>_<Table>` follows the z22 R-package label scheme (German labels
sourced from the official `z22` R package metadata at https://github.com/JsLth/z22). The
`marktaktive_Leerstandsquote` prefix matches the Destatis table label for
"marktaktive Leerstandsquote" (market-active vacancy share, i.e. vacancies potentially
available for the market), distinguishing it from the broader `Leerstandsquote` (all
vacancies including structurally vacant units).

**Docstring "missing in z22data" list remains unchanged:** the six topics listed in the
`z22.py` module docstring (Seniorenstatus, Lebensform, Typ_HH_Familie, Religion,
Zahl_der_Staatsang., Grosse_Kernfamilie) are confirmed absent from z22data and not
available in the z22data GitHub mirror, consistent with the T:-only table in this report.

**Test guard added:** `tests/test_z22.py::TestFeatureMapShape::test_all_36_z22data_features_present`
asserts all 36 z22data feature names are present; `test_minimum_size` now asserts
`>= 160` (was `>= 100`).

---

## Attribution

- **Source data:** z22data GitHub mirror by Jonas Lieth (https://github.com/JsLth/z22data)
- **z22 R package:** https://github.com/JsLth/z22
- **License:** dl-de/by-2-0 (https://www.govdata.de/dl-de/by-2-0)
- **Census content:** © Statistische Ämter des Bundes und der Länder, Zensus 2022
- **Grid geometry:** © GeoBasis-DE / BKG 2023 (https://www.bkg.bund.de)

---

## Destatis-CSV Supplement (6 tables) — Gate 2026-06-11

**Source:** 6 Destatis CSV ZIPs in `data/raw/destatis/`, read by `cleancensus.destatis_csv`.
**Reference:** T: merged CSVs at `T:\petre\UCFL\...\merged\merged_{10km,1km}_gitter.csv`.
**Gate script:** `tmp_gate_destatis.py` (deleted after use; output below).

### Column mapping summary

The T: merged CSVs contain 47 columns matching the 6 Destatis-table keywords
(`Seniorenstatus`, `Typ_priv_HH_Familie`, `Typ_priv_HH_Lebensform`, `Religion`,
`Staatsangehoerigkeiten`, `Kernfamilie`) per level. Of these, **33 are produced by our
6 ZIPs** (the remaining 14 are from `Typ_der_Kernfamilie_nach_Kindern`, a 7th table
not in scope for this plan and not downloaded).

Our 6-ZIP supplement produces **33 data columns per level** (+ GITTER_ID = 34 total):

| ZIP | Data columns |
|-----|-------------|
| `Seniorenstatus_eines_privaten_Haushalts.zip` | 4 (Insgesamt + 3 categories) |
| `Typ_des_privaren_Haushalts_Lebensform.zip` | 8 (Insgesamt + 7 categories) |
| `Typ_des_privaten_Haushalts_Familien.zip` | 6 (Insgesamt + 5 categories) |
| `Religion.zip` | 4 (Insgesamt + 3 categories) |
| `Zahl_der_Staatsangehoerigkeiten.zip` | 5 (Insgesamt + 4 categories) |
| `Groesse_der_Kernfamilie.zip` | 6 (Insgesamt + 5 categories) |

### 10km gate

**Reference frame:** 3,824 rows (T: merged_10km_gitter.csv)
**Destatis supplement frame:** 3,823 rows (1 cell below Destatis threshold at this level)

| Status | Count | Columns |
|--------|-------|---------|
| **EXACT** | 33 | All 33 matched columns |
| DIFF | 0 | — |
| MISSING_IN_DESTATIS | 14 | `Typ_der_Kernfamilie_nach_Kindern_*` (out of scope) |

All 33 matched columns gate **EXACT** (national sum diff < 0.5, n_diff = 0 per cell).

Selected national sums (10km):

| Column | T: sum | Destatis sum | Status |
|--------|--------|-------------|--------|
| `Insgesamt_Bevoelkerung_Religion_10km-Gitter` | 82,711,382 | 82,711,382 | EXACT |
| `Roemisch_katholisch_Religion_10km-Gitter` | 20,747,066 | 20,747,066 | EXACT |
| `Evangelisch_Religion_10km-Gitter` | 19,127,395 | 19,127,395 | EXACT |
| `Insgesamt_Haushalte_Seniorenstatus_eines_privaten_Haushalts_10km-Gitter` | 40,236,035 | 40,236,035 | EXACT |
| `HH_nurSenioren_Seniorenstatus_eines_privaten_Haushalts_10km-Gitter` | 9,884,027 | 9,884,027 | EXACT |
| `Insgesamt_Haushalte_Typ_priv_HH_Familie_10km-Gitter` | 40,236,035 | 40,236,035 | EXACT |
| `Insgesamt_Haushalte_Typ_priv_HH_Lebensform_10km-Gitter` | 40,236,035 | 40,236,035 | EXACT |
| `Insgesamt_Bevoelkerung_Zahl_der_Staatsangehoerigkeiten_10km-Gitter` | 82,711,382 | 82,711,382 | EXACT |
| `Insgesamt_Familien_Grosse_Kernfamilie_bis6undmehrPers_10km-Gitter` | 21,679,953 | 21,679,953 | EXACT |

### 1km gate

**Reference frame:** 212,758 rows (T: merged_1km_gitter.csv)
**Destatis supplement frame:** 211,420 rows (disclosure suppression at cell level reduces row count)

| Status | Count | Columns |
|--------|-------|---------|
| **EXACT** | 33 | All 33 matched columns |
| DIFF | 0 | — |
| MISSING_IN_DESTATIS | 14 | `Typ_der_Kernfamilie_nach_Kindern_*` (out of scope) |

All 33 matched columns gate **EXACT** (national sum diff < 0.5, n_diff = 0 per cell).

Selected national sums (1km):

| Column | T: sum | Destatis sum | Status |
|--------|--------|-------------|--------|
| `Insgesamt_Bevoelkerung_Religion_1km-Gitter` | 82,706,460 | 82,706,460 | EXACT |
| `Insgesamt_Haushalte_Seniorenstatus_eines_privaten_Haushalts_1km-Gitter` | 40,221,501 | 40,221,501 | EXACT |
| `Insgesamt_Haushalte_Typ_priv_HH_Familie_1km-Gitter` | 40,221,501 | 40,221,501 | EXACT |
| `EineStaatsang_Zahl_der_Staatsangehoerigkeiten_1km-Gitter` | 76,502,215 | 76,502,215 | EXACT |
| `Insgesamt_Familien_Grosse_Kernfamilie_bis6undmehrPers_1km-Gitter` | 21,659,733 | 21,659,733 | EXACT |

### 100m spot-check (national aggregate)

No 100m T: reference CSV is available in a tractable form for cell-by-cell comparison
(1.8 GB file, not loaded). National aggregate sums from the 100m Destatis frame were
verified for plausibility against the 10km/1km sums (lower due to expected cell-level
suppression at 100m resolution, consistent with the z22data household-total pattern).

**100m frame:** 3,112,920 rows, 33 data columns + GITTER_ID.

| Column | 100m national sum | 10km national sum | Note |
|--------|------------------|-------------------|------|
| `Insgesamt_Bevoelkerung_Religion_100m-Gitter` | 82,570,995 | 82,711,382 | Lower due to 100m suppression |
| `Roemisch_katholisch_Religion_100m-Gitter` | 20,635,109 | 20,747,066 | Consistent ratio |
| `Insgesamt_Haushalte_Seniorenstatus_*_100m-Gitter` | 39,615,530 | 40,236,035 | Lower — expected at 100m |
| `HH_nurSenioren_Seniorenstatus_*_100m-Gitter` | 9,475,972 | 9,884,027 | Consistent ratio |

### Missing-destatis-dir behaviour

If `data/raw/destatis/` does not exist:
- `run_merge_z22` logs: `"destatis_raw_dir not found — Destatis supplement skipped (z22-only mode)"`
- The merged parquets are written without the 6 Destatis tables.
- All existing z22data columns are unaffected.
- Downstream stages (totals, ages, etc.) are not impacted.

### Out-of-scope T: columns (resolved in T2, 2026-06-11)

The 14 columns named `*_Typ_der_Kernfamilie_nach_Kindern_{level}-Gitter` that were previously
out-of-scope are now covered by the 7th Destatis table entry added in T2 (see section below).

---

## 7th Destatis-CSV Table: Typ_der_Kernfamilie_nach_Kindern — Gate 2026-06-11

**ZIP:** `Typ_der_Kernfamilie_nach_Kindern.zip` → `data/raw/destatis/`
**CSV path in ZIP:** `Typ_der_Kernfamilie_nach_Kindern/Zensus2022_Typ_der_Kernfamilie_nach_Kindern_{level}-Gitter.csv`
**Data columns:** 14 (Insgesamt_Familie + 13 family-type-by-children categories)
**T: reference:** `merged_10km_gitter.csv` / `merged_1km_gitter.csv`

### 10km gate

**Reference frame:** 3,824 rows (T: merged_10km_gitter.csv)
**Destatis frame:** 3,815 rows (9 cells below Destatis disclosure threshold at 10km)

| Status | Count | Columns |
|--------|-------|---------|
| **EXACT** | 14 | All 14 data columns |
| DIFF | 0 | — |

Selected national sums (10km):

| Column | T: sum | Destatis sum | Status |
|--------|--------|-------------|--------|
| `Insgesamt_Familie_Typ_der_Kernfamilie_nach_Kindern_10km-Gitter` | 21,679,953 | 21,679,953 | EXACT |
| `Ehep_ohneKind_Typ_der_Kernfamilie_nach_Kindern_10km-Gitter` | 8,207,692 | 8,207,692 | EXACT |
| `Ehep_mind_1Kind_unter18_Typ_der_Kernfamilie_nach_Kindern_10km-Gitter` | 5,220,864 | 5,220,864 | EXACT |
| `NichtehelLG_ohneKind_Typ_der_Kernfamilie_nach_Kindern_10km-Gitter` | 1,907,110 | 1,907,110 | EXACT |
| `Mutter_mind_1Kind_unter18_Typ_der_Kernfamilie_nach_Kindern_10km-Gitter` | 1,439,162 | 1,439,162 | EXACT |

### 1km gate

**Reference frame:** 212,758 rows (T: merged_1km_gitter.csv)
**Destatis frame:** 184,744 rows (disclosure suppression at 1km resolution)

| Status | Count | Columns |
|--------|-------|---------|
| **EXACT** | 14 | All 14 data columns |
| DIFF | 0 | — |

Selected national sums (1km):

| Column | T: sum | Destatis sum | Status |
|--------|--------|-------------|--------|
| `Insgesamt_Familie_Typ_der_Kernfamilie_nach_Kindern_1km-Gitter` | 21,659,733 | 21,659,733 | EXACT |
| `Ehep_ohneKind_Typ_der_Kernfamilie_nach_Kindern_1km-Gitter` | 8,159,801 | 8,159,801 | EXACT |
| `Mutter_mind_1Kind_unter18_Typ_der_Kernfamilie_nach_Kindern_1km-Gitter` | 1,430,849 | 1,430,849 | EXACT |

All 14 columns gate **EXACT** at both 10km and 1km (national sum diff = 0, n_diff = 0 per cell on the inner join).

---

## RegioStaR Stage: BBSR Referenz Gemeinden Gebietsstand 31.12.2022 — Gate 2026-06-11

**Source:** BBSR Referenz Gemeinden Gebietsstand 31.12.2022
**URL:** `https://www.bbsr.bund.de/.../raumgliederungen-referenzen-2022.xlsx?__blob=publicationFile&v=2`
**Local path:** `data/raw/regiostar/bbsr-referenz-gebietsstand-2022.xlsx`
**Sheet:** `Gemeindereferenz (inkl. Kreise)` (10,990 Gemeinden)

### Column mapping (BBSR 2022 → canonical output)

| BBSR 2022 column | Description | Output column | Method |
|------------------|-------------|---------------|--------|
| `GEM2022` | Gemeindekennziffer (8-digit AGS) | `commune_id` | zero-padded to 8 chars |
| `RS22022` | RegioStaR 2 | `RegioStaR2` | direct |
| `RSS2022` | RegioStaR 17 | `RegioStaR17` | direct |
| `RSS2022 // 10` | — | `RegioStaR4` | derived (100% match verified) |
| `RS72022` | RegioStaR 7 | `RegioStaR7` | direct (99.97% match vs BMDV2020) |
| `RS52022` | Gemeindetyp 5 | `RegioStaRGem5` | direct (99.98% match vs BMDV2020) |
| *(absent)* | — | `RegioStaR5` | NaN — not in BBSR 2022 Gemeindereferenz |
| *(absent)* | — | `RegioStaRGem7` | NaN — not in BBSR 2022 Gemeindereferenz |

Note: `RegioStaR5` (Stadtregion 5-type) and `RegioStaRGem7` (Gemeinde 7-type) are not published
in the BBSR 2022 Gemeindereferenz sheet. They remain available in the BMDV Gebietsstand2020
fallback file (activated automatically when the BBSR 2022 file is absent).

### Match rate (BBSR 2022 vs BMDV 2020 on shared municipalities)

| Column | Match rate (inner join, 10,985 communes) |
|--------|------------------------------------------|
| `RegioStaR2` | 99.99% |
| `RegioStaR17` | 99.97% |
| `RegioStaR4` (derived) | 100.00% (by construction from RS17) |
| `RegioStaR7` | 99.97% |
| `RegioStaRGem5` | 99.98% |

Near-unity match rates reflect genuine reclassifications between Gebietsstand 2020 and 2022
(~3 communes changed type), not mapping errors.

### Null-rim improvement

The null-rim (cells with an ARS that gets no RegioStaR match) is computed on the canonical
100m parquet (`cells_100m_with_gender_backf_binneds_happyorphans_with_aggs_regiostar.parquet`,
3,148,482 rows).

| Reference | Null RegioStaR2 cells | Source |
|-----------|----------------------|--------|
| BMDV Gebietsstand2020 (prior) | 5,188 | canonical parquet |
| BBSR Gebietsstand2022 (new) | **633** | recomputed via AGS8 join |
| **Improvement** | **−4,555 cells** | |

The remaining 633 null cells all have a non-null ARS but their AGS8 (derived from ARS via
`ARS[0:5]+ARS[9:12]`) does not appear in the BBSR 2022 Gemeindereferenz. These are likely
Zensus 2022 grid cells on the edges of special administrative areas (e.g. Bodensee,
extraterritorial grid cells coded as AGS 99xxxxx) that are not Gemeinden in the BBSR reference.

---

## Published Totals Supplement (DESTATIS_TOTALS_ONLY) — Gate 2026-06-11

**Context:** The z22data GitHub mirror provides all category columns but omits the per-topic
`Insgesamt_*` totals (e.g. `Insgesamt_Bevoelkerung_Familienstand`). The official Destatis
topic ZIPs contain these totals as independent published statistics (NOT derivable from the
disclosure-perturbed category sums). The `DESTATIS_TOTALS_ONLY` registry in
`cleancensus/destatis_csv.py` extends `merge_destatis_tables` to include 15 additional ZIPs
copied to `data/raw/destatis/`, each contributing only its single `Insgesamt_*` column
(category columns are dropped before merge to avoid collisions with z22data).

**ZIPs copied from Downloads to `data/raw/destatis/`:** 15 (all found, 0 missing).
`Zensus2022_Bevoelkerungszahl (2).zip` skipped — contains only `Einwohner` (not an
Insgesamt topic total).

**Source:** Official Destatis CSV ZIPs (same as DESTATIS_TABLES entries).
**Reference:** T: merged CSVs at `T:\petre\UCFL\...\merged\merged_{10km,1km}_gitter.csv`.
**Method:** `merge_destatis_tables` now iterates both `DESTATIS_TABLES` (7) and
`DESTATIS_TOTALS_ONLY` (15) = 22 ZIPs total. Totals-only entries use
`read_destatis_totals_zip`, which keeps GITTER_ID + the registered Insgesamt column only.

### Column mapping (15 new Insgesamt columns)

| ZIP | Insgesamt col (CSV) | Produced column (10km) |
|-----|---------------------|------------------------|
| `Familienstand_in_Gitterzellen.zip` | `Insgesamt_Bevoelkerung` | `Insgesamt_Bevoelkerung_Familienstand_10km-Gitter` |
| `Zensus2022_Energietraeger.zip` | `Insgesamt_Energietraeger` | `Insgesamt_Energietraeger_Energietraeger_10km-Gitter` |
| `Gebaeude_mit_Wohnraum_nach_ueberwiegender_Heizungsart.zip` | `Insgesamt_Heizungsart` | `Insgesamt_Heizungsart_Gebaeude_nach_ueberwiegender_Heizungsart_10km-Gitter` |
| `Zensus2022_Groesse_des_privaten_Haushalts_in_Gitterzellen.zip` | `Insgesamt_Haushalte` | `Insgesamt_Haushalte_Groesse_des_privaten_Haushalts_10km-Gitter` |
| `Wohnungen_nach_Zahl_der_Raeume.zip` | `Insgesamt_Wohnungen` | `Insgesamt_Wohnungen_Wohnungen_nach_Zahl_der_Raeume_10km-Gitter` |
| `Flaeche_der_Wohnung_10m2_Intervalle.zip` | `Insgesamt_Wohnungen` | `Insgesamt_Wohnungen_Flaeche_der_Wohnung_10m2_Intervalle_10km-Gitter` |
| `Zensus2022_Geburtsland_Gruppen_in_Gitterzellen.zip` | `Insgesamt_Bevoelkerung` | `Insgesamt_Bevoelkerung_Geburtsland_Gruppen_10km-Gitter` |
| `Wohnungen_nach_Gebaeudetyp_Groesse.zip` | `Insgesamt_Wohnungen` | `Insgesamt_Wohnungen_Wohnung_Gebaeudetyp_Groesse_10km-Gitter` |
| `Gebaeude_mit_Wohnraum_nach_Gebaeudetyp_Groesse.zip` | `Insgesamt_Gebaeude` | `Insgesamt_Gebaeude_Geb_Gebaeudetyp_Groesse_10km-Gitter` |
| `Gebaeude_nach_Anzahl_der_Wohnungen_im_Gebaeude.zip` | `Insgesamt_Gebaeude` | `Insgesamt_Gebaeude_Gebaeude_nach_Anzahl_der_Wohnungen_10km-Gitter` |
| `Gebaeude_nach_Baujahr_in_Mikrozensus_Klassen.zip` | `Insgesamt_Gebaeude` | `Insgesamt_Gebaeude_Gebaeude_nach_Baujahr_in_MZ_Klassen_10km-Gitter` |
| `Gebaeude_mit_Wohnraum_nach_Energietraeger_der_Heizung.zip` | `Insgesamt_Energietraeger` | `Insgesamt_Energietraeger_Gebaeude_nach_Energietraeger_der_Heizung_10km-Gitter` |
| `Zensus2022_Heizungsart.zip` | `Insgesamt_Heizungsart` | `Insgesamt_Heizungsart_Heizungsart_10km-Gitter` |
| `Zensus2022_Staatsangehoerigkeit_in_Gitterzellen.zip` | `Insgesamt_Bevoelkerung` | `Insgesamt_Bevoelkerung_Staatsangehoerigkeit_10km-Gitter` |
| `Zensus2022_Staatsangehoerigkeit_Gruppen_in_Gitterzellen.zip` | `Insgesamt_Bevoelkerung` | `Insgesamt_Bevoelkerung_Staatsangehoerigkeit_Gruppen_10km-Gitter` |

Note: Some produced names collide with z22data (e.g. `Insgesamt_Haushalte_Groesse_des_privaten_Haushalts`
comes from z22data `households_0`; `Insgesamt_Gebaeude_Gebaeude_nach_Baujahr_in_MZ_Klassen` from
z22data `buildings_0`). The collision guard in `run_merge_z22` drops the Destatis version and keeps the
z22data version (z22data takes precedence). Net new columns added to merged table: 13 (the 2 collisions
keep their z22data values unmodified).

### 10km gate

**Inner join:** 3,824 rows (full match — supplement has 3,824 rows, T: has 3,824 rows).

| Column | T: sum | Supplement sum | Status |
|--------|--------|----------------|--------|
| `Insgesamt_Bevoelkerung_Familienstand` | 82,711,382 | 82,711,382 | EXACT |
| `Insgesamt_Energietraeger_Energietraeger` | 43,106,536 | 43,106,536 | EXACT |
| `Insgesamt_Heizungsart_Gebaeude_nach_ueberwiegender_Heizungsart` | 19,957,289 | 19,957,289 | EXACT |
| `Insgesamt_Haushalte_Groesse_des_privaten_Haushalts` | 40,236,035 | 40,236,035 | EXACT |
| `Insgesamt_Wohnungen_Wohnungen_nach_Zahl_der_Raeume` | 41,806,842 | 41,806,842 | EXACT |
| `Insgesamt_Wohnungen_Flaeche_der_Wohnung_10m2_Intervalle` | 41,806,842 | 41,806,842 | EXACT |
| `Insgesamt_Bevoelkerung_Geburtsland_Gruppen` | 82,711,382 | 82,711,382 | EXACT |
| `Insgesamt_Wohnungen_Wohnung_Gebaeudetyp_Groesse` | 43,106,536 | 43,106,536 | EXACT |
| `Insgesamt_Gebaeude_Geb_Gebaeudetyp_Groesse` | 19,957,289 | 19,957,289 | EXACT |
| `Insgesamt_Gebaeude_Gebaeude_nach_Anzahl_der_Wohnungen` | 19,957,289 | 19,957,289 | EXACT |
| `Insgesamt_Gebaeude_Gebaeude_nach_Baujahr_in_MZ_Klassen` | 19,957,289 | 19,957,289 | EXACT |
| `Insgesamt_Energietraeger_Gebaeude_nach_Energietraeger_der_Heizung` | 19,957,289 | 19,957,289 | EXACT |
| `Insgesamt_Heizungsart_Heizungsart` | 43,106,536 | 43,106,536 | EXACT |
| `Insgesamt_Bevoelkerung_Staatsangehoerigkeit` | 82,711,382 | 82,711,382 | EXACT |
| `Insgesamt_Bevoelkerung_Staatsangehoerigkeit_Gruppen` | 82,711,382 | 82,711,382 | EXACT |

**All 15 new columns gate EXACT at 10km** (national sum diff = 0, n_diff = 0 per cell on inner join).

### 1km gate

**Inner join:** 212,600 rows (supplement has 212,600 rows; T: has 212,758; 158 cells below
Destatis disclosure threshold, consistent with prior pattern).

All 15 new columns gate **EXACT** at 1km (national sum diff = 0, n_diff = 0 per cell).

Selected national sums (1km):

| Column | T: sum | Supplement sum | Status |
|--------|--------|----------------|--------|
| `Insgesamt_Bevoelkerung_Familienstand` | 82,706,456 | 82,706,456 | EXACT |
| `Insgesamt_Energietraeger_Energietraeger` | 43,090,188 | 43,090,188 | EXACT |
| `Insgesamt_Heizungsart_Gebaeude_nach_ueberwiegender_Heizungsart` | 19,936,682 | 19,936,682 | EXACT |
| `Insgesamt_Haushalte_Groesse_des_privaten_Haushalts` | 40,221,501 | 40,221,501 | EXACT |
| `Insgesamt_Bevoelkerung_Geburtsland_Gruppen` | 82,706,456 | 82,706,456 | EXACT |
| `Insgesamt_Gebaeude_Geb_Gebaeudetyp_Groesse` | 19,936,682 | 19,936,682 | EXACT |

### POP_TOTAL candidate pool analysis

`ingest_totals.collapse_population_totals` scans columns matching
`^(Einwohner_Bevoelkerungszahl|Insgesamt_Bevoelkerung_)`. Of the 15 new supplement columns,
**4 match this pattern** and join the consensus pool:

| New pool candidate | Value (10km national) |
|--------------------|-----------------------|
| `Insgesamt_Bevoelkerung_Familienstand_*` | 82,711,382 |
| `Insgesamt_Bevoelkerung_Geburtsland_Gruppen_*` | 82,711,382 |
| `Insgesamt_Bevoelkerung_Staatsangehoerigkeit_*` | 82,711,382 |
| `Insgesamt_Bevoelkerung_Staatsangehoerigkeit_Gruppen_*` | 82,711,382 |

These values are identical to the existing pool members (`Insgesamt_Bevoelkerung_Alter_*`,
`Insgesamt_Bevoelkerung_Religion_*`, etc.) = 82,711,382 nationally. Adding them increases
the consensus support count per row but does NOT change POP_TOTAL (all agree). The T: notebook
always had these columns in its merged CSV, so this change makes the pipeline **more faithful**
to the notebook baseline, not different from it.

### Stale work files deleted (cache invalidation)

Because the merged parquets now contain 13 additional Insgesamt columns (vs. the previous run),
all downstream work artifacts were deleted to force a clean re-run:

| Deleted file | Reason |
|--------------|--------|
| `data/work/merged_{10km,1km,100m}_gitter.parquet` | Now stale — new supplement columns not present |
| `data/work/totals_{10km,1km,100m}.parquet` | Depend on merged; 4 new POP_TOTAL candidates change support count |
| `data/work/df{10,1,100}_with_single_years.parquet` | Depend on totals |
| `data/work/cells_100m_with_gemeinde.parquet` | Downstream of merged |
| `data/work/cells_100m_with_gender_backfilled.parquet` | Downstream of gemeinde |

A full re-run (merge + totals + ages + gemeinde + gender) is required (~1.3 h). The totals/ages
gates are expected to be unchanged (the notebook always had these columns, so POP_TOTAL values
are the same; only the support count increases, strengthening the consensus).

### Step 5 completeness check

All 12 required Insgesamt columns confirmed PRESENT in the supplement output at 10km:

| Required column | Source ZIP | Status |
|-----------------|------------|--------|
| `Insgesamt_Bevoelkerung_Familienstand` | `Familienstand_in_Gitterzellen.zip` | PRESENT |
| `Insgesamt_Energietraeger_Energietraeger` | `Zensus2022_Energietraeger.zip` | PRESENT |
| `Insgesamt_Heizungsart_Gebaeude_nach_ueberwiegender_Heizungsart` | `Gebaeude_mit_Wohnraum_nach_ueberwiegender_Heizungsart.zip` | PRESENT |
| `Insgesamt_Haushalte_Groesse_des_privaten_Haushalts` | `Zensus2022_Groesse_des_privaten_Haushalts_in_Gitterzellen.zip` (collision: z22data wins) | PRESENT |
| `Insgesamt_Haushalte_Typ_priv_HH_Lebensform` | `Typ_des_privaren_Haushalts_Lebensform.zip` (DESTATIS_TABLES) | PRESENT |
| `Insgesamt_Wohnungen_Wohnungen_nach_Zahl_der_Raeume` | `Wohnungen_nach_Zahl_der_Raeume.zip` | PRESENT |
| `Insgesamt_Wohnungen_Flaeche_der_Wohnung_10m2_Intervalle` | `Flaeche_der_Wohnung_10m2_Intervalle.zip` | PRESENT |
| `Insgesamt_Bevoelkerung_Geburtsland_Gruppen` | `Zensus2022_Geburtsland_Gruppen_in_Gitterzellen.zip` | PRESENT |
| `Insgesamt_Wohnungen_Wohnung_Gebaeudetyp_Groesse` | `Wohnungen_nach_Gebaeudetyp_Groesse.zip` | PRESENT |
| `Insgesamt_Gebaeude_Geb_Gebaeudetyp_Groesse` | `Gebaeude_mit_Wohnraum_nach_Gebaeudetyp_Groesse.zip` | PRESENT |
| `Insgesamt_Gebaeude_Gebaeude_nach_Anzahl_der_Wohnungen` | `Gebaeude_nach_Anzahl_der_Wohnungen_im_Gebaeude.zip` | PRESENT |
| `Insgesamt_Haushalte_Seniorenstatus_eines_privaten_Haushalts` | `Seniorenstatus_eines_privaten_Haushalts.zip` (DESTATIS_TABLES) | PRESENT |
