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
    assert cfg.out_1.name == "zensus2022_grid_1km_de_v2.parquet"


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


# ---------------------------------------------------------------------------
# Stage-gated input resolution tests (resolved_path_10 / _1 / _100)
# ---------------------------------------------------------------------------

def _write_with_stages(tmp_path, stages_toml: str = "") -> object:
    """Helper: write config and create work_dir with dummy parquet artifacts."""
    body = stages_toml
    return _write(tmp_path, body)


# --- resolved_path_10 ---

def test_resolved_path_10_fallback(tmp_path):
    """Stage 'ages' disabled (default) -> resolved_path_10 returns inputs_dir pickle."""
    cfg = load_config(_write(tmp_path, ""))
    # stage 'ages' is off by default
    assert not cfg.stages["ages"]
    assert cfg.resolved_path_10 == cfg.path_10
    assert cfg.resolved_path_10.suffix == ".pickle"


def test_resolved_path_10_prefers_work_when_stage_enabled(tmp_path):
    """Stage 'ages' enabled + work_dir artifact present -> resolved_path_10 returns work_dir path."""
    # Create the work_dir artifact (touch a dummy file)
    cfg = load_config(_write(tmp_path, """
        [stages]
        ages = true
    """))
    work_artifact = cfg.work_dir / "df10_with_single_years.parquet"
    work_artifact.parent.mkdir(parents=True, exist_ok=True)
    work_artifact.touch()
    assert cfg.stages["ages"]
    assert cfg.resolved_path_10 == work_artifact
    assert cfg.resolved_path_10.suffix == ".parquet"


def test_resolved_path_10_ignores_work_when_stage_disabled(tmp_path):
    """KEY safety test: work_dir artifact exists but stage 'ages' is off -> inputs_dir path returned."""
    cfg = load_config(_write(tmp_path, ""))
    # Create the work artifact — must NOT be picked up when stage is disabled
    work_artifact = cfg.work_dir / "df10_with_single_years.parquet"
    work_artifact.parent.mkdir(parents=True, exist_ok=True)
    work_artifact.touch()
    assert not cfg.stages["ages"]
    assert cfg.resolved_path_10 == cfg.path_10  # falls back to inputs_dir pickle


# --- resolved_path_1 ---

def test_resolved_path_1_fallback(tmp_path):
    """Stage 'topics8' disabled (default) -> resolved_path_1 returns inputs_dir parquet."""
    cfg = load_config(_write(tmp_path, ""))
    assert not cfg.stages["topics8"]
    assert cfg.resolved_path_1 == cfg.path_1
    assert "cells_1km_with_binneds" in cfg.resolved_path_1.name


def test_resolved_path_1_prefers_work_when_stage_enabled(tmp_path):
    """Stage 'topics8' enabled -> resolved_path_1 returns work_dir path."""
    cfg = load_config(_write(tmp_path, """
        [stages]
        topics8 = true
    """))
    work_artifact = cfg.work_dir / "cells_1km_with_binneds.parquet"
    work_artifact.parent.mkdir(parents=True, exist_ok=True)
    work_artifact.touch()
    assert cfg.stages["topics8"]
    assert cfg.resolved_path_1 == work_artifact


def test_resolved_path_1_ignores_work_when_stage_disabled(tmp_path):
    """KEY safety test: work_dir artifact exists but stage 'topics8' is off -> inputs_dir path returned."""
    cfg = load_config(_write(tmp_path, ""))
    work_artifact = cfg.work_dir / "cells_1km_with_binneds.parquet"
    work_artifact.parent.mkdir(parents=True, exist_ok=True)
    work_artifact.touch()
    assert not cfg.stages["topics8"]
    assert cfg.resolved_path_1 == cfg.path_1


# --- resolved_path_100 ---

def test_resolved_path_100_fallback(tmp_path):
    """Stage 'regiostar' disabled (default) -> resolved_path_100 returns inputs_dir parquet."""
    cfg = load_config(_write(tmp_path, ""))
    assert not cfg.stages["regiostar"]
    assert cfg.resolved_path_100 == cfg.path_100
    assert "regiostar" in cfg.resolved_path_100.name


def test_resolved_path_100_prefers_work_when_stage_enabled(tmp_path):
    """Stage 'regiostar' enabled -> resolved_path_100 returns work_dir path."""
    cfg = load_config(_write(tmp_path, """
        [stages]
        regiostar = true
    """))
    work_artifact = (
        cfg.work_dir
        / "cells_100m_with_gender_backf_binneds_happyorphans_with_aggs_regiostar.parquet"
    )
    work_artifact.parent.mkdir(parents=True, exist_ok=True)
    work_artifact.touch()
    assert cfg.stages["regiostar"]
    assert cfg.resolved_path_100 == work_artifact


def test_resolved_path_100_ignores_work_when_stage_disabled(tmp_path):
    """KEY safety test: work_dir artifact exists but stage 'regiostar' is off -> inputs_dir path returned."""
    cfg = load_config(_write(tmp_path, ""))
    work_artifact = (
        cfg.work_dir
        / "cells_100m_with_gender_backf_binneds_happyorphans_with_aggs_regiostar.parquet"
    )
    work_artifact.parent.mkdir(parents=True, exist_ok=True)
    work_artifact.touch()
    assert not cfg.stages["regiostar"]
    assert cfg.resolved_path_100 == cfg.path_100
