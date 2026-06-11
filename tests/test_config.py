import textwrap

import pytest

from cleancensus.config import load_config


def _write(tmp_path, body):
    p = tmp_path / "config.toml"
    p.write_text(textwrap.dedent(body), encoding="utf-8")
    return p


def test_defaults(tmp_path):
    cfg = load_config(_write(tmp_path, ""))
    assert cfg.topics == ["Whg_Gebaeudetyp", "HH_Seniorenstatus"]
    assert cfg.mode == "national"
    assert cfg.sanity == "fail"
    assert cfg.derived_tenure is False
    assert cfg.derived_vacancy is False
    assert cfg.version_tag == "v2"
    assert cfg.out_1.name == "cells_1km_with_binneds_v2.parquet"


def test_topics_all_expands_catalog(tmp_path):
    cfg = load_config(_write(tmp_path, """
        [harmonize]
        topics = "all"
    """))
    assert len(cfg.topics) == 14


def test_tiers_selector(tmp_path):
    cfg = load_config(_write(tmp_path, """
        [harmonize]
        tiers = [2]
    """))
    assert cfg.topics == ["HH_Seniorenstatus", "HH_Familientyp", "Pers_Staatsangehoerigkeit"]


def test_topics_and_tiers_conflict(tmp_path):
    with pytest.raises(ValueError, match="not both"):
        load_config(_write(tmp_path, """
            [harmonize]
            topics = ["HH_Seniorenstatus"]
            tiers = [1]
        """))


def test_unknown_topic_raises(tmp_path):
    with pytest.raises(ValueError, match="Unknown topic names"):
        load_config(_write(tmp_path, """
            [harmonize]
            topics = ["Nope"]
        """))


def test_subset_requires_prefixes(tmp_path):
    with pytest.raises(ValueError, match="requires non-empty ars_prefixes"):
        load_config(_write(tmp_path, """
            [scope]
            mode = "subset"
        """))


def test_national_rejects_prefixes(tmp_path):
    with pytest.raises(ValueError, match="only allowed with"):
        load_config(_write(tmp_path, """
            [scope]
            ars_prefixes = ["03101"]
        """))


def test_bad_sanity_mode(tmp_path):
    with pytest.raises(ValueError, match="sanity"):
        load_config(_write(tmp_path, """
            [run]
            sanity = "maybe"
        """))


# ---------------------------------------------------------------------------
# RegioStaR config wiring tests
# ---------------------------------------------------------------------------

def test_regiostar_ref_defaults_to_none(tmp_path):
    """regiostar_ref defaults to None (enrich.py auto-discovers the BBSR 2022 file)."""
    cfg = load_config(_write(tmp_path, ""))
    assert cfg.regiostar_ref is None


def test_regiostar_sheet_defaults_to_empty(tmp_path):
    """regiostar_sheet defaults to empty string (triggers auto-detect in enrich.py)."""
    cfg = load_config(_write(tmp_path, ""))
    assert cfg.regiostar_sheet == ""


def test_regiostar_ref_toml_override(tmp_path):
    """[data].regiostar_ref in TOML is resolved relative to the config file."""
    cfg = load_config(_write(tmp_path, """
        [data]
        regiostar_ref = "data/raw/regiostar/bbsr-referenz-gebietsstand-2022.xlsx"
    """))
    assert cfg.regiostar_ref is not None
    # Should be an absolute path resolved from tmp_path
    assert cfg.regiostar_ref.is_absolute()
    assert cfg.regiostar_ref.name == "bbsr-referenz-gebietsstand-2022.xlsx"


def test_regiostar_sheet_toml_override(tmp_path):
    """[data].regiostar_sheet in TOML is passed through as-is."""
    cfg = load_config(_write(tmp_path, """
        [data]
        regiostar_sheet = "Gemeindereferenz (inkl. Kreise)"
    """))
    assert cfg.regiostar_sheet == "Gemeindereferenz (inkl. Kreise)"
