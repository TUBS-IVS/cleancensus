"""Tests for the single-source colour theme + stage→phase map."""
from __future__ import annotations

import sys

from cleancensus import theme


def test_phase_of_known_stages():
    assert theme.phase_of("merge") == "acquire"
    assert theme.phase_of("extend") == "transform"
    assert theme.phase_of("sanity") == "validate"
    assert theme.phase_of("gemeinde") == "controls"
    assert theme.phase_of("pipeline") == "orchestrate"


def test_phase_of_unknown_is_misc():
    assert theme.phase_of("totally-new-stage") == "misc"


def test_stage_color_returns_ansi_for_its_phase():
    # acquire == azure 38;5;39, validate == violet 38;5;141
    assert theme.stage_color("merge") == theme.PHASE_COLOR["acquire"]
    assert theme.stage_color("sanity") == theme.PHASE_COLOR["validate"]
    assert theme.stage_color("merge").startswith("\x1b[38;5;")


def test_phase_colors_are_distinct_from_severity():
    # No phase hue may equal a severity colour (so a stage tag never reads as a level).
    severity = set(theme.LEVEL_COLOR.values())
    for hue in theme.PHASE_COLOR.values():
        assert hue not in severity


def test_level_color_has_all_levels():
    for lvl in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"):
        assert lvl in theme.LEVEL_COLOR


def test_want_color_off_when_no_color_env(monkeypatch):
    monkeypatch.setenv("NO_COLOR", "1")
    assert theme.want_color("auto") is False


def test_want_color_off_when_mode_none(monkeypatch):
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setenv("CLEANCENSUS_COLOR", "none")
    assert theme.want_color("auto") is False


def test_want_color_explicit_overrides(monkeypatch):
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.delenv("CLEANCENSUS_COLOR", raising=False)
    assert theme.want_color(True) is True
    assert theme.want_color(False) is False


def test_want_color_respects_stream_tty(monkeypatch):
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.delenv("CLEANCENSUS_COLOR", raising=False)

    class FakeTTY:
        def isatty(self):
            return True

    class FakeNotTTY:
        def isatty(self):
            return False

    assert theme.want_color("auto", stream=FakeTTY()) is True
    assert theme.want_color("auto", stream=FakeNotTTY()) is False
