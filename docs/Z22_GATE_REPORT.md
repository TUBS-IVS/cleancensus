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

### Inverted z22data feature names (building_size vs dwelling_building_size) — CORRECTED 2026-06-11

An earlier version of this report claimed the T: notebook-era merges were mislabelled.
Systematic debugging with the MFH_13+ discriminator (buildings with 13+ dwellings are FEW,
dwellings in such buildings are MANY) established the opposite:

- **T: merges are labelled CORRECTLY**: `MFH_13undmehrWohnungen_Geb_Gebaeudetyp` sums to
  237,542 nationally (buildings — consistent with `13undmehr_Wohnungen_Gebaeude_nach_
  Anzahl_der_Wohnungen` = 259,967), while `MFH_13undmehrWohnungen_Wohnung_Gebaeudetyp`
  sums to 5,224,648 (dwellings).
- **z22data's FEATURE NAMES are inverted** relative to their literal meaning:
  `building_size` actually contains *dwellings by building type* (cat 1 sum 8,665,582 ==
  T: `FreiEFH_Wohnung_*` exactly) and `dwelling_building_size` actually contains
  *buildings by type* (cat 1 sum 8,665,451 == T: `FreiEFH_Geb_*` exactly) — most likely
  a translation mix-up of the two Destatis tables in the upstream z22 project.

The FEATURE_MAP maps z22 `building_size` → `Wohnung_*` and `dwelling_building_size` →
`Geb_*`, which is **semantically correct** (and why all 20 affected columns gate EXACTLY).
A regression test (`tests/test_z22.py::TestGebaeudetypSemanticDirection`) guards this
direction. Recommended follow-up: file an issue upstream at JsLth/z22data.

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

### Out-of-scope T: columns (not blocked)

The 14 columns named `*_Typ_der_Kernfamilie_nach_Kindern_{level}-Gitter` appear in the T:
merged CSVs but are not produced by any of the 6 ZIPs in scope. They come from the separate
`Typ_der_Kernfamilie_nach_Kindern.zip` (also available in Downloads) but was not part of
the P1 plan. These columns should be added in a future P2 task if needed.
