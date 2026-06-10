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
