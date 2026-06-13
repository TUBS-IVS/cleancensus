"""Unit tests for central logging setup (cleancensus.logsetup)."""
from __future__ import annotations

import logging

from cleancensus import logsetup


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
