"""Unit tests for the aggs and regiostar enrichment stages (R6).

Tests are deliberately lightweight (no heavy IO):
  * test_aggs_bin_spec_covers_ages     — AGE_BINS constant sanity check
  * test_aggs_regiostar_stages_implemented — pipeline registry check
  * test_aggs_summation_synthetic      — agg computation on a tiny synthetic df
  * test_regiostar_ars_to_ags8        — ARS -> AGS8 key conversion
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest


# ---------------------------------------------------------------------------
# Bin spec coverage
# ---------------------------------------------------------------------------

def test_aggs_bin_spec_covers_ages():
    """AGE_BINS constant must cover ages 0-100 with no gaps and correct labels."""
    from cleancensus.enrich import AGE_BINS, AGE_TOP

    expected_labels = [
        "0_9", "10_19", "20_29", "30_39", "40_49",
        "50_59", "60_69", "70_79", "80_plus",
    ]
    got_labels = [label for label, _, _ in AGE_BINS]
    assert got_labels == expected_labels, f"Labels mismatch: {got_labels}"

    # Verify no gaps and correct coverage 0..AGE_TOP
    all_ages: list[int] = []
    for _, lo, hi in AGE_BINS:
        all_ages.extend(range(lo, hi + 1))
    assert all_ages == list(range(AGE_TOP + 1)), (
        f"AGE_BINS does not cover 0..{AGE_TOP} without gaps/overlaps"
    )

    # Last bin must reach AGE_TOP
    last_label, last_lo, last_hi = AGE_BINS[-1]
    assert last_label == "80_plus"
    assert last_hi == AGE_TOP


# ---------------------------------------------------------------------------
# Pipeline registry
# ---------------------------------------------------------------------------

def test_aggs_regiostar_stages_implemented():
    """Both aggs and regiostar must be registered as implemented in the pipeline."""
    from cleancensus.pipeline import REGISTRY

    by_name = {s.name: s for s in REGISTRY}

    assert "aggs" in by_name, "aggs stage not found in REGISTRY"
    assert by_name["aggs"].implemented, "aggs stage is not marked as implemented"

    assert "regiostar" in by_name, "regiostar stage not found in REGISTRY"
    assert by_name["regiostar"].implemented, "regiostar stage is not marked as implemented"


# ---------------------------------------------------------------------------
# Synthetic summation unit test
# ---------------------------------------------------------------------------

def test_aggs_summation_synthetic():
    """_compute_aggs should produce correct decade sums on a tiny synthetic df."""
    from cleancensus.enrich import _compute_aggs, AGE_BINS, AGE_TOP

    rng = np.random.default_rng(42)
    n = 20
    data = {}
    for i in range(AGE_TOP + 1):
        data[f"M_AGE_{i}"] = rng.uniform(0, 5, size=n).astype("float64")
        data[f"F_AGE_{i}"] = rng.uniform(0, 5, size=n).astype("float64")
    df = pd.DataFrame(data)

    result = _compute_aggs(df)

    # Verify M and F bins
    for label, lo, hi in AGE_BINS:
        expected_m = df[[f"M_AGE_{i}" for i in range(lo, hi + 1)]].sum(axis=1)
        expected_f = df[[f"F_AGE_{i}" for i in range(lo, hi + 1)]].sum(axis=1)

        pd.testing.assert_series_equal(
            result[f"M_AGE_{label}_agg"].reset_index(drop=True),
            expected_m.reset_index(drop=True),
            check_names=False,
            atol=1e-10,
            rtol=0,
        )
        pd.testing.assert_series_equal(
            result[f"F_AGE_{label}_agg"].reset_index(drop=True),
            expected_f.reset_index(drop=True),
            check_names=False,
            atol=1e-10,
            rtol=0,
        )

        # Undiff agg = M + F
        expected_undiff = expected_m + expected_f
        pd.testing.assert_series_equal(
            result[f"AGE_{label}_agg"].reset_index(drop=True),
            expected_undiff.reset_index(drop=True),
            check_names=False,
            atol=1e-10,
            rtol=0,
        )

    # Verify totals
    expected_m_total = df[[f"M_AGE_{i}" for i in range(AGE_TOP + 1)]].sum(axis=1)
    expected_f_total = df[[f"F_AGE_{i}" for i in range(AGE_TOP + 1)]].sum(axis=1)
    pd.testing.assert_series_equal(
        result["M_TOTAL"].reset_index(drop=True),
        expected_m_total.reset_index(drop=True),
        check_names=False, atol=1e-10, rtol=0,
    )
    pd.testing.assert_series_equal(
        result["F_TOTAL"].reset_index(drop=True),
        expected_f_total.reset_index(drop=True),
        check_names=False, atol=1e-10, rtol=0,
    )


# ---------------------------------------------------------------------------
# ARS -> AGS8 conversion
# ---------------------------------------------------------------------------

def test_regiostar_ars_to_ags8():
    """_ars_to_ags8 must strip the 4-char Verbandsgemeinde block correctly."""
    from cleancensus.enrich import _ars_to_ags8

    # Known example: ARS 097800133133 -> AGS8 09780133
    assert _ars_to_ags8("097800133133") == "09780133", (
        "12-digit ARS not converted correctly to 8-digit AGS"
    )

    # 8-digit input must be returned unchanged (idempotent)
    assert _ars_to_ags8("09780133") == "09780133"

    # Another known example: ARS 010010000000 -> 01001000
    assert _ars_to_ags8("010010000000") == "01001000"


# ---------------------------------------------------------------------------
# Column normalization unit tests (BBSR 2022 vs legacy BMDV 2020 formats)
# ---------------------------------------------------------------------------

class TestRegioStarColumnNormalization:
    """Unit tests for _is_bbsr2022_format, _normalize_bbsr2022, _normalize_bmdv2020."""

    def _make_bbsr2022_frame(self) -> pd.DataFrame:
        """Minimal synthetic BBSR 2022 Gemeindereferenz sheet (post-skiprows)."""
        return pd.DataFrame({
            "GEM2022":  [1001000, 1002000, 1003000],
            "GEM2022_RS": [10010000000, 10020000000, 10030000000],
            "GEM_NAME": ["Stadt A", "Stadt B", "Gemeinde C"],
            "RS22022":  [1, 1, 2],
            "RSS2022":  [111, 113, 221],
            "RS72022":  [71, 72, 75],
            "RS52022":  [51, 52, 53],
        })

    def _make_bmdv2020_frame(self) -> pd.DataFrame:
        """Minimal synthetic BMDV 2020 ReferenzGebietsstand2020 sheet."""
        return pd.DataFrame({
            "gem_20":       [1002000, 1003000, 1004000],
            "RegioStaR2":   [1, 1, 2],
            "RegioStaR4":   [11, 11, 21],
            "RegioStaR17":  [111, 113, 211],
            "RegioStaR7":   [71, 72, 74],
            "RegioStaR5":   [51, 51, 52],
            "RegioStaRGem7":[71, 72, 74],
            "RegioStaRGem5":[51, 51, 52],
        })

    def test_is_bbsr2022_format_true_for_bbsr_frame(self):
        from cleancensus.enrich import _is_bbsr2022_format
        df = self._make_bbsr2022_frame()
        assert _is_bbsr2022_format(df) is True

    def test_is_bbsr2022_format_false_for_bmdv_frame(self):
        from cleancensus.enrich import _is_bbsr2022_format
        df = self._make_bmdv2020_frame()
        assert _is_bbsr2022_format(df) is False

    def test_normalize_bbsr2022_commune_id_zero_padded(self):
        from cleancensus.enrich import _normalize_bbsr2022
        df = self._make_bbsr2022_frame()
        ref = _normalize_bbsr2022(df)
        assert ref["commune_id"].iloc[0] == "01001000"
        assert ref["commune_id"].iloc[1] == "01002000"

    def test_normalize_bbsr2022_regiostar2_correct(self):
        from cleancensus.enrich import _normalize_bbsr2022
        df = self._make_bbsr2022_frame()
        ref = _normalize_bbsr2022(df)
        assert list(ref["RegioStaR2"]) == [1.0, 1.0, 2.0]

    def test_normalize_bbsr2022_regiostar4_derived(self):
        """RegioStaR4 must equal RegioStaR17 // 10."""
        from cleancensus.enrich import _normalize_bbsr2022
        df = self._make_bbsr2022_frame()
        ref = _normalize_bbsr2022(df)
        # RSS2022 = [111, 113, 221] -> RS4 = [11, 11, 22]
        assert list(ref["RegioStaR4"]) == [11.0, 11.0, 22.0]

    def test_normalize_bbsr2022_regiostar17_correct(self):
        from cleancensus.enrich import _normalize_bbsr2022
        df = self._make_bbsr2022_frame()
        ref = _normalize_bbsr2022(df)
        assert list(ref["RegioStaR17"]) == [111.0, 113.0, 221.0]

    def test_normalize_bbsr2022_regiostar7_correct(self):
        from cleancensus.enrich import _normalize_bbsr2022
        df = self._make_bbsr2022_frame()
        ref = _normalize_bbsr2022(df)
        assert list(ref["RegioStaR7"]) == [71.0, 72.0, 75.0]

    def test_normalize_bbsr2022_reggem5_correct(self):
        from cleancensus.enrich import _normalize_bbsr2022
        df = self._make_bbsr2022_frame()
        ref = _normalize_bbsr2022(df)
        assert list(ref["RegioStaRGem5"]) == [51.0, 52.0, 53.0]

    def test_normalize_bbsr2022_regiostar5_is_nan(self):
        """RegioStaR5 (Stadtregion 5-type) is not in BBSR 2022 sheet -> must be NaN."""
        from cleancensus.enrich import _normalize_bbsr2022
        df = self._make_bbsr2022_frame()
        ref = _normalize_bbsr2022(df)
        assert ref["RegioStaR5"].isna().all(), "RegioStaR5 should be NaN for BBSR 2022 source"

    def test_normalize_bbsr2022_reggem7_is_nan(self):
        """RegioStaRGem7 is not in BBSR 2022 sheet -> must be NaN."""
        from cleancensus.enrich import _normalize_bbsr2022
        df = self._make_bbsr2022_frame()
        ref = _normalize_bbsr2022(df)
        assert ref["RegioStaRGem7"].isna().all(), "RegioStaRGem7 should be NaN for BBSR 2022 source"

    def test_normalize_bmdv2020_commune_id_zero_padded(self):
        from cleancensus.enrich import _normalize_bmdv2020
        df = self._make_bmdv2020_frame()
        ref = _normalize_bmdv2020(df)
        assert ref["commune_id"].iloc[0] == "01002000"

    def test_normalize_bmdv2020_all_regiostar_cols_present(self):
        """BMDV 2020 normalization must produce all 7 REGIOSTAR_COLS."""
        from cleancensus.enrich import _normalize_bmdv2020, REGIOSTAR_COLS
        df = self._make_bmdv2020_frame()
        ref = _normalize_bmdv2020(df)
        for col in REGIOSTAR_COLS:
            assert col in ref.columns, f"Missing column {col!r} in BMDV 2020 normalized ref"

    def test_normalize_bmdv2020_regiostar4_correct(self):
        from cleancensus.enrich import _normalize_bmdv2020
        df = self._make_bmdv2020_frame()
        ref = _normalize_bmdv2020(df)
        assert list(ref["RegioStaR4"]) == [11.0, 11.0, 21.0]

    def test_output_cols_seven_total(self):
        """Both normalizers must produce exactly 7 RegioStaR output columns."""
        from cleancensus.enrich import _normalize_bbsr2022, _normalize_bmdv2020, REGIOSTAR_COLS
        ref_bbsr = _normalize_bbsr2022(self._make_bbsr2022_frame())
        ref_bmdv = _normalize_bmdv2020(self._make_bmdv2020_frame())
        for ref in (ref_bbsr, ref_bmdv):
            missing = [c for c in REGIOSTAR_COLS if c not in ref.columns]
            assert not missing, f"Missing REGIOSTAR_COLS: {missing}"
