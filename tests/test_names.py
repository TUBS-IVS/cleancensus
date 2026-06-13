"""Unit tests for the file-name registry (cleancensus.names)."""
from __future__ import annotations

from cleancensus import names


def test_output_schema_unchanged():
    assert names.output(1, "e2e") == "zensus2022_grid_1km_de_e2e.parquet"
    assert names.output(100, "e2e") == "zensus2022_grid_100m_de_e2e.parquet"
    assert names.output("10km", "v3") == "zensus2022_grid_10km_de_v3.parquet"


def test_subset_output():
    assert names.output(100, "e2e", subset=True) == "zensus2022_grid_100m_de_e2e_subset.parquet"


def test_canonical_input_unchanged():
    assert names.canonical_input("10km") == "zensus2022_grid_10km_de_prepared.parquet"
    assert names.canonical_input(100) == "zensus2022_grid_100m_de_prepared.parquet"


def test_workfile_numbered_scheme():
    assert names.work("merge", "10km") == "01_merge_10km.parquet"
    assert names.work("totals", "1km") == "02_totals_1km.parquet"
    assert names.work("topics8", "100m") == "06_topics8_100m.parquet"


def test_legacy_aliases_for_regiostar_workfile():
    al = names.legacy_aliases(names.work("regiostar", "100m"))
    assert "cells_100m_with_gender_backf_binneds_happyorphans_with_aggs_regiostar.parquet" in al


def test_legacy_alias_for_merge():
    assert "merged_10km_gitter.parquet" in names.legacy_aliases(names.work("merge", "10km"))


def test_resolve_prefers_new_then_legacy(tmp_path):
    new = names.work("merge", "1km")
    # nothing exists -> returns path to write (new name)
    assert names.resolve(tmp_path, new).name == new
    # legacy exists -> returns it
    legacy = names.legacy_aliases(new)[0]
    (tmp_path / legacy).write_text("x")
    assert names.resolve(tmp_path, new).name == legacy
    # new exists -> wins over legacy
    (tmp_path / new).write_text("x")
    assert names.resolve(tmp_path, new).name == new


def test_unknown_level_raises():
    import pytest
    with pytest.raises(ValueError):
        names.canonical_input("5km")
