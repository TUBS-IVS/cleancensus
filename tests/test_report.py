"""Unit tests for the CLI presentation layer (cleancensus.report)."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from cleancensus import report


def _cfg():
    return SimpleNamespace(
        config_path=Path("config_e2e.toml"),
        derived_tenure=True,
        derived_vacancy=True,
        sanity="fail",
        mode="national",
        version_tag="e2e",
    )


def _steps():
    names = ["merge", "totals", "ages", "gemeinde", "gender", "topics8",
             "aggs", "regiostar", "extend", "tenure", "vacancy", "sanity"]
    return [{"name": n, "action": "run"} for n in names]


def test_banner_plain_contains_key_facts():
    out = report.render_banner(_cfg(), _steps(), color=False)
    assert "cleancensus" in out
    assert "config_e2e.toml" in out
    assert "national" in out
    assert "version_tag = e2e" in out
    assert "(12)" in out
    assert "\x1b[" not in out  # no ANSI when color off


def test_banner_box_lines_have_equal_visible_width():
    out = report.render_banner(_cfg(), _steps(), color=False)
    box = [ln for ln in out.splitlines() if ln and ln[0] in "╭│╰"]
    widths = {len(line) for line in box}
    assert len(widths) == 1, f"misaligned box: {widths}"


def test_summary_success_and_failure():
    ok = report.render_summary(_cfg(), {"merge": 12.0, "sanity": 0.4}, 0,
                               [], total_elapsed=12.4, color=False)
    assert "✓ completed" in ok and "merge" in ok and "0:12" in ok
    bad = report.render_summary(_cfg(), {"merge": 12.0}, 2, [], 12.0, color=False)
    assert "✗ 2 sanity failure" in bad


def test_summary_color_adds_ansi():
    out = report.render_summary(_cfg(), {"merge": 1.0}, 0, [], 1.0, color=True)
    assert "\x1b[" in out


def test_stage_frame():
    f = report.stage_frame(6, 12, "topics8", last="~0:00", color=False)
    assert "stage 6/12" in f and "topics8" in f
