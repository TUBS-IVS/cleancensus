# Pipeline polish: unified logging, file naming & startup banner

**Date:** 2026-06-13
**Status:** approved (design)
**Goal:** Make the cleancensus pipeline look and feel like a professional software product —
one consistent, informative logging style across all stages, a single source of truth for
file names, an elegant startup banner + closing summary, and matching documentation.
Behaviour-preserving: no change to numeric outputs or the public output schema.

## Motivation

Today the pipeline is functionally complete but cosmetically inconsistent:
- Logging is split between stdlib `logging` (`ages`, `gemeinde`, `gender`, `ingest_totals`,
  `enrich`) and raw `print()` (`cli`, `harmonization`, `z22`, `topics8`, `stages`, `tenure`,
  `vacancy`, `sanity`, `gemeinde_controls`, `pipeline`). There is **no central logging
  config**, so `log.*` calls are effectively silent unless something configures the root
  logger; only the `print()` lines reliably show.
- Stage tags are ad-hoc and inconsistent: `[merge/z22]`, `[gender]`, `[topics8-100m]`,
  `[tenure-100m]`, `[aggs]`, …
- work_dir intermediate filenames are notebook-era and inconsistent
  (`cells_100m_with_gender_backf_binneds_happyorphans_with_aggs_regiostar.parquet`,
  `df10_with_single_years.parquet`, `merged_{level}_gitter.parquet`, …), scattered as string
  literals across modules.

## Decisions (agreed with user)

1. **Logging engine:** stdlib `logging` + a custom colorized formatter. No new dependency.
2. **Naming:** unify everything via a central registry; keep the public **output** schema
   `zensus2022_grid_{level}_de_{tag}.parquet`; renumber/standardize work_dir intermediates;
   keep **read-fallbacks** for every renamed file so existing artifacts, gates and consumers
   keep working.
3. **Banner:** the "elegant box" style + config/scope/options/stages summary.
4. **Docs:** README + DATA.md + CHANGELOG + any doc referencing old names get cleaned up to
   match.

## Components

### 1. `cleancensus/logsetup.py` (new)
- `setup_logging(level="INFO", color="auto") -> None` — called once in `cli.main()` (and a
  safe no-op-ish default so library use still works).
- `ColorFormatter(logging.Formatter)` rendering `HH:MM:SS │ LEVEL │ stage │ message`.
  - Level colored (DEBUG dim, INFO green, WARNING yellow, ERROR/CRITICAL red), timestamp dim,
    stage tag in an accent color.
  - Colour auto-disabled when `not sys.stderr.isatty()`, `NO_COLOR` is set, or output is
    redirected to a file (so `logs/*.log` stays clean plain text).
- Stage tag comes from the logger name: each module uses `log = get_logger("merge")` →
  logger `cleancensus.merge`; the formatter shows the short suffix as the `stage` field.
- `get_logger(stage: str)` helper wrapping `logging.getLogger(f"cleancensus.{stage}")`.

### 2. `cleancensus/names.py` (new) — single source of truth for file names
- Constants/helpers for every pipeline artifact, parameterized by `level`/`tag`:
  - Inputs (canonical, unchanged): `zensus2022_grid_{level}_de_prepared.parquet`.
  - Outputs (unchanged schema): `zensus2022_grid_{level}_de_{tag}.parquet`; subset
    standardized to `…_de_{tag}_subset.parquet`.
  - work_dir intermediates, stage-numbered & uniform:
    `01_merge_{level}.parquet`, `02_totals_{level}.parquet`, `03_ages_{level}.parquet`,
    `04_gemeinde_100m.parquet`, `05_gender_100m.parquet`,
    `06_topics8_{1km,100m}.parquet`, `07_aggs_100m.parquet`, `08_regiostar_100m.parquet`.
- `legacy_aliases(name) -> list[str]` returns historical names for read-fallback. `config.py`
  and each stage resolve inputs via "new name first, then aliases", exactly as the canonical
  input resolution already does.
- `config.py` work_dir/output properties delegate to `names.py` (no literals in config).

### 3. Banner + stage framing + summary (in `cli.py` / `pipeline.py` + a small `report.py` helper)
- `print_banner(cfg)`: elegant box + `config / scope / options / stages` lines.
- Restyle the per-stage frame to one consistent look: `▶ stage k/N · <stage>` + a dim rule,
  keeping the existing last-run/ETA timing.
- `print_summary(cfg, timings, failures, outputs)`: closing box with ✓/✗ status, a per-stage
  timings table, output paths + sizes, and the sanity result.

### 4. Mechanical conversion across stages
- Replace `print("[tag] …")` and `log.info("[tag] …")` with `log.<level>(…)` on the
  per-stage logger (tag dropped from the message — the formatter adds it).
- Level discipline: routine progress = INFO; per-cell harmonization diagnostics
  (`INFO: abs difference …`, the parent/child dumps) = DEBUG; mass-rescale notes = WARNING.
- Add `--verbose/-v` (DEBUG) and `--quiet/-q` (WARNING) to the CLI; default INFO.
- `progress.py` bars stay; ensure they share the colour on/off decision and route through
  stderr so they interleave cleanly with logging.

## Non-goals
- No change to numeric results or the content of any output.
- No change to the public output filename **schema** (`zensus2022_grid_{level}_de_{tag}`).
- No unrelated refactoring of stage logic.

## Risk & mitigation
- **Consumer/gate breakage from renames:** every renamed work_dir/intermediate keeps a
  read-fallback alias; outputs keep their schema. Gate reports & eqasim consumers unaffected.
- **In-flight re-run:** unaffected — it runs from already-imported code and its outputs are
  not touched. New naming/logging applies to the next run.
- **Behaviour drift:** changes are limited to logging/printing and filename strings; full
  test suite (286) must stay green; a smoke run of `--dry-run` must render banner + plan.

## Rollout order
1. `logsetup.py` + `names.py` (+ wire `cli.main` and `config.py`).
2. Convert stages module-by-module to the per-stage logger (merge → … → sanity).
3. Banner + stage frame + summary.
4. `--verbose/--quiet` flags.
5. Update tests that assert names/printed strings.
6. Docs pass: README, DATA.md, CHANGELOG, any doc referencing old work_dir names.
7. `--dry-run` smoke check + full test suite green.

## Success criteria
- One consistent, colored (TTY) / clean (file) log line format across all 12 stages.
- All file names resolved from `names.py`; no scattered literals; old artifacts still read.
- Elegant banner on start, professional summary on finish.
- README/docs reflect the new naming and logging.
- 286 tests green; `--dry-run` shows banner + plan.
