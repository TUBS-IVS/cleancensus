import pandas as pd
import pytest

from cleancensus.config import load_config
from cleancensus import stages


def _cfg(tmp_path, body=""):
    p = tmp_path / "config.toml"
    p.write_text(body, encoding="utf-8")
    return load_config(p)


def test_downscale_kw_matches_reference(tmp_path):
    assert stages.DOWNSCALE_KW == dict(inner_passes=10, outer_iters=2, rake_tol=1e-11,
                                       rake_max_iter=1000, validate_row_tol=2e-4, verbose=False)


def test_build_subset_parents_national_is_none(tmp_path):
    cfg = _cfg(tmp_path)
    assert stages.build_subset_parents(cfg) is None


def test_stage_a_aborts_on_no_specs(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    monkeypatch.setattr("cleancensus.stages.build_new_topic_specs", lambda *a, **k: [])
    with pytest.raises(SystemExit):
        stages.run_stage_a(cfg)
