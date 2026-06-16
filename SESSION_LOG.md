# Session Log

## [2026-06-16] eqasim-bs popsim — Kreis-Income-Control + Logging/Progress + tier1/2 fit → shipped to BS main

Built and shipped three eqasim-bs features to `origin/main` (TUBS-IVS/eqasim-bs, fast-forward to
`a75ac98`): **Kreis-Income-Control** (replaces the `midpoint × INKAR_scale` income fudge with a real
continuous MiD draw + max-entropy per-Kreis calibration; adds a per-capita income column + a Pareto
open-top tail), **coloured live logging + progress bar** (cleancensus port: `braunschweig/
logging_setup.py` + `progress.py`, wired into run_synpp/batch/handoff), and an **`hh_type5` seed-build
fix** found via systematic debugging (the default `complete_members=True` path never derived
`hh_type5`, crashing the Tier-1 household_type control). Enabling `controls_source: catalog` +
`control_tiers: tier0,1,2` + stratify turned household_size/type/tenure/building_type control-fit from
"needs improvement" → **very good** (building_type 15.8→0.38pp), validated on a 1.10M-person full-region
run. Made the per-batch PopulationSim timeout configurable (`batch_timeout_s`, 0=disable) + worker
tuning. Each feature TDD'd subagent-driven with two-stage review. Artifact: HTML report at
`~/.agent/diagrams/allfeatures-report.html`. Memory: `project-control-catalog-tier12` updated +
`reference-eqasim-bs-run-conventions` added. NEXT: optional clean run (no timeout, 8+ workers); D =
Tier-3 Gemeinde controls (Erwerb+Bildung).

## [2026-06-15] Income-signal cell-column inventory — investigation (interrupted)

Set up (but did not run) a read-only inventory of every 100m cell-level variable that could
carry a within-Kreis household-income signal, for the popsim-g5 worktree. Confirmed the prepared
parquet path (`eqasim-data/.../zensus2022_grid_100m_de_prepared.parquet`, 8.5GB, config key
`braunschweig.population.popsim.cells_100m_path`) and the exact cleaned column names the income
tilt already reads in stage.py (`durchschnMieteQM_Durchschn_Nettokaltmiete_100m_Gitter`,
`Eigentuemerquote_Eigentuemerquote_100m_Gitter`, the HH-weight `_adj` col), with cleaning via
`prepared_cells.clean_col_name`. Session was /close'd before the coverage-on-03101 script ran;
no cleancensus code changed (work was in the eqasim-bs worktree, read-only).

Main artifact: memory `project-control-catalog-tier12.md` (2026-06-15 update + new OPEN item 0).

## [2026-06-14] PopulationSim control catalog (cleancensus → eqasim-bs) + income-tilt design

Designed (brainstorm) and built the full **MiD-controllable PopulationSim control catalog** for
eqasim-bs popsim_mid/open: a filtered superset `CatalogControl` foundation (csv-default
byte-identical | catalog switch), then **household_size** (both seeds), **household_type**
(MiD, 5-class), **tenure** (H_MIETE), **building_type** (3-class, with a new multi-column census
aggregation), plus a **popsim_validation** module (realized-vs-target SRMSE/coverage/grade,
seniorenstatus as a reference). To make household_type a clean `_adj`, harmonized the
`HH_Familientyp` topic in cleancensus (new `config_mid_controls.toml` trio, national extend-only,
sanity 0 failures) and imported it to the canonical eqasim-data path (old file backed up).
787 tests green, baseline guard 9/9. **Pushed** both feature branches
(eqasim-bs `feature/population-method-workflows` +21; cleancensus `feature/harmonize-tier1-2`).
Also: a cited **deep-research** report on rent→income, feeding a **design spec + plan** for a
Nettokaltmiete-based within-Kreis spatial income tilt (GAMMA layer, default-ON + tested OFF path)
— planned, not yet built.

Main artifacts: eqasim-bs `docs/superpowers/{specs,plans}/2026-06-14-popsim-control-catalog-*`
+ `...-nettokaltmiete-income-tilt*` (gitignored, popsim-g5) · cleancensus `config_mid_controls.toml`.

## [2026-06-14] cleancensus — z22data fixes + full E2E validation + pipeline polish

Reported two upstream z22data bugs (building_size/dwelling_building_size swap = issue #4; and
sparse `households_0` totals at 1km/100m) — both fixed upstream by JsLth the same day; adapted
our merge accordingly (z22 primary HH source again, cache-bust required). Completed the **first
full raw→final `--force` E2E run with 0 sanity failures** (HH_Groesse==Seniorenstatus max|d|=0,
was 7936). Delivered a pipeline polish: central colourised stdlib logging (`logsetup.py`), a
file-name registry with legacy aliases (`names.py`, work_dir → `NN_<stage>_<level>`), an elegant
startup banner + run summary (`report.py`), `--verbose/--quiet`, and a fancy in-place coloured
progress bar (`progress.py`); all 15 stages converted to per-stage loggers; docs updated. Also
rebuilt an ACL-corrupted `.venv`, installed `gh`. 303 tests green. All merged to `main`
(PR #1 + merge `eabfddc`).

Main artifact: `docs/superpowers/specs/2026-06-13-pipeline-polish-logging-naming-design.md` ·
main @ `eabfddc`.
