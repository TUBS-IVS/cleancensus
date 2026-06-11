"""Unit tests for cleancensus/vacancy.py.

Tests cover:
- Derivation arithmetic at 1km (clip, signal rule, occupied+vacant == anchor)
- Signal rule: quote==0 & dwellings>0 yields zeros (parent-share fill handled downstream)
- Config: derived_vacancy defaults to False
- Stage order: vacancy appears after tenure, before sanity in STAGE_NAMES
"""
import textwrap

import numpy as np
import pandas as pd
import pytest

from cleancensus.vacancy import (
    build_parent_vacancy,
    QUOTE_1,
    DWG_ADJ_1,
    OCC_1,
    VAC_1,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_df1(quotes, dwg_adj, g10=None):
    """Build a minimal 1km DataFrame for build_parent_vacancy."""
    n = len(quotes)
    return pd.DataFrame({
        "GITTER_ID_1km": [f"1kmN{i}E{i}" for i in range(n)],
        "GITTER_ID_10km": g10 if g10 is not None else ["10kmA"] * n,
        QUOTE_1: quotes,
        DWG_ADJ_1: dwg_adj,
    })


# ---------------------------------------------------------------------------
# Arithmetic tests
# ---------------------------------------------------------------------------

def test_basic_derivation():
    """quote=10 & dwg=100 -> vacant=10, occupied=90."""
    df = _make_df1(quotes=[10.0], dwg_adj=[100.0])
    result = build_parent_vacancy(df)
    assert float(result[VAC_1].iloc[0]) == pytest.approx(10.0, abs=0.01)
    assert float(result[OCC_1].iloc[0]) == pytest.approx(90.0, abs=0.01)


def test_sum_equals_anchor():
    """occupied + vacant == DWG_adj for all rows."""
    quotes = [0.0, 5.0, 10.0, 50.0, 0.0]
    dwg = [0.0, 200.0, 100.0, 50.0, 300.0]
    df = _make_df1(quotes=quotes, dwg_adj=dwg)
    result = build_parent_vacancy(df)
    total = result[OCC_1] + result[VAC_1]
    adj = pd.to_numeric(result[DWG_ADJ_1], errors="coerce").fillna(0.0)
    np.testing.assert_allclose(total.values, adj.values, atol=0.1)


def test_quote_clipped_above_100():
    """quote > 100 is clipped to 100; vacant <= dwg always."""
    df = _make_df1(quotes=[150.0], dwg_adj=[100.0])
    result = build_parent_vacancy(df)
    assert float(result[VAC_1].iloc[0]) <= float(result[DWG_ADJ_1].iloc[0]) + 0.01
    assert float(result[OCC_1].iloc[0]) >= -0.01


def test_zero_dwellings_yields_zero():
    """quote=5 & dwg=0 -> both occupied and vacant are 0."""
    df = _make_df1(quotes=[5.0], dwg_adj=[0.0])
    result = build_parent_vacancy(df)
    assert float(result[VAC_1].iloc[0]) == pytest.approx(0.0, abs=0.01)
    assert float(result[OCC_1].iloc[0]) == pytest.approx(0.0, abs=0.01)


def test_signal_rule_zero_quote_with_dwellings():
    """quote==0 & dwg>0 -> no local signal; group-mean fill is applied.
    With a single 10km group, the fill uses the group mean of the signal cells."""
    # Cell 0: has signal (quote=10, dwg=100)
    # Cell 1: no signal (quote=0, dwg=50) -> gets group mean fill
    df = _make_df1(
        quotes=[10.0, 0.0],
        dwg_adj=[100.0, 50.0],
        g10=["10kmA", "10kmA"],
    )
    result = build_parent_vacancy(df)
    # Group mean = 10.0 (only cell 0 has signal)
    # Cell 1: vacant = 10.0/100 * 50 = 5.0
    assert float(result[VAC_1].iloc[1]) == pytest.approx(5.0, abs=0.1)
    assert float(result[OCC_1].iloc[1]) == pytest.approx(45.0, abs=0.1)


def test_no_negatives():
    """Occupied (dwg - vacant) is always clipped to >= 0."""
    # Even if due to float error the subtraction would go negative, clip guards it.
    quotes = [100.0, 99.9, 0.1, 50.0]
    dwg = [100.0, 100.0, 100.0, 0.0]
    df = _make_df1(quotes=quotes, dwg_adj=dwg)
    result = build_parent_vacancy(df)
    assert float(result[OCC_1].min()) >= -0.01


def test_output_dtype_float32():
    """Output columns are float32."""
    df = _make_df1(quotes=[4.3], dwg_adj=[1000.0])
    result = build_parent_vacancy(df)
    assert result[VAC_1].dtype == np.float32
    assert result[OCC_1].dtype == np.float32


# ---------------------------------------------------------------------------
# Config wiring
# ---------------------------------------------------------------------------

def test_derived_vacancy_default_false(tmp_path):
    """derived_vacancy defaults to False when not set in config."""
    p = tmp_path / "config.toml"
    p.write_text("", encoding="utf-8")
    from cleancensus.config import load_config
    cfg = load_config(p)
    assert cfg.derived_vacancy is False


def test_derived_vacancy_can_be_enabled(tmp_path):
    """derived_vacancy=true in [harmonize] is parsed correctly."""
    p = tmp_path / "config.toml"
    p.write_text(textwrap.dedent("""
        [harmonize]
        derived_vacancy = true
    """), encoding="utf-8")
    from cleancensus.config import load_config
    cfg = load_config(p)
    assert cfg.derived_vacancy is True


# ---------------------------------------------------------------------------
# Stage order
# ---------------------------------------------------------------------------

def test_stage_order_vacancy_after_tenure_before_sanity():
    from cleancensus.pipeline import STAGE_NAMES
    names = list(STAGE_NAMES)
    assert "vacancy" in names
    assert names.index("vacancy") > names.index("tenure")
    assert names.index("vacancy") < names.index("sanity")


def test_registry_includes_vacancy():
    from cleancensus.pipeline import STAGE_NAMES
    assert STAGE_NAMES == (
        "merge", "totals", "ages", "gemeinde", "gender", "topics8",
        "aggs", "regiostar", "extend", "tenure", "vacancy", "sanity",
    )
