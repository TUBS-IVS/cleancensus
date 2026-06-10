# Changelog

**Note on versioning:** versions below refer to **data harmonization snapshots** (the results
of specific pipeline runs); the software itself is versioned independently — see
`CITATION.cff` / `pyproject.toml`. In the new pipeline a single run with `derived_tenure = true`
produces what previously required two separate runs (v2 topic harmonization + v3 tenure),
all in one `version_tag`.

All notable changes to cleancensus are documented here.
Dates are the date the run was validated or the version was released.

---

## [Unreleased] — pipeline refactor

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
