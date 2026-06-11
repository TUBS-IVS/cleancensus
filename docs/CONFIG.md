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

**External file config keys** (pass these as top-level keys under `[stages]` or as TOML
string values at the top level — they are read via `getattr(cfg, key, None)` at runtime):

| Config key | Stage | Description |
|---|---|---|
| `gemeinde_age_csv_path` | `gender` | Path to the GENESIS 1000A-2027 CSV export (population by age and sex at Gemeinde level). Download from [ergebnisse.zensus2022.de/datenbank/online/table/1000A-2027](https://ergebnisse.zensus2022.de/datenbank/online/table/1000A-2027). |
| `vg250_gpkg_path` | `gemeinde` | Path to BKG VG250 GeoPackage (`DE_VG250.gpkg`, reference date 2022-01-01, EPSG:25832). |
| `regiostar_ref` | `regiostar` | Path to BBSR `regiostar_referenzdatei.xlsx` (sheet `ReferenzGebietsstand2020`). Default: `data/inputs/regiostar_referenzdatei.xlsx`. |

**CLI flags:**

| Flag | Description |
|---|---|
| `--dry-run` | Print the resolved execution plan and exit; no I/O |
| `--force` | Re-run stages even if their outputs already exist (bypass cache) |
| `--from <stage>` | Skip all stages before `<stage>` (treat them as already complete) |

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

# Paths to external reference files (required for gemeinde and gender stages):
# gemeinde_age_csv_path = "data/inputs/1000A-2027_de.csv"
# vg250_gpkg_path       = "data/inputs/DE_VG250.gpkg"
# regiostar_ref         = "data/inputs/regiostar_referenzdatei.xlsx"
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
