import textwrap

from cleancensus.cli import main


def _write(tmp_path, body=""):
    p = tmp_path / "config.toml"
    p.write_text(textwrap.dedent(body), encoding="utf-8")
    return p


def test_dry_run_prints_plan_and_exits_zero(tmp_path, capsys):
    cfg = _write(tmp_path, """
        [harmonize]
        derived_tenure = true
    """)
    rc = main(["--config", str(cfg), "--dry-run"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "stage_a" in out and "stage_b" in out
    assert "tenure" in out
    assert "sanity" in out


def test_dry_run_without_tenure_omits_step(tmp_path, capsys):
    cfg = _write(tmp_path)
    rc = main(["--config", str(cfg), "--dry-run"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "tenure (owner/renter" not in out
