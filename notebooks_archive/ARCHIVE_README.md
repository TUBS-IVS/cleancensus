# Notebook Archive (original pipeline, preserved)

These notebooks are the ORIGINAL implementation of the cleancensus data preparation,
including their run history (cell outputs). They are preserved unchanged for
provenance: their outputs are the canonical input files of the script pipeline.
Do not re-run them casually — several stages take hours and the produced inputs
are already final.

## Provenance map

| Notebook | What it produced | Superseded by |
|---|---|---|
| `data_prep.ipynb` | merged 10km/1km/100m Zensus tables; population totals reconciled across levels (IPF); basis pickles/CSVs (`df10_with_single_years.pickle`, `merged_*_gitter.csv`) | not ported (one-off upstream step; outputs are the pipeline inputs) |
| `ages.ipynb` | single-year age columns `AGE_0..AGE_100` per cell | not ported (one-off) |
| `gender.ipynb` | gender split `M_AGE_*` / `F_AGE_*` + backfill (`cells_100m_with_gender_backfilled*.parquet`) | not ported (one-off) |
| `other_binned_data.ipynb` | trust-blended IPF downscaling of 8 categorical topics (Familienstand, Energieträger, Heizungsart, HH-Größe, Lebensform, Räume, Wohnfläche, Geburtsland) → `*_adj` totals + harmonized categories; orphan fix ("happyorphans") | **`cleancensus/harmonization.py`** (cell 1 extracted VERBATIM) + `cleancensus/stages.py` (driver) |
| `overlays.ipynb` | visual checks on intermediate outputs | superseded by `cleancensus/sanity.py` + `tools/equivalence_zgb.py` |

## Figures

`before_after_distro.png`, `resolution_gain_boxplot.png`, `spatial_entropy_map.png` —
analysis figures from the original runs (see the paper:
Petre, Bienzeisler, Friedrich (2026), Procedia Computer Science 280, 965-970,
doi:10.1016/j.procs.2026.04.122).

## Equivalence

The script pipeline was gated against these notebooks' outputs: the ZGB-region
re-run reproduces the legacy results with max abs deviation 3e-05 (float32 noise);
raw totals bit-exact. See `tools/equivalence_zgb.py` and the repo README.
