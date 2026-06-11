"""Tests for cleancensus.gemeinde_controls.

Uses in-memory synthetic mini-sheets to test the parser, Gemeinde-row filtering,
and suppression -> NaN conversion — no real Excel file required.
"""
from __future__ import annotations

import io
import warnings

import numpy as np
import pandas as pd
import pytest


# ---------------------------------------------------------------------------
# Helpers to build synthetic in-memory Excel workbooks
# ---------------------------------------------------------------------------

def _make_excel_bytes(sheets: dict[str, pd.DataFrame]) -> bytes:
    """Serialize a dict of DataFrames to an xlsx bytes buffer (xlsxwriter engine)."""
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        for sheet_name, df in sheets.items():
            df.to_excel(writer, sheet_name=sheet_name, index=False)
    return buf.getvalue()


def _synthetic_erwerbsstatus_df() -> pd.DataFrame:
    """Minimal CSV-Erwerbsstatus sheet with rows at multiple Regionalebene levels."""
    rows = [
        # Bund row
        {
            "Berichtszeitpunkt": 20220515,
            "_RS": "00",
            "Name": "Deutschland",
            "Regionalebene": "Bund",
            "ERWERBSTAT_KURZ_STP": 80_000_000,
            "ERWERBSTAT_KURZ_STP__M": 39_000_000,
            "ERWERBSTAT_KURZ_STP__W": 41_000_000,
            "ERWERBSTAT_KURZ_STP__1": 43_000_000,
            "ERWERBSTAT_KURZ_STP__11": 41_000_000,
            "ERWERBSTAT_KURZ_STP__12": 2_000_000,
            "ERWERBSTAT_KURZ_STP__2": 37_000_000,
        },
        # Land row
        {
            "Berichtszeitpunkt": 20220515,
            "_RS": "01",
            "Name": "Schleswig-Holstein",
            "Regionalebene": "Land",
            "ERWERBSTAT_KURZ_STP": 2_800_000,
            "ERWERBSTAT_KURZ_STP__M": 1_400_000,
            "ERWERBSTAT_KURZ_STP__W": 1_400_000,
            "ERWERBSTAT_KURZ_STP__1": 1_500_000,
            "ERWERBSTAT_KURZ_STP__11": 1_400_000,
            "ERWERBSTAT_KURZ_STP__12": 100_000,
            "ERWERBSTAT_KURZ_STP__2": 1_300_000,
        },
        # Kreis row (not Gemeinde)
        {
            "Berichtszeitpunkt": 20220515,
            "_RS": "01001",
            "Name": "Flensburg (Kreis)",
            "Regionalebene": "Stadtkreis/kreisfreie Stadt/Landkreis",
            "ERWERBSTAT_KURZ_STP": 92_000,
            "ERWERBSTAT_KURZ_STP__M": 46_000,
            "ERWERBSTAT_KURZ_STP__W": 46_000,
            "ERWERBSTAT_KURZ_STP__1": 52_000,
            "ERWERBSTAT_KURZ_STP__11": 48_000,
            "ERWERBSTAT_KURZ_STP__12": 4_000,
            "ERWERBSTAT_KURZ_STP__2": 40_000,
        },
        # Gemeinde row – no suppression
        {
            "Berichtszeitpunkt": 20220515,
            "_RS": "010010000000",
            "Name": "Flensburg, Stadt",
            "Regionalebene": "Gemeinde",
            "ERWERBSTAT_KURZ_STP": 92_000,
            "ERWERBSTAT_KURZ_STP__M": 46_000,
            "ERWERBSTAT_KURZ_STP__W": 46_000,
            "ERWERBSTAT_KURZ_STP__1": 52_000,
            "ERWERBSTAT_KURZ_STP__11": 48_000,
            "ERWERBSTAT_KURZ_STP__12": 4_000,
            "ERWERBSTAT_KURZ_STP__2": 40_000,
        },
        # Gemeinde row – suppressed value ('/')
        {
            "Berichtszeitpunkt": 20220515,
            "_RS": "010515163003",
            "Name": "Averlak",
            "Regionalebene": "Gemeinde",
            "ERWERBSTAT_KURZ_STP": "/",   # suppressed total
            "ERWERBSTAT_KURZ_STP__M": "/",
            "ERWERBSTAT_KURZ_STP__W": "/",
            "ERWERBSTAT_KURZ_STP__1": "/",
            "ERWERBSTAT_KURZ_STP__11": "/",
            "ERWERBSTAT_KURZ_STP__12": "/",
            "ERWERBSTAT_KURZ_STP__2": "/",
        },
        # Second Gemeinde row – partial suppression
        {
            "Berichtszeitpunkt": 20220515,
            "_RS": "010510011011",
            "Name": "Brunsbüttel, Stadt",
            "Regionalebene": "Gemeinde",
            "ERWERBSTAT_KURZ_STP": 12_270,
            "ERWERBSTAT_KURZ_STP__M": 6_180,
            "ERWERBSTAT_KURZ_STP__W": 6_090,
            "ERWERBSTAT_KURZ_STP__1": 6_340,
            "ERWERBSTAT_KURZ_STP__11": 5_940,
            "ERWERBSTAT_KURZ_STP__12": 400,
            "ERWERBSTAT_KURZ_STP__2": "/",   # single suppressed value
        },
    ]
    return pd.DataFrame(rows)


def _make_synthetic_xlsx(tmp_path) -> "Path":
    """Write a synthetic xlsx with CSV-Erwerbsstatus to tmp_path and return the path."""
    from pathlib import Path
    df = _synthetic_erwerbsstatus_df()
    path = tmp_path / "test_regionaltabelle.xlsx"
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="CSV-Erwerbsstatus", index=False)
    path.write_bytes(buf.getvalue())
    return path


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestParseSheetInternals:
    """Unit tests on the _parse_sheet helper."""

    def test_parse_returns_dataframe(self, tmp_path):
        from cleancensus.gemeinde_controls import _parse_sheet
        path = _make_synthetic_xlsx(tmp_path)
        df = _parse_sheet(path, "CSV-Erwerbsstatus")
        assert isinstance(df, pd.DataFrame)

    def test_parse_has_ars_column(self, tmp_path):
        from cleancensus.gemeinde_controls import _parse_sheet
        path = _make_synthetic_xlsx(tmp_path)
        df = _parse_sheet(path, "CSV-Erwerbsstatus")
        assert "_RS" in df.columns

    def test_ars_zero_padded_to_12(self, tmp_path):
        """ARS values for Gemeinde rows must be 12-digit strings."""
        from cleancensus.gemeinde_controls import _parse_sheet
        path = _make_synthetic_xlsx(tmp_path)
        df = _parse_sheet(path, "CSV-Erwerbsstatus")
        gemeinde_rows = df[df["Regionalebene"] == "Gemeinde"]
        for ars in gemeinde_rows["_RS"]:
            assert len(ars) == 12, f"ARS {ars!r} is not 12 chars"

    def test_suppression_slash_becomes_nan(self, tmp_path):
        """'/' suppression markers must become NaN in data columns."""
        from cleancensus.gemeinde_controls import _parse_sheet
        path = _make_synthetic_xlsx(tmp_path)
        df = _parse_sheet(path, "CSV-Erwerbsstatus")
        # Averlak row should be all-NaN in data columns
        averlak = df[df["Name"] == "Averlak"]
        assert len(averlak) == 1
        data_cols = [c for c in df.columns if c not in ("Berichtszeitpunkt", "_RS", "Name", "Regionalebene")]
        for col in data_cols:
            assert pd.isna(averlak[col].iloc[0]), f"Column {col} should be NaN for suppressed Averlak row"

    def test_partial_suppression_single_nan(self, tmp_path):
        """A single suppressed cell becomes NaN; other cells in the row remain numeric."""
        from cleancensus.gemeinde_controls import _parse_sheet
        path = _make_synthetic_xlsx(tmp_path)
        df = _parse_sheet(path, "CSV-Erwerbsstatus")
        brunsbuettel = df[df["Name"] == "Brunsbüttel, Stadt"]
        assert len(brunsbuettel) == 1
        # ERWERBSTAT_KURZ_STP (total) should be numeric
        assert brunsbuettel["ERWERBSTAT_KURZ_STP"].iloc[0] == 12_270
        # ERWERBSTAT_KURZ_STP__2 (suppressed) should be NaN
        assert pd.isna(brunsbuettel["ERWERBSTAT_KURZ_STP__2"].iloc[0])


class TestGemeindeFiltering:
    """Tests that build_gemeinde_controls keeps only Gemeinde-level rows."""

    def test_only_gemeinde_rows_returned(self, tmp_path):
        from cleancensus.gemeinde_controls import build_gemeinde_controls
        path = _make_synthetic_xlsx(tmp_path)
        sheets = {"erwerbsstatus": "CSV-Erwerbsstatus"}
        result = build_gemeinde_controls(path, sheets=sheets)
        df = result["erwerbsstatus"]
        # Synthetic data has 3 Gemeinde rows; Bund/Land/Kreis rows must be excluded
        assert len(df) == 3

    def test_bund_row_excluded(self, tmp_path):
        from cleancensus.gemeinde_controls import build_gemeinde_controls
        path = _make_synthetic_xlsx(tmp_path)
        sheets = {"erwerbsstatus": "CSV-Erwerbsstatus"}
        result = build_gemeinde_controls(path, sheets=sheets)
        df = result["erwerbsstatus"]
        assert "Deutschland" not in df["Name"].values

    def test_land_row_excluded(self, tmp_path):
        from cleancensus.gemeinde_controls import build_gemeinde_controls
        path = _make_synthetic_xlsx(tmp_path)
        sheets = {"erwerbsstatus": "CSV-Erwerbsstatus"}
        result = build_gemeinde_controls(path, sheets=sheets)
        df = result["erwerbsstatus"]
        assert "Schleswig-Holstein" not in df["Name"].values

    def test_kreis_row_excluded(self, tmp_path):
        from cleancensus.gemeinde_controls import build_gemeinde_controls
        path = _make_synthetic_xlsx(tmp_path)
        sheets = {"erwerbsstatus": "CSV-Erwerbsstatus"}
        result = build_gemeinde_controls(path, sheets=sheets)
        df = result["erwerbsstatus"]
        assert "Flensburg (Kreis)" not in df["Name"].values

    def test_ars_column_renamed(self, tmp_path):
        """_RS column must be renamed to ARS in the output."""
        from cleancensus.gemeinde_controls import build_gemeinde_controls
        path = _make_synthetic_xlsx(tmp_path)
        sheets = {"erwerbsstatus": "CSV-Erwerbsstatus"}
        result = build_gemeinde_controls(path, sheets=sheets)
        df = result["erwerbsstatus"]
        assert "ARS" in df.columns
        assert "_RS" not in df.columns

    def test_regionalebene_dropped(self, tmp_path):
        """Regionalebene meta column should be dropped (always 'Gemeinde' in output)."""
        from cleancensus.gemeinde_controls import build_gemeinde_controls
        path = _make_synthetic_xlsx(tmp_path)
        sheets = {"erwerbsstatus": "CSV-Erwerbsstatus"}
        result = build_gemeinde_controls(path, sheets=sheets)
        df = result["erwerbsstatus"]
        assert "Regionalebene" not in df.columns

    def test_ars_all_12_digits(self, tmp_path):
        """All ARS values in output must be 12-character strings."""
        from cleancensus.gemeinde_controls import build_gemeinde_controls
        path = _make_synthetic_xlsx(tmp_path)
        sheets = {"erwerbsstatus": "CSV-Erwerbsstatus"}
        result = build_gemeinde_controls(path, sheets=sheets)
        df = result["erwerbsstatus"]
        for ars in df["ARS"]:
            assert isinstance(ars, str), f"ARS {ars!r} is not a string"
            assert len(ars) == 12, f"ARS {ars!r} is not 12 chars"


class TestSuppressionNaN:
    """Targeted suppression -> NaN tests."""

    def test_fully_suppressed_row_all_nan(self, tmp_path):
        from cleancensus.gemeinde_controls import build_gemeinde_controls
        path = _make_synthetic_xlsx(tmp_path)
        sheets = {"erwerbsstatus": "CSV-Erwerbsstatus"}
        result = build_gemeinde_controls(path, sheets=sheets)
        df = result["erwerbsstatus"]
        averlak = df[df["Name"] == "Averlak"]
        data_cols = [c for c in df.columns if c not in ("ARS", "Name")]
        assert averlak[data_cols].isna().all(axis=None)

    def test_non_suppressed_row_no_nan(self, tmp_path):
        from cleancensus.gemeinde_controls import build_gemeinde_controls
        path = _make_synthetic_xlsx(tmp_path)
        sheets = {"erwerbsstatus": "CSV-Erwerbsstatus"}
        result = build_gemeinde_controls(path, sheets=sheets)
        df = result["erwerbsstatus"]
        flensburg = df[df["Name"] == "Flensburg, Stadt"]
        data_cols = [c for c in df.columns if c not in ("ARS", "Name")]
        assert flensburg[data_cols].notna().all(axis=None)

    def test_data_columns_float64(self, tmp_path):
        """Data columns must be float64, not object."""
        from cleancensus.gemeinde_controls import build_gemeinde_controls
        path = _make_synthetic_xlsx(tmp_path)
        sheets = {"erwerbsstatus": "CSV-Erwerbsstatus"}
        result = build_gemeinde_controls(path, sheets=sheets)
        df = result["erwerbsstatus"]
        data_cols = [c for c in df.columns if c not in ("ARS", "Name")]
        for col in data_cols:
            assert df[col].dtype in (np.float64, float), (
                f"Column {col} has dtype {df[col].dtype!r}, expected float64"
            )


class TestBuildGemeindeControlsMultiSheet:
    """Tests with multiple sheets in one workbook."""

    def _make_two_sheet_xlsx(self, tmp_path):
        """Write synthetic xlsx with CSV-Erwerbsstatus and CSV-Hoechster_Schulabschluss."""
        df_erw = _synthetic_erwerbsstatus_df()
        # Minimal Schulabschluss sheet (same Gemeinden)
        df_sch = df_erw[["Berichtszeitpunkt", "_RS", "Name", "Regionalebene"]].copy()
        df_sch["SCHULABS_STP"] = df_erw["ERWERBSTAT_KURZ_STP"]
        df_sch["SCHULABS_STP__1"] = "//"
        df_sch["SCHULABS_STP__2"] = df_erw["ERWERBSTAT_KURZ_STP__1"]

        from pathlib import Path
        path = tmp_path / "test_two_sheets.xlsx"
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine="openpyxl") as writer:
            df_erw.to_excel(writer, sheet_name="CSV-Erwerbsstatus", index=False)
            df_sch.to_excel(writer, sheet_name="CSV-Hoechster_Schulabschluss", index=False)
        path.write_bytes(buf.getvalue())
        return path

    def test_two_sheets_both_returned(self, tmp_path):
        from cleancensus.gemeinde_controls import build_gemeinde_controls
        path = self._make_two_sheet_xlsx(tmp_path)
        sheets = {
            "erwerbsstatus": "CSV-Erwerbsstatus",
            "schulabschluss": "CSV-Hoechster_Schulabschluss",
        }
        result = build_gemeinde_controls(path, sheets=sheets)
        assert "erwerbsstatus" in result
        assert "schulabschluss" in result

    def test_each_result_is_dataframe(self, tmp_path):
        from cleancensus.gemeinde_controls import build_gemeinde_controls
        path = self._make_two_sheet_xlsx(tmp_path)
        sheets = {
            "erwerbsstatus": "CSV-Erwerbsstatus",
            "schulabschluss": "CSV-Hoechster_Schulabschluss",
        }
        result = build_gemeinde_controls(path, sheets=sheets)
        for name, df in result.items():
            assert isinstance(df, pd.DataFrame), f"{name} is not a DataFrame"

    def test_same_gemeinde_count_in_both(self, tmp_path):
        from cleancensus.gemeinde_controls import build_gemeinde_controls
        path = self._make_two_sheet_xlsx(tmp_path)
        sheets = {
            "erwerbsstatus": "CSV-Erwerbsstatus",
            "schulabschluss": "CSV-Hoechster_Schulabschluss",
        }
        result = build_gemeinde_controls(path, sheets=sheets)
        assert len(result["erwerbsstatus"]) == len(result["schulabschluss"])


class TestRunGemeindeControlsSmoke:
    """Smoke test for run_gemeinde_controls (writes parquet files)."""

    def _make_config(self, tmp_path):
        """Create a minimal Config pointing to tmp_path."""
        from cleancensus.config import Config
        inputs_dir = tmp_path / "inputs"
        inputs_dir.mkdir()
        outputs_dir = tmp_path / "outputs"
        outputs_dir.mkdir()
        return Config(
            inputs_dir=inputs_dir,
            outputs_dir=outputs_dir,
            version_tag="test",
            topics=["Whg_Gebaeudetyp"],
            derived_tenure=False,
            derived_vacancy=False,
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

    def _make_full_xlsx(self, tmp_path):
        """Write synthetic xlsx with all 3 required sheets."""
        from pathlib import Path
        df_erw = _synthetic_erwerbsstatus_df()
        # Minimal Schulabschluss
        df_sch = df_erw[["Berichtszeitpunkt", "_RS", "Name", "Regionalebene"]].copy()
        df_sch["SCHULABS_STP"] = df_erw["ERWERBSTAT_KURZ_STP"]
        df_sch["SCHULABS_STP__1"] = df_erw["ERWERBSTAT_KURZ_STP__1"]
        df_sch["SCHULABS_STP__2"] = df_erw["ERWERBSTAT_KURZ_STP__2"]
        # Minimal Berufl Abschluss
        df_beruf = df_erw[["Berichtszeitpunkt", "_RS", "Name", "Regionalebene"]].copy()
        df_beruf["BERUFABS_AUSF_STP"] = df_erw["ERWERBSTAT_KURZ_STP"]
        df_beruf["BERUFABS_AUSF_STP__1"] = df_erw["ERWERBSTAT_KURZ_STP__1"]
        df_beruf["BERUFABS_AUSF_STP__2"] = df_erw["ERWERBSTAT_KURZ_STP__2"]

        raw_dir = tmp_path / "inputs" / ".." / "raw" / "regionaltabellen"
        raw_dir.mkdir(parents=True, exist_ok=True)
        path = raw_dir / "Regionaltabelle_Bildung_Erwerbstaetigkeit.xlsx"
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine="openpyxl") as writer:
            df_erw.to_excel(writer, sheet_name="CSV-Erwerbsstatus", index=False)
            df_sch.to_excel(writer, sheet_name="CSV-Hoechster_Schulabschluss", index=False)
            df_beruf.to_excel(writer, sheet_name="CSV-Hoechster_berufl_Abschluss", index=False)
        path.write_bytes(buf.getvalue())
        return path

    def test_run_creates_output_dir(self, tmp_path):
        from cleancensus.gemeinde_controls import run_gemeinde_controls
        cfg = self._make_config(tmp_path)
        self._make_full_xlsx(tmp_path)
        run_gemeinde_controls(cfg)
        assert (cfg.outputs_dir / "gemeinde_controls").exists()

    def test_run_creates_three_parquets(self, tmp_path):
        from cleancensus.gemeinde_controls import run_gemeinde_controls
        cfg = self._make_config(tmp_path)
        self._make_full_xlsx(tmp_path)
        run_gemeinde_controls(cfg)
        out_dir = cfg.outputs_dir / "gemeinde_controls"
        for name in ("erwerbsstatus", "schulabschluss", "berufl_abschluss"):
            assert (out_dir / f"{name}.parquet").exists(), f"{name}.parquet not found"

    def test_parquet_readable(self, tmp_path):
        from cleancensus.gemeinde_controls import run_gemeinde_controls
        cfg = self._make_config(tmp_path)
        self._make_full_xlsx(tmp_path)
        run_gemeinde_controls(cfg)
        df = pd.read_parquet(cfg.outputs_dir / "gemeinde_controls" / "erwerbsstatus.parquet")
        assert isinstance(df, pd.DataFrame)
        assert "ARS" in df.columns
        assert len(df) == 3  # 3 Gemeinde rows in synthetic data

    def test_missing_xlsx_raises_file_not_found(self, tmp_path):
        from cleancensus.gemeinde_controls import run_gemeinde_controls
        cfg = self._make_config(tmp_path)
        # Do NOT create the xlsx
        with pytest.raises(FileNotFoundError, match="Regionaltabelle not found"):
            run_gemeinde_controls(cfg)


class TestCategoryCodeConstants:
    """Basic sanity checks on the exported category code maps."""

    def test_erwerbsstatus_cats_has_erwerbstaetige(self):
        from cleancensus.gemeinde_controls import ERWERBSSTATUS_CATS
        assert "Erwerbstaetige" in ERWERBSSTATUS_CATS
        assert ERWERBSSTATUS_CATS["Erwerbstaetige"] == "ERWERBSTAT_KURZ_STP__11"

    def test_schulabschluss_cats_has_abitur(self):
        from cleancensus.gemeinde_controls import SCHULABSCHLUSS_CATS
        assert "Abitur" in SCHULABSCHLUSS_CATS

    def test_berufl_abschluss_cats_has_lehre(self):
        from cleancensus.gemeinde_controls import BERUFL_ABSCHLUSS_CATS
        assert "Lehre" in BERUFL_ABSCHLUSS_CATS

    def test_default_sheets_has_three_entries(self):
        from cleancensus.gemeinde_controls import DEFAULT_SHEETS
        assert len(DEFAULT_SHEETS) == 3
        assert "erwerbsstatus" in DEFAULT_SHEETS
        assert "schulabschluss" in DEFAULT_SHEETS
        assert "berufl_abschluss" in DEFAULT_SHEETS
