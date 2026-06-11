# Design: Handling disclosure suppression in Gemeinde-level controls (Erwerb/Bildung)

Date: 2026-06-11 · Status: approved (user)

## Problem

The Zensus 2022 Regionaltabelle Bildung+Erwerbstätigkeit suppresses ~85–89 % of
Gemeinde-level cell values (9,208 of 10,786 Gemeinden affected; the 1,578 unsuppressed
Gemeinden cover 74 % of the population). Kreis-level rows are **0 % suppressed**
(verified: all 400 Kreise complete, incl. the 8 ZGB Kreise). PopulationSim controls
need complete (non-NaN) control totals per geography.

## Use cases

- **A (primary): ZGB popsim runs** — 8 Kreise; BS/SZ/WOB are kreisfrei (Kreis == Stadt).
- **B (repo-generic): all of Germany** — public GPL repo, others should be able to use it.

## Decision (approach 1 + 2 combined; pseudo-zone approach rejected)

1. **Kreis level is always emitted, exact** (from the Kreis rows; no estimation).
   For ZGB this is the recommended control geography — documented in
   docs/GEMEINDE_CONTROLS.md, wiring stays in eqasim-bs behind its measure-gain gate.
2. **Optional Gemeinde completion via the repo's own harmonization machinery**
   (`fill = "harmonize"`): treat each Kreis as parent and its Gemeinden as children —
   unsuppressed Gemeinden carry local signal, suppressed ones get the trust-blended
   IPF fill (population-weighted Kreis shares as no-signal prior), identical in spirit
   to the tenure/vacancy derivation but over the ARS hierarchy instead of the grid.
   Output gains an `is_estimated` flag per Gemeinde×table; observed Gemeinden are
   NEVER modified except the final raking that makes Σ(Gemeinden) == Kreis exact.
3. Rejected: "Rest-Kreis" pseudo-zones (exact but pushes mixed-geography complexity
   into every downstream crosswalk).

## Interface

`cleancensus --config ... --gemeinde-controls [--fill harmonize]`
(default fill = none → current behaviour + NEW: additionally write
`gemeinde_controls/kreis_{erwerbsstatus,schulabschluss,berufl_abschluss}.parquet`).
With `--fill harmonize`: gemeinde parquets gain completed values + `is_estimated`.

## Invariants / gates

- Kreis tables: identical to the source rows (exact).
- fill=harmonize: Σ(Gemeinden within Kreis) == Kreis value per category (< 0.5 abs);
  observed (unsuppressed) Gemeinden unchanged within raking tolerance (rel < 1e-3,
  report max change); `is_estimated` true exactly for previously-NaN rows;
  no NaN/negatives in output.
- Honest reporting: per-table count of estimated Gemeinden + their population share.

## Out of scope

popsim control wiring (eqasim-bs, measure-gain gate); choosing Kreis vs Gemeinde as
the control geography (user decision per run, documented trade-off).
