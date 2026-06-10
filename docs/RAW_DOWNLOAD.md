# Downloading Raw Zensus 2022 Grid Data

---

## Recommended: z22data mirror (default merge stage)

The `merge` stage now ingests directly from the **z22data GitHub mirror** by Jonas Lieth —
a stable, machine-readable distribution of the Zensus 2022 grid data as Parquet files,
requiring no manual portal navigation or ZIP unpacking.

| | |
|---|---|
| **z22data repo** | https://github.com/JsLth/z22data |
| **z22 R package** | https://github.com/JsLth/z22 |
| **URL pattern** | `https://raw.githubusercontent.com/JsLth/z22data/main/z22_data_{level}/{feature}_{cat}.parquet` |
| **Levels** | `10km`, `1km`, `100m` |
| **Format** | Parquet, columns `x`/`y` (INSPIRE midpoints, EPSG:3035 m) + `value` |
| **License** | **dl-de/by-2-0** (same as original Destatis data) |

**Credit:** Jonas Lieth's [z22](https://github.com/JsLth/z22) / [z22data](https://github.com/JsLth/z22data)
project provides the Parquet conversion and hosting that makes this ingest path possible.

**Attribution** (required for any publication or data product):
> Census content: **© Statistische Ämter des Bundes und der Länder, Zensus 2022**
> Grid geometry: **© GeoBasis-DE / BKG 2023** (<https://www.bkg.bund.de>)
> z22data mirror: Jonas Lieth (<https://github.com/JsLth/z22>)

Enable the merge stage in your config to have the pipeline download and assemble the grid
automatically:

```toml
[stages]
merge = true
```

Downloads are cached in `data/raw/z22/` (gitignored). Re-runs are skipped if files exist.
See [`docs/Z22_GATE_REPORT.md`](Z22_GATE_REPORT.md) for the validation of this ingest path
against the notebook-era reference merges.

---

## Alternative: Destatis portal (manual download)

This page explains how to obtain the official Zensus 2022 grid-cell CSVs that the
cleancensus pipeline processes.  Everything is handled by a single tool script;
no third-party packages are required.

---

## Portal and source

| | |
|---|---|
| **Human portal** | [www.zensus2022.de → Ergebnisse → Gitterzellenbasierte Ergebnisse](https://www.zensus2022.de/DE/Ergebnisse-des-Zensus/gitterzellen.html) |
| **Destatis redirect** | <https://www.destatis.de/zensus2022> |
| **GENESIS database** | <https://ergebnisse.zensus2022.de/datenbank/online/> |
| **Confirmed download base path** | `https://www.destatis.de/DE/Themen/Gesellschaft-Umwelt/Bevoelkerung/Zensus2022/Publikationen/Downloads-Publikationen/Gitterdaten/` |

Asset URLs follow the pattern:
```
<base>/<slug>.zip?__blob=publicationFile&v=<N>
```
(the `v=` version query string is optional; omitting it still resolves to the current file).

---

## Licence and attribution

All Zensus 2022 grid data is published under the **Open Data Licence Germany – Attribution 2.0
(dl-de/by-2-0)**: <https://www.govdata.de/dl-de/by-2-0>.

Required attribution in any publication or product:

> Census content: **© Statistische Ämter des Bundes und der Länder, Zensus 2022**
> Grid geometry: **© GeoBasis-DE / BKG 2023** (<https://www.bkg.bund.de>)

The download script prints this reminder at the end of every download run.

---

## Quick start

### 1  Probe which candidate URLs resolve

```bash
uv run python tools/download_zensus_grid.py \
    --manifest tools/zensus_grid_manifest.toml \
    --probe
```

This performs lightweight HTTP checks on every topic that has a `zip =` slug in the manifest
and prints a table:

```
topic                               status / note
--------------------------------------------------------------------
wohnungen_zahl_raeume               OK  <size>
  URL:  https://www.destatis.de/…/wohnungen_zahl_raeume.zip?__blob=…
auslaenderanteil_eu_nicht_eu        OK  <size>
  URL:  …
einwohner                           [skip] no slug — add zip= in manifest (see TODO entries)
…
```

Topics with `zip = ""` (the TODO entries) are skipped.  Entries that resolve to an HTML page
instead of a ZIP are reported as `redirect-to-html` — that means the slug is wrong and needs
to be looked up on the live portal (see section below).

### 2  Download all resolved ZIPs

```bash
uv run python tools/download_zensus_grid.py \
    --manifest tools/zensus_grid_manifest.toml \
    --out data/raw
```

Options:

| Flag | Default | Description |
|---|---|---|
| `--manifest` | *(required)* | Path to `tools/zensus_grid_manifest.toml` |
| `--out` | `data/raw` | Root output dir; ZIPs land in `<out>/zips/`, CSVs in `<out>/csv/` |
| `--only` | *(all)* | Space-separated list of topic names to restrict download |
| `--probe` | off | Check URLs only; do not download |

The script:
- Resumes partial downloads (HTTP Range header).
- Skips ZIPs that are already complete (by Content-Length).
- Retries up to 3 times on network errors (backoff 5 / 15 / 30 s).
- Unzips all CSV members flat into `<out>/csv/`.
- Rejects HTML responses instead of silently saving them as `.zip`.

### 3  Download a single topic for testing

```bash
uv run python tools/download_zensus_grid.py \
    --manifest tools/zensus_grid_manifest.toml \
    --only wohnungen_zahl_raeume \
    --out data/raw
```

---

## Completing the manifest (browser required)

The Destatis download portal is a JavaScript application; it cannot be
machine-enumerated.  For every topic listed with `zip = ""` in
`tools/zensus_grid_manifest.toml`:

1. Open the portal in a browser:
   <https://www.zensus2022.de/DE/Ergebnisse-des-Zensus/gitterzellen.html>
2. Find the relevant dataset ("Gitterdaten zum Download …").
3. Right-click the **ZIP download button** → *Copy link address*.
4. Extract the filename from the URL (everything between the last `/` and `?`).
5. Paste it as the `zip` value for that `[[topic]]` entry in the manifest.
6. Re-run `--probe` to verify it resolves.

---

## Where the CSVs land and how the merge stage uses them

Unzipped CSVs are placed in `<out>/csv/` (default: `data/raw/csv/`).

The merge stage (enabled via `[stages] merge = true` in your config) globs for files
matching `*<level>-Gitter*.csv` in the directory configured as `raw_dir`, for example:

```toml
[data]
raw_dir = "data/raw/csv"
```

The expected filename convention from Destatis is:
```
Zensus2022_<Thema>_<level>-Gitter.csv
```
e.g. `Zensus2022_Bevoelkerung_100m-Gitter.csv`.

Make sure `raw_dir` in your config points to the same directory where the downloader
places the CSVs (`data/raw/csv` by default).

---

## Disk-space estimates

| Level | Topics | Approx. size (all unzipped) |
|---|---|---|
| 100 m | population alone | ~315 MB (compressed ZIP ~80 MB) |
| All levels, all topics | ~20 GB unzipped | ~6–8 GB ZIPs |

A full national download is the user's responsibility; the `--probe` run
verifies slugs without transferring significant data.
