"""Unit tests for ingest_totals and ages_stage.

No heavy I/O — all tests use tiny synthetic frames or hard-coded examples.
"""
from __future__ import annotations

import textwrap

import numpy as np
import pandas as pd
import pytest

# ---------------------------------------------------------------------------
# ingest_totals
# ---------------------------------------------------------------------------


class TestParentGitterId:
    """Regression tests for parent_gitter_id (faithfully ported from cell [2])."""

    def test_1km_to_10km(self):
        from cleancensus.ingest_totals import parent_gitter_id

        result = parent_gitter_id("CRS3035RES1000mN2689000E4337000", 10_000)
        assert result == "CRS3035RES10000mN2680000E4330000"

    def test_100m_to_1km(self):
        from cleancensus.ingest_totals import parent_gitter_id

        result = parent_gitter_id("CRS3035RES100mN2689400E4337600", 1_000)
        assert result == "CRS3035RES1000mN2689000E4337000"

    def test_100m_to_10km(self):
        from cleancensus.ingest_totals import parent_gitter_id

        result = parent_gitter_id("CRS3035RES100mN2689400E4337600", 10_000)
        assert result == "CRS3035RES10000mN2680000E4330000"

    def test_non_string_returns_none(self):
        from cleancensus.ingest_totals import parent_gitter_id

        assert parent_gitter_id(None, 1000) is None
        assert parent_gitter_id(42, 1000) is None

    def test_malformed_id_returns_none(self):
        from cleancensus.ingest_totals import parent_gitter_id

        assert parent_gitter_id("NOT_A_VALID_ID", 1000) is None

    def test_floor_not_round(self):
        """N=2689999 -> floor to nearest 10000 = 2680000, not 2690000."""
        from cleancensus.ingest_totals import parent_gitter_id

        result = parent_gitter_id("CRS3035RES1000mN2689999E4339999", 10_000)
        assert result == "CRS3035RES10000mN2680000E4330000"


class TestAddParentIds:
    def test_1km_adds_10km_column(self):
        from cleancensus.ingest_totals import add_parent_ids_for_level

        df = pd.DataFrame(
            {"GITTER_ID_1km": ["CRS3035RES1000mN2689000E4337000"]}
        )
        out = add_parent_ids_for_level(df, "1km")
        assert "GITTER_ID_10km" in out.columns
        assert out["GITTER_ID_10km"].iloc[0] == "CRS3035RES10000mN2680000E4330000"

    def test_100m_adds_both_parent_columns(self):
        from cleancensus.ingest_totals import add_parent_ids_for_level

        df = pd.DataFrame(
            {"GITTER_ID_100m": ["CRS3035RES100mN2689400E4337600"]}
        )
        out = add_parent_ids_for_level(df, "100m")
        assert "GITTER_ID_1km" in out.columns
        assert "GITTER_ID_10km" in out.columns
        assert out["GITTER_ID_1km"].iloc[0] == "CRS3035RES1000mN2689000E4337000"
        assert out["GITTER_ID_10km"].iloc[0] == "CRS3035RES10000mN2680000E4330000"

    def test_existing_parent_column_not_overwritten(self):
        """If GITTER_ID_10km already exists, add_parent_ids leaves it alone."""
        from cleancensus.ingest_totals import add_parent_ids_for_level

        df = pd.DataFrame(
            {
                "GITTER_ID_1km": ["CRS3035RES1000mN2689000E4337000"],
                "GITTER_ID_10km": ["EXISTING"],
            }
        )
        out = add_parent_ids_for_level(df, "1km")
        assert out["GITTER_ID_10km"].iloc[0] == "EXISTING"


class TestCollapsePopulationTotals:
    """Toy tests for the consensus collapse logic."""

    def _make_df(self, rows):
        """rows: list of dicts with Einwohner_... or Insgesamt_... keys."""
        return pd.DataFrame(rows)

    def test_unanimous_one_column(self):
        from cleancensus.ingest_totals import collapse_population_totals

        df = self._make_df([
            {"Einwohner_Bevoelkerungszahl_10km-Gitter": 100},
            {"Einwohner_Bevoelkerungszahl_10km-Gitter": 200},
        ])
        df_out, pop_col = collapse_population_totals(df, "10km", verbose=False)
        assert pop_col == "POP_TOTAL_10km"
        assert list(df_out[pop_col]) == [100.0, 200.0]

    def test_unanimous_two_matching_columns(self):
        from cleancensus.ingest_totals import collapse_population_totals

        df = self._make_df([
            {
                "Einwohner_Bevoelkerungszahl_10km-Gitter": 100,
                "Insgesamt_Bevoelkerung_Alter_INFR_10km-Gitter": 100,
            },
        ])
        df_out, pop_col = collapse_population_totals(df, "10km", verbose=False)
        assert df_out[pop_col].iloc[0] == pytest.approx(100.0)

    def test_majority_wins_conflict(self):
        """Two columns agree at 300; one disagrees at 500 -> 300 wins."""
        from cleancensus.ingest_totals import collapse_population_totals

        df = self._make_df([
            {
                "Einwohner_Bevoelkerungszahl_10km-Gitter": 300,
                "Insgesamt_Bevoelkerung_Alter_INFR_10km-Gitter": 300,
                "Insgesamt_Bevoelkerung_Alter_in_10er-Jahresgruppen_10km-Gitter": 500,
            },
        ])
        df_out, _ = collapse_population_totals(df, "10km", verbose=False)
        assert df_out["POP_TOTAL_10km"].iloc[0] == pytest.approx(300.0)

    def test_no_pop_col_raises(self):
        from cleancensus.ingest_totals import collapse_population_totals

        df = pd.DataFrame({"OTHER_COL": [1, 2]})
        with pytest.raises(ValueError, match="No population total columns"):
            collapse_population_totals(df, "10km", verbose=False)

    def test_all_nan_row_gives_nan(self):
        from cleancensus.ingest_totals import collapse_population_totals

        df = self._make_df([
            {"Einwohner_Bevoelkerungszahl_10km-Gitter": float("nan")},
        ])
        df_out, pop_col = collapse_population_totals(df, "10km", verbose=False)
        assert np.isnan(df_out[pop_col].iloc[0])


class TestProportionalAdjust:
    def test_simple_two_child_adjust(self):
        """One parent (total=100) with two children each contributing 40 ->
        scale = 100 / 80 = 1.25, children become 50."""
        from cleancensus.ingest_totals import proportional_adjust_to_parent

        parent = pd.DataFrame({
            "GITTER_ID_10km": ["CRS3035RES10000mN2680000E4330000"],
            "POP_TOTAL_10km": [100.0],
        })
        child = pd.DataFrame({
            "GITTER_ID_1km": [
                "CRS3035RES1000mN2689000E4337000",
                "CRS3035RES1000mN2689000E4338000",
            ],
            "GITTER_ID_10km": [
                "CRS3035RES10000mN2680000E4330000",
                "CRS3035RES10000mN2680000E4330000",
            ],
            "POP_TOTAL_1km": [40.0, 40.0],
        })
        out = proportional_adjust_to_parent(
            child, parent, "1km", "10km", "POP_TOTAL_1km", "POP_TOTAL_10km"
        )
        assert out["POP_TOTAL_1km"].sum() == pytest.approx(100.0, rel=1e-9)
        assert list(out["POP_TOTAL_1km"]) == pytest.approx([50.0, 50.0], rel=1e-9)

    def test_zero_child_sum_produces_nan(self):
        """If child sum is 0 and parent total > 0, the result is NaN (0 * inf).
        This is the faithful port of cell [4] behaviour — the notebook does not
        special-case this; callers must handle NaN downstream."""
        from cleancensus.ingest_totals import proportional_adjust_to_parent

        parent = pd.DataFrame({
            "GITTER_ID_10km": ["CRS3035RES10000mN2680000E4330000"],
            "POP_TOTAL_10km": [100.0],
        })
        child = pd.DataFrame({
            "GITTER_ID_1km": ["CRS3035RES1000mN2689000E4337000"],
            "GITTER_ID_10km": ["CRS3035RES10000mN2680000E4330000"],
            "POP_TOTAL_1km": [0.0],
        })
        out = proportional_adjust_to_parent(
            child, parent, "1km", "10km", "POP_TOTAL_1km", "POP_TOTAL_10km"
        )
        # 0 * (100/0) = 0 * inf = NaN (faithful port — no special-casing)
        assert np.isnan(out["POP_TOTAL_1km"].iloc[0])


# ---------------------------------------------------------------------------
# ages_stage
# ---------------------------------------------------------------------------


class TestAgesUtilities:
    def test_age_cols(self):
        from cleancensus.ages_stage import age_cols

        c = age_cols(100)
        assert len(c) == 101
        assert c[0] == "AGE_0"
        assert c[100] == "AGE_100"

    def test_age_idx_clamps_hi(self):
        from cleancensus.ages_stage import _age_idx

        idx = _age_idx(75, 200, 100)  # hi clamped to 100
        assert idx[-1] == 100
        assert len(idx) == 26  # 75..100 inclusive

    def test_bin_specs_make_infr(self):
        from cleancensus.ages_stage import make_infr_bins

        spec = make_infr_bins("1km")
        assert "Unter3_Alter_INFR_1km-Gitter" in spec.cols_to_ranges
        lo, hi = spec.cols_to_ranges["Unter3_Alter_INFR_1km-Gitter"]
        assert lo == 0 and hi == 2

    def test_bin_specs_make_tenyear(self):
        from cleancensus.ages_stage import make_tenyear_bins

        spec = make_tenyear_bins("100m")
        assert "Unter10_Alter_in_10er-Jahresgruppen_100m-Gitter" in spec.cols_to_ranges
        lo, hi = spec.cols_to_ranges["Unter10_Alter_in_10er-Jahresgruppen_100m-Gitter"]
        assert lo == 0 and hi == 9

    def test_bin_specs_make_fiveclass(self):
        from cleancensus.ages_stage import make_fiveclass_bins

        spec = make_fiveclass_bins("10km")
        assert "Unter18_Alter_in_5_Altersklassen_10km-Gitter" in spec.cols_to_ranges


class TestFinalRake:
    def test_already_satisfied(self):
        from cleancensus.ages_stage import _final_rake_to_margins

        X = np.array([[10.0, 20.0], [30.0, 40.0]])
        row_t = np.array([30.0, 70.0])
        col_t = np.array([40.0, 60.0])
        _final_rake_to_margins(X, row_t, col_t)
        assert np.allclose(X.sum(axis=0), col_t, atol=1e-9)
        assert np.allclose(X.sum(axis=1), row_t, atol=1e-9)

    def test_single_cell(self):
        from cleancensus.ages_stage import _final_rake_to_margins

        X = np.array([[5.0]])
        _final_rake_to_margins(X, np.array([10.0]), np.array([10.0]))
        assert X[0, 0] == pytest.approx(10.0)

    def test_convergence_2x2(self):
        from cleancensus.ages_stage import _final_rake_to_margins

        X = np.array([[1.0, 2.0], [3.0, 4.0]])
        row_t = np.array([100.0, 200.0])
        col_t = np.array([120.0, 180.0])
        _final_rake_to_margins(X, row_t, col_t, tol=1e-10, max_iter=200)
        assert np.allclose(X.sum(axis=0), col_t, atol=1e-6)
        assert np.allclose(X.sum(axis=1), row_t, atol=1e-6)


class TestMakeChildTotalsAdj:
    def test_basic_adjustment(self):
        from cleancensus.ages_stage import make_child_totals_adj

        parent = pd.DataFrame({
            "GITTER_ID_10km": ["P1"],
            "POP_TOTAL_10km_adj": [200.0],
        })
        child = pd.DataFrame({
            "GITTER_ID_10km": ["P1", "P1"],
            "POP_TOTAL_1km": [60.0, 40.0],
        })
        out = make_child_totals_adj(
            parent, child,
            parent_id_col="GITTER_ID_10km",
            child_parent_id_col="GITTER_ID_10km",
            parent_adj_col="POP_TOTAL_10km_adj",
            child_pop_col="POP_TOTAL_1km",
        )
        assert out["POP_TOTAL_1km_adj"].sum() == pytest.approx(200.0, rel=1e-9)
        # children should be scaled by 200/100 = 2
        assert list(out["POP_TOTAL_1km_adj"]) == pytest.approx([120.0, 80.0], rel=1e-9)

    def test_degenerate_zero_child_sum(self):
        """When all children have zero, split equally."""
        from cleancensus.ages_stage import make_child_totals_adj

        parent = pd.DataFrame({
            "GITTER_ID_10km": ["P1"],
            "POP_TOTAL_10km_adj": [100.0],
        })
        child = pd.DataFrame({
            "GITTER_ID_10km": ["P1", "P1"],
            "POP_TOTAL_1km": [0.0, 0.0],
        })
        out = make_child_totals_adj(
            parent, child,
            parent_id_col="GITTER_ID_10km",
            child_parent_id_col="GITTER_ID_10km",
            parent_adj_col="POP_TOTAL_10km_adj",
            child_pop_col="POP_TOTAL_1km",
        )
        # each child gets 50
        assert list(out["POP_TOTAL_1km_adj"]) == pytest.approx([50.0, 50.0], rel=1e-9)


class TestLoadNationalSingleYears:
    def test_basic_parse(self, tmp_path):
        from cleancensus.ages_stage import load_national_single_years

        csv_content = "Alter;Zahl\n0 Jahre;1000\n1 Jahre;900\n100 Jahre;500\n"
        p = tmp_path / "nat.csv"
        p.write_text(csv_content, encoding="utf-8")
        nat = load_national_single_years(p)
        assert nat.index[0] == 0
        assert nat.index[-1] == 100
        assert nat[0] == 1000.0
        assert nat[1] == 900.0
        assert nat[100] == 500.0

    def test_missing_ages_filled_with_zero(self, tmp_path):
        from cleancensus.ages_stage import load_national_single_years

        csv_content = "Alter;Zahl\n0 Jahre;100\n50 Jahre;200\n100 Jahre;50\n"
        p = tmp_path / "nat.csv"
        p.write_text(csv_content, encoding="utf-8")
        nat = load_national_single_years(p)
        assert nat[1] == 0.0
        assert nat[49] == 0.0

    def test_zero_total_raises(self, tmp_path):
        from cleancensus.ages_stage import load_national_single_years

        p = tmp_path / "nat.csv"
        p.write_text("Alter;Zahl\n0 Jahre;0\n", encoding="utf-8")
        with pytest.raises(ValueError, match="National total is zero"):
            load_national_single_years(p)


class TestFitSingleYears10km:
    """Micro-test of fit_single_years_10km on a 2-cell toy."""

    def _nat(self) -> pd.Series:
        """Uniform national vector 0..100."""
        return pd.Series(np.ones(101), index=range(101))

    def _df(self):
        df = pd.DataFrame(
            {
                "POP_TOTAL_10km": [100.0, 200.0],
            }
        )
        return df

    def test_output_shape(self):
        from cleancensus.ages_stage import fit_single_years_10km

        df = self._df()
        ages, totals = fit_single_years_10km(df, self._nat(), outer_iters=2, inner_passes=5, verbose=False)
        assert ages.shape == (2, 101)
        assert len(totals) == 2

    def test_national_margin_is_met(self):
        from cleancensus.ages_stage import fit_single_years_10km

        df = self._df()
        nat = self._nat()
        ages, totals = fit_single_years_10km(df, nat, outer_iters=5, inner_passes=10, verbose=False)
        nat_arr = nat.values
        col_sums = ages.sum(axis=0).values
        assert np.allclose(col_sums, nat_arr, atol=1e-6)

    def test_cell_totals_match_scaled(self):
        """Cell totals should match the scaled totals (sum to national total)."""
        from cleancensus.ages_stage import fit_single_years_10km

        df = self._df()
        nat = self._nat()
        ages, totals = fit_single_years_10km(df, nat, outer_iters=5, inner_passes=10, verbose=False)
        # Row sums should match 'totals'
        assert np.allclose(ages.sum(axis=1).values, totals, atol=1e-4)


# ---------------------------------------------------------------------------
# Registry / integration tests
# ---------------------------------------------------------------------------


class TestRegistryImplemented:
    def test_totals_implemented(self):
        from cleancensus.pipeline import REGISTRY

        by_name = {s.name: s for s in REGISTRY}
        assert by_name["totals"].implemented is True

    def test_ages_implemented(self):
        from cleancensus.pipeline import REGISTRY

        by_name = {s.name: s for s in REGISTRY}
        assert by_name["ages"].implemented is True

    def test_gemeinde_implemented(self):
        from cleancensus.pipeline import REGISTRY

        by_name = {s.name: s for s in REGISTRY}
        assert by_name["gemeinde"].implemented is True

    def test_gender_implemented(self):
        from cleancensus.pipeline import REGISTRY

        by_name = {s.name: s for s in REGISTRY}
        assert by_name["gender"].implemented is True


class TestPlanWithTotalsAges:
    def _cfg(self, tmp_path, body=""):
        from cleancensus.config import load_config

        p = tmp_path / "config.toml"
        p.write_text(textwrap.dedent(body), encoding="utf-8")
        return load_config(p)

    def test_totals_enabled_shows_run(self, tmp_path):
        from cleancensus.pipeline import plan

        cfg = self._cfg(tmp_path, """
            [stages]
            totals = true
            extend = false
        """)
        actions = {s["name"]: s["action"] for s in plan(cfg)}
        # work_dir is empty -> not complete -> should be "run"
        assert actions["totals"] == "run"

    def test_ages_enabled_shows_run(self, tmp_path):
        from cleancensus.pipeline import plan

        cfg = self._cfg(tmp_path, """
            [stages]
            ages = true
            extend = false
        """)
        actions = {s["name"]: s["action"] for s in plan(cfg)}
        assert actions["ages"] == "run"

    def test_totals_and_ages_default_skip_disabled(self, tmp_path):
        from cleancensus.pipeline import plan

        cfg = self._cfg(tmp_path, "")
        actions = {s["name"]: s["action"] for s in plan(cfg)}
        assert actions["totals"] == "skip-disabled"
        assert actions["ages"] == "skip-disabled"
