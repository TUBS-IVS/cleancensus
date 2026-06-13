import textwrap

import pytest

from cleancensus.cli import main


def _write(tmp_path, body=""):
    p = tmp_path / "config.toml"
    p.write_text(textwrap.dedent(body), encoding="utf-8")
    return p


def test_dry_run_lists_all_stages_and_exits_zero(tmp_path):
    from cleancensus.config import load_config
    from cleancensus.pipeline import plan

    cfg_path = _write(tmp_path, """
        [harmonize]
        derived_tenure = true
    """)
    # CLI dry-run exits cleanly...
    assert main(["--config", str(cfg_path), "--dry-run"]) == 0
    # ...and the plan lists every stage.
    names = {s["name"] for s in plan(load_config(str(cfg_path)))}
    for name in ("merge", "totals", "ages", "gemeinde", "gender", "topics8",
                 "aggs", "regiostar", "extend", "tenure", "sanity"):
        assert name in names


def test_dry_run_tenure_disabled_shows_skip(tmp_path):
    from cleancensus.config import load_config
    from cleancensus.pipeline import plan

    cfg_path = _write(tmp_path)  # derived_tenure defaults False
    assert main(["--config", str(cfg_path), "--dry-run"]) == 0
    steps = {s["name"]: s["action"] for s in plan(load_config(str(cfg_path)))}
    assert steps["tenure"] == "skip-disabled"


def test_unknown_from_stage_errors(tmp_path):
    cfg = _write(tmp_path)
    with pytest.raises(ValueError, match="unknown stage"):
        main(["--config", str(cfg), "--dry-run", "--from", "nope"])
