"""Unit tests for central logging setup (cleancensus.logsetup)."""
from __future__ import annotations

import logging

from cleancensus import logsetup
from cleancensus import theme as _theme


def test_get_logger_namespaced():
    log = logsetup.get_logger("merge")
    assert log.name == "cleancensus.merge"


def test_formatter_plain_has_stage_and_message():
    rec = logging.LogRecord("cleancensus.merge", logging.INFO, __file__, 1,
                            "hello", None, None)
    out = logsetup.ColorFormatter(color=False).format(rec)
    assert "merge" in out and "hello" in out and "INFO" in out
    assert "\x1b[" not in out  # no ANSI when color disabled


def test_formatter_color_adds_ansi_when_enabled():
    rec = logging.LogRecord("cleancensus.x", logging.WARNING, __file__, 1,
                            "w", None, None)
    out = logsetup.ColorFormatter(color=True).format(rec)
    assert "\x1b[" in out


def test_setup_logging_idempotent():
    logsetup.setup_logging("INFO", color=False)
    logsetup.setup_logging("DEBUG", color=False)  # must not add a duplicate handler
    root = logging.getLogger("cleancensus")
    assert len(root.handlers) == 1


def test_stage_tag_uses_phase_colour():
    rec = logging.LogRecord("cleancensus.sanity", logging.INFO, __file__, 1,
                            "ok", None, None)
    out = logsetup.ColorFormatter(color=True).format(rec)
    assert _theme.stage_color("sanity") in out          # violet, not constant cyan
    assert _theme.LEVEL_COLOR["INFO"] in out


def test_different_phases_get_different_stage_colours():
    def fmt(name):
        rec = logging.LogRecord(f"cleancensus.{name}", logging.INFO, __file__, 1,
                                "m", None, None)
        return logsetup.ColorFormatter(color=True).format(rec)
    # merge=acquire(azure) vs sanity=validate(violet) → different escapes present
    assert _theme.stage_color("merge") in fmt("merge")
    assert _theme.stage_color("sanity") in fmt("sanity")
    assert _theme.stage_color("merge") != _theme.stage_color("sanity")
