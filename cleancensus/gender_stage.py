"""Gender stage: male/female age split at 100m + orphan backfill.

Ported faithfully from notebooks_archive/gender.ipynb cells [0]/[1] (reference
loading), [6] (gender split), and [8] (backfill).

The stage consists of three logical parts:
  1. load_age_csv_to_matrices  (cells [0]+[1]) — parse the GENESIS 1000A-2027
     CSV export into three DataFrames total/male/female, keyed by 12-digit ARS.
  2. add_gender_split  (cell [6]) — for every 100m cell apply per-age, per-ARS
     male share from the Gemeinde reference; fall back to the national share for
     cells whose ARS is not in the reference.
  3. backfill_orphans  (cell [8]) — cells that have pop>0 but all AGE_* == 0
     AND the is_orphan flag are age-distributed using Gemeinde age shares, then
     re-split by gender.

Reference data
--------------
GENESIS table 1000A-2027  (Zensus 2022, Bevölkerung nach Alter und Geschlecht,
Gemeinden):
    https://ergebnisse.zensus2022.de/datenbank/online/table/1000A-2027
    -> "Anpassen" -> change geography to "Gemeinden" -> download CSV

Available at:
    T:\\petre\\UCFL\\Synthetic Population\\Zensus\\additional_data\\1000A-2027_de.csv
    (cfg.gemeinde_age_csv_path or the T: default above)

Inputs
------
    cfg.work_dir / "cells_100m_with_gemeinde.parquet"   (gemeinde stage output)

Outputs
-------
    cfg.work_dir / "cells_100m_with_gender_backfilled.parquet"
    cfg.work_dir / "backfilled_rows_log.csv"
"""
from __future__ import annotations

import csv
import io
import re
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from cleancensus.logsetup import get_logger
from cleancensus.progress import progress_iter

log = get_logger("gender")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ARS_COL   = "RegionalSchlüssel_ARS"
AGE_TOP   = 100
AGE_COLS  = [f"AGE_{a}" for a in range(AGE_TOP + 1)]
M_COLS    = [f"M_AGE_{a}" for a in range(AGE_TOP + 1)]
F_COLS    = [f"F_AGE_{a}" for a in range(AGE_TOP + 1)]

_12DIG = re.compile(r"^\d{12}$")
_AGE_RE = re.compile(r"^\s*(\d+)\s+Jahr")

_T_1000A = Path(
    r"T:\petre\UCFL\Synthetic Population\Zensus\additional_data\1000A-2027_de.csv"
)

# data/raw local copy — resolved at import time relative to this file's package root
_LOCAL_1000A = (
    Path(__file__).resolve().parent.parent
    / "data" / "raw" / "genesis"
    / "1000A-2027_bevoelkerung_alter_geschlecht_gemeinden.csv"
)

# ---------------------------------------------------------------------------
# Part 1: parse 1000A-2027_de.csv (cells [0] + [1])
# ---------------------------------------------------------------------------


def _read_text_utf8(path: Path, prefer_sep: str = ";") -> tuple[str, str]:
    b = path.read_bytes()
    try:
        text = b.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = b.decode("utf-8", errors="ignore")

    if "\n" not in text and "\r" in text:
        text = text.replace("\r", "\n")
    text = text.replace("\r\n", "\n")
    text = text.replace("\x00", "").replace(" ", " ")

    head = "\n".join(text.splitlines()[:10])
    if head.count(prefer_sep) < 3:
        counts = {s: head.count(s) for s in [";", "\t", ","]}
        prefer_sep = max(counts, key=counts.get)
    return text, prefer_sep


def _read_csv_anycols(text: str, sep: str) -> pd.DataFrame:
    lines = text.splitlines()
    max_fields = max((ln.count(sep) for ln in lines[:2000]), default=0) + 1
    names = list(range(max_fields))
    return pd.read_csv(
        io.StringIO(text),
        sep=sep,
        header=None,
        names=names,
        dtype=str,
        quoting=csv.QUOTE_NONE,
        keep_default_na=False,
        na_filter=False,
        low_memory=False,
    )


def _row_has_many_geo_codes(row: pd.Series) -> bool:
    c = 0
    for cell in row.fillna(""):
        parts = str(cell).split()
        if parts and _12DIG.match(parts[0]):
            c += 1
    return c >= 3


def _find_block_bounds(df: pd.DataFrame) -> tuple[dict, int]:
    first_data = df.index[(df[0] == "Insgesamt") & (df[1] == "Insgesamt")]
    if len(first_data) == 0:
        raise ValueError("Couldn't find 'Insgesamt / Insgesamt' start.")
    start_total = int(first_data[0])

    male_hdr   = df.index[(df[0] == "Männlich") & (df[1] == "Insgesamt")]
    female_hdr = df.index[(df[0] == "Weiblich") & (df[1] == "Insgesamt")]
    if len(male_hdr) == 0 or len(female_hdr) == 0:
        raise ValueError("Couldn't find Männlich/Weiblich markers.")
    start_male, start_female = int(male_hdr[0]), int(female_hdr[0])

    footer_idx = df.index[
        df[0].fillna("").astype(str).str.startswith(("©", "Stand:", "__________"))
    ]
    footer = int(footer_idx[0]) if len(footer_idx) else len(df)

    return {
        "total":  (start_total,       start_male - 1),
        "male":   (start_male + 1,    start_female - 1),
        "female": (start_female + 1,  footer - 1),
    }, start_total


def _build_geo_schema(df: pd.DataFrame, data_start_row: int) -> list:
    geo_line_idx = None
    for r in range(data_start_row - 1, max(0, data_start_row - 10), -1):
        if _row_has_many_geo_codes(df.loc[r]):
            geo_line_idx = r
            break
    if geo_line_idx is None:
        raise ValueError("Geo header line not found.")

    sub_line_idx = geo_line_idx + 2
    geo_line = df.loc[geo_line_idx].fillna("")
    sub_line = df.loc[sub_line_idx].fillna("")

    schema = []
    c = 2
    max_c = df.shape[1]

    while c < max_c:
        geo_cell = str(geo_line.iloc[c]).strip()
        sub = str(sub_line.iloc[c]).strip().lower()

        if not geo_cell:
            c += 1
            continue

        parts = geo_cell.split()
        geo_id = parts[0] if (parts and _12DIG.match(parts[0])) else "DE"

        if sub.startswith("anzahl") or sub.startswith("%"):
            measure = "share" if sub.startswith("%") else "anzahl"
            flag_idx = (
                c + 1
                if (c + 1 < max_c and str(sub_line.iloc[c + 1]).strip().lower() in {"e", ""})
                else None
            )
            schema.append({
                "value_col": c,
                "flag_col":  flag_idx,
                "geo_id":    geo_id,
                "measure":   measure,
            })
            c = (flag_idx + 1) if flag_idx is not None else (c + 1)
        else:
            c += 1

    return schema


def _clean_num_zero(s) -> float:
    if s is None:
        return 0.0
    s = str(s).strip()
    if s in {"", "-", "–"}:
        return 0.0
    s = s.replace(",", ".")
    try:
        return float(s)
    except Exception:
        return 0.0


def _block_to_matrix(df: pd.DataFrame, start: int, end: int, schema: list) -> pd.DataFrame:
    ages, age_rows = [], []
    for r in range(start, end + 1):
        age = str(df.iat[r, 1]).strip()
        if not age or age.lower().startswith("davon"):
            continue
        ages.append(age)
        age_rows.append(r)

    value_specs = [s for s in schema if s["measure"] == "anzahl"]
    geo_ids = [s["geo_id"] for s in value_specs]
    geo_ids_unique = list(dict.fromkeys(geo_ids))
    data = {gid: [0.0] * len(ages) for gid in geo_ids_unique}

    for idx, r in enumerate(age_rows):
        for s in value_specs:
            gid = s["geo_id"]
            c   = s["value_col"]
            data[gid][idx] = _clean_num_zero(df.iat[r, c])

    mat = pd.DataFrame(data, index=ages)
    mat.index.name = "age_label"
    return mat.sort_index(axis=1)


def _canon_age(lbl: str) -> str:
    s = str(lbl).strip()
    sl = s.lower()
    if sl.startswith("unter 1 jahr"):
        return "0"
    if sl.startswith("100 jahre und älter"):
        return "100"
    if sl == "insgesamt":
        return "Insgesamt"
    m = _AGE_RE.match(s)
    if m:
        return str(int(m.group(1)))
    raise ValueError(f"Unrecognized age label: {lbl!r}")


def _rename_ages(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out.index = [_canon_age(x) for x in out.index]
    ages = [str(i) for i in range(0, 101)]
    order = [a for a in ages if a in out.index]
    if "Insgesamt" in out.index:
        order.append("Insgesamt")
    return out.reindex(order)


def load_age_csv_to_matrices(path: Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Parse 1000A-2027_de.csv -> (total_df, male_df, female_df).

    Returns DataFrames with:
        - rows  : age labels "0".."100" (plus optionally "Insgesamt")
        - columns: 12-digit ARS keys (Deutschland column "DE" dropped)
    """
    text, sep = _read_text_utf8(path, prefer_sep=";")
    raw = _read_csv_anycols(text, sep)
    raw = raw.dropna(how="all", axis=0).dropna(how="all", axis=1).reset_index(drop=True)
    raw = raw.map(lambda x: x.strip() if isinstance(x, str) else x)

    bounds, first_data_row = _find_block_bounds(raw)
    schema = _build_geo_schema(raw, first_data_row)

    total_df  = _block_to_matrix(raw, *bounds["total"],  schema)
    male_df   = _block_to_matrix(raw, *bounds["male"],   schema)
    female_df = _block_to_matrix(raw, *bounds["female"], schema)

    # Ensure identical row order
    all_ages = total_df.index.union(male_df.index).union(female_df.index)
    total_df  = total_df.reindex(all_ages)
    male_df   = male_df.reindex(all_ages)
    female_df = female_df.reindex(all_ages)

    # Drop the "DE" national summary column (present in the raw CSV)
    for df in (total_df, male_df, female_df):
        df.drop(columns=["DE"], errors="ignore", inplace=True)

    # Rename age labels to canonical ("0".."100") and reorder
    total_df  = _rename_ages(total_df)
    male_df   = _rename_ages(male_df)
    female_df = _rename_ages(female_df)

    return total_df, male_df, female_df


def _as_age_index(df: pd.DataFrame) -> pd.DataFrame:
    """Coerce row index to integer ages, keep only 0..100, sorted."""
    out = df.copy()
    out.index = pd.to_numeric(out.index, errors="coerce").astype("Int64")
    return out.loc[out.index.isin(range(AGE_TOP + 1))].sort_index()


# ---------------------------------------------------------------------------
# Part 2: add_gender_split (cell [6])
# ---------------------------------------------------------------------------


def add_gender_split(
    cells: pd.DataFrame,
    gem_m: pd.DataFrame,
    gem_f: pd.DataFrame,
) -> pd.DataFrame:
    """Apply per-age, per-ARS male share to 100m cells.

    Adds M_AGE_0..M_AGE_100, F_AGE_0..F_AGE_100, M_TOTAL, F_TOTAL.
    Uses national fallback share for cells whose ARS is not in gem_m/gem_f.
    Faithful port of notebook cell [6].

    Parameters
    ----------
    cells : DataFrame with AGE_0..AGE_100 and RegionalSchlüssel_ARS columns.
    gem_m : DataFrame (age rows 0..100 x ARS columns), male counts.
    gem_f : DataFrame (age rows 0..100 x ARS columns), female counts.

    Returns
    -------
    cells (with new M_AGE_*/F_AGE_*/M_TOTAL/F_TOTAL columns)
    """
    cells = cells.copy()

    # --- Prepare Gemeinde tables ---
    gem_m = _as_age_index(gem_m).apply(pd.to_numeric, errors="coerce").fillna(0.0)
    gem_f = _as_age_index(gem_f).apply(pd.to_numeric, errors="coerce").fillna(0.0)

    gem_m.columns = gem_m.columns.astype(str).str.strip()
    gem_f.columns = gem_f.columns.astype(str).str.strip()

    common_ars = gem_m.columns.intersection(gem_f.columns)
    gem_m = gem_m[common_ars]
    gem_f = gem_f[common_ars]

    MF = gem_m.values + gem_f.values           # (A, G)
    with np.errstate(divide="ignore", invalid="ignore"):
        share = np.divide(gem_m.values, np.maximum(MF, 1e-12))
    share = np.clip(share, 0.0, 1.0)

    # National fallback per age
    nat_m = gem_m.sum(axis=1).to_numpy(float)
    nat_f = gem_f.sum(axis=1).to_numpy(float)
    with np.errstate(divide="ignore", invalid="ignore"):
        nat_share = np.divide(nat_m, np.maximum(nat_m + nat_f, 1e-12))
    nat_share = np.clip(nat_share, 0.0, 1.0)

    share_df = pd.DataFrame(share, index=gem_m.index, columns=common_ars)

    # Clean ARS keys in cells; convert AGE_* to float32
    cells[ARS_COL] = cells[ARS_COL].astype(str).str.strip()
    for c in AGE_COLS:
        cells[c] = pd.to_numeric(cells[c], errors="coerce").fillna(0.0).astype(np.float32)

    cells[ARS_COL] = cells[ARS_COL].astype("category")

    for a in progress_iter(range(AGE_TOP + 1), "gender/age-split", total=AGE_TOP + 1):
        age_col = f"AGE_{a}"
        m_col   = f"M_AGE_{a}"
        f_col   = f"F_AGE_{a}"

        s_map  = share_df.loc[a].astype(np.float32)
        s_vals = cells[ARS_COL].map(s_map)
        # map() on a categorical column returns a Categorical; cast to float first
        # so fillna() can accept a new value (the national fallback)
        s_vals = s_vals.astype("float32")
        s_vals = s_vals.fillna(np.float32(nat_share[a]))
        s_arr  = s_vals.to_numpy(np.float32, copy=False)

        age_arr = cells[age_col].to_numpy(np.float32, copy=False)
        m_arr   = age_arr * s_arr
        cells[m_col] = m_arr
        cells[f_col] = age_arr - m_arr

    # Cheap reconstruction check
    mf_sum = (
        cells.filter(like="M_AGE_").to_numpy(np.float32)
        + cells.filter(like="F_AGE_").to_numpy(np.float32)
    )
    aa_sum = cells[AGE_COLS].to_numpy(np.float32)
    max_diff = float(np.abs(mf_sum - aa_sum).max())
    log.info("cell-age reconstruction max abs diff: %.3e", max_diff)

    m_age_cols = [f"M_AGE_{a}" for a in range(AGE_TOP + 1)]
    f_age_cols = [f"F_AGE_{a}" for a in range(AGE_TOP + 1)]
    cells["M_TOTAL"] = cells[m_age_cols].sum(axis=1).astype(np.float32)
    cells["F_TOTAL"] = cells[f_age_cols].sum(axis=1).astype(np.float32)

    return cells


# ---------------------------------------------------------------------------
# Part 3: backfill_orphans (cell [8])
# ---------------------------------------------------------------------------


def backfill_orphans(
    cells: pd.DataFrame,
    gem_m: pd.DataFrame,
    gem_f: pd.DataFrame,
    *,
    log_path: Optional[Path] = None,
) -> tuple[pd.DataFrame, int]:
    """Backfill orphan rows (pop>0, age_sum==0, is_orphan) using Gemeinde shares.

    Faithful port of notebook cell [8].

    Parameters
    ----------
    cells    : DataFrame with AGE_*, M_AGE_*, F_AGE_*, POP_TOTAL_100m_adj,
               RegionalSchlüssel_ARS, is_orphan (bool) columns.
    gem_m    : male reference DataFrame (raw age labels, ARS columns).
    gem_f    : female reference DataFrame.
    log_path : if given, write CSV log of backfilled rows.

    Returns
    -------
    (cells_out, n_backfilled)
    """
    cells = cells.copy()

    # Clean keys
    cells[ARS_COL] = cells[ARS_COL].astype(str).str.strip()
    gem_m = gem_m.copy()
    gem_f = gem_f.copy()
    gem_m.columns = gem_m.columns.astype(str).str.strip()
    gem_f.columns = gem_f.columns.astype(str).str.strip()

    # Align Gemeinde tables
    gem_m = _as_age_index(gem_m).apply(pd.to_numeric, errors="coerce").fillna(0.0)
    gem_f = _as_age_index(gem_f).apply(pd.to_numeric, errors="coerce").fillna(0.0)
    common_ars = gem_m.columns.intersection(gem_f.columns)
    gem_m = gem_m[common_ars]
    gem_f = gem_f[common_ars]

    # Identify offenders
    row_age = cells[AGE_COLS].sum(axis=1).to_numpy(float)
    pop     = pd.to_numeric(cells["POP_TOTAL_100m_adj"], errors="coerce").fillna(0.0).to_numpy(float)

    is_orphan_col = cells.get("is_orphan", False)
    if isinstance(is_orphan_col, pd.Series):
        is_orphan = is_orphan_col.to_numpy(bool)
    else:
        is_orphan = np.zeros(len(cells), dtype=bool)

    off_mask = (pop > 0) & (row_age == 0) & is_orphan
    off_idx  = np.flatnonzero(off_mask)
    n_backfilled = off_idx.size

    log.info("backfilling %d orphan rows", n_backfilled)

    if log_path is not None and off_idx.size:
        cols_show = ["GITTER_ID_100m", ARS_COL, "POP_TOTAL_100m_adj"]
        cells.loc[cells.index[off_idx], cols_show].to_csv(log_path, index=False)
        log.info("wrote backfill log to %s", log_path)

    if off_idx.size == 0:
        return cells, 0

    # National male share (per age vector, length 101)
    MF = gem_m + gem_f
    nat_m  = gem_m.sum(axis=1).to_numpy(float)
    nat_f  = gem_f.sum(axis=1).to_numpy(float)
    with np.errstate(divide="ignore", invalid="ignore"):
        nat_share = np.divide(nat_m, np.maximum(nat_m + nat_f, 1e-12))
    nat_share = np.clip(nat_share, 0.0, 1.0)

    # Per-ARS age shares from Gemeinde totals (M+F), national fallback
    G_age_tot    = MF.to_numpy(float)         # (101, G)
    nat_age_share = G_age_tot.sum(axis=1)
    nat_age_share = nat_age_share / max(nat_age_share.sum(), 1e-12)   # (101,)

    ars_to_col = {ars: j for j, ars in enumerate(MF.columns)}
    ars_idx    = cells.loc[cells.index[off_idx], ARS_COL].map(ars_to_col).to_numpy(object)

    S_age = np.empty((off_idx.size, 101), dtype=np.float64)
    for j, col in enumerate(ars_idx):
        if isinstance(col, (int, np.integer)) and 0 <= col < G_age_tot.shape[1]:
            v   = G_age_tot[:, int(col)]
            den = v.sum()
            S_age[j, :] = v / den if den > 0 else nat_age_share
        else:
            S_age[j, :] = nat_age_share

    # Pre-cast the partial-assign target columns to float64 so the .loc backfills below
    # don't emit pandas' incompatible-dtype FutureWarning. float64 is exactly the dtype
    # the assignments already upcast these columns to today, so the values are unchanged.
    _bf_cols = [*AGE_COLS, *M_COLS, *F_COLS, "M_TOTAL", "F_TOTAL"]
    _bf_cols = [c for c in _bf_cols if c in cells.columns]
    cells[_bf_cols] = cells[_bf_cols].astype(np.float64)

    ages_off = pop[off_idx][:, None] * S_age
    cells.loc[cells.index[off_idx], AGE_COLS] = ages_off

    # Male-share matrix (age x ARS)
    with np.errstate(divide="ignore", invalid="ignore"):
        share_df = (gem_m / np.maximum(gem_m + gem_f, 1e-12)).clip(0.0, 1.0)

    share_vals  = share_df.to_numpy(np.float32)                               # (101, G)
    share_vals  = np.concatenate([share_vals, nat_share.reshape(101, 1)], 1)  # (101, G+1)
    fallback_col = share_vals.shape[1] - 1

    ars_to_col_gender = {ars: j for j, ars in enumerate(share_df.columns)}
    col_idx = cells.loc[cells.index[off_idx], ARS_COL].map(ars_to_col_gender).to_numpy(object)
    col_idx = np.array(
        [c if isinstance(c, (int, np.integer)) else fallback_col for c in col_idx],
        dtype=np.int64,
    )

    S_gender   = share_vals[:, col_idx].T.astype(np.float64)   # (k x 101)
    male_off   = ages_off * S_gender
    female_off = ages_off - male_off

    cells.loc[cells.index[off_idx], M_COLS]    = male_off
    cells.loc[cells.index[off_idx], F_COLS]    = female_off
    cells.loc[cells.index[off_idx], "M_TOTAL"] = male_off.sum(axis=1)
    cells.loc[cells.index[off_idx], "F_TOTAL"] = female_off.sum(axis=1)

    log.info("filled %d orphan rows via Gemeinde age shares + male shares.", off_idx.size)

    # QA
    row_age_post = cells[AGE_COLS].sum(axis=1).to_numpy(float)
    rel_vs_pop   = np.abs(row_age_post - pop) / np.maximum(pop, 1.0)
    log.info(
        "backfill vs POP_TOTAL_100m_adj: max=%.3e mean=%.3e",
        rel_vs_pop.max(), rel_vs_pop.mean(),
    )
    agg_m = cells[M_COLS].sum(axis=0).to_numpy(float)
    agg_f = cells[F_COLS].sum(axis=0).to_numpy(float)
    agg_a = cells[AGE_COLS].sum(axis=0).to_numpy(float)
    log.info(
        "backfill national-by-age max|M+F-AGE|=%.3e",
        float(np.abs((agg_m + agg_f) - agg_a).max()),
    )

    return cells, n_backfilled


# ---------------------------------------------------------------------------
# Locate reference CSV
# ---------------------------------------------------------------------------


def _resolve_1000a_csv(cfg) -> Path:
    """Return path to the GENESIS 1000A-2027 CSV.

    Resolution order:
      1. cfg.gemeinde_age_csv_path  — explicit config key (highest priority)
      2. data/raw/genesis/1000A-2027_bevoelkerung_alter_geschlecht_gemeinden.csv  — local copy
      3. T: legacy path  — fallback with a warning
    """
    p = getattr(cfg, "gemeinde_age_csv_path", None)
    if p is not None:
        return Path(p)
    if _LOCAL_1000A.exists():
        return _LOCAL_1000A
    if _T_1000A.exists():
        log.warning(
            "GENESIS CSV local copy not found at %s; "
            "falling back to T: path %s — consider copying to "
            "'data/raw/genesis/1000A-2027_bevoelkerung_alter_geschlecht_gemeinden.csv'",
            _LOCAL_1000A,
            _T_1000A,
        )
        return _T_1000A
    raise FileNotFoundError(
        "GENESIS 1000A-2027 CSV not found. Expected one of:\n"
        f"  1. cfg.gemeinde_age_csv_path (TOML key [data].gemeinde_age_csv_path)\n"
        f"  2. {_LOCAL_1000A}\n"
        f"  3. {_T_1000A}\n"
        "Download from: https://ergebnisse.zensus2022.de/datenbank/online/table/1000A-2027\n"
        "  -> Anpassen -> Gemeinden -> download CSV"
    )


# ---------------------------------------------------------------------------
# Pipeline entry point
# ---------------------------------------------------------------------------


def run_gender(cfg) -> None:
    """Pipeline entry point for the gender stage."""
    work = cfg.work_dir
    work.mkdir(parents=True, exist_ok=True)

    cells_in  = work / "cells_100m_with_gemeinde.parquet"
    cells_out = work / "cells_100m_with_gender_backfilled.parquet"
    log_out   = work / "backfilled_rows_log.csv"

    # --- 1) Load reference data ---
    csv_path = _resolve_1000a_csv(cfg)
    log.info("loading 1000A reference from %s", csv_path)
    total_df, male_df, female_df = load_age_csv_to_matrices(csv_path)
    log.info("reference tables: shape=%s", male_df.shape)

    # --- 2) Load cells (gemeinde stage output) ---
    log.info("loading gemeinde cells from %s", cells_in)
    cells = pd.read_parquet(cells_in)
    log.info("cells loaded: %d rows x %d cols", *cells.shape)

    # --- 3) Gender split ---
    cells = add_gender_split(cells, male_df, female_df)

    # --- 4) Backfill orphans ---
    cells, n_filled = backfill_orphans(cells, male_df, female_df, log_path=log_out)
    log.info("backfilled %d rows", n_filled)

    # --- 5) Write output ---
    cells.to_parquet(cells_out, index=False)
    log.info("wrote %s (%d rows)", cells_out.name, len(cells))


def gender_complete(cfg) -> bool:
    return (cfg.work_dir / "cells_100m_with_gender_backfilled.parquet").exists()
