"""Unit tests for cleancensus.z22 (no network access required)."""
from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# GITTER_ID formula tests (hardcoded from verified real examples)
# ---------------------------------------------------------------------------

class TestGitterIdFormula:
    """Verified against T:\\petre\\UCFL\\...\\merged_*_gitter.csv."""

    def test_10km_known_cell(self):
        """x_mp=4335000, y_mp=2685000 -> CRS3035RES10000mN2680000E4330000."""
        from cleancensus.z22 import make_gitter_id
        assert make_gitter_id(4335000, 2685000, "10km") == "CRS3035RES10000mN2680000E4330000"

    def test_10km_second_known_cell(self):
        from cleancensus.z22 import make_gitter_id
        assert make_gitter_id(4345000, 2695000, "10km") == "CRS3035RES10000mN2690000E4340000"

    def test_1km_known_cell(self):
        """x_mp=4337500, y_mp=2689500 -> CRS3035RES1000mN2689000E4337000."""
        from cleancensus.z22 import make_gitter_id
        assert make_gitter_id(4337500, 2689500, "1km") == "CRS3035RES1000mN2689000E4337000"

    def test_100m_known_cell(self):
        """x_mp=4337050, y_mp=2689150 -> CRS3035RES100mN2689100E4337000."""
        from cleancensus.z22 import make_gitter_id
        assert make_gitter_id(4337050, 2689150, "100m") == "CRS3035RES100mN2689100E4337000"

    def test_10km_half_cell_is_5000(self):
        from cleancensus.z22 import make_gitter_id, _LEVEL_HALF
        assert _LEVEL_HALF["10km"] == 5000

    def test_1km_half_cell_is_500(self):
        from cleancensus.z22 import _LEVEL_HALF
        assert _LEVEL_HALF["1km"] == 500

    def test_100m_half_cell_is_50(self):
        from cleancensus.z22 import _LEVEL_HALF
        assert _LEVEL_HALF["100m"] == 50

    def test_res_strings(self):
        from cleancensus.z22 import _LEVEL_RES_STR
        assert _LEVEL_RES_STR["10km"] == "10000m"
        assert _LEVEL_RES_STR["1km"] == "1000m"
        assert _LEVEL_RES_STR["100m"] == "100m"


# ---------------------------------------------------------------------------
# FEATURE_MAP shape tests
# ---------------------------------------------------------------------------

class TestFeatureMapShape:
    def test_feature_map_imported(self):
        from cleancensus.z22 import FEATURE_MAP
        assert isinstance(FEATURE_MAP, dict)

    def test_all_keys_are_2_tuples_of_str_int(self):
        from cleancensus.z22 import FEATURE_MAP
        for key in FEATURE_MAP:
            assert isinstance(key, tuple) and len(key) == 2, f"Bad key: {key}"
            feat, cat = key
            assert isinstance(feat, str) and len(feat) > 0, f"Bad feature in key: {key}"
            assert isinstance(cat, int), f"Category code must be int, got {type(cat)} in key: {key}"

    def test_values_are_non_empty_strings(self):
        from cleancensus.z22 import FEATURE_MAP
        for key, val in FEATURE_MAP.items():
            assert isinstance(val, str) and len(val) > 0, f"Empty/non-string value for key {key}"

    def test_values_are_unique(self):
        from cleancensus.z22 import FEATURE_MAP
        values = list(FEATURE_MAP.values())
        duplicates = [v for v in values if values.count(v) > 1]
        assert not duplicates, f"Duplicate column base names in FEATURE_MAP: {set(duplicates)}"

    def test_no_level_suffix_in_values(self):
        """Values should NOT contain the level suffix (that is added at merge time)."""
        from cleancensus.z22 import FEATURE_MAP
        for key, val in FEATURE_MAP.items():
            for level in ("_10km-Gitter", "_1km-Gitter", "_100m-Gitter"):
                assert level not in val, f"Value for {key} contains level suffix: {val!r}"

    def test_minimum_size(self):
        from cleancensus.z22 import FEATURE_MAP
        # We know there are ~160 entries (verified during development)
        assert len(FEATURE_MAP) >= 100, f"FEATURE_MAP too small: {len(FEATURE_MAP)} entries"

    def test_population_key_present(self):
        from cleancensus.z22 import FEATURE_MAP
        assert ("population", 0) in FEATURE_MAP

    def test_marital_status_all_8_categories(self):
        from cleancensus.z22 import FEATURE_MAP
        for cat in range(1, 9):
            assert ("marital_status", cat) in FEATURE_MAP, f"marital_status_{cat} missing"

    def test_age_long_all_9_categories(self):
        from cleancensus.z22 import FEATURE_MAP
        for cat in range(1, 10):
            assert ("age_long", cat) in FEATURE_MAP, f"age_long_{cat} missing"

    def test_age_short_all_5_categories(self):
        from cleancensus.z22 import FEATURE_MAP
        for cat in range(1, 6):
            assert ("age_short", cat) in FEATURE_MAP, f"age_short_{cat} missing"


# ---------------------------------------------------------------------------
# Pipeline registry test
# ---------------------------------------------------------------------------

class TestMergeStageInRegistry:
    def test_merge_stage_present(self):
        from cleancensus.pipeline import REGISTRY
        names = [s.name for s in REGISTRY]
        assert "merge" in names

    def test_merge_stage_implemented(self):
        from cleancensus.pipeline import REGISTRY
        merge_stage = next(s for s in REGISTRY if s.name == "merge")
        assert merge_stage.implemented, "merge stage must be implemented=True"

    def test_merge_stage_has_run_callable(self):
        from cleancensus.pipeline import REGISTRY
        merge_stage = next(s for s in REGISTRY if s.name == "merge")
        assert callable(merge_stage.run), "merge stage must have a callable run"

    def test_merge_stage_has_is_complete_callable(self):
        from cleancensus.pipeline import REGISTRY
        merge_stage = next(s for s in REGISTRY if s.name == "merge")
        assert callable(merge_stage.is_complete), "merge stage must have callable is_complete"

    def test_merge_is_first_stage(self):
        from cleancensus.pipeline import REGISTRY, STAGE_NAMES
        assert STAGE_NAMES[0] == "merge"

    def test_merge_disabled_by_default(self, tmp_path):
        """merge should show skip-disabled in the dry-run plan when not enabled."""
        from cleancensus.config import Config
        from cleancensus.pipeline import plan

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
            stages={s: False for s in ("merge", "totals", "ages", "gemeinde", "gender",
                                        "topics8", "aggs", "regiostar", "extend")},
            config_path=tmp_path / "config.toml",
        )
        steps = plan(cfg)
        merge_step = next(s for s in steps if s["name"] == "merge")
        assert merge_step["action"] == "skip-disabled"


# ---------------------------------------------------------------------------
# Semantic direction of the building/dwelling Gebaeudetyp mapping
# ---------------------------------------------------------------------------

class TestGebaeudetypSemanticDirection:
    """Guard the SEMANTICALLY CORRECT (counter-intuitive) mapping direction.

    z22data's feature names are inverted relative to their literal meaning
    (established 2026-06-11 via the MFH_13+ discriminator, see z22.py docstring):
      z22 'building_size' cat 9 (MFH 13+) national 10km sum ~= 5,224,648 -> DWELLINGS
      z22 'dwelling_building_size' cat 9 national 10km sum  ~=   237,542 -> BUILDINGS
    Therefore 'building_size' MUST map to Wohnung_* and 'dwelling_building_size'
    to Geb_* columns. Do NOT "fix" this to match the literal z22 feature names.
    """

    def test_building_size_maps_to_wohnung_columns(self):
        from cleancensus.z22 import FEATURE_MAP
        targets = [v for (f, c), v in FEATURE_MAP.items()
                   if f == "building_size" and c > 0]
        assert targets, "building_size categories missing from FEATURE_MAP"
        assert all("_Wohnung_Gebaeudetyp_Groesse" in t for t in targets), targets

    def test_dwelling_building_size_maps_to_geb_columns(self):
        from cleancensus.z22 import FEATURE_MAP
        targets = [v for (f, c), v in FEATURE_MAP.items()
                   if f == "dwelling_building_size" and c > 0]
        assert targets, "dwelling_building_size categories missing from FEATURE_MAP"
        assert all("_Geb_Gebaeudetyp_Groesse" in t for t in targets), targets
