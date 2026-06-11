# Destatis-CSV Supplement (6 Missing Tables) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the `merge` stage so the three per-level merged parquets include the 6 census grid topics that z22data does not mirror, by reading them directly from Destatis-downloaded ZIP files.

**Architecture:** New module `cleancensus/destatis_csv.py` encapsulates all ZIP-reading, column-naming, and table-merging logic for the 6 Destatis-CSV tables. `cleancensus/z22.py::run_merge_z22` is extended to call `merge_destatis_tables` and left-join the result onto the z22 table per level. The `Config` dataclass gains a `destatis_raw_dir` property (default `data/raw/destatis`); no new TOML key is required since the path is deterministic. The 6 ZIPs are copied (not moved) from `C:\Users\bienzeisler\Downloads\Zensus\` to `data/raw/destatis/`.

**Tech Stack:** Python 3.11, pandas, pyarrow/parquet, stdlib zipfile — no new dependencies.

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `cleancensus/destatis_csv.py` | **Create** | All logic for reading the 6 Destatis CSV ZIPs and merging them into a wide frame |
| `cleancensus/z22.py` | **Modify** | `run_merge_z22`: after building the z22 table, left-join Destatis supplement |
| `cleancensus/config.py` | **Modify** | Add `destatis_raw_dir` property to `Config` |
| `config.example.toml` | **Modify** | Add commented `destatis_raw_dir` key under `[data]` |
| `data/raw/destatis/` | **Populate** | Copy the 6 ZIPs here (gitignored; runtime only) |
| `tests/test_destatis_csv.py` | **Create** | Unit tests: registry shape, column naming, merge smoke |
| `docs/Z22_GATE_REPORT.md` | **Modify** | Append new section with gate numbers |

---

## Background: CSV Format (Verified by Reconnaissance)

- **Delimiter:** `;`
- **Encoding:** UTF-8 (try first); fall back to ISO-8859-1
- **Decimal:** comma (`,` → `.` conversion needed for float columns)
- **`–` suppressed values:** the `–` character (U+2013 EN DASH) appears in cells where Destatis suppressed a count. Read with `dtype=str` then convert numerically; treat `–` as NaN.
- **werterlaeuternde_Zeichen columns:** not present in the 6 target ZIPs (confirmed by inspection). If they appeared, drop them (columns named `werterlaeuternde_Zeichen*`).
- **GITTER_ID column name:** `GITTER_ID_{level}` — already correct, no rename needed.
- **x/y columns:** `x_mp_{level}`, `y_mp_{level}` — drop after reading (level coordinates already in z22 table).

## Background: Column Naming Convention (Verified vs T: Merged CSVs)

The notebook's `merge_gitter_level` function named columns as:

```
{data_col}_{filename_stem_without_Zensus2022_prefix}
```

where the stem includes the `{level}-Gitter` part, e.g.:

```
HH_nurSenioren_Seniorenstatus_eines_privaten_Haushalts_10km-Gitter
```

These names were verified to be IDENTICAL to the T: merged CSV headers. The `DESTATIS_TABLES` registry in `destatis_csv.py` encodes the exact mapping explicitly so column names are deterministic without inspecting the ZIP at runtime.

## Exact Column Names per Table (all levels)

Suffix pattern: `{data_col}_{file_stem_without_Zensus2022_prefix}` where file stem includes `_{level}-Gitter`.

### Seniorenstatus_eines_privaten_Haushalts.zip
CSV name: `Zensus2022_Seniorenstatus_eines_privaten_Haushalts_{level}-Gitter.csv`
Stem (after stripping `Zensus2022_`): `Seniorenstatus_eines_privaten_Haushalts_{level}-Gitter`

Data columns → full column names (10km example):
- `Insgesamt_Haushalte` → `Insgesamt_Haushalte_Seniorenstatus_eines_privaten_Haushalts_10km-Gitter`
- `HH_nurSenioren` → `HH_nurSenioren_Seniorenstatus_eines_privaten_Haushalts_10km-Gitter`
- `HH_mitSenioren` → `HH_mitSenioren_Seniorenstatus_eines_privaten_Haushalts_10km-Gitter`
- `HH_ohneSenioren` → `HH_ohneSenioren_Seniorenstatus_eines_privaten_Haushalts_10km-Gitter`

### Typ_des_privaren_Haushalts_Lebensform.zip  (Destatis typo: "privaren")
CSV name: `Typ_des_privaren_Haushalts_Lebensform/Zensus2022_Typ_priv_HH_Lebensform_{level}-Gitter.csv`
Stem: `Typ_priv_HH_Lebensform_{level}-Gitter`

Data columns:
- `Insgesamt_Haushalte` → `Insgesamt_Haushalte_Typ_priv_HH_Lebensform_10km-Gitter`
- `EinpersHH_SingleHH` → `EinpersHH_SingleHH_Typ_priv_HH_Lebensform_10km-Gitter`
- `Ehepaare` → `Ehepaare_Typ_priv_HH_Lebensform_10km-Gitter`
- `EingetrLebensp` → `EingetrLebensp_Typ_priv_HH_Lebensform_10km-Gitter`
- `NichtehelLebensg` → `NichtehelLebensg_Typ_priv_HH_Lebensform_10km-Gitter`
- `AlleinerzMuetter` → `AlleinerzMuetter_Typ_priv_HH_Lebensform_10km-Gitter`
- `AlleinerzVaeter` → `AlleinerzVaeter_Typ_priv_HH_Lebensform_10km-Gitter`
- `MehrpersHHohneKernfam` → `MehrpersHHohneKernfam_Typ_priv_HH_Lebensform_10km-Gitter`

### Typ_des_privaten_Haushalts_Familien.zip
CSV name: `Typ_des_privaten_Haushalts_Familien/Zensus2022_Typ_priv_HH_Familie_{level}-Gitter.csv`
Stem: `Typ_priv_HH_Familie_{level}-Gitter`

Data columns:
- `Insgesamt_Haushalte` → `Insgesamt_Haushalte_Typ_priv_HH_Familie_10km-Gitter`
- `EinpersHH_SingleHH` → `EinpersHH_SingleHH_Typ_priv_HH_Familie_10km-Gitter`
- `Paare_ohneKind` → `Paare_ohneKind_Typ_priv_HH_Familie_10km-Gitter`
- `Paare_mitKind` → `Paare_mitKind_Typ_priv_HH_Familie_10km-Gitter`
- `Alleinerziehende` → `Alleinerziehende_Typ_priv_HH_Familie_10km-Gitter`
- `MehrpersHHohneKernfam` → `MehrpersHHohneKernfam_Typ_priv_HH_Familie_10km-Gitter`

### Religion.zip
CSV name: `Zensus2022_Religion_{level}-Gitter.csv`
Stem: `Religion_{level}-Gitter`

Data columns:
- `Insgesamt_Bevoelkerung` → `Insgesamt_Bevoelkerung_Religion_10km-Gitter`
- `Roemisch_katholisch` → `Roemisch_katholisch_Religion_10km-Gitter`
- `Evangelisch` → `Evangelisch_Religion_10km-Gitter`
- `Sonstige_keine_ohneAngabe` → `Sonstige_keine_ohneAngabe_Religion_10km-Gitter`

### Zahl_der_Staatsangehoerigkeiten.zip
CSV name: `Zensus2022_Zahl_der_Staatsangehoerigkeiten_{level}-Gitter.csv`
Stem: `Zahl_der_Staatsangehoerigkeiten_{level}-Gitter`

Data columns:
- `Insgesamt_Bevoelkerung` → `Insgesamt_Bevoelkerung_Zahl_der_Staatsangehoerigkeiten_10km-Gitter`
- `EineStaatsang` → `EineStaatsang_Zahl_der_Staatsangehoerigkeiten_10km-Gitter`
- `Mehrere_deutsch_und_auslaendisch` → `Mehrere_deutsch_und_auslaendisch_Zahl_der_Staatsangehoerigkeiten_10km-Gitter`
- `Mehrere_nur_auslaendisch` → `Mehrere_nur_auslaendisch_Zahl_der_Staatsangehoerigkeiten_10km-Gitter`
- `Nicht_bekannt` → `Nicht_bekannt_Zahl_der_Staatsangehoerigkeiten_10km-Gitter`

### Groesse_der_Kernfamilie.zip
CSV name: `Groesse_der_Kernfamilie/Zensus2022_Grosse_Kernfamilie_bis6undmehrPers_{level}-Gitter.csv`
Stem: `Grosse_Kernfamilie_bis6undmehrPers_{level}-Gitter`  (note: "Grosse" not "Groesse" — Destatis typo in filename)

Data columns:
- `Insgesamt_Familien` → `Insgesamt_Familien_Grosse_Kernfamilie_bis6undmehrPers_10km-Gitter`
- `a2Personen` → `a2Personen_Grosse_Kernfamilie_bis6undmehrPers_10km-Gitter`
- `a3Personen` → `a3Personen_Grosse_Kernfamilie_bis6undmehrPers_10km-Gitter`
- `a4Personen` → `a4Personen_Grosse_Kernfamilie_bis6undmehrPers_10km-Gitter`
- `a5Personen` → `a5Personen_Grosse_Kernfamilie_bis6undmehrPers_10km-Gitter`
- `a6Pers_und_mehr` → `a6Pers_und_mehr_Grosse_Kernfamilie_bis6undmehrPers_10km-Gitter`

---

## Task 1: Copy ZIPs to data/raw/destatis/

**Files:**
- Populate: `data/raw/destatis/` (gitignored; runtime data, not tracked)

- [ ] **Step 1.1: Create the destination directory**

```powershell
New-Item -ItemType Directory -Force "c:\Users\bienzeisler\Documents\GitHub\cleancensus\data\raw\destatis"
```

Expected: directory created (or already exists — no error).

- [ ] **Step 1.2: Copy the 6 ZIPs**

```powershell
$src = "C:\Users\bienzeisler\Downloads\Zensus"
$dst = "c:\Users\bienzeisler\Documents\GitHub\cleancensus\data\raw\destatis"
$zips = @(
    "Seniorenstatus_eines_privaten_Haushalts.zip",
    "Typ_des_privaren_Haushalts_Lebensform.zip",
    "Typ_des_privaten_Haushalts_Familien.zip",
    "Religion.zip",
    "Zahl_der_Staatsangehoerigkeiten.zip",
    "Groesse_der_Kernfamilie.zip"
)
foreach ($z in $zips) {
    Copy-Item (Join-Path $src $z) (Join-Path $dst $z) -Force
    Write-Host "Copied: $z"
}
```

Expected output: 6 "Copied: ..." lines. Verify with `ls $dst`.

- [ ] **Step 1.3: Verify**

```powershell
ls "c:\Users\bienzeisler\Documents\GitHub\cleancensus\data\raw\destatis" | Select-Object Name, Length
```

Expected: 6 files, each > 100 KB.

---

## Task 2: Add `destatis_raw_dir` property to `Config`

**Files:**
- Modify: `c:\Users\bienzeisler\Documents\GitHub\cleancensus\cleancensus\config.py`
- Modify: `c:\Users\bienzeisler\Documents\GitHub\cleancensus\config.example.toml`

- [ ] **Step 2.1: Write a failing test for the new property**

In `tests/test_destatis_csv.py` (create file):

```python
"""Tests for cleancensus.destatis_csv."""
from __future__ import annotations


class TestConfigDesatisDir:
    def test_destatis_raw_dir_default(self, tmp_path):
        from cleancensus.config import Config
        cfg = Config(
            inputs_dir=tmp_path / "inputs",
            outputs_dir=tmp_path / "outputs",
            version_tag="test",
            topics=["Whg_Gebaeudetyp"],
            derived_tenure=False,
            mode="national",
            ars_prefixes=[],
            sanity="skip",
            write_manifest=False,
            stages={s: False for s in (
                "merge", "totals", "ages", "gemeinde", "gender",
                "topics8", "aggs", "regiostar", "extend"
            )},
            config_path=tmp_path / "config.toml",
        )
        # destatis_raw_dir should be data/raw/destatis relative to inputs_dir.parent
        assert cfg.destatis_raw_dir == tmp_path / "raw" / "destatis"
```

- [ ] **Step 2.2: Run test to verify it fails**

```powershell
cd "c:\Users\bienzeisler\Documents\GitHub\cleancensus"
uv run --no-sync pytest tests/test_destatis_csv.py::TestConfigDesatisDir -v
```

Expected: FAIL with `AttributeError: 'Config' object has no attribute 'destatis_raw_dir'`.

- [ ] **Step 2.3: Add the property to `Config`**

In `cleancensus/config.py`, after the `work_dir` property (around line 47), add:

```python
    @property
    def destatis_raw_dir(self) -> Path:
        """Directory containing the 6 Destatis CSV ZIPs (copied from Downloads).
        Defaults to data/raw/destatis (sibling of inputs_dir, gitignored).
        Create it and populate it before enabling the merge stage.
        """
        return self.inputs_dir.parent / "raw" / "destatis"
```

- [ ] **Step 2.4: Run test to verify it passes**

```powershell
uv run --no-sync pytest tests/test_destatis_csv.py::TestConfigDesatisDir -v
```

Expected: PASS.

- [ ] **Step 2.5: Add comment in config.example.toml**

In `config.example.toml` under `[data]`, add after `outputs_dir`:

```toml
# destatis_raw_dir = "data/raw/destatis"  # auto-derived; override only if ZIPs are elsewhere
```

- [ ] **Step 2.6: Commit**

```powershell
cd "c:\Users\bienzeisler\Documents\GitHub\cleancensus"
git add cleancensus/config.py config.example.toml tests/test_destatis_csv.py
git commit -m "feat: Config.destatis_raw_dir property + test skeleton"
```

---

## Task 3: Implement `cleancensus/destatis_csv.py`

**Files:**
- Create: `c:\Users\bienzeisler\Documents\GitHub\cleancensus\cleancensus\destatis_csv.py`

- [ ] **Step 3.1: Write failing tests first (add to test_destatis_csv.py)**

Append to `tests/test_destatis_csv.py`:

```python
class TestDesatisTablesRegistry:
    def test_destatis_tables_imported(self):
        from cleancensus.destatis_csv import DESTATIS_TABLES
        assert isinstance(DESTATIS_TABLES, dict)

    def test_six_tables_registered(self):
        from cleancensus.destatis_csv import DESTATIS_TABLES
        assert len(DESTATIS_TABLES) == 6

    def test_all_required_zip_names_present(self):
        from cleancensus.destatis_csv import DESTATIS_TABLES
        required_zips = {
            "Seniorenstatus_eines_privaten_Haushalts.zip",
            "Typ_des_privaren_Haushalts_Lebensform.zip",
            "Typ_des_privaten_Haushalts_Familien.zip",
            "Religion.zip",
            "Zahl_der_Staatsangehoerigkeiten.zip",
            "Groesse_der_Kernfamilie.zip",
        }
        assert set(DESTATIS_TABLES.keys()) == required_zips

    def test_each_table_has_csv_names_for_all_levels(self):
        from cleancensus.destatis_csv import DESTATIS_TABLES
        for zip_name, info in DESTATIS_TABLES.items():
            for level in ("10km", "1km", "100m"):
                assert level in info["csv_names"], (
                    f"{zip_name} missing csv_names[{level!r}]"
                )

    def test_each_table_has_data_cols(self):
        from cleancensus.destatis_csv import DESTATIS_TABLES
        for zip_name, info in DESTATIS_TABLES.items():
            assert "data_cols" in info, f"{zip_name} missing 'data_cols'"
            assert len(info["data_cols"]) >= 3, (
                f"{zip_name} has < 3 data_cols: {info['data_cols']}"
            )

    def test_seniorenstatus_data_cols(self):
        from cleancensus.destatis_csv import DESTATIS_TABLES
        info = DESTATIS_TABLES["Seniorenstatus_eines_privaten_Haushalts.zip"]
        assert set(info["data_cols"]) == {
            "Insgesamt_Haushalte", "HH_nurSenioren",
            "HH_mitSenioren", "HH_ohneSenioren",
        }

    def test_religion_data_cols(self):
        from cleancensus.destatis_csv import DESTATIS_TABLES
        info = DESTATIS_TABLES["Religion.zip"]
        assert set(info["data_cols"]) == {
            "Insgesamt_Bevoelkerung", "Roemisch_katholisch",
            "Evangelisch", "Sonstige_keine_ohneAngabe",
        }


class TestColumnNaming:
    """Verify the column naming function on in-memory CSV data."""

    def test_column_name_seniorenstatus_10km(self):
        """build_col_name(data_col, csv_name, level) matches T: convention."""
        from cleancensus.destatis_csv import build_col_name
        result = build_col_name(
            "HH_nurSenioren",
            "Zensus2022_Seniorenstatus_eines_privaten_Haushalts_10km-Gitter.csv",
        )
        assert result == "HH_nurSenioren_Seniorenstatus_eines_privaten_Haushalts_10km-Gitter"

    def test_column_name_lebensform_1km(self):
        from cleancensus.destatis_csv import build_col_name
        result = build_col_name(
            "EinpersHH_SingleHH",
            "Zensus2022_Typ_priv_HH_Lebensform_1km-Gitter.csv",
        )
        assert result == "EinpersHH_SingleHH_Typ_priv_HH_Lebensform_1km-Gitter"

    def test_column_name_religion_100m(self):
        from cleancensus.destatis_csv import build_col_name
        result = build_col_name(
            "Roemisch_katholisch",
            "Zensus2022_Religion_100m-Gitter.csv",
        )
        assert result == "Roemisch_katholisch_Religion_100m-Gitter"

    def test_column_name_kernfamilie_10km(self):
        from cleancensus.destatis_csv import build_col_name
        # Note: CSV filename has "Grosse" (missing the second 'e'), not "Groesse"
        result = build_col_name(
            "a2Personen",
            "Zensus2022_Grosse_Kernfamilie_bis6undmehrPers_10km-Gitter.csv",
        )
        assert result == "a2Personen_Grosse_Kernfamilie_bis6undmehrPers_10km-Gitter"


class TestReadDesatisZip:
    """Unit test read_destatis_zip using an in-memory fake ZIP."""

    def _make_fake_zip(self, tmp_path):
        """Write a minimal fake Seniorenstatus ZIP to tmp_path and return path."""
        import io, zipfile
        csv_content = (
            "GITTER_ID_10km;x_mp_10km;y_mp_10km;Insgesamt_Haushalte;HH_nurSenioren;HH_mitSenioren;HH_ohneSenioren\n"
            "CRS3035RES10000mN2690000E4330000;4335000;2695000;143;39;15;87\n"
            "CRS3035RES10000mN2700000E4330000;4335000;2705000;50;10;5;35\n"
        )
        zip_path = tmp_path / "Seniorenstatus_eines_privaten_Haushalts.zip"
        with zipfile.ZipFile(zip_path, "w") as z:
            z.writestr(
                "Zensus2022_Seniorenstatus_eines_privaten_Haushalts_10km-Gitter.csv",
                csv_content,
            )
        return zip_path

    def test_read_returns_dataframe(self, tmp_path):
        from cleancensus.destatis_csv import read_destatis_zip
        zip_path = self._make_fake_zip(tmp_path)
        df = read_destatis_zip(zip_path, "10km")
        import pandas as pd
        assert isinstance(df, pd.DataFrame)

    def test_read_has_gitter_id_column(self, tmp_path):
        from cleancensus.destatis_csv import read_destatis_zip
        zip_path = self._make_fake_zip(tmp_path)
        df = read_destatis_zip(zip_path, "10km")
        assert "GITTER_ID_10km" in df.columns

    def test_read_has_correct_row_count(self, tmp_path):
        from cleancensus.destatis_csv import read_destatis_zip
        zip_path = self._make_fake_zip(tmp_path)
        df = read_destatis_zip(zip_path, "10km")
        assert len(df) == 2

    def test_read_drops_xy_columns(self, tmp_path):
        from cleancensus.destatis_csv import read_destatis_zip
        zip_path = self._make_fake_zip(tmp_path)
        df = read_destatis_zip(zip_path, "10km")
        assert "x_mp_10km" not in df.columns
        assert "y_mp_10km" not in df.columns

    def test_read_column_names_match_t_convention(self, tmp_path):
        from cleancensus.destatis_csv import read_destatis_zip
        zip_path = self._make_fake_zip(tmp_path)
        df = read_destatis_zip(zip_path, "10km")
        expected_cols = {
            "GITTER_ID_10km",
            "Insgesamt_Haushalte_Seniorenstatus_eines_privaten_Haushalts_10km-Gitter",
            "HH_nurSenioren_Seniorenstatus_eines_privaten_Haushalts_10km-Gitter",
            "HH_mitSenioren_Seniorenstatus_eines_privaten_Haushalts_10km-Gitter",
            "HH_ohneSenioren_Seniorenstatus_eines_privaten_Haushalts_10km-Gitter",
        }
        assert set(df.columns) == expected_cols

    def test_read_suppressed_dash_becomes_nan(self, tmp_path):
        """The '–' (EN DASH) suppressed value must become NaN, not a string."""
        import io, zipfile
        import pandas as pd
        csv_content = (
            "GITTER_ID_10km;x_mp_10km;y_mp_10km;Insgesamt_Bevoelkerung;Roemisch_katholisch;Evangelisch;Sonstige_keine_ohneAngabe\n"
            "CRS3035RES10000mN2680000E4330000;4335000;2685000;4;4;–;–\n"
        )
        zip_path = tmp_path / "Religion.zip"
        with zipfile.ZipFile(zip_path, "w") as z:
            z.writestr("Zensus2022_Religion_10km-Gitter.csv", csv_content)
        from cleancensus.destatis_csv import read_destatis_zip
        df = read_destatis_zip(zip_path, "10km")
        assert pd.isna(df["Evangelisch_Religion_10km-Gitter"].iloc[0])


class TestMergeDesatisTablesSmoke:
    """Integration smoke: merge_destatis_tables with fake ZIPs."""

    def _make_two_fake_zips(self, tmp_path):
        import zipfile
        # Seniorenstatus (4 data cols)
        csv1 = (
            "GITTER_ID_10km;x_mp_10km;y_mp_10km;Insgesamt_Haushalte;HH_nurSenioren;HH_mitSenioren;HH_ohneSenioren\n"
            "ID_A;1;2;100;30;10;60\n"
            "ID_B;3;4;50;5;5;40\n"
        )
        with zipfile.ZipFile(tmp_path / "Seniorenstatus_eines_privaten_Haushalts.zip", "w") as z:
            z.writestr("Zensus2022_Seniorenstatus_eines_privaten_Haushalts_10km-Gitter.csv", csv1)
        # Religion (4 data cols)
        csv2 = (
            "GITTER_ID_10km;x_mp_10km;y_mp_10km;Insgesamt_Bevoelkerung;Roemisch_katholisch;Evangelisch;Sonstige_keine_ohneAngabe\n"
            "ID_A;1;2;200;80;60;60\n"
            "ID_C;5;6;30;10;10;10\n"
        )
        with zipfile.ZipFile(tmp_path / "Religion.zip", "w") as z:
            z.writestr("Zensus2022_Religion_10km-Gitter.csv", csv2)

    def test_merge_produces_union_of_ids(self, tmp_path):
        """Outer join on GITTER_ID should give union of all IDs across tables."""
        self._make_two_fake_zips(tmp_path)
        from cleancensus.destatis_csv import merge_destatis_tables
        df = merge_destatis_tables("10km", tmp_path)
        assert set(df["GITTER_ID_10km"]) == {"ID_A", "ID_B", "ID_C"}

    def test_merge_missing_zip_does_not_raise(self, tmp_path):
        """If only some ZIPs are present, merge still completes (warn only)."""
        # Only Seniorenstatus present (no Religion, etc.)
        import zipfile
        csv1 = (
            "GITTER_ID_10km;x_mp_10km;y_mp_10km;Insgesamt_Haushalte;HH_nurSenioren;HH_mitSenioren;HH_ohneSenioren\n"
            "ID_A;1;2;100;30;10;60\n"
        )
        with zipfile.ZipFile(tmp_path / "Seniorenstatus_eines_privaten_Haushalts.zip", "w") as z:
            z.writestr("Zensus2022_Seniorenstatus_eines_privaten_Haushalts_10km-Gitter.csv", csv1)
        from cleancensus.destatis_csv import merge_destatis_tables
        df = merge_destatis_tables("10km", tmp_path)
        assert len(df) == 1
        assert "HH_nurSenioren_Seniorenstatus_eines_privaten_Haushalts_10km-Gitter" in df.columns

    def test_merge_all_missing_returns_none(self, tmp_path):
        """If no ZIPs present, return None (caller checks for None)."""
        from cleancensus.destatis_csv import merge_destatis_tables
        result = merge_destatis_tables("10km", tmp_path)
        assert result is None
```

- [ ] **Step 3.2: Run the new tests to verify they fail**

```powershell
cd "c:\Users\bienzeisler\Documents\GitHub\cleancensus"
uv run --no-sync pytest tests/test_destatis_csv.py -v 2>&1 | tail -20
```

Expected: many FAIL/ERROR with `ModuleNotFoundError: cleancensus.destatis_csv`.

- [ ] **Step 3.3: Create `cleancensus/destatis_csv.py`**

```python
"""Read the 6 Destatis-CSV ZIP supplements not available in z22data.

These 6 Zensus 2022 Gitterzellen topics were not published in the z22data GitHub
mirror (JsLth/z22data) and must be read from the official Destatis CSV ZIPs,
which the user downloads manually from:
  https://www.destatis.de/DE/Themen/Gesellschaft-Umwelt/Bevoelkerung/Zensus2022/
  _publikationen.html?nn=1391172#1418258

Expected location: data/raw/destatis/<zip-name>.zip   (see Config.destatis_raw_dir)

Column-naming convention (mirrors the notebook-era merge_gitter_level logic):
  {data_col}_{csv_stem_without_Zensus2022_prefix}
  e.g. HH_nurSenioren_Seniorenstatus_eines_privaten_Haushalts_10km-Gitter

'–' (EN DASH, U+2013) is Destatis's suppression marker — converted to NaN.

werterlaeuternde_Zeichen columns, if present, are dropped.
"""
from __future__ import annotations

import re
import warnings
import zipfile
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pandas as pd


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

# Each entry:
#   zip_name -> {
#       "csv_names": {level: member_path_inside_zip},
#       "data_cols": [list of data column names in the CSV],
#   }
DESTATIS_TABLES: dict[str, dict] = {
    "Seniorenstatus_eines_privaten_Haushalts.zip": {
        "csv_names": {
            "10km": "Zensus2022_Seniorenstatus_eines_privaten_Haushalts_10km-Gitter.csv",
            "1km":  "Zensus2022_Seniorenstatus_eines_privaten_Haushalts_1km-Gitter.csv",
            "100m": "Zensus2022_Seniorenstatus_eines_privaten_Haushalts_100m-Gitter.csv",
        },
        "data_cols": [
            "Insgesamt_Haushalte",
            "HH_nurSenioren",
            "HH_mitSenioren",
            "HH_ohneSenioren",
        ],
    },
    "Typ_des_privaren_Haushalts_Lebensform.zip": {
        "csv_names": {
            "10km": "Typ_des_privaren_Haushalts_Lebensform/Zensus2022_Typ_priv_HH_Lebensform_10km-Gitter.csv",
            "1km":  "Typ_des_privaren_Haushalts_Lebensform/Zensus2022_Typ_priv_HH_Lebensform_1km-Gitter.csv",
            "100m": "Typ_des_privaren_Haushalts_Lebensform/Zensus2022_Typ_priv_HH_Lebensform_100m-Gitter.csv",
        },
        "data_cols": [
            "Insgesamt_Haushalte",
            "EinpersHH_SingleHH",
            "Ehepaare",
            "EingetrLebensp",
            "NichtehelLebensg",
            "AlleinerzMuetter",
            "AlleinerzVaeter",
            "MehrpersHHohneKernfam",
        ],
    },
    "Typ_des_privaten_Haushalts_Familien.zip": {
        "csv_names": {
            "10km": "Typ_des_privaten_Haushalts_Familien/Zensus2022_Typ_priv_HH_Familie_10km-Gitter.csv",
            "1km":  "Typ_des_privaten_Haushalts_Familien/Zensus2022_Typ_priv_HH_Familie_1km-Gitter.csv",
            "100m": "Typ_des_privaten_Haushalts_Familien/Zensus2022_Typ_priv_HH_Familie_100m-Gitter.csv",
        },
        "data_cols": [
            "Insgesamt_Haushalte",
            "EinpersHH_SingleHH",
            "Paare_ohneKind",
            "Paare_mitKind",
            "Alleinerziehende",
            "MehrpersHHohneKernfam",
        ],
    },
    "Religion.zip": {
        "csv_names": {
            "10km": "Zensus2022_Religion_10km-Gitter.csv",
            "1km":  "Zensus2022_Religion_1km-Gitter.csv",
            "100m": "Zensus2022_Religion_100m-Gitter.csv",
        },
        "data_cols": [
            "Insgesamt_Bevoelkerung",
            "Roemisch_katholisch",
            "Evangelisch",
            "Sonstige_keine_ohneAngabe",
        ],
    },
    "Zahl_der_Staatsangehoerigkeiten.zip": {
        "csv_names": {
            "10km": "Zensus2022_Zahl_der_Staatsangehoerigkeiten_10km-Gitter.csv",
            "1km":  "Zensus2022_Zahl_der_Staatsangehoerigkeiten_1km-Gitter.csv",
            "100m": "Zensus2022_Zahl_der_Staatsangehoerigkeiten_100m-Gitter.csv",
        },
        "data_cols": [
            "Insgesamt_Bevoelkerung",
            "EineStaatsang",
            "Mehrere_deutsch_und_auslaendisch",
            "Mehrere_nur_auslaendisch",
            "Nicht_bekannt",
        ],
    },
    "Groesse_der_Kernfamilie.zip": {
        "csv_names": {
            # Note: Destatis typo — "Grosse" (not "Groesse") in the actual CSV filename
            "10km": "Groesse_der_Kernfamilie/Zensus2022_Grosse_Kernfamilie_bis6undmehrPers_10km-Gitter.csv",
            "1km":  "Groesse_der_Kernfamilie/Zensus2022_Grosse_Kernfamilie_bis6undmehrPers_1km-Gitter.csv",
            "100m": "Groesse_der_Kernfamilie/Zensus2022_Grosse_Kernfamilie_bis6undmehrPers_100m-Gitter.csv",
        },
        "data_cols": [
            "Insgesamt_Familien",
            "a2Personen",
            "a3Personen",
            "a4Personen",
            "a5Personen",
            "a6Pers_und_mehr",
        ],
    },
}

# Suppression marker used by Destatis in the CSVs
_SUPPRESSED = "–"  # EN DASH '–'


# ---------------------------------------------------------------------------
# Column naming
# ---------------------------------------------------------------------------

def build_col_name(data_col: str, csv_filename: str) -> str:
    """Return the canonical column name for a data column from a Destatis CSV.

    Mirrors the notebook-era _filename_suffix + rename logic:
      {data_col}_{csv_stem_without_Zensus2022_prefix}

    Parameters
    ----------
    data_col : str
        The raw column name from the CSV (e.g. "HH_nurSenioren").
    csv_filename : str
        The basename of the CSV member (e.g.
        "Zensus2022_Seniorenstatus_eines_privaten_Haushalts_10km-Gitter.csv").
        Subdirectory prefix is stripped automatically.

    Returns
    -------
    str
        e.g. "HH_nurSenioren_Seniorenstatus_eines_privaten_Haushalts_10km-Gitter"
    """
    # Strip any directory prefix
    basename = csv_filename.rsplit("/", 1)[-1]
    stem = basename.removesuffix(".csv")
    stem = re.sub(r"^Zensus2022_", "", stem)
    return f"{data_col}_{stem}"


# ---------------------------------------------------------------------------
# ZIP reader
# ---------------------------------------------------------------------------

def _read_csv_from_zip(zip_path: Path, member_name: str) -> "pd.DataFrame":
    """Read a semicolon-separated CSV from inside a ZIP, handling encoding."""
    import io
    import pandas as pd

    with zipfile.ZipFile(zip_path) as z:
        raw_bytes = z.read(member_name)

    for enc in ("utf-8", "ISO-8859-1"):
        try:
            text = raw_bytes.decode(enc, errors="replace")
            df = pd.read_csv(
                io.StringIO(text),
                sep=";",
                dtype=str,
                na_values=[_SUPPRESSED, ""],
                keep_default_na=False,
            )
            df.columns = df.columns.str.strip()
            return df
        except Exception:
            continue
    raise RuntimeError(f"Could not read {member_name!r} from {zip_path}")


def read_destatis_zip(zip_path: str | Path, level: str) -> "pd.DataFrame":
    """Read the level CSV from a Destatis ZIP and return a renamed wide frame.

    Parameters
    ----------
    zip_path : Path
        Path to the ZIP file.
    level : str
        "10km", "1km", or "100m".

    Returns
    -------
    pd.DataFrame
        Columns: GITTER_ID_{level} + one column per data column
        (named per the T: convention; x/y and annotation columns dropped).
        Numeric data columns are cast to float64.
    """
    import pandas as pd

    zip_path = Path(zip_path)
    zip_name = zip_path.name
    if zip_name not in DESTATIS_TABLES:
        raise ValueError(
            f"Unknown ZIP {zip_name!r}. Registered: {list(DESTATIS_TABLES)}"
        )

    info = DESTATIS_TABLES[zip_name]
    csv_member = info["csv_names"][level]
    data_cols = info["data_cols"]
    csv_basename = csv_member.rsplit("/", 1)[-1]

    df = _read_csv_from_zip(zip_path, csv_member)

    gid_col = f"GITTER_ID_{level}"
    x_col = f"x_mp_{level}"
    y_col = f"y_mp_{level}"

    # Drop coordinate columns (already in z22 table)
    drop_cols = [c for c in (x_col, y_col) if c in df.columns]
    # Drop werterlaeuternde_Zeichen annotation columns if present
    drop_cols += [c for c in df.columns if c.startswith("werterlaeuternde_Zeichen")]
    if drop_cols:
        df = df.drop(columns=drop_cols)

    # Rename data columns to T: convention
    rename_map: dict[str, str] = {}
    for col in data_cols:
        if col in df.columns:
            rename_map[col] = build_col_name(col, csv_basename)
    df = df.rename(columns=rename_map)

    # Keep only GITTER_ID + the renamed data columns (drop any unrecognised extra)
    keep = [gid_col] + [rename_map[c] for c in data_cols if c in rename_map]
    df = df[[c for c in keep if c in df.columns]]

    # Cast data columns to numeric
    for col in df.columns:
        if col != gid_col:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    return df


# ---------------------------------------------------------------------------
# Multi-table merge
# ---------------------------------------------------------------------------

def merge_destatis_tables(level: str, raw_dir: str | Path) -> "pd.DataFrame | None":
    """Read all 6 Destatis ZIPs for the given level and outer-merge on GITTER_ID.

    Parameters
    ----------
    level : str
        "10km", "1km", or "100m".
    raw_dir : Path
        Directory containing the 6 ZIP files.

    Returns
    -------
    pd.DataFrame or None
        Wide frame with GITTER_ID_{level} and all available data columns,
        outer-joined across tables. Returns None if no ZIP files are found.
    """
    import pandas as pd

    raw_dir = Path(raw_dir)
    gid_col = f"GITTER_ID_{level}"

    merged: pd.DataFrame | None = None
    found = 0

    for zip_name in DESTATIS_TABLES:
        zip_path = raw_dir / zip_name
        if not zip_path.exists():
            warnings.warn(
                f"[destatis_csv] ZIP not found, skipping: {zip_path}",
                stacklevel=2,
            )
            continue

        try:
            df = read_destatis_zip(zip_path, level)
        except Exception as exc:
            warnings.warn(
                f"[destatis_csv] Failed to read {zip_name} for level={level!r}: {exc}",
                stacklevel=2,
            )
            continue

        found += 1
        if merged is None:
            merged = df
        else:
            merged = merged.merge(df, on=gid_col, how="outer")

    if found == 0:
        return None
    return merged
```

- [ ] **Step 3.4: Run the new tests to verify they pass**

```powershell
cd "c:\Users\bienzeisler\Documents\GitHub\cleancensus"
uv run --no-sync pytest tests/test_destatis_csv.py -v 2>&1 | tail -30
```

Expected: all tests PASS.

- [ ] **Step 3.5: Run the full test suite to catch any regressions**

```powershell
uv run --no-sync pytest -q
```

Expected: all 127 previous tests + new tests pass.

- [ ] **Step 3.6: Commit**

```powershell
git add cleancensus/destatis_csv.py tests/test_destatis_csv.py
git commit -m "feat: destatis_csv module — DESTATIS_TABLES registry + read/merge logic"
```

---

## Task 4: Integrate into `run_merge_z22`

**Files:**
- Modify: `c:\Users\bienzeisler\Documents\GitHub\cleancensus\cleancensus\z22.py`

The integration left-joins the Destatis supplement onto the z22 table per level. If `cfg.destatis_raw_dir` does not exist, it logs a warning and continues (z22-only mode).

- [ ] **Step 4.1: Write a failing test**

Append to `tests/test_destatis_csv.py`:

```python
class TestMergeWithZ22Integration:
    """Smoke test: merge_destatis_tables output left-joins onto a synthetic z22 table."""

    def test_left_join_adds_destatis_columns(self, tmp_path):
        """Verifies that the merge logic in run_merge_z22 adds Destatis columns."""
        import zipfile
        import pandas as pd

        # Build a minimal fake ZIP
        csv_content = (
            "GITTER_ID_10km;x_mp_10km;y_mp_10km;Insgesamt_Bevoelkerung;Roemisch_katholisch;Evangelisch;Sonstige_keine_ohneAngabe\n"
            "CRS3035RES10000mN2690000E4330000;4335000;2695000;100;40;30;30\n"
            "CRS3035RES10000mN2700000E4330000;4335000;2705000;50;20;15;15\n"
        )
        raw_dir = tmp_path / "destatis"
        raw_dir.mkdir()
        with zipfile.ZipFile(raw_dir / "Religion.zip", "w") as z:
            z.writestr("Zensus2022_Religion_10km-Gitter.csv", csv_content)

        # Synthetic z22 frame (3 rows; only 2 overlap with Destatis)
        z22_df = pd.DataFrame({
            "GITTER_ID_10km": [
                "CRS3035RES10000mN2690000E4330000",
                "CRS3035RES10000mN2700000E4330000",
                "CRS3035RES10000mN2710000E4330000",
            ],
            "Einwohner_Bevoelkerungszahl_10km-Gitter": [100, 50, 30],
        })

        from cleancensus.destatis_csv import merge_destatis_tables
        destatis_df = merge_destatis_tables("10km", raw_dir)
        assert destatis_df is not None

        result = z22_df.merge(destatis_df, on="GITTER_ID_10km", how="left")
        assert "Roemisch_katholisch_Religion_10km-Gitter" in result.columns
        # Third row (no Destatis data) should be NaN
        assert pd.isna(result["Roemisch_katholisch_Religion_10km-Gitter"].iloc[2])
        # First two rows should have values
        assert result["Roemisch_katholisch_Religion_10km-Gitter"].iloc[0] == 40.0
```

- [ ] **Step 4.2: Run to verify it passes (the module already exists)**

```powershell
cd "c:\Users\bienzeisler\Documents\GitHub\cleancensus"
uv run --no-sync pytest tests/test_destatis_csv.py::TestMergeWithZ22Integration -v
```

Expected: PASS (the module is already implemented in Task 3).

- [ ] **Step 4.3: Modify `cleancensus/z22.py::run_merge_z22`**

Find the `run_merge_z22` function (starts at line 486). Replace the current function body with one that calls `merge_destatis_tables` after building the z22 table and left-joins. The key addition is after `df = build_merged_table(level, raw_dir)`:

```python
def run_merge_z22(cfg) -> None:
    """Merge stage: download z22data parquets and build per-level wide tables.

    Additionally ingests the 6 Destatis-CSV ZIP supplements (if present in
    cfg.destatis_raw_dir) and left-joins them onto the z22 table.

    Writes ``work_dir/merged_{level}_gitter.parquet`` for each level.
    Downloads go to ``inputs_dir.parent / "raw" / "z22" / {level}`` (gitignored).

    Parameters
    ----------
    cfg : cleancensus.config.Config
    """
    import pyarrow as pa
    import pyarrow.parquet as pq

    from cleancensus.destatis_csv import merge_destatis_tables

    features = list(FEATURE_MAP.keys())

    levels = ["10km", "1km", "100m"]
    for level in levels:
        raw_dir = cfg.inputs_dir.parent / "raw" / "z22" / level
        print(f"[merge/z22] level={level}: downloading to {raw_dir} ...")
        download_z22(level, features, raw_dir)

        print(f"[merge/z22] level={level}: building z22 merged table ...")
        df = build_merged_table(level, raw_dir)

        # ---- Destatis-CSV supplement ----------------------------------------
        destatis_dir = cfg.destatis_raw_dir
        if destatis_dir.exists():
            print(f"[merge/z22] level={level}: ingesting Destatis-CSV supplement from {destatis_dir} ...")
            destatis_df = merge_destatis_tables(level, destatis_dir)
            if destatis_df is not None:
                gid_col = f"GITTER_ID_{level}"
                before = df.shape[1]
                df = df.merge(destatis_df, on=gid_col, how="left")
                added = df.shape[1] - before
                print(f"[merge/z22] level={level}: added {added} Destatis-CSV columns")
            else:
                print(f"[merge/z22] level={level}: no Destatis ZIPs found in {destatis_dir}, skipping supplement")
        else:
            print(
                f"[merge/z22] level={level}: {destatis_dir} not found — "
                "Destatis supplement skipped (z22-only mode). "
                "Copy the 6 ZIPs there to include the 6 missing topics."
            )
        # ----------------------------------------------------------------------

        out_path = cfg.work_dir / f"merged_{level}_gitter.parquet"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        pq.write_table(pa.Table.from_pandas(df), out_path)
        print(f"[merge/z22] level={level}: wrote {out_path} ({len(df):,} rows, {df.shape[1]} cols)")
```

- [ ] **Step 4.4: Run full test suite**

```powershell
cd "c:\Users\bienzeisler\Documents\GitHub\cleancensus"
uv run --no-sync pytest -q
```

Expected: all tests pass.

- [ ] **Step 4.5: Verify z22-only mode behaviour (destatis_raw_dir absent)**

```powershell
python -c "
from pathlib import Path
from cleancensus.config import Config
cfg = Config(
    inputs_dir=Path('data/inputs'),
    outputs_dir=Path('data/outputs'),
    version_tag='test',
    topics=['Whg_Gebaeudetyp'],
    derived_tenure=False,
    mode='national',
    ars_prefixes=[],
    sanity='skip',
    write_manifest=False,
    stages={s: False for s in ('merge','totals','ages','gemeinde','gender','topics8','aggs','regiostar','extend')},
    config_path=Path('config.example.toml').resolve(),
)
print('destatis_raw_dir exists:', cfg.destatis_raw_dir.exists())
print('destatis_raw_dir path:', cfg.destatis_raw_dir)
"
```

Expected: prints the path (which may or may not exist depending on Task 1 completion).

- [ ] **Step 4.6: Commit**

```powershell
git add cleancensus/z22.py tests/test_destatis_csv.py
git commit -m "feat: run_merge_z22 left-joins Destatis-CSV supplement (6 missing tables)"
```

---

## Task 5: Gate — Verify against T: Merged CSVs

This task runs a gate comparison for the 6 new tables at 10km and 1km levels, then appends findings to the gate report.

- [ ] **Step 5.1: Run the gate script (run interactively or via a temp script)**

Create a temporary script (do NOT commit it — delete after use):

```python
# tmp_gate_destatis.py  — DELETE AFTER USE
"""Gate the 6 Destatis-CSV tables against T: merged CSVs."""
import warnings
import pandas as pd
from pathlib import Path

ZIP_DIR = Path(r"c:\Users\bienzeisler\Documents\GitHub\cleancensus\data\raw\destatis")
T_DIR = Path(r"T:\petre\UCFL\Synthetic Population\Zensus\merged")

KEYWORDS = [
    "Seniorenstatus", "Typ_priv_HH_Familie", "Typ_priv_HH_Lebensform",
    "Religion", "Staatsangehoerigkeiten", "Kernfamilie",
]


def get_destatis_cols(t_df, level):
    """Return columns in T: that belong to the 6 destatis tables."""
    return [c for c in t_df.columns if any(k in c for k in KEYWORDS) and f"{level}-Gitter" in c]


results = {}
for level in ["10km", "1km"]:
    gid = f"GITTER_ID_{level}"
    t_path = T_DIR / f"merged_{level}_gitter.csv"
    if not t_path.exists():
        print(f"T: {level} not found, skipping")
        continue

    print(f"\n=== {level} ===")
    t_df = pd.read_csv(t_path, low_memory=False)
    dest_cols = get_destatis_cols(t_df, level)
    print(f"  T: Destatis columns: {len(dest_cols)}")

    from cleancensus.destatis_csv import merge_destatis_tables
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        d_df = merge_destatis_tables(level, ZIP_DIR)

    if d_df is None:
        print("  ERROR: merge_destatis_tables returned None")
        continue

    print(f"  Destatis frame: {len(d_df)} rows, {len(d_df.columns)} cols")

    # Align on GITTER_ID
    t_sub = t_df.set_index(gid)[dest_cols]
    d_sub = d_df.set_index(gid).drop(columns=[c for c in d_df.columns if c == gid], errors="ignore")

    col_results = {}
    for col in dest_cols:
        if col not in d_sub.columns:
            col_results[col] = "MISSING_IN_DESTATIS"
            continue
        shared = t_sub.index.intersection(d_sub.index)
        t_vals = pd.to_numeric(t_sub.loc[shared, col], errors="coerce")
        d_vals = pd.to_numeric(d_sub.loc[shared, col], errors="coerce")
        t_sum = t_vals.sum(skipna=True)
        d_sum = d_vals.sum(skipna=True)
        diff = abs(d_sum - t_sum)
        n_diff = (t_vals.fillna(0) != d_vals.fillna(0)).sum()
        if diff < 0.5:
            status = "EXACT"
        elif diff / max(abs(t_sum), 1) < 0.001:
            status = "NEAR-EXACT"
        else:
            status = f"DIFF({diff:.0f}, {diff/max(abs(t_sum),1):.2%})"
        col_results[col] = f"{status} | t_sum={t_sum:.0f} d_sum={d_sum:.0f} n_diff={n_diff}"
        print(f"  {col}: {col_results[col]}")

    results[level] = col_results

print("\nDone. Paste output into docs/Z22_GATE_REPORT.md.")
```

Run it:

```powershell
cd "c:\Users\bienzeisler\Documents\GitHub\cleancensus"
uv run --no-sync python tmp_gate_destatis.py
```

- [ ] **Step 5.2: Append results to `docs/Z22_GATE_REPORT.md`**

Add a new section at the end of the file:

```markdown
---

## Destatis-CSV Supplement (6 tables) — Gate 2026-06-11

**Source:** 6 Destatis CSV ZIPs in `data/raw/destatis/`, read by `cleancensus.destatis_csv`.
**Reference:** T: merged CSVs at `T:\petre\UCFL\...\merged\merged_{10km,1km}_gitter.csv`.

### Column mapping summary

[Paste the exact per-column output from the gate script here.]

### 10km gate

[Fill in from script output: EXACT / NEAR-EXACT / DIFF count per column.]

### 1km gate

[Fill in from script output.]

### 100m spot-check (ZGB subset)

[Optional: run against a known ZGB subset if needed.]

### Missing-destatis-dir behaviour

If `data/raw/destatis/` does not exist:
- `run_merge_z22` logs: "destatis_raw_dir not found — Destatis supplement skipped (z22-only mode)"
- The merged parquets are written without the 6 Destatis tables.
- All existing z22data columns are unaffected.
- Downstream stages (totals, ages, etc.) are not impacted.
```

- [ ] **Step 5.3: Delete the temporary gate script**

```powershell
Remove-Item "c:\Users\bienzeisler\Documents\GitHub\cleancensus\tmp_gate_destatis.py"
```

- [ ] **Step 5.4: Commit the gate report update**

```powershell
git add docs/Z22_GATE_REPORT.md
git commit -m "docs: gate report — Destatis-CSV supplement (6 tables)"
```

---

## Task 6: Final verification and commit

- [ ] **Step 6.1: Run full test suite and confirm count**

```powershell
cd "c:\Users\bienzeisler\Documents\GitHub\cleancensus"
uv run --no-sync pytest -q
```

Expected output ending: `XXX passed in Y.Zs` (previous 127 + new tests, all green).

- [ ] **Step 6.2: Verify the module docstring is accurate**

Confirm `cleancensus/destatis_csv.py` docstring mentions the expected ZIP location and the column naming convention.

- [ ] **Step 6.3: Final commit**

```powershell
git add -A
git commit -m "feat: merge stage ingests the 6 z22data-missing tables from Destatis CSV ZIPs (P1, gated vs T:)"
```

---

## Self-Review Checklist

**Spec coverage:**
- [x] Step 1: Import — ZIPs copied to `data/raw/destatis/` (Task 1)
- [x] Step 2: CSV format reconnaissance — documented in plan header; used in implementation
- [x] Step 3: `cleancensus/destatis_csv.py` — `read_destatis_zip`, `DESTATIS_TABLES`, `merge_destatis_tables` (Task 3)
- [x] Step 3 config: `destatis_raw_dir` on Config (Task 2); `config.example.toml` comment (Task 2)
- [x] Step 3 integration: left-merge in `run_merge_z22` (Task 4); missing dir = warn not fail (Task 4.3/4.5)
- [x] Step 4: Gate vs T: merged CSVs (Task 5); append to `docs/Z22_GATE_REPORT.md` (Task 5.2)
- [x] Step 5: Tests in `tests/test_destatis_csv.py` (Tasks 2, 3, 4) — registry, naming, merge smoke, z22 integration
- [x] Step 6: pytest all green; commit message matches spec (Task 6)

**Placeholder scan:** No TBD/TODO/placeholder — every step has actual code or exact commands.

**Type consistency:**
- `DESTATIS_TABLES` is `dict[str, dict]` throughout
- `build_col_name(data_col: str, csv_filename: str) -> str` — used consistently
- `read_destatis_zip(zip_path, level) -> pd.DataFrame` — used in `merge_destatis_tables` and tests
- `merge_destatis_tables(level, raw_dir) -> pd.DataFrame | None` — returns None when no ZIPs found (tested)
- `cfg.destatis_raw_dir -> Path` — used in `run_merge_z22`

**Edge cases covered:**
- `–` (EN DASH) suppressed values → NaN via `na_values` (tested in `test_read_suppressed_dash_becomes_nan`)
- Missing individual ZIP files → warning + continue (tested in `test_merge_missing_zip_does_not_raise`)
- All ZIPs missing → return None (tested in `test_merge_all_missing_returns_none`)
- `destatis_raw_dir` directory absent → log only, no error (Task 4.3 code + Task 4.5 verification)
- `werterlaeuternde_Zeichen` columns → dropped in `read_destatis_zip` (code present; not in actual ZIPs so no dedicated test needed)
