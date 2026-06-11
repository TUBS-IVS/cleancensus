"""Read the 7 Destatis-CSV ZIP supplements not available in z22data.

These 7 Zensus 2022 Gitterzellen topics were not published in the z22data GitHub
mirror (JsLth/z22data) and must be read from the official Destatis CSV ZIPs,
which the user downloads manually from:
  https://www.destatis.de/DE/Themen/Gesellschaft-Umwelt/Bevoelkerung/Zensus2022/
  _publikationen.html?nn=1391172#1418258

Expected location: data/raw/destatis/<zip-name>.zip   (see Config.destatis_raw_dir)

Column-naming convention (mirrors the notebook-era merge_gitter_level logic):
  {data_col}_{csv_stem_without_Zensus2022_prefix}
  e.g. HH_nurSenioren_Seniorenstatus_eines_privaten_Haushalts_10km-Gitter

'-' (EN DASH, U+2013) is Destatis's suppression marker -- converted to NaN.

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
            # Note: Destatis typo -- "Grosse" (not "Groesse") in the actual CSV filename
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
    "Typ_der_Kernfamilie_nach_Kindern.zip": {
        "csv_names": {
            "10km": "Typ_der_Kernfamilie_nach_Kindern/Zensus2022_Typ_der_Kernfamilie_nach_Kindern_10km-Gitter.csv",
            "1km":  "Typ_der_Kernfamilie_nach_Kindern/Zensus2022_Typ_der_Kernfamilie_nach_Kindern_1km-Gitter.csv",
            "100m": "Typ_der_Kernfamilie_nach_Kindern/Zensus2022_Typ_der_Kernfamilie_nach_Kindern_100m-Gitter.csv",
        },
        "data_cols": [
            "Insgesamt_Familie",
            "Ehep_ohneKind",
            "Ehep_mind_1Kind_unter18",
            "Ehep_Kinder_ab18",
            "EingetrLP_ohneKind",
            "EingetrLP_mind_1Kind_unter18",
            "EingetrLP_Kinder_ab18",
            "NichtehelLG_ohneKind",
            "NichtehelLG_mind_1Kind_unter18",
            "NichtehelLG_Kinder_ab18",
            "Vater_mind_1Kind_unter18",
            "Vater_Kinder_ab18",
            "Mutter_mind_1Kind_unter18",
            "Mutter_Kinder_ab18",
        ],
    },
}

# Suppression marker used by Destatis in the CSVs (EN DASH U+2013)
_SUPPRESSED = "–"


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
    """Read all 7 Destatis ZIPs for the given level and outer-merge on GITTER_ID.

    Parameters
    ----------
    level : str
        "10km", "1km", or "100m".
    raw_dir : Path
        Directory containing the 7 ZIP files.

    Returns
    -------
    pd.DataFrame or None
        Wide frame with GITTER_ID_{level} and all available data columns,
        outer-joined across tables. Returns None if no ZIP files are found.
    """
    import pandas as pd

    from cleancensus.progress import progress_iter

    raw_dir = Path(raw_dir)
    gid_col = f"GITTER_ID_{level}"

    merged: pd.DataFrame | None = None
    found = 0

    for zip_name in progress_iter(list(DESTATIS_TABLES), "destatis/tables", total=len(DESTATIS_TABLES)):
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
