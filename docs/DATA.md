# Data Dictionary

This document describes the input files consumed by cleancensus, the columns it produces,
and important caveats about data quality and licensing.

---

## Raw source data — the original Zensus 2022 grid

Everything in this pipeline starts from the **publicly available original Zensus 2022
grid data** ("Gitterdaten"). The pipeline does not invent data — it takes these official
released grids and progressively makes them internally consistent.

### What are the grid cells?

Germany's 2022 census publishes its results not only per municipality but also on a
regular **geographic grid** based on the Europe-wide INSPIRE grid (ETRS89-LAEA,
EPSG:3035). Each cell is a square; the census is released at three nested resolutions:

- **100 m** cells — the finest level (~3.15 million inhabited cells nationwide)
- **1 km** cells — each contains up to 100 of the 100 m cells
- **10 km** cells — each contains up to 100 of the 1 km cells

Every cell carries a stable INSPIRE id (e.g. `CRS3035RES100mN2691900E4341100`), exposed in
the data as `GITTER_ID_100m` / `GITTER_ID_1km` / `GITTER_ID_10km`. For each cell the census
reports counts and ratios for many topics: population by age/sex/marital status/country of
birth/citizenship/religion, households by size/type/senior status, buildings by type/size/
construction year/heating, dwellings by floor area/rooms/tenure, etc. To protect privacy,
small counts are perturbed and suppressed — which is exactly why category counts do not add
up to the published totals and the three levels disagree (the problem this pipeline solves).

### Where to download it

- **Portal:** Zensus 2022 — *Gitterdaten zum Download für geografische Informationssysteme
  (GIS)*, reachable from [www.zensus2022.de](https://www.zensus2022.de) →
  *Ergebnisse → Gitterzellenbasierte Ergebnisse*
  (currently hosted under Destatis:
  `https://www.destatis.de/DE/Themen/Gesellschaft-Umwelt/Bevoelkerung/Zensus2022/Publikationen/`).
- **Format:** ZIP archives of CSV tables (one set per topic) plus Excel dataset descriptions,
  for the 100 m / 1 km / 10 km grids, covering population, households, buildings and dwellings.
- **Licence:** Open Data License Germany – Attribution 2.0 (**dl-de/by-2-0**).
- **Attribution:** census content — *© Statistische Ämter des Bundes und der Länder, Zensus
  2022*; grid geometry — *© GeoBasis-DE / BKG 2023* (https://www.bkg.bund.de).
- **Automated download:** see [docs/RAW_DOWNLOAD.md](RAW_DOWNLOAD.md) for the manifest-driven
  downloader (`tools/download_zensus_grid.py`) that fetches and unzips the ZIPs into
  `data/raw/csv/` for consumption by the merge stage.

## Pipeline input files and work_dir intermediates

The three files in `data/inputs/` are the **prepared inputs** for the extend/tenure/sanity
stages (prepared mode). They are produced by running stages 1–8 of the full pipeline, which
is now fully implemented in `cleancensus/`. The archived notebooks that originally produced
them are superseded by these pipeline stages — see `notebooks_archive/ARCHIVE_README.md`.

**To reproduce from scratch:** enable all stages in the config and run `uv run cleancensus`;
the pipeline downloads z22data automatically and runs the complete chain (multi-hour for the
national dataset). To obtain the prepared files directly, contact the authors (`CITATION.cff`);
publication on a data archive (e.g. Zenodo) is planned.

Place the three files in `data/inputs/` (or the directory configured as `inputs_dir`) for
prepared-mode operation.

| File | Shape | Produced by | Content |
|---|---|---|---|
| `df10_with_single_years.pickle` | 3,824 × 346 | stages `merge` + `totals` + `ages` | 10 km grid cells; merged Zensus 2022 topic tables per cell, plus single-year age columns `AGE_0`–`AGE_100`; index is `GITTER_ID_10km` |
| `cells_1km_with_binneds.parquet` | 212,758 × 256 | stages `totals` + `topics8` | 1 km cells; includes the original 8 harmonized topics (Familienstand, Energietraeger, Heizungsart, Haushaltsgroesse, Lebensform, Raeume, Wohnflaeche, Geburtsland) plus binned age/gender columns; key columns: `GITTER_ID_1km`, `GITTER_ID_10km` |
| `cells_100m_with_gender_backf_binneds_happyorphans_with_aggs_regiostar.parquet` | 3,148,482 × 570 | stages `gemeinde` + `gender` + `topics8` + `aggs` + `regiostar` | Full national 100 m cell table (~7.7 GB); includes age/gender columns, aggregated categorical topic columns for the 8 original topics, RegioStaR 2022 classification, `is_orphan` flag, and `Eigentuemerquote` ratio; key columns: `GITTER_ID_100m`, `GITTER_ID_1km` |

### work_dir intermediates (full mode only)

When running with one or more raw→prepared stages enabled, the pipeline writes intermediate
files to `data/work/` (the `work_dir` sibling of `inputs_dir`, gitignored).  Each stage reads
the previous stage's file and appends its output.

| work_dir file | Written by | Content |
|---|---|---|
| `merged_10km_gitter.parquet` | `merge` | Wide table at 10 km; one column per FEATURE_MAP entry (160 columns + 3 coordinate cols) |
| `merged_1km_gitter.parquet` | `merge` | Same at 1 km |
| `merged_100m_gitter.parquet` | `merge` | Same at 100 m |
| `totals_10km.parquet` | `totals` | 10 km cells + `POP_TOTAL_10km` consensus column |
| `totals_1km.parquet` | `totals` | 1 km cells + `POP_TOTAL_1km` + `scale` (adjustment factor) |
| `totals_100m.parquet` | `totals` | 100 m cells + `POP_TOTAL_100m` + `scale` |
| `df10_with_single_years.parquet` | `ages` | 10 km cells + `AGE_0`..`AGE_100` |
| `df1_with_single_years.parquet` | `ages` | 1 km cells + `AGE_0`..`AGE_100` |
| `df100_with_single_years.parquet` | `ages` | 100 m cells + `AGE_0`..`AGE_100` + `is_orphan` flag |
| `cells_100m_with_gemeinde.parquet` | `gemeinde` | 100 m cells + ARS sub-fields (Land, Kreis, Gemeinde, …) |
| `cells_100m_with_gender_backfilled.parquet` | `gender` | + `M_AGE_0`..`M_AGE_100`, `F_AGE_0`..`F_AGE_100`, `M_TOTAL`, `F_TOTAL` |
| `cells_100m_with_gender_backf_binneds_happyorphans.parquet` | `topics8` | + 8 harmonized categorical topics (`*_adj` totals + category columns) |
| `cells_100m_with_gender_backf_binneds_happyorphans_with_aggs.parquet` | `aggs` | + decade-binned age aggregates (`M_AGE_0_9_agg`…`F_AGE_80_plus_agg`, `AGE_*_agg`) |
| `cells_100m_with_gender_backf_binneds_happyorphans_with_aggs_regiostar.parquet` | `regiostar` | + RegioStaR columns (`RegioStaR2`, `RegioStaR4`, `RegioStaR17`, `RegioStaR7`, `RegioStaR5`, `RegioStaRGem7`, `RegioStaRGem5`) — this file is the final prepared input |

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

### Destatis-CSV supplement columns (7 tables, all gated EXACT)

The `merge` stage optionally ingests 7 Destatis CSV ZIPs from `data/raw/destatis/`
that supply topics absent from z22data (z11-only in z22data's feature set).
All 33 + 14 produced columns gate EXACT against the notebook-era T: artifacts
(see `docs/Z22_GATE_REPORT.md`).

| ZIP name | Column group | Categories |
|---|---|---|
| `Seniorenstatus_eines_privaten_Haushalts.zip` | `*_Seniorenstatus_eines_privaten_Haushalts_*` | 4 (Insgesamt + 3 senior-status types) |
| `Typ_des_privaren_Haushalts_Lebensform.zip` | `*_Typ_priv_HH_Lebensform_*` | 8 (Insgesamt + 7 lifestyle types) |
| `Typ_des_privaten_Haushalts_Familien.zip` | `*_Typ_priv_HH_Familie_*` | 6 (Insgesamt + 5 family types) |
| `Religion.zip` | `*_Religion_*` | 4 (Insgesamt + kath. + evang. + Sonstiges/ohne) |
| `Zahl_der_Staatsangehoerigkeiten.zip` | `*_Zahl_der_Staatsangehoerigkeiten_*` | 5 (Insgesamt + 4 citizenship-count cats) |
| `Groesse_der_Kernfamilie.zip` | `*_Grosse_Kernfamilie_bis6undmehrPers_*` | 6 (Insgesamt + 5 family-size cats) |
| `Typ_der_Kernfamilie_nach_Kindern.zip` | `*_Typ_der_Kernfamilie_nach_Kindern_*` | 14 (Insgesamt + 13 family-type-by-children cats) |

### Tenure columns (when `derived_tenure = true`)

Two columns are added to both the 1 km and 100 m output files:

| Column | Level | Description |
|---|---|---|
| `EigentuemerHH_Tenure_1km-Gitter` | 1 km | Estimated number of owner-occupier households |
| `MieterHH_Tenure_1km-Gitter` | 1 km | Estimated number of renter households |
| `EigentuemerHH_Tenure_100m-Gitter` | 100 m | Estimated number of owner-occupier households |
| `MieterHH_Tenure_100m-Gitter` | 100 m | Estimated number of renter households |

Values are stored as `float32`.

### Vacancy columns (when `derived_vacancy = true`)

Two columns are added to both the 1 km and 100 m output files:

| Column | Level | Description |
|---|---|---|
| `BewohntWhg_Leerstand_1km-Gitter` | 1 km | Estimated number of occupied (inhabited) dwellings |
| `LeerstehendWhg_Leerstand_1km-Gitter` | 1 km | Estimated number of vacant dwellings |
| `BewohntWhg_Leerstand_100m-Gitter` | 100 m | Estimated number of occupied dwellings |
| `LeerstehendWhg_Leerstand_100m-Gitter` | 100 m | Estimated number of vacant dwellings |

Values are stored as `float32`. Derived from the `Leerstandsquote` ratio column and anchored
to the universe-A dwelling total (`Insgesamt_Wohnungen_Wohnungen_nach_Zahl_der_Raeume_*_adj`
≈ 41.8 M dwellings). **Universe-A approximation note:** The official Zensus 2022 vacancy rate
(4.3 %) is defined on universe B (≈ 42.5 M dwellings in residential buildings); anchoring to
universe A introduces a ~1.7 % universe difference, so `occupied + vacant` will sum to universe A
(not B). National vacancy signal rate: 4.26 % (consistent with official ≈ 4.3 %).

### Gemeinde-level control outputs (`--gemeinde-controls`)

Running `uv run cleancensus --config config.toml --gemeinde-controls` writes three Parquet
files to `<outputs_dir>/gemeinde_controls/`:

| File | Universe | National total (Bund) | Gemeinde rows | Description |
|---|---|---|---|---|
| `erwerbsstatus.parquet` | Persons 15+ | 80,777,360 | 10,786 | Labour-force participation (Erwerbstätige, Erwerbslose, Nichterwerbspersonen) by sex |
| `schulabschluss.parquet` | Persons 15+ | 69,439,520 | 10,786 | Highest school qualification (Hauptschule, POS, Realschule, Abitur, ohne) by sex |
| `berufl_abschluss.parquet` | Persons 15+ | 69,439,520 | 10,786 | Highest vocational qualification (Lehre, Fachschule, Bachelor, Master, Diplom, Promotion, ohne) by sex |

All three tables carry 12-digit ARS keys; suppressed values are NaN. See
[`docs/GEMEINDE_CONTROLS.md`](GEMEINDE_CONTROLS.md) for the full column dictionary, MiD
crosswalks, and the geography/overspecification notes.

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
