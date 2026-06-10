# Data Dictionary

This document describes the input files consumed by cleancensus, the columns it produces,
and important caveats about data quality and licensing.

---

## Raw source data

The ultimate data source is the **Zensus 2022 grid data** published by the Statistische Ämter
des Bundes und der Länder under the **dl-de/by-2-0** licence.
Download the "Ergebnisse auf Gitterzellenebene" CSVs from
[www.zensus2022.de](https://www.zensus2022.de).
Attribution required: *Datenquelle: Statistische Ämter des Bundes und der Länder, Zensus 2022*.

## Pipeline input files (derived intermediates)

The three files consumed by cleancensus are **derived artifacts** produced by the archived
notebooks from the raw Zensus 2022 grid CSVs — they are NOT directly downloadable from
zensus2022.de. The derivation sequence is:

1. `notebooks_archive/data_prep.ipynb` — merges raw CSVs, constructs 10 km cell table
2. `notebooks_archive/ages.ipynb` — computes single-year age columns
3. `notebooks_archive/gender.ipynb` — adds gender split columns at 100 m
4. `notebooks_archive/other_binned_data.ipynb` — adds remaining binned topic columns

Each notebook run takes multiple hours on a full national dataset.
**The derived input files are not publicly hosted yet.**
To reproduce them from scratch, run the archived notebooks in the order above on the raw
grid CSVs. To obtain the prepared files directly, contact the authors (see `CITATION.cff`).
*(Archival on Zenodo is planned as future work.)*

Place these three files in `data/inputs/` (or the directory configured as `inputs_dir`).

| File | Shape | Origin notebook | Content |
|---|---|---|---|
| `df10_with_single_years.pickle` | 3,824 × 346 | `notebooks_archive/data_prep.ipynb` + `ages.ipynb` | 10 km grid cells; merged Zensus 2022 topic tables per cell, plus single-year age columns `AGE_0` – `AGE_100`; index is `GITTER_ID_10km` |
| `cells_1km_with_binneds.parquet` | 212,758 × 256 | `notebooks_archive/other_binned_data.ipynb` + previous pipeline runs | 1 km cells; includes the original 8 harmonized topics (Familienstand, Energietraeger, Heizungsart, Haushaltsgroesse, Lebensform, Raeume, Wohnflaeche, Geburtsland) plus binned age/gender columns; key columns: `GITTER_ID_1km`, `GITTER_ID_10km` |
| `cells_100m_with_gender_backf_binneds_happyorphans_with_aggs_regiostar.parquet` | 3,148,482 × 570 | `notebooks_archive/gender.ipynb` + `other_binned_data.ipynb` (orphan pass) | Full national 100 m cell table (~7.7 GB); includes age/gender columns, aggregated categorical topic columns for the 8 original topics, RegioStar 2022 classification, `is_orphan` flag, and `Eigentuemerquote` ratio; key columns: `GITTER_ID_100m`, `GITTER_ID_1km` |

### Column naming convention

Zensus grid columns carry the resolution suffix: `_10km-Gitter`, `_1km-Gitter`, or `_100m-Gitter`.
The total column for a topic is prefixed `Insgesamt_`; category columns are named for
their value (e.g. `Gas_Energietraeger_10km-Gitter`).
Adjusted totals produced by cleancensus carry an additional `_adj` suffix:
`Insgesamt_Haushalte_Groesse_des_privaten_Haushalts_100m-Gitter_adj`.

---

## Produced columns

### Per-topic harmonized output

The pipeline produces two new column sets per harmonized topic:

1. `Insgesamt_*_adj` — the adjusted total; equals the parent-level adjusted total distributed
   proportionally to each child's raw total. This is the row margin that the category columns sum to.
2. Category columns (same names as inputs, same suffix) — trust-blended downscaled values
   whose sum equals the adjusted total for that cell.

The table below lists all 14 topics in the catalog.
The "Default" column marks topics included when neither `topics` nor `tiers` is set in the config.

| Name | Tier | Categories | Universe | Default |
|---|---|---|---|---|
| `Geb_Gebaeudetyp` | 1 | 10 | Gebaeude | |
| `Geb_AnzahlWohnungen` | 1 | 5 | Gebaeude | |
| `Geb_Baujahr` | 1 | 8 | Gebaeude | |
| `Geb_Energietraeger` | 1 | 9 | Gebaeude | |
| `Whg_Gebaeudetyp` | 1 | 10 | Wohnungen B | yes |
| `Whg_Heizungsart` | 1 | 6 | Wohnungen B | |
| `HH_Seniorenstatus` | 2 | 3 | Haushalte | yes |
| `HH_Familientyp` | 2 | 5 | Haushalte | |
| `Pers_Staatsangehoerigkeit` | 2 | 2 | Personen | |
| `Pers_StaatsangGruppen` | 3 | 6 | Personen | |
| `Pers_ZahlStaatsang` | 3 | 4 | Personen | |
| `Pers_Religion` | 3 | 3 | Personen | |
| `Fam_Groesse` | 3 | 5 | Familien | |
| `Fam_TypNachKindern` | 3 | 13 | Familien | |

In addition, `cleancensus/harmonization.py` contains the original 8 topics
(Familienstand, Energietraeger, Heizungsart, Haushaltsgroesse, Lebensform, Raeume,
Wohnflaeche, Geburtsland) that were harmonized in the notebook era;
their adjusted columns are present in `cells_1km_with_binneds.parquet` as inputs.

### Tenure columns (when `derived_tenure = true`)

Two columns are added to both the 1 km and 100 m output files:

| Column | Level | Description |
|---|---|---|
| `EigentuemerHH_Tenure_1km-Gitter` | 1 km | Estimated number of owner-occupier households |
| `MieterHH_Tenure_1km-Gitter` | 1 km | Estimated number of renter households |
| `EigentuemerHH_Tenure_100m-Gitter` | 100 m | Estimated number of owner-occupier households |
| `MieterHH_Tenure_100m-Gitter` | 100 m | Estimated number of renter households |

Values are stored as `float32`.

---

## Caveats

### `fillna(0)` and disclosure suppression

`fillna(0)` is applied to all input frames before processing.
A zero value in any harmonized category column is therefore **indistinguishable** from a
disclosure-suppressed value that was rounded to zero by the Zensus release.
Downstream models must treat zero as "missing or true zero" rather than "definitively zero".

The `Eigentuemerquote` column is an exception: it is **never published as 0** for inhabited
cells. A zero `Eigentuemerquote` therefore unambiguously means the value is missing.

### Orphan cell tenure deviation

In the validated national run (legacy v2+v3 artifacts), 4 orphan cells deviate by more than
0.5 households from their tenure anchor (maximum deviation: 3 households).
This is a known benign artifact of the orphan imputation order and is reported as INFO,
not as a sanity failure.

### Float32 precision

All produced category columns are cast to `float32` (~7 significant decimal digits).
The adjusted total columns are also `float32`.
The `sum(categories) == *_adj` invariant is checked with a tolerance of 0.5 (not 0),
because the round-trip through `float32` arithmetic can produce sub-integer rounding errors.

### Wohnungen A vs Wohnungen B universes

Two sets of dwelling topics exist in the Zensus 2022 release with different universes:

- **Wohnungen A** (Raeume, Wohnflaeche): 41.2 M dwellings — counted for dwellings with
  reported room count and floor area.
- **Wohnungen B** (Whg_Gebaeudetyp, Whg_Heizungsart, Geb_*): 42.5 M dwellings — counted
  for dwellings in residential buildings by building characteristics.

These two universes must never be used as anchors for each other.
The sanity check only pairs topics within the same universe.

---

## Output naming scheme

Output files follow the pattern:

```
cells_1km_with_binneds_<version_tag>.parquet
cells_100m_with_gender_backf_binneds_happyorphans_with_aggs_regiostar_<version_tag>.parquet
```

For subset runs, the 100 m file is named:

```
cells_100m_with_gender_backf_binneds_happyorphans_with_aggs_regiostar_<version_tag>_SUBSET.parquet
```

### Run manifest fields

`run_manifest_<version_tag>.json` is written on completion (when `write_manifest = true`).

| Field | Type | Content |
|---|---|---|
| `cleancensus_version` | string | Package version from `cleancensus.__version__` |
| `git_sha` | string | `git rev-parse HEAD` at run time, or `"unknown"` |
| `config_file` | string | Absolute path to the config TOML |
| `config_resolved` | object | Resolved config values: `version_tag`, `topics`, `derived_tenure`, `mode`, `ars_prefixes`, `sanity` |
| `started_utc` | ISO-8601 string | UTC timestamp when the CLI started |
| `finished_utc` | ISO-8601 string | UTC timestamp when the CLI finished |
| `timings_seconds` | object | Per-stage wall time: `stage_a`, `stage_b`, optionally `tenure` and `sanity` |
| `sanity_failures` | integer | Count of invariant check failures (0 = pass) |
| `outputs` | object | Map from output file name to file size in bytes |
