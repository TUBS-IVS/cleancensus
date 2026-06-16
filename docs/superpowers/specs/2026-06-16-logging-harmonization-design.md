---
title: Logging & Terminal-UX Harmonization (Scheme B — phase-grouped colour)
date: 2026-06-16
status: Draft — awaiting user review
supersedes-partial: 2026-06-13-pipeline-polish-logging-naming-design.md (refines its logging layer)
---

# Logging & CLI Harmonization — Design

## Problem

cleancensus already has a polished logging stack (`logsetup.py`, `progress.py`, `report.py`)
and a working colour story. It is **not broken — it is uneven** ("nicht wie aus einem Guss"):

1. **Three independent ANSI palettes.** `logsetup._LEVEL_COLOR/_ACCENT/_DIM`,
   `progress._CYAN/_DIM/_BOLD`, and `report._PAL` each define their own escape codes →
   they drift; there is no single source of truth.
2. **The stage tag is always cyan.** Every stage renders the same colour, so the eye gets
   *no* help grouping log lines by pipeline phase ("keine Farbe für verschiedene Aufgaben").
3. **Stray `print()` bypasses the logger.** e.g. the eqasim popsim `socioprofessional_class`
   line prints with no timestamp/level — breaks the visual rhythm.
4. **Progress rate degenerates.** On slow loops (minutes/hours per item) the rate prints
   `0.0 it/s` and the ETA jumps wildly (seen in the popsim batch run).
5. **cleancensus ↔ eqasim-bs drift.** eqasim-bs carries a separate hand-port of the same
   modules; the two looks diverge over time.

## Goals

- **One palette + one stage→phase map** in `cleancensus/theme.py`; `logsetup`/`progress`/
  `report` consume it. Re-tuning any colour is a one-file, one-line change.
- **Phase-grouped colour identity** on the stage tag (Scheme B): ~5 severity-safe hue
  families, so each pipeline phase reads at a glance — without a rainbow.
- **Adaptive progress rate** — never `0.0 it/s` again; smoothed ETA.
- **All pipeline output through the logger**; `print` reserved for banner/summary/progress.
- **eqasim-bs gets a verbatim copy** of `theme.py` (canonical home = cleancensus, its own
  project), kept in sync via a header note.

## Non-goals

- **No change to the log format** (`HH:MM:SS │ LEVEL │ stage │ message`) and **no change to
  the non-TTY/redirect guarantee** — `logs/*.log` stay colourless and greppable, byte-identical
  to today in the no-colour path.
- **No shared package / cross-repo import.** cleancensus is standalone; eqasim-bs gets a copy,
  not a dependency. (Future option, out of scope: publish cleancensus as a package and import.)
- **No new logging framework** — stay on stdlib `logging`.

## Design

### 1. `cleancensus/theme.py` — single source of truth

New module, the *only* place ANSI codes and the phase map live. Exports:

- `want_color(color="auto") -> bool` — the TTY / `NO_COLOR` / redirect / `CLEANCENSUS_COLOR`
  decision (moved out of `logsetup`; `report.color_enabled` becomes a thin re-export).
- **Severity palette** `LEVEL_COLOR`: DEBUG dim · INFO green · WARNING yellow · ERROR red ·
  CRITICAL bold-red.
- **Structural** `DIM`, `BOLD`, `RESET`, `BORDER`, `TITLE`, `ACCENT`.
- **Phase palette** `PHASE_COLOR: dict[phase, ansi]` (256-colour, see §2).
- **Stage→phase map** `PHASE_OF: dict[stage, phase]` + `phase_of(stage) -> phase`
  (unknown → `"misc"` → neutral grey).
- `stage_color(stage) -> ansi` = `PHASE_COLOR[phase_of(stage)]`.

`logsetup`, `progress`, `report` import from `theme` and delete their local colour constants.

### 2. Phase taxonomy & colour map (Scheme B)

Phase hues are chosen **distinct from the severity palette** (green/yellow/red) so a stage tag
never reads as a warning. 256-colour, with a basic-16 fallback when 256 is unsupported
(`CLEANCENSUS_COLOR=auto|basic|none`, default auto). Severity always wins on the LEVEL column.

| Phase | Hue (256) | cleancensus stages | eqasim popsim loggers |
|---|---|---|---|
| **Acquire** | azure `38;5;39` | `merge` `totals` `destatis` | `seed` `member_completion` |
| **Transform** | teal `38;5;43` | `ages` `gender` `topics8` `aggs` `regiostar` `harmonize` `extend` `tenure` `vacancy` | `stage` `mid` `batch` `merge` · `expand` `missing` `attributes` |
| **Validate** | violet `38;5;141` | `sanity` | (popsim_validation) |
| **Controls / Income** | orange `38;5;208` | `gemeinde` `gemeinde-controls` *(+ Tier-3 later)* | `income` `income_kreis_control` `income_spatial_tilt` |
| **Orchestrate** | slate (dim) `38;5;103` | `cli` `pipeline` | `synpp` |
| misc / unknown | grey `38;5;245` | — | — |

*(Exact 256 codes are a starting point, tunable in `theme.py` — see §"Colour tuning".)*

### 3. Log line

Format unchanged. Only the **stage field** is coloured by `stage_color(stage)` instead of the
constant cyan accent. timestamp dim · LEVEL severity-coloured · message default. The no-colour
path is unchanged (golden-string tested).

### 4. Progress (`progress.py`) — adaptive rate + smoothed ETA

Replace the single `{rate:.1f} it/s` with an adaptive formatter `format_rate(rate)`:

- `rate ≥ 1/s`   → `12.3/s`
- `1/min ≤ rate < 1/s` → `45.0/min`
- `rate < 1/min`  → per-item duration, `~52m/it`
- `i == 0` or `elapsed == 0` → omit the rate token entirely (never print `0.0`)

ETA uses a lightly smoothed rate (EWMA over recent items) so it stops swinging. Bar + spinner
colours come from `theme`. Non-TTY plain lines keep their greppable shape (rate token adapts).

### 5. Stray-`print` cleanup + guard

- Sweep every pipeline module (cleancensus, then eqasim-bs) for bare `print(`; route through the
  module's stage logger at the right level. *(Inventory is subagent-driven — see Plan.)*
- `print` survives **only** in `report.py` (banner/summary) and `progress.py` (the bar) —
  intentional stdout/stderr presentation.
- Add a test that asserts no bare `print(` in `cleancensus/*.py` except `report`/`progress`.

### 6. `report.py`

Banner, summary, and `stage_frame` pull every colour from `theme` (drop `_PAL`). `stage_frame`
colours the stage name with `stage_color()` so the per-stage frame matches its log lines.

### 7. eqasim-bs mirror

`braunschweig/theme.py` = verbatim copy of `cleancensus/theme.py` + header
`# Ported from cleancensus/theme.py — keep in sync.` `braunschweig/logging_setup.py` and
`progress.py` consume it (same edits as §1/§4). Shipped as a **separate PR in the eqasim-bs repo**
(origin = TUBS-IVS, never upstream). Only then is the look unified across both projects.

## Colour tuning / live demo

`config_demo.toml` (03101 subset, `extend→sanity` in minutes) is the tuning harness: run it to
see Scheme B in a real terminal, adjust `PHASE_COLOR` in `theme.py` (one place), re-run. No other
code changes. This is how hues get finalised after the first build.

## Testing

- **theme:** `phase_of` for known stages + unknown→`misc`; `want_color` decision matrix;
  `auto|basic|none` modes.
- **logsetup:** stage tag uses the phase colour; **no-colour output byte-identical** to today
  (golden string).
- **progress:** `format_rate` table (≥1/s, /min, /it, zero-case); ETA smoothing; non-TTY plain
  lines stay greppable.
- **report:** banner/summary render from theme; ASCII-fold path still works.
- **guard:** no bare `print(` in pipeline modules.
- Existing `test_logsetup` / `test_progress` stay green.

## Plan preview (for writing-plans)

1. `theme.py` + tests — extract the three palettes into one; prove no-colour output unchanged.
2. Rewire `logsetup`/`progress`/`report` onto `theme`; delete local palettes.
3. Phase map + stage-tag colouring + tests.
4. Adaptive progress rate + smoothed ETA + tests.
5. Stray-`print` sweep (subagent inventory across cleancensus) + guard test.
6. eqasim-bs mirror (separate repo / PR).

Each step TDD; cleancensus work → PR → `main` (merge via button).

## Decisions (defaults — flag any you want changed at review)

- 256-colour phase hues as in §2, severity-safe, tunable in `theme.py`.
- `tenure` / `vacancy` folded into **Transform** (no own hue).
- ERROR colours only the LEVEL column; the stage tag keeps its phase colour (calmer).
- Mirror = **copy**, not a shared package.
- Optional sidecar (separate PR): GitHub-Actions CI running pytest on PRs + `main` branch
  protection requiring it green. *(Independent of this design; decide separately.)*
