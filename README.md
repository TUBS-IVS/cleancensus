# cleancensus

Preparation and harmonization of the German **Zensus 2022 grid data** (100m / 1km / 10km)
into consistent, analysis-ready cell tables — the spatial backbone for synthetic
population generation (PopulationSim / eqasim).

## What it does

The raw Zensus 2022 grid tables are perturbed for disclosure control: category counts do
not sum to the published totals, and the three grid levels disagree with each other. This
repo makes them consistent:

1. **Merge** all Zensus 2022 grid CSVs per level (10km / 1km / 100m).
2. **Adjust totals** across levels (IPF): population totals at each level are reconciled
   against the coarser level.
3. **Downscale topics** (`other_binned_data` method): per categorical topic
   (e.g. marital status, household size, dwelling size), a trust-blended IPF rakes the
   100m category vectors so that per cell `sum(categories) == adjusted total` and the
   1km category margins are respected. Adjusted totals get an `_adj` suffix.
4. **Orphan handling**: 100m cells without a 1km parent get prior-based imputation.
5. **Single-year ages + gender**: separate pipeline (`ages.ipynb`, `gender.ipynb`)
   produces `AGE_0..`, `M_AGE_*`, `F_AGE_*` columns.

## Repository layout

| Path | What |
|---|---|
| `*.ipynb` | Original pipeline notebooks (reference implementation; run history preserved) |
| `harmonization.py` | The downscaling machinery, extracted verbatim from `other_binned_data.ipynb` |
| `new_topics.py` | Spec catalog of additional topics; default scope = topics controllable via MiD household data (`Whg_Gebaeudetyp`, `HH_Seniorenstatus`) |
| `extend_topics.py` | Driver: `stage_a` (10km→1km), `stage_b` (1km→100m, streamed over the 7.7 GB file) |
| `sanity_extend.py` | Post-run invariant checks (exit code 0 = pass) |
| `paths.py` | Single source of truth for data locations (repo-relative, `data/` is gitignored) |
| `tests/` | pytest suite (synthetic fixtures + schema validation against the real files) |
| `data/inputs/`, `data/outputs/` | Local only, never committed |

## Usage

```bash
uv sync                                  # install deps (Python >= 3.13)
uv run pytest                            # tests
uv run python extend_topics.py stage_a   # 10km -> 1km (minutes)
uv run python extend_topics.py stage_b   # 1km -> 100m (national: ~1-2 h)
uv run python sanity_extend.py           # invariants; 0 failures required
```

Subset validation run (e.g. ZGB region) before a national run:
`extend_topics.py stage_b --parents-csv zgb_parents.csv`.

Other topics from the catalog: `--topics Geb_Baujahr Pers_Religion ...`
(see `new_topics.RAW_TOPICS`; default deliberately covers only what MiD household
data can control as PopulationSim targets).

## Data

Inputs are NOT in this repo (size + Zensus licensing). Required in `data/inputs/`:

| File | Source |
|---|---|
| `df10_with_single_years.pickle` | 10km merged Zensus tables (from `data_prep.ipynb`) |
| `cells_1km_with_binneds.parquet` | 1km cells incl. previous harmonization run |
| `cells_100m_with_gender_backf_binneds_happyorphans_with_aggs_regiostar.parquet` | the prepared 100m cell table (3.15M cells × 570 cols, all Germany) |

Note: zero values in harmonized columns can be true zeros OR disclosure-suppressed
values filled with 0 — they are indistinguishable downstream.

## Method invariants (checked by `sanity_extend.py`)

- per topic: `sum(categories) == Insgesamt_*_adj` per cell (hard, < 0.5 abs)
- topics sharing a universe have per-cell identical `_adj` totals
- national mass per topic within 2% of the 10km raw total
- no NaN / negatives in produced columns
