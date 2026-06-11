"""Unit tests for the gemeinde and gender stage core transforms.

These tests cover synthetic toy-frame behaviour only — no heavy IO, no T: drive
access.  They validate:
  - M/F split arithmetic on a toy DataFrame
  - national fallback when ARS is unknown
  - backfill case selection: pop>0 & age_sum==0 & is_orphan
  - Gemeinde age-share application during backfill
  - ARS sub-field decomposition (Land, Kreis, etc.)
  - 12-digit ARS validation helper
  - age-label canonicalisation (0..100, Insgesamt)
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

# ---------------------------------------------------------------------------
# Helpers imported from the stage modules
# ---------------------------------------------------------------------------
from cleancensus.gender_stage import (
    _as_age_index,
    _canon_age,
    add_gender_split,
    backfill_orphans,
)
from cleancensus.gemeinde_stage import _add_ars_parts, _require_exact_12_digit_key


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

AGE_TOP = 100
AGE_COLS = [f"AGE_{a}" for a in range(AGE_TOP + 1)]
M_COLS   = [f"M_AGE_{a}" for a in range(AGE_TOP + 1)]
F_COLS   = [f"F_AGE_{a}" for a in range(AGE_TOP + 1)]


def _make_gem_tables(n_ars: int = 3, seed: int = 0) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return small synthetic (male, female) Gemeinde reference DataFrames."""
    rng = np.random.default_rng(seed)
    ars_ids = [f"{i:012d}" for i in range(n_ars)]
    male   = pd.DataFrame(
        rng.integers(10, 200, size=(101, n_ars)).astype(float),
        index=list(range(101)),
        columns=ars_ids,
    )
    female = pd.DataFrame(
        rng.integers(10, 200, size=(101, n_ars)).astype(float),
        index=list(range(101)),
        columns=ars_ids,
    )
    return male, female


def _make_cells(n: int = 5, ars_ids: list | None = None, seed: int = 42) -> pd.DataFrame:
    """Return a tiny cells DataFrame with AGE_0..AGE_100, ARS, POP_TOTAL_100m_adj."""
    rng = np.random.default_rng(seed)
    if ars_ids is None:
        ars_ids = [f"{i:012d}" for i in range(3)]

    age_data = {c: rng.integers(0, 10, size=n).astype(float) for c in AGE_COLS}
    df = pd.DataFrame(age_data)
    df["GITTER_ID_100m"]        = [f"CRS3035RES100mN{2700000+i*100}E{4300000+i*100}" for i in range(n)]
    df["RegionalSchlüssel_ARS"] = [ars_ids[i % len(ars_ids)] for i in range(n)]
    df["POP_TOTAL_100m_adj"]    = df[AGE_COLS].sum(axis=1)
    df["is_orphan"]             = False
    return df


# ---------------------------------------------------------------------------
# Test: ARS sub-field decomposition (gemeinde_stage)
# ---------------------------------------------------------------------------

class _FakeGDF(dict):
    """Minimal stand-in for a GeoDataFrame for _add_ars_parts."""
    def __init__(self, ars_list):
        import geopandas as gpd
        self._df = gpd.GeoDataFrame({
            "Regionalschlüssel_ARS": ars_list,
            "geometry": gpd.GeoSeries.from_wkt(["POINT(0 0)"] * len(ars_list)),
        })

    def __getattr__(self, k):
        return getattr(self._df, k)

    def __contains__(self, k):
        return k in self._df.columns

    def copy(self):
        return type(self)(self._df["Regionalschlüssel_ARS"].tolist())

    # delegate column access
    def __getitem__(self, k):
        return self._df[k]

    def __setitem__(self, k, v):
        self._df[k] = v


def test_add_ars_parts_slices_correctly():
    """_add_ars_parts should produce the 7 fixed-length sub-fields."""
    import geopandas as gpd

    ars = "097800133133"
    gem = gpd.GeoDataFrame({
        "Regionalschlüssel_ARS": [ars],
        "geometry": gpd.GeoSeries.from_wkt(["POINT(0 0)"]),
    })
    gem2 = _add_ars_parts(gem, "Regionalschlüssel_ARS")

    assert gem2["RegionalSchlüssel_ARS"].iloc[0] == ars
    assert gem2["Land"].iloc[0]             == "09"   # chars 0:2
    assert gem2["Regierungsbezirk"].iloc[0] == "7"    # char  2:3
    assert gem2["Kreis"].iloc[0]            == "80"   # chars 3:5
    assert gem2["VerwaltungsgemeinschaftTeil1"].iloc[0] == "01"  # chars 5:7
    assert gem2["VerwaltungsgemeinschaftTeil2"].iloc[0] == "33"  # chars 7:9
    assert gem2["Gemeinde"].iloc[0]         == "133"  # chars 9:12


def test_require_exact_12_digit_key_raises_on_short():
    import geopandas as gpd

    gem = gpd.GeoDataFrame({
        "Regionalschlüssel_ARS": ["12345"],
        "geometry": gpd.GeoSeries.from_wkt(["POINT(0 0)"]),
    })
    with pytest.raises(ValueError, match="12 digits"):
        _require_exact_12_digit_key(gem)


def test_require_exact_12_digit_key_raises_on_missing_col():
    import geopandas as gpd

    gem = gpd.GeoDataFrame({
        "some_other_col": ["097800133133"],
        "geometry": gpd.GeoSeries.from_wkt(["POINT(0 0)"]),
    })
    with pytest.raises(KeyError):
        _require_exact_12_digit_key(gem)


# ---------------------------------------------------------------------------
# Test: age-label canonicalisation (gender_stage)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("label,expected", [
    ("Unter 1 Jahr", "0"),
    ("unter 1 Jahr", "0"),
    ("1 Jahr", "1"),
    ("10 Jahre", "10"),
    ("99 Jahre", "99"),
    ("100 Jahre und älter", "100"),
    ("Insgesamt", "Insgesamt"),
])
def test_canon_age(label, expected):
    assert _canon_age(label) == expected


def test_canon_age_raises_on_unknown():
    with pytest.raises(ValueError, match="Unrecognized"):
        _canon_age("some garbage label")


# ---------------------------------------------------------------------------
# Test: _as_age_index (gender_stage)
# ---------------------------------------------------------------------------

def test_as_age_index_keeps_only_0_to_100():
    df = pd.DataFrame({"A": [1.0, 2.0, 3.0]}, index=["0", "101", "Insgesamt"])
    out = _as_age_index(df)
    assert 0 in out.index
    assert "Insgesamt" not in out.index
    assert 101 not in out.index


# ---------------------------------------------------------------------------
# Test: add_gender_split arithmetic
# ---------------------------------------------------------------------------

def test_gender_split_mf_reconstructs_age():
    """M_AGE_a + F_AGE_a == AGE_a for every cell and every age."""
    gem_m, gem_f = _make_gem_tables(n_ars=3)
    cells = _make_cells(n=10, ars_ids=gem_m.columns.tolist())

    result = add_gender_split(cells, gem_m, gem_f)

    for a in range(101):
        age_col = f"AGE_{a}"
        m_col   = f"M_AGE_{a}"
        f_col   = f"F_AGE_{a}"
        recon = result[m_col].astype(float) + result[f_col].astype(float)
        np.testing.assert_allclose(
            recon.values, result[age_col].astype(float).values,
            rtol=0, atol=1e-4,
            err_msg=f"M+F != AGE for age {a}",
        )


def test_gender_split_nonnegative():
    """M_AGE_* and F_AGE_* must be non-negative (no cell can go negative)."""
    gem_m, gem_f = _make_gem_tables(n_ars=3)
    cells = _make_cells(n=8, ars_ids=gem_m.columns.tolist())

    result = add_gender_split(cells, gem_m, gem_f)

    for col in M_COLS + F_COLS:
        assert (result[col].astype(float) >= -1e-7).all(), f"{col} has negatives"


def test_gender_split_unknown_ars_uses_national_fallback():
    """Cells with an ARS not in the reference tables should still get M+F==AGE."""
    gem_m, gem_f = _make_gem_tables(n_ars=2)
    cells = _make_cells(n=5, ars_ids=["999999999999"])  # not in gem tables

    result = add_gender_split(cells, gem_m, gem_f)

    for a in range(101):
        recon = result[f"M_AGE_{a}"].astype(float) + result[f"F_AGE_{a}"].astype(float)
        np.testing.assert_allclose(
            recon.values, result[f"AGE_{a}"].astype(float).values,
            rtol=0, atol=1e-4,
        )


def test_gender_split_totals_columns():
    """M_TOTAL and F_TOTAL must equal sum of M_AGE_* / F_AGE_*."""
    gem_m, gem_f = _make_gem_tables(n_ars=3)
    cells = _make_cells(n=6, ars_ids=gem_m.columns.tolist())

    result = add_gender_split(cells, gem_m, gem_f)

    m_sum = result[M_COLS].astype(float).sum(axis=1)
    f_sum = result[F_COLS].astype(float).sum(axis=1)
    np.testing.assert_allclose(result["M_TOTAL"].astype(float).values, m_sum.values, rtol=1e-5)
    np.testing.assert_allclose(result["F_TOTAL"].astype(float).values, f_sum.values, rtol=1e-5)


# ---------------------------------------------------------------------------
# Test: backfill_orphans case selection
# ---------------------------------------------------------------------------

def test_backfill_only_touches_orphans_with_pop():
    """Rows that are orphans but pop==0, or have pop>0 but are not is_orphan, must not change."""
    gem_m, gem_f = _make_gem_tables(n_ars=3)

    rng = np.random.default_rng(1)
    n = 6
    age_data = {c: rng.integers(5, 20, size=n).astype(float) for c in AGE_COLS}
    cells = pd.DataFrame(age_data)
    cells["GITTER_ID_100m"]        = [f"ID{i}" for i in range(n)]
    cells["RegionalSchlüssel_ARS"] = [gem_m.columns[i % 3] for i in range(n)]
    cells["POP_TOTAL_100m_adj"]    = cells[AGE_COLS].sum(axis=1)

    # Create M/F columns via gender split first
    cells = add_gender_split(cells, gem_m, gem_f)

    # Now zero out AGE_* for rows 0 and 1 to simulate orphan candidates
    cells.loc[0, AGE_COLS] = 0.0  # pop>0 but age_sum==0 (pop was set from non-zero ages)
    cells.loc[1, AGE_COLS] = 0.0
    cells.loc[0, M_COLS] = 0.0
    cells.loc[0, F_COLS] = 0.0
    cells.loc[1, M_COLS] = 0.0
    cells.loc[1, F_COLS] = 0.0

    # Row 0: orphan=True, pop>0 -> should be backfilled
    # Row 1: orphan=False, pop>0 -> should NOT be backfilled
    # Rows 2-5: orphan=True but age_sum>0 -> should NOT be backfilled
    cells["is_orphan"] = False
    cells.loc[0, "is_orphan"] = True
    cells.loc[2, "is_orphan"] = True
    cells.loc[3, "is_orphan"] = True

    pre_row1_age = cells.loc[1, AGE_COLS[0]]
    pre_row2_age_sum = cells.loc[2, AGE_COLS].sum()

    out, n_filled = backfill_orphans(cells, gem_m, gem_f)

    assert n_filled == 1, f"Expected 1 backfilled row, got {n_filled}"
    # Row 0 should now have age_sum > 0
    assert out.loc[0, AGE_COLS].sum() > 0, "Row 0 should have been backfilled"
    # Row 1 must not change (not is_orphan)
    assert out.loc[1, AGE_COLS[0]] == pre_row1_age
    # Row 2 must not change (age_sum was > 0 before)
    assert abs(out.loc[2, AGE_COLS].sum() - pre_row2_age_sum) < 1e-7


def test_backfill_restores_mf_sum_equals_age():
    """After backfill, M+F must equal AGE for the filled row."""
    gem_m, gem_f = _make_gem_tables(n_ars=2)

    n = 3
    cells = pd.DataFrame({c: [5.0, 0.0, 3.0] for c in AGE_COLS})
    cells["GITTER_ID_100m"]        = ["A", "B", "C"]
    cells["RegionalSchlüssel_ARS"] = [gem_m.columns[0], gem_m.columns[1], gem_m.columns[0]]
    cells["POP_TOTAL_100m_adj"]    = [cells.loc[0, AGE_COLS].sum(), 10.0, cells.loc[2, AGE_COLS].sum()]
    cells["is_orphan"]             = [False, True, False]

    cells = add_gender_split(cells, gem_m, gem_f)
    # row 1: zero the ages/mf to simulate "no age data" despite pop>0
    cells.loc[1, AGE_COLS] = 0.0
    cells.loc[1, M_COLS]   = 0.0
    cells.loc[1, F_COLS]   = 0.0

    out, n_filled = backfill_orphans(cells, gem_m, gem_f)

    assert n_filled == 1
    for a in range(101):
        m = float(out.loc[1, f"M_AGE_{a}"])
        f = float(out.loc[1, f"F_AGE_{a}"])
        age = float(out.loc[1, f"AGE_{a}"])
        np.testing.assert_allclose(m + f, age, atol=1e-7, err_msg=f"M+F!=AGE at age {a}")


def test_backfill_log_written(tmp_path):
    """backfill_orphans should write a CSV log at log_path when there are filled rows."""
    gem_m, gem_f = _make_gem_tables(n_ars=2)

    cells = pd.DataFrame({c: [0.0] for c in AGE_COLS})
    cells["GITTER_ID_100m"]        = ["X"]
    cells["RegionalSchlüssel_ARS"] = [gem_m.columns[0]]
    cells["POP_TOTAL_100m_adj"]    = [7.0]
    cells["is_orphan"]             = [True]
    cells = add_gender_split(cells, gem_m, gem_f)
    cells.loc[0, AGE_COLS] = 0.0
    cells.loc[0, M_COLS]   = 0.0
    cells.loc[0, F_COLS]   = 0.0

    log_path = tmp_path / "backfilled_rows_log.csv"
    out, n_filled = backfill_orphans(cells, gem_m, gem_f, log_path=log_path)

    assert n_filled == 1
    assert log_path.exists()
    import csv as _csv
    with open(log_path, newline="") as fh:
        rows = list(_csv.DictReader(fh))
    assert len(rows) == 1
    assert rows[0]["GITTER_ID_100m"] == "X"


def test_backfill_no_orphans_writes_no_log(tmp_path):
    """When there are no orphans, no log file should be written."""
    gem_m, gem_f = _make_gem_tables(n_ars=2)
    cells = _make_cells(n=3, ars_ids=gem_m.columns.tolist())
    cells = add_gender_split(cells, gem_m, gem_f)
    # all is_orphan=False; age_sum > 0 -> no offenders

    log_path = tmp_path / "should_not_exist.csv"
    out, n_filled = backfill_orphans(cells, gem_m, gem_f, log_path=log_path)

    assert n_filled == 0
    assert not log_path.exists()


# ---------------------------------------------------------------------------
# Test: gemeinde_complete / gender_complete flags
# ---------------------------------------------------------------------------

def test_gemeinde_complete_false_when_missing(tmp_path):
    from cleancensus.gemeinde_stage import gemeinde_complete

    class _Cfg:
        work_dir = tmp_path

    assert not gemeinde_complete(_Cfg())


def test_gender_complete_false_when_missing(tmp_path):
    from cleancensus.gender_stage import gender_complete

    class _Cfg:
        work_dir = tmp_path

    assert not gender_complete(_Cfg())


def test_gemeinde_complete_true_when_file_exists(tmp_path):
    from cleancensus.gemeinde_stage import gemeinde_complete

    (tmp_path / "cells_100m_with_gemeinde.parquet").touch()

    class _Cfg:
        work_dir = tmp_path

    assert gemeinde_complete(_Cfg())


def test_gender_complete_true_when_file_exists(tmp_path):
    from cleancensus.gender_stage import gender_complete

    (tmp_path / "cells_100m_with_gender_backfilled.parquet").touch()

    class _Cfg:
        work_dir = tmp_path

    assert gender_complete(_Cfg())
