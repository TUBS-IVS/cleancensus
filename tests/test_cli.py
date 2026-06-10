import textwrap

import pytest

from cleancensus.cli import main


def _write(tmp_path, body=""):
    p = tmp_path / "config.toml"
    p.write_text(textwrap.dedent(body), encoding="utf-8")
    return p


def test_dry_run_lists_all_stages_and_exits_zero(tmp_path, capsys):
    cfg = _write(tmp_path, """
        [harmonize]
        derived_tenure = true
    """)
    rc = main(["--config", str(cfg), "--dry-run"])
    out = capsys.readouterr().out
    assert rc == 0
    # all 11 stages appear in the plan
    for name in ("merge", "totals", "ages", "gemeinde", "gender", "topics8",
                 "aggs", "regiostar", "extend", "tenure", "sanity"):
        assert name in out
    # extend always enabled by default; tenure enabled here -> a run/skip action, not disabled
    assert "extend" in out


def test_dry_run_tenure_disabled_shows_skip(tmp_path, capsys):
    cfg = _write(tmp_path)  # derived_tenure defaults False
    rc = main(["--config", str(cfg), "--dry-run"])
    out = capsys.readouterr().out
    assert rc == 0
    # tenure plan row (has an action bracket) present but marked skip-disabled
    tenure_line = next(ln for ln in out.splitlines() if "tenure" in ln and "[" in ln)
    assert "skip-disabled" in tenure_line


def test_unknown_from_stage_errors(tmp_path):
    cfg = _write(tmp_path)
    with pytest.raises(ValueError, match="unknown stage"):
        main(["--config", str(cfg), "--dry-run", "--from", "nope"])
