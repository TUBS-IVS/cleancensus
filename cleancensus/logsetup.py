"""Central logging configuration for cleancensus.

One namespaced logger per stage (``cleancensus.<stage>``); a single colorized
formatter rendering ``HH:MM:SS │ LEVEL │ stage │ message``. Colour is auto-disabled
for non-TTY output, when ``NO_COLOR`` is set, or when output is redirected to a file,
so ``logs/*.log`` stay clean plain text.
"""
from __future__ import annotations

import logging
import sys

from cleancensus import theme

_ROOT = "cleancensus"


class ColorFormatter(logging.Formatter):
    """Format ``HH:MM:SS │ LEVEL │ stage │ message`` with optional ANSI colour."""

    def __init__(self, color="auto"):
        super().__init__()
        self.color = theme.want_color(color)

    def format(self, record: logging.LogRecord) -> str:
        ts = self.formatTime(record, "%H:%M:%S")
        stage = record.name.split(".", 1)[-1] if record.name.startswith(_ROOT) else record.name
        level = record.levelname
        msg = record.getMessage()
        if record.exc_info:
            msg = msg + "\n" + self.formatException(record.exc_info)
        if self.color:
            lc = theme.LEVEL_COLOR.get(level, "")
            sc = theme.stage_color(stage)
            d, r = theme.DIM, theme.RESET
            return (f"{d}{ts}{r} {d}│{r} {lc}{level:<7}{r} "
                    f"{d}│{r} {sc}{stage:<10}{r} {d}│{r} {msg}")
        return f"{ts} │ {level:<7} │ {stage:<10} │ {msg}"


def _force_utf8_streams() -> None:
    """Make stdout/stderr emit UTF-8 so box-drawing/✓/→ never raise on Windows
    (cp1252) consoles or redirected log files. Best-effort; ignored if unsupported.
    """
    for stream in (sys.stdout, sys.stderr):
        enc = (getattr(stream, "encoding", "") or "").lower().replace("-", "")
        if enc == "utf8":
            continue  # already UTF-8 (e.g. pytest capture buffers) — don't touch
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except (AttributeError, ValueError, OSError):
            pass


def setup_logging(level: str = "INFO", color="auto") -> None:
    """Configure the ``cleancensus`` logger once (idempotent)."""
    _force_utf8_streams()
    root = logging.getLogger(_ROOT)
    root.setLevel(getattr(logging, str(level).upper(), logging.INFO))
    root.propagate = False
    if not root.handlers:
        h = logging.StreamHandler(stream=sys.stderr)
        h.setFormatter(ColorFormatter(color=color))
        root.addHandler(h)
    else:
        for h in root.handlers:
            h.setFormatter(ColorFormatter(color=color))
            # rebind to the *current* sys.stderr (matters when streams are swapped,
            # e.g. pytest capture between test cases)
            if isinstance(h, logging.StreamHandler):
                try:
                    h.setStream(sys.stderr)
                except Exception:  # noqa: BLE001
                    pass


def get_logger(stage: str) -> logging.Logger:
    """Return the namespaced logger for a pipeline stage."""
    return logging.getLogger(f"{_ROOT}.{stage}")


def color_enabled(color="auto") -> bool:
    """Whether ANSI colour should be emitted (shared by report.py banner/summary)."""
    return theme.want_color(color)
