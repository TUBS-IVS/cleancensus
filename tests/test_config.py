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
