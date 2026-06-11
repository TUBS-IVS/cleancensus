# Notebook Archive (original pipeline, preserved)

These notebooks are the ORIGINAL implementation of the cleancensus data preparation,
including their run history (cell outputs). They are preserved unchanged for
provenance: their outputs are the canonical input files of the script pipeline.
Do not re-run them casually — several stages take hours and the produced inputs
are already final.

## Provenance map

All four data-producing notebooks are now **fully superseded** by cleancensus pipeline stages.
The archived notebooks are kept unchanged for provenance only — do not re-run them.

| Notebook | What it produced | Superseded by |
|---|---|---|
| `data_prep.ipynb` | merged 10 km/1 km/100 m Zensus tables; population totals reconciled across levels (IPF); basis pickles/CSVs (`df10_with_single_years.pickle`, `merged_*_gitter.csv`) | **`cleancensus/z22.py`** (`merge` stage: `FEATURE_MAP`, `download_z22`, `build_merged_table`) + **`cleancensus/ingest_totals.py`** (`totals` stage) |
| `ages.ipynb` | single-year age columns `AGE_0..AGE_100` per cell | **`cleancensus/ages_stage.py`** (`ages` stage: `fit_single_years_10km`, `downscale_single_years`) |
| `gender.ipynb` | Gemeinde spatial join (cell [4]); gender split `M_AGE_*` / `F_AGE_*` (cell [6]); orphan backfill (cell [8]) | **`cleancensus/gemeinde_stage.py`** (`gemeinde` stage) + **`cleancensus/gender_stage.py`** (`gender` stage) + **`cleancensus/enrich.py`** (`aggs` + `regiostar` stages, reconstructed) |
| `other_binned_data.ipynb` | trust-blended IPF downscaling of 8 categorical topics (Familienstand, Energieträger, Heizungsart, HH-Größe, Lebensform, Räume, Wohnfläche, Geburtsland) → `*_adj` totals + harmonized categories; orphan fix ("happyorphans") | **`cleancensus/harmonization.py`** (cell 1 extracted VERBATIM) + **`cleancensus/topics8.py`** (`topics8` stage) + `cleancensus/stages.py` (extend stage driver) |
| `overlays.ipynb` | visual checks on intermediate outputs | **`cleancensus/sanity.py`** + `tools/equivalence_zgb.py` |

## Figures

`before_after_distro.png`, `resolution_gain_boxplot.png`, `spatial_entropy_map.png` —
analysis figures from the original runs (see the paper:
Petre, Bienzeisler, Friedrich (2026), Procedia Computer Science 280, 965-970,
doi:10.1016/j.procs.2026.04.122).

## Equivalence

The script pipeline was gated against these notebooks' outputs: the ZGB-region
re-run reproduces the legacy results with max abs deviation 3e-05 (float32 noise);
raw totals bit-exact. See `tools/equivalence_zgb.py` and the repo README.
