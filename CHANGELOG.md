# Changelog

**Note on versioning:** versions below refer to **data harmonization snapshots** (the results
of specific pipeline runs); the software itself is versioned independently — see
`CITATION.cff` / `pyproject.toml`. In the new pipeline a single run with `derived_tenure = true`
produces what previously required two separate runs (v2 topic harmonization + v3 tenure),
all in one `version_tag`.

All notable changes to cleancensus are documented here.
Dates are the date the run was validated or the version was released.

---

## [Unreleased] — full raw→final pipeline + documentation

### Full raw→final pipeline (stages 1–11)

- Implemented all 8 raw→prepared stages, completing the full pipeline from z22data
  ingest to the final harmonized cell tables:
  - **merge** (`cleancensus/z22.py`): `FEATURE_MAP` (160 entries, all 36 z22data features),
    `download_z22()`, `build_merged_table()` — ingest from Jonas Lieth's z22data GitHub mirror.
  - **totals** (`cleancensus/ingest_totals.py`): consensus collapse of population total columns
    + proportional cross-level adjustment (10 km → 1 km → 100 m).
  - **ages** (`cleancensus/ages_stage.py`): single-year age columns `AGE_0..AGE_100` via
    trust-mixed multiplicative IPF; hierarchical downscaling.
  - **gemeinde** (`cleancensus/gemeinde_stage.py`): streaming spatial join of BKG VG250
    Gemeinde polygons onto 100 m cell centroids; ARS sub-fields attached.
  - **gender** (`cleancensus/gender_stage.py`): M/F age split from GENESIS 1000A-2027
    per-Gemeinde shares + orphan backfill (36 cells).
  - **topics8** (`cleancensus/topics8.py`): trust-blended IPF downscaling of the 8 original
    categorical topics (Familienstand, Energietraeger, Heizungsart, Haushaltsgroesse,
    Lebensform, Raeume, Wohnflaeche, Geburtsland) 10 km → 1 km → 100 m.
  - **aggs** (`cleancensus/enrich.py`): decade-binned gendered age aggregates.
  - **regiostar** (`cleancensus/enrich.py`): BBSR RegioStaR 2022 join via 8-digit AGS.
- Stage orchestration: `cleancensus/pipeline.py` registers all 11 stages with full
  `plan()` / `run_pipeline()` / `--force` / `--from` support.
- `[stages]` TOML block: 9 producer switches (default: only `extend = true`).

### z22data ingest and FEATURE_MAP completion

- `FEATURE_MAP` now covers all 36 z22data feature names (160 entries, fully spot-gated).
- **Corrected z22data feature-name inversion**: `building_size` and `dwelling_building_size`
  feature names in z22data are swapped relative to their literal meaning (translation
  mix-up in the upstream z22 project). The `FEATURE_MAP` maps them semantically correctly
  (`building_size` → `Wohnung_*`, `dwelling_building_size` → `Geb_*`); verified by the
  MFH_13+ discriminator (buildings with 13+ dwellings are FEW, dwellings in such buildings
  are MANY). See `docs/Z22_GATE_REPORT.md` for the full investigation.
- Vacancy/market-vacancy/owner-occupier ratio features mapped:
  `Leerstandsquote_Leerstandsquote`, `marktaktive_Leerstandsquote_Marktaktive_Leerstandsquote`,
  `Eigentuemerquote_Eigentuemerquote`.
- `tools/download_zensus_grid.py` downloader added for the Destatis portal alternative.

### Gate reports

- `docs/Z22_GATE_REPORT.md`: 10 km gate (157/158 exact + 1 near-exact); 1 km gate
  (158/159 exact + 1 systematic disclosure suppression); Coverage completion section.
- `docs/AGES_GATE_REPORT.md`: totals 10 km exact, 1 km max|d|=3.6e-12; ages all levels
  exact (full national 10 km/1 km; 100 m subset).
- `docs/GENDER_GATE_REPORT.md`: gender backfill 36/36 exact; Bavaria column sums rel.
  diff < 2.4e-6 (float32 noise).

### Documentation

- README.md: eleven-stage flowchart, dual quickstart (prepared/full mode), stage gate
  summary table, updated repository layout and data section.
- `docs/CONFIG.md`: `[stages]` block with 9 producer switches, external file config keys
  (`gemeinde_age_csv_path`, `vg250_gpkg_path`, `regiostar_ref`), CLI flags, full-mode
  example config.
- `docs/DATA.md`: work_dir intermediates table (12 chained files); updated derivation chain.
- `notebooks_archive/ARCHIVE_README.md`: provenance table "Superseded by" column updated.

### Tests

- pytest suite expanded from 23 to 125+ tests covering all new stages.
- `test_z22.py`: `test_minimum_size` now asserts `>= 160`; new
  `test_all_36_z22data_features_present` and `test_vacancies_features_present` guards.

---

## [Unreleased] — pipeline refactor (earlier)

- Extracted the entire pipeline into the `cleancensus/` Python package
  (`config.py`, `harmonization.py`, `topics.py`, `stages.py`, `tenure.py`,
  `sanity.py`, `cli.py`).
- Single TOML config contract (`Config` dataclass, `load_config`); all paths,
  topic selection, scope, and run behaviour controlled from one file.
- CLI entry point: `uv run cleancensus --config config.toml [--dry-run]`.
- Equivalence gate (`tools/equivalence_zgb.py`): new package output == legacy
  script output; worst `max|d| = 3.05e-05` (float32 noise), raw totals bit-exact,
  over 43,660 ZGB cells.
- Comprehensive pytest suite: 23 tests covering config validation, topic catalog,
  harmonization numerics, stage orchestration, and CLI.
- Complete documentation set: `README.md`, `docs/METHOD.md`, `docs/DATA.md`,
  `docs/CONFIG.md`, `CHANGELOG.md`, `CITATION.cff`, `LICENSE` (GPL-3.0).

---

## v3 — 2026-06-10 (legacy two-step: v2 topic harmonization + tenure)

- Derived tenure topic: owner-occupier and renter household counts at 1 km and 100 m,
  derived from the published `Eigentuemerquote` ratio.
- Fill strategy: missing 1 km quotes filled from the HH-weighted 10 km group mean
  (12,086 cells) or the national mean (9 cells).
- 100 m downscaling via the same trust-blended IPF mechanism as categorical topics.
- Validated national owner share: 0.4419 (official Zensus 2022 benchmark ≈ 0.436).
- 4 orphan cells deviate by > 0.5 and at most 3 households from the tenure anchor (benign,
  reported as INFO).
- *New pipeline note:* `derived_tenure = true` in a single config run reproduces the
  combined v2+v3 result without two separate runs.

---

## v2 — 2026-06-10 (topic harmonization run; v3 adds tenure on top)

- Extended topic harmonization: `Whg_Gebaeudetyp` (10 categories, Wohnungen B universe)
  and `HH_Seniorenstatus` (3 categories, Haushalte universe) harmonized nationally at
  100 m.
- 3,148,482 cells processed; 0 sanity failures; `sum(categories) == *_adj` exact per cell.
- `Seniorenstatus_adj == HH-Groesse_adj` per cell exact.
- National mass relative deviation: 0.0001.
- Raw-to-harmonized ratio range: 1.00 – 1.07.

---

## v1 — 2026-01 (notebooks era)

Original 8-topic harmonization + ages/gender pipeline implemented in
`notebooks_archive/` by F. Petre.

- 8 categorical topics harmonized using trust-blended IPF:
  Familienstand, Energietraeger, Heizungsart, Haushaltsgroesse, Lebensform,
  Raeume, Wohnflaeche, Geburtsland.
- Single-year ages `AGE_0` – `AGE_100` per cell.
- Gender split `M_AGE_*` / `F_AGE_*` per cell.
- Orphan 100 m cells handled ("happyorphans" pass).
- Results described in: Petre, F., Bienzeisler, L., Friedrich, B. (2026).
  *Procedia Computer Science*, 280, 965-970.
  [doi:10.1016/j.procs.2026.04.122](https://doi.org/10.1016/j.procs.2026.04.122)
