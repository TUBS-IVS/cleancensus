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

| Key | Type | Default | Validation | Effect |
|---|---|---|---|---|
| `topics` | list of strings, or the literal string `"all"` | *(omit for default)* | Each name must be in `RAW_TOPICS`; `"all"` selects all 14 catalog topics; mutually exclusive with `tiers` | Explicit list of topic names to harmonize |
| `tiers` | list of integers | *(omit for default)* | Values must be from `{1, 2, 3}`; mutually exclusive with `topics` | Selects all topics belonging to the given tiers |
| `derived_tenure` | bool | `false` | — | When `true`, runs `run_tenure` after the harmonization stages and appends tenure checks to `run_sanity` |

### `[scope]`

| Key | Type | Default | Validation | Effect |
|---|---|---|---|---|
| `mode` | `"national"` or `"subset"` | `"national"` | Exactly one of the two values | `"national"` processes all cells; `"subset"` filters to the given ARS prefixes |
| `ars_prefixes` | list of strings | `[]` | Required and non-empty when `mode = "subset"`; must be absent (or empty) when `mode = "national"` | ARS-5 codes (2-digit Land + 1-digit Regierungsbezirk + 2-digit Kreis) used to select 1 km parent cells for subset runs |

### `[run]`

| Key | Type | Default | Validation | Effect |
|---|---|---|---|---|
| `sanity` | `"fail"`, `"warn"`, or `"skip"` | `"fail"` | Exactly one of the three values | `"fail"` — exit code 1 if any invariant check fails; `"warn"` — print failures but exit 0; `"skip"` — omit sanity stage entirely |
| `write_manifest` | bool | `true` | — | When `true`, writes `run_manifest_<version_tag>.json` to `outputs_dir` on completion |

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

Use this pattern to test on the ZGB (Zukunftsregion Gesundheit Bochum) region subset,
which covers 8 districts in Lower Saxony.

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
