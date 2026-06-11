# Gemeinde-level control tables (Zensus Regionaltabellen P2/P4)

This document describes the Gemeinde-level control tables produced from the Zensus 2022
Regionaltabellen (P2: Bildung/Erwerbstätigkeit; P4: Demografie).

These tables are **not** pipeline stages. They are Gemeinde-resolution marginal totals that
serve as PopulationSim controls in the eqasim-bs synthetic-population workflow.
They complement the grid-cell outputs (100 m / 1 km) produced by the main pipeline.

---

## Source data

**File:** `Regionaltabelle_Bildung_Erwerbstaetigkeit.xlsx`
(Zensus 2022, Statistische Ämter des Bundes und der Länder)

- Reference date: 15 May 2022 (`Berichtszeitpunkt: 20220515`)
- Download: [Zensus 2022 Ergebnisdatenbank](https://ergebnisse.zensus2022.de) →
  Regionaldaten → P2 Bildung und Erwerbstätigkeit
- Licence: dl-de/by-2-0

The file contains three CSV-sheets relevant to this pipeline:

| Logical name | Excel sheet name | Topic |
|---|---|---|
| `erwerbsstatus` | `CSV-Erwerbsstatus` | Labour-force participation (ILO) |
| `schulabschluss` | `CSV-Hoechster_Schulabschluss` | Highest school qualification |
| `berufl_abschluss` | `CSV-Hoechster_berufl_Abschluss` | Highest vocational qualification |

---

## Structure of the Regionaltabellen

Each CSV-sheet contains rows for **all geographic levels** simultaneously:

| Regionalebene | Meaning | Row count |
|---|---|---|
| `Bund` | Federal total (Germany) | 1 |
| `Land` | State (16 Länder) | 16 |
| `Regierungsbezirk` | Administrative district | 29 |
| `Stadtkreis/kreisfreie Stadt/Landkreis` | County / urban district | 400 |
| `Gemeindeverband` | Municipal association | 1,207 |
| `Gemeinde` | Municipality | 10,786 |

**ARS key column:** `_RS` — 12-digit Amtlicher Regionalschlüssel
(2-digit Land + 1-digit RB + 2-digit Kreis + 4-digit Gemeindeverband + 3-digit Gemeinde).
The `build_gemeinde_controls` parser reads `_RS` as a string and zero-pads it to 12 digits.

**Suppression:** small-count values are suppressed with `/` in the source.
The parser converts `/` (and any other non-numeric token) to `NaN` via `pd.to_numeric(errors='coerce')`.

---

## Output tables and columns

Output files land in `<outputs_dir>/gemeinde_controls/`:

### `erwerbsstatus.parquet`

Universe: persons 15 years and older classified by employment status (ILO definition).
National total (Bund): 80,777,360 persons.

| Column | Meaning |
|---|---|
| `ARS` | 12-digit Amtlicher Regionalschlüssel |
| `Name` | Municipality name |
| `ERWERBSTAT_KURZ_STP` | Insgesamt (total 15+ population) |
| `ERWERBSTAT_KURZ_STP__M` | Männlich (male) |
| `ERWERBSTAT_KURZ_STP__W` | Weiblich (female) |
| `ERWERBSTAT_KURZ_STP__1` | Erwerbspersonen (labour force: employed + unemployed) |
| `ERWERBSTAT_KURZ_STP__1_M` | Erwerbspersonen männlich |
| `ERWERBSTAT_KURZ_STP__1_W` | Erwerbspersonen weiblich |
| `ERWERBSTAT_KURZ_STP__11` | Erwerbstätige (employed) |
| `ERWERBSTAT_KURZ_STP__11_M` | Erwerbstätige männlich |
| `ERWERBSTAT_KURZ_STP__11_W` | Erwerbstätige weiblich |
| `ERWERBSTAT_KURZ_STP__12` | Erwerbslose (ILO unemployed) |
| `ERWERBSTAT_KURZ_STP__12_M` | Erwerbslose männlich |
| `ERWERBSTAT_KURZ_STP__12_W` | Erwerbslose weiblich |
| `ERWERBSTAT_KURZ_STP__2` | Nichterwerbspersonen (not in labour force) |
| `ERWERBSTAT_KURZ_STP__2_M` | NEP männlich |
| `ERWERBSTAT_KURZ_STP__2_W` | NEP weiblich |

Bund-level totals: Erwerbstätige 41,043,450 | Erwerbspersonen 43,752,890 |
Nichterwerbspersonen 37,024,470.

### `schulabschluss.parquet`

Universe: persons 15 years and older by highest general school qualification.
National total (Bund): 69,439,520 persons.

| Column | Meaning |
|---|---|
| `ARS` | 12-digit ARS |
| `Name` | Municipality name |
| `SCHULABS_STP` | Insgesamt (15+ persons) |
| `SCHULABS_STP__1` | Noch in schulischer Ausbildung (still in school) |
| `SCHULABS_STP__2` | Mit allgemeinbildendem Schulabschluss (has a school qualification) |
| `SCHULABS_STP__21` | Haupt-/Volksschulabschluss |
| `SCHULABS_STP__22` | Abschluss der Polytechnischen Oberschule (POS, DDR) |
| `SCHULABS_STP__23` | Realschulabschluss / Mittlere Reife |
| `SCHULABS_STP__24` | Fachhochschul- oder Hochschulreife (Abitur) |
| `SCHULABS_STP__3` | Ohne allgemeinbildenden Schulabschluss |

### `berufl_abschluss.parquet`

Universe: persons 15 years and older by highest vocational qualification (detailed).
National total (Bund): 69,439,520 persons.

| Column | Meaning |
|---|---|
| `ARS` | 12-digit ARS |
| `Name` | Municipality name |
| `BERUFABS_AUSF_STP` | Insgesamt (15+ persons) |
| `BERUFABS_AUSF_STP__1` | Mit beruflichem Bildungsabschluss (has a vocational qualification) |
| `BERUFABS_AUSF_STP__11` | Lehre / Berufsausbildung im dualen System |
| `BERUFABS_AUSF_STP__12` | Fachschulabschluss (West) |
| `BERUFABS_AUSF_STP__13` | Fachschulabschluss in der ehem. DDR |
| `BERUFABS_AUSF_STP__14` | Bachelor |
| `BERUFABS_AUSF_STP__15` | Master |
| `BERUFABS_AUSF_STP__16` | Diplom |
| `BERUFABS_AUSF_STP__17` | Promotion |
| `BERUFABS_AUSF_STP__2` | Ohne beruflichen Bildungsabschluss |

---

## Coverage

| Table | Gemeinden | Gemeinden with total unsuppressed | Suppression share (total row) | National sum from unsuppressed Gemeinden |
|---|---|---|---|---|
| `erwerbsstatus` | 10,786 | 1,578 | 85.4 % | 59,946,770 (74.2 % of Bund) |
| `schulabschluss` | 10,786 | ~1,578 | ~85.4 % | 51,557,370 |
| `berufl_abschluss` | 10,786 | ~1,578 | ~85.4 % | 51,557,370 |

**Note on high suppression rates:** Small municipalities have all cells suppressed when any
cell value is below the Zensus 2022 disclosure threshold. The 85 % suppression rate of the
*total count column* reflects the dominance of very small Gemeinden in the German municipal
structure. Larger Gemeinden (covering the bulk of the national population) have unsuppressed
totals. The ParquetWriter writes NaN for suppressed cells — downstream code must treat NaN as
"suppressed, do not use" and rely on Kreis- or Land-level marginals for small municipalities.

---

## Proposed MiD crosswalks for PopulationSim controls

### Erwerbsstatus ↔ MiD `taet`

The MiD 2023 variable `taet` classifies the principal occupation of survey respondents.
Proposed category mapping (coarsened to avoid overspecification — see warning below):

| Zensus Erwerbsstatus code | Zensus label | MiD `taet` value(s) | MiD label |
|---|---|---|---|
| `__11` | Erwerbstätige | 1 | Erwerbstätig (Voll-/Teilzeit/Minijob) |
| `__12` | Erwerbslose (ILO) | 5 | Sonstiges (nicht erwerbstätig) |
| `__1` (gap) | Erwerbspersonen not yet classified | 5 | Sonstiges |
| `__2` | Nichterwerbspersonen | 2, 3, 4, 5 | Schüler/Student/Azubi, Hausfrau/-mann, Rentner/Pensionär, Sonstiges |

**Mapping limitations:**
- MiD distinguishes Schüler/Stud./Azubi (2), Hausfrau (3), Rentner (4), Sonstiges (5) within
  Nichterwerbspersonen; Zensus collapses these into a single `__2` code.
- The Zensus Erwerbslose (ILO) correspond most closely to MiD `taet=5` but are not separately
  coded; they are a small fraction (~3 %) of the total.
- **Recommended control:** use `ERWERBSTAT_KURZ_STP__11` (Erwerbstätige) as a binary control
  (employed vs. not-employed), mapping to MiD `taet==1` vs. `taet!=1`.
  This gives a clean 2-category control with high Gemeinde coverage.

### Schulabschluss ↔ MiD `bildung1`

MiD `bildung1` classifies the highest school qualification of the respondent.
Proposed mapping (4-category crosswalk):

| Zensus code | Zensus label | MiD `bildung1` value | MiD label |
|---|---|---|---|
| `__21` | Haupt-/Volksschulabschluss | 1 | Hauptschulabschluss |
| `__22` | POS-Abschluss (DDR) | 2 | Mittlere Reife (DDR equivalent) |
| `__23` | Realschulabschluss / Mittlere Reife | 2 | Mittlere Reife |
| `__24` | Fachhochschul- oder Hochschulreife | 3 | Hochschulreife / Abitur |
| `__3` | Ohne allgemeinbildenden Schulabschluss | 4 | Kein Schulabschluss |
| `__1` | Noch in schulischer Ausbildung | — | Exclude or map to respondent-type |

### Berufl. Abschluss ↔ MiD `bildung2`

MiD `bildung2` classifies the highest vocational qualification.
Proposed mapping (3-category crosswalk):

| Zensus code | Zensus label | MiD `bildung2` value | MiD label |
|---|---|---|---|
| `__11` | Lehre / duales System | 1 | Berufsausbildung |
| `__12` + `__13` | Fachschulabschluss (West/DDR) | 1 | Berufsausbildung (Fachschule) |
| `__14` + `__15` + `__16` + `__17` | Bachelor/Master/Diplom/Promotion | 2 | (Fach-)Hochschulabschluss |
| `__2` | Ohne beruflichen Bildungsabschluss | 3 | Kein Berufsabschluss |

---

## Multi-geography note

The Regionaltabellen operate at **Gemeinde** resolution. The main pipeline grid cells operate
at **100 m / 1 km** cell resolution. There is no direct cell-level link between the two:

- Grid cells ≤ 1 km² are spatial sub-units of municipalities; the `ARS` field in the 100 m
  grid output (from the `gemeinde` stage) maps each cell to its parent municipality.
- PopulationSim uses Gemeinde-level totals (`ARS`) as seed/control marginals; the grid cells
  (with their spatial topics harmonized) serve as the synthetic-person zones.
- The Gemeinde control tables are thus marginals for the **correct** geographic unit for
  PopulationSim's `geo_cross_walk` mechanism (ZONE → PUMA → META → etc.).

---

## Overspecification warning

Adding both Erwerbsstatus and Bildung controls simultaneously to a PopulationSim run
risks overspecification — the controls may be collinear (employed persons tend to have
higher qualifications; student/apprentice status overlaps with in-schooling).

**Recommended gate before wiring:**
1. Add one control at a time, measure the fit improvement in eqasim-bs.
2. Monitor the IPF convergence rate and the maximum household weight ratio.
3. If adding a second Bildung control (schulabschluss + berufl_abschluss simultaneously)
   does not improve household weight distribution meaningfully (e.g. RMSE < 2 % improvement),
   drop the weaker control.

The wiring of these controls into the eqasim-bs PopulationSim configuration is done in the
`eqasim-bs` repository, not here.

---

## How to generate

```bash
# Place the xlsx in data/raw/regionaltabellen/ then run:
uv run cleancensus --config config.toml --gemeinde-controls
```

Outputs are written to `<outputs_dir>/gemeinde_controls/`:
- `erwerbsstatus.parquet`
- `schulabschluss.parquet`
- `berufl_abschluss.parquet`

Source: `cleancensus/gemeinde_controls.py` — `build_gemeinde_controls()` / `run_gemeinde_controls()`.

## Suppression handling (approved design, 2026-06-11)

Two output levels per table (see `docs/superpowers/specs/2026-06-11-gemeinde-controls-suppression-design.md`):

1. **Kreis tables (`kreis_*.parquet`) — always written, exact.** Source Kreis rows are
   copied verbatim. Kreis-level suppression is 0% for Erwerbsstatus; Bildung tables have
   a small residue (Schulabschluss 76/9,600 = 0.8%, berufl. Abschluss 472/12,000 = 3.9%
   cells, concentrated in fine gender x Promotion splits). **Recommendation for ZGB runs:
   use the Kreis level as the control geography** (BS/SZ/WOB are kreisfrei, so Kreis ==
   Stadt there).
2. **Gemeinde completion (`--fill harmonize`) — optional, estimated.** Each Kreis acts as
   the parent of its Gemeinden; unsuppressed Gemeinden carry local signal, suppressed ones
   receive population-weighted totals and trust-blended category fills (the repo's standard
   downscaling machinery over the ARS hierarchy). `is_estimated` flags every row that had
   any suppressed value. Logged per category: estimated-Gemeinde count + their population
   share (~9,200 Gemeinden / ~26% of population for the main categories).

Guarantees with `--fill harmonize`:
- Sum(Gemeinden) == Kreis per category **wherever the Kreis value is observed**
  (max abs diff 0.0000 in the national run).
- Where the Kreis value itself is suppressed (Bildung fine splits, see above), no sharp
  target exists; both levels are then model-based and the reported per-category
  "max sum-vs-Kreis abs diff" can be non-zero (observed up to ~240 on national category
  masses of millions, i.e. rel ~1e-4).
- Observed Gemeinden are only touched by the per-Kreis feasibility rescale
  (max |scale-1| ~ 1e-3, logged) — published rounding makes Gemeinde and Kreis
  "Insgesamt" values mutually inconsistent by a few persons (e.g. kreisfreie Stadt
  Zweibrücken: delta = 10).
- Degenerate Kreise (parent mass but zero child signal because the Kreis total of that
  category was suppressed) fall back to an equal split, mirroring make_child_totals_adj.

**Overspecification reminder:** prefer few reliable controls; Gemeinde-level estimated
values should only become popsim controls after a measure-gain check (eqasim-side).
