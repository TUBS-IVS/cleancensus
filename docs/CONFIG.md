# Configuration Reference

cleancensus uses a single TOML config file.
Pass it with `--config <path>` on every invocation.

```
uv run cleancensus --config config.toml
uv run cleancensus --config config.toml --dry-run   # prints the plan, no I/O
```

The config file is loaded by `cleancensus/config.py:load_config()`.
All paths in the config are resolved relative to the directory that contains the config file.

---

## Sections and keys

### `[data]`

| Key | Type | Default | Validation | Effect |
|---|---|---|---|---|
| `inputs_dir` | string (path) | `"data/inputs"` | Must exist at run time | Directory containing the three canonical input files |
| `outputs_dir` | string (path) | `"data/outputs"` | Created if absent | Destination for versioned output parquet files and the run manifest |
| `version_tag` | string | `"v2"` | Any string; avoid spaces and slashes | Appended to output file names to distinguish pipeline runs |
| `destatis_raw_dir` | string (path) | *(derived)* | Optional | Override for the Destatis CSV ZIPs directory (default: `data/raw/destatis/` sibling of `inputs_dir`). Populated automatically by the merge stage if the directory exists. |
| `regiostar_ref` | string (path) | *(auto-discovered)* | Optional | Override the BBSR RegioStaR reference workbook. Default: auto-discovers the BBSR Referenz Gemeinden Gebietsstand 31.12.2022 xlsx in `data/raw/regiostar/`; falls back to the BMDV Gebietsstand2020 file if absent. |
| `regiostar_sheet` | string | `""` | Optional | Sheet name within the `regiostar_ref` workbook. Leave empty for auto-detection. |
| `regionaltabellen_xlsx` | string (path) | *(derived)* | Optional | Path to `Regionaltabelle_Bildung_Erwerbstaetigkeit.xlsx` for `--gemeinde-controls`. Default: `data/raw/regionaltabellen/Regionaltabelle_Bildung_Erwerbstaetigkeit.xlsx`. |
| `vg250_gpkg_path` | string (path) | *(auto-discovered)* | Optional | Override for the BKG VG250 GeoPackage used by the `gemeinde` stage. Default resolution: (1) this key, (2) `data/raw/vg250/DE_VG250.gpkg`, (3) T: legacy path (with warning). |
| `gemeinde_age_csv_path` | string (path) | *(auto-discovered)* | Optional | Override for the GENESIS 1000A-2027 CSV used by the `gender` stage. Default resolution: (1) this key, (2) `data/raw/genesis/1000A-2027_bevoelkerung_alter_geschlecht_gemeinden.csv`, (3) T: legacy path (with warning). |

### `[harmonize]`

Exactly one of `topics` or `tiers` may be specified; specifying both raises an error.
If neither is specified, the pipeline uses the MiD-controllable default:
`["Whg_Gebaeudetyp", "HH_Seniorenstatus"]`.
MiD = Mobilität in Deutschland, the German national household travel survey (2023 edition).
The default topics are exactly those census attributes that the MiD household data can serve
as PopulationSim controls for: building type via the geocoded `haustyp` variable
(`Whg_Gebaeudetyp`) and senior status via household member ages (`HH_Seniorenstatus`).

| Key | Type | Default | Validation | Effect |
|---|---|---|---|---|
| `topics` | list of strings, or the literal string `"all"` | *(omit for default)* | Each name must be in `RAW_TOPICS`; `"all"` selects all 14 catalog topics; mutually exclusive with `tiers` | Explicit list of topic names to harmonize |
| `tiers` | list of integers | *(omit for default)* | Values must be from `{1, 2, 3}`; mutually exclusive with `topics` | Selects all topics belonging to the given tiers |
| `derived_tenure` | bool | `false` | — | When `true`, runs `run_tenure` after the harmonization stages and appends tenure checks to `run_sanity`. Tenure anchors to the harmonized household total already present in the 100 m INPUT file; it does **not** require any specific topic in `[harmonize].topics`. |
| `derived_vacancy` | bool | `false` | — | When `true`, runs `run_vacancy` after the harmonization stages and adds `BewohntWhg_Leerstand_*` (occupied) and `LeerstehendWhg_Leerstand_*` (vacant) dwelling columns to both the 1 km and 100 m outputs. Anchored to the universe-A dwelling total (Wohnungen nach Zahl der Raeume ≈ 41.8 M). Signal: `Leerstandsquote > 0`; zero-quote cells receive parent-share fill. National vacancy rate ≈ 4.26 % (official Zensus 2022 ≈ 4.3 %). |

### `[scope]`

| Key | Type | Default | Validation | Effect |
|---|---|---|---|---|
| `mode` | `"national"` or `"subset"` | `"national"` | Exactly one of the two values | `"national"` processes all cells; `"subset"` filters to the given ARS prefixes |
| `ars_prefixes` | list of strings | `[]` | Required and non-empty when `mode = "subset"`; must be absent (or empty) when `mode = "national"` | ARS-5 codes (2-digit Land + 1-digit Regierungsbezirk + 2-digit Kreis) used to select 1 km parent cells for subset runs |

`mode = "subset"` without `ars_prefixes` (and vice versa: `ars_prefixes` set with `mode = "national"`) raises a `ValueError` at config load, before anything runs.

### `[run]`

| Key | Type | Default | Validation | Effect |
|---|---|---|---|---|
| `sanity` | `"fail"`, `"warn"`, or `"skip"` | `"fail"` | Exactly one of the three values | `"fail"` — exit code 1 if any invariant check fails; `"warn"` — print failures but exit 0; `"skip"` — omit sanity stage entirely |
| `write_manifest` | bool | `true` | — | When `true`, writes `run_manifest_<version_tag>.json` to `outputs_dir` on completion |

### `[stages]`

Controls which data-producing stages execute.  `tenure` is controlled by
`[harmonize].derived_tenure`; `sanity` is controlled by `[run].sanity` (not listed here).

By default only `extend = true`; all raw→prepared stages default to `false` (prepared-mode
behaviour — the three canonical input files in `data/inputs/` are used directly).

| Stage | Default | Description | Prerequisite |
|---|---|---|---|
| `merge` | `false` | Download z22data Parquet files and assemble wide tables at 10 km / 1 km / 100 m | Internet access; writes to `data/raw/z22/` |
| `totals` | `false` | Consensus-collapse population total columns; proportional cross-level adjustment | `merge` output in `work/` |
| `ages` | `false` | Single-year age columns `AGE_0..AGE_100` via trust-mixed IPF | `totals` output in `work/` |
| `gemeinde` | `false` | Spatial join of BKG VG250 Gemeinde polygons → ARS/Land/Kreis on 100 m cells | `ages` output; `vg250_gpkg_path` |
| `gender` | `false` | Male/female age split using GENESIS 1000A-2027 per-Gemeinde shares + orphan backfill | `gemeinde` output; `gemeinde_age_csv_path` |
| `topics8` | `false` | Trust-blended IPF downscaling of 8 original categorical topics 10 km → 1 km → 100 m | `gender` output |
| `aggs` | `false` | Decade-binned gendered age aggregates (`M_AGE_0_9_agg` … `F_AGE_80_plus_agg`) | `topics8` output |
| `regiostar` | `false` | Join 7 BBSR RegioStaR 2022 classification columns via 8-digit AGS | `aggs` output; `regiostar_referenzdatei.xlsx` |
| `extend` | **`true`** | Harmonize additional topics from the catalog (stage_a 10 km→1 km, stage_b 1 km→100 m) | Prepared input files in `data/inputs/` (or `regiostar` output) |

**External reference file config keys** (set these under `[data]` in the TOML):

| Config key | Stage | Default resolution | Description |
|---|---|---|---|
| `vg250_gpkg_path` | `gemeinde` | `data/raw/vg250/DE_VG250.gpkg` (then T: legacy path) | Path to BKG VG250 GeoPackage (`DE_VG250.gpkg`, reference date 2022-01-01, EPSG:25832). Copy from `T:\petre\...\vg250_ebenen_0101\DE_VG250.gpkg`. |
| `gemeinde_age_csv_path` | `gender` | `data/raw/genesis/1000A-2027_bevoelkerung_alter_geschlecht_gemeinden.csv` (then T: legacy path) | Path to the GENESIS 1000A-2027 CSV export (population by age and sex at Gemeinde level). Download from [ergebnisse.zensus2022.de/datenbank/online/table/1000A-2027](https://ergebnisse.zensus2022.de/datenbank/online/table/1000A-2027). |
| `regiostar_ref` | `regiostar` | `data/raw/regiostar/bbsr-referenz-gebietsstand-2022.xlsx` | Path to BBSR RegioStaR reference workbook. Default: auto-discovered in `data/raw/regiostar/`. |

**CLI flags:**

| Flag | Description |
|---|---|
| `--dry-run` | Print the resolved execution plan and exit; no I/O |
| `--force` | Re-run stages even if their outputs already exist (bypass cache) |
| `--from <stage>` | Skip all stages before `<stage>` (treat them as already complete) |
| `--gemeinde-controls` | Parse Regionaltabellen P2/P4 into Gemeinde-level parquets and exit. Does not run any pipeline stage. Source: `data/raw/regionaltabellen/Regionaltabelle_Bildung_Erwerbstaetigkeit.xlsx` (or `regionaltabellen_xlsx` in config). Writes `outputs_dir/gemeinde_controls/{erwerbsstatus,schulabschluss,berufl_abschluss}.parquet`. See [`docs/GEMEINDE_CONTROLS.md`](GEMEINDE_CONTROLS.md). |

---

## Example configurations

### (a) National default — two MiD-controllable topics + tenure

This is the configuration used for the validated national v2 run.

```toml
# config.toml — national default
[data]
inputs_dir  = "data/inputs"
outputs_dir = "data/outputs"
version_tag = "v2"

[harmonize]
topics = ["Whg_Gebaeudetyp", "HH_Seniorenstatus"]
derived_tenure = true

[scope]
mode = "national"

[run]
sanity = "fail"
write_manifest = true
```

### (b) ZGB subset validation — equivalence gate before national run

Use this pattern to test on the ZGB (Zweckverband Großraum Braunschweig — the regional
association of Braunschweig, covering 8 Kreise in Lower Saxony: Braunschweig 03101,
Salzgitter 03102, Wolfsburg 03103, Gifhorn 03151, Goslar 03153, Helmstedt 03154,
Peine 03157, Wolfenbüttel 03158) region subset.

```toml
# config_zgb_subset.toml — ZGB subset validation
[data]
inputs_dir  = "data/inputs"
outputs_dir = "data/outputs"
version_tag = "v2_zgb"

[harmonize]
topics = ["Whg_Gebaeudetyp", "HH_Seniorenstatus"]
derived_tenure = true

[scope]
mode = "subset"
ars_prefixes = ["03101", "03102", "03151", "03153", "03154", "03157", "03158", "03103"]

[run]
sanity = "fail"
write_manifest = true
```

Then compare against the reference output using:
```
uv run python tools/equivalence_zgb.py --new data/outputs/cells_100m_..._v2_zgb_SUBSET.parquet \
    --ref <reference.parquet>
```

### (c) Full catalog — all three tiers + tenure

Run the complete 14-topic catalog plus tenure.
Expect longer runtime (~2–3 h at 100 m) and larger output files.

```toml
# config_full.toml — all tiers 1-3 + tenure
[data]
inputs_dir  = "data/inputs"
outputs_dir = "data/outputs"
version_tag = "v3_full"

[harmonize]
tiers = [1, 2, 3]
derived_tenure = true

[scope]
mode = "national"

[run]
sanity = "warn"       # downgrade to warn so the run always completes
write_manifest = true
```

### (d) Full mode — raw→final pipeline (all 11 stages)

Run the complete pipeline from the raw z22data Parquet files through to the final output.
Requires internet access (merge stage) and the two external reference files (gemeinde/gender).

```toml
# config_fullmode.toml — complete raw->final pipeline
[data]
inputs_dir  = "data/inputs"
outputs_dir = "data/outputs"
version_tag = "v2_full"

[harmonize]
topics = ["Whg_Gebaeudetyp", "HH_Seniorenstatus"]
derived_tenure = true

[scope]
mode = "national"

[run]
sanity = "fail"
write_manifest = true

[stages]
merge     = true
totals    = true
ages      = true
gemeinde  = true
gender    = true
topics8   = true
aggs      = true
regiostar = true
extend    = true

# Paths to external reference files (auto-discovered under data/raw/ by default):
# vg250_gpkg_path         = "data/raw/vg250/DE_VG250.gpkg"
# gemeinde_age_csv_path   = "data/raw/genesis/1000A-2027_bevoelkerung_alter_geschlecht_gemeinden.csv"
# regiostar_ref           = "data/raw/regiostar/bbsr-referenz-gebietsstand-2022.xlsx"
```

---

## Topic catalog

For reference, the following topic names are valid in `topics = [...]`:

**Tier 1** (building and dwelling characteristics):
`Geb_Gebaeudetyp`, `Geb_AnzahlWohnungen`, `Geb_Baujahr`, `Geb_Energietraeger`,
`Whg_Gebaeudetyp`, `Whg_Heizungsart`

**Tier 2** (household composition and citizenship):
`HH_Seniorenstatus`, `HH_Familientyp`, `Pers_Staatsangehoerigkeit`

**Tier 3** (detailed citizenship, religion, family structure):
`Pers_StaatsangGruppen`, `Pers_ZahlStaatsang`, `Pers_Religion`,
`Fam_Groesse`, `Fam_TypNachKindern`

Use `topics = "all"` to select all 14 topics at once.
