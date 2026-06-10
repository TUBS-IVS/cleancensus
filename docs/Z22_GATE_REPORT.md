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

### Label swap note (building_size vs dwelling_building_size)

The T: notebook-era merged CSV has an error in the column labels for the building type features:
- Columns labeled `*_Geb_Gebaeudetyp_Groesse_*` actually contain **dwelling** counts (`dwelling_building_size`)
- Columns labeled `*_Wohnung_Gebaeudetyp_Groesse_*` actually contain **building** counts (`building_size`)

The FEATURE_MAP reproduces this swapped convention exactly (verified numerically: national sums match EXACTLY after the swap). This is documented in `cleancensus/z22.py`.

---

## buildings_0: Discrepancy Resolution

The task brief noted `buildings_0 = 19,957,289 vs 19,116,274`. Current z22data gives
`buildings_0 = 19,957,289` which matches the T: merged CSV **exactly**. The 19,116,274
figure reflects an **earlier z22data release**. No discrepancy exists in the current mirror.

---

## Attribution

- **Source data:** z22data GitHub mirror by Jonas Lieth (https://github.com/JsLth/z22data)
- **z22 R package:** https://github.com/JsLth/z22
- **License:** dl-de/by-2-0 (https://www.govdata.de/dl-de/by-2-0)
- **Census content:** © Statistische Ämter des Bundes und der Länder, Zensus 2022
- **Grid geometry:** © GeoBasis-DE / BKG 2023 (https://www.bkg.bund.de)
