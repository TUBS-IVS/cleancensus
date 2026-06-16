"""Single source of truth for cleancensus terminal colour + the stage→phase map.

Every ANSI escape used by logsetup.py, progress.py and report.py lives here, so the
palette can be retuned in ONE place. Scheme B: the stage tag is coloured by its
pipeline *phase* (acquire / transform / validate / controls / orchestrate). Phase hues
are chosen distinct from the severity palette so a stage tag never reads as a warning.

Colour is opt-out via NO_COLOR or CLEANCENSUS_COLOR=none, and auto-off for non-TTY
streams (so logs/*.log stay plain + greppable).
"""
from __future__ import annotations

import os
import sys

RESET = "\x1b[0m"
DIM = "\x1b[2m"
BOLD = "\x1b[1m"

# Severity — coloured on the LEVEL column.
LEVEL_COLOR = {
    "DEBUG": "\x1b[2m",       # dim
    "INFO": "\x1b[32m",       # green
    "WARNING": "\x1b[33m",    # yellow
    "ERROR": "\x1b[31m",      # red
    "CRITICAL": "\x1b[1;31m", # bold red
}

# Structural — banner / summary / bars.
BORDER = "\x1b[2m"
TITLE = "\x1b[1;36m"
ACCENT = "\x1b[36m"


def _c256(n: int) -> str:
    return f"\x1b[38;5;{n}m"


# Phase palette — stage tag. 256-colour, severity-safe (no green/yellow/red).
PHASE_COLOR = {
    "acquire": _c256(39),      # azure
    "transform": _c256(43),    # teal
    "validate": _c256(141),    # violet
    "controls": _c256(208),    # orange
    "orchestrate": _c256(103), # slate (dim-ish)
    "misc": _c256(245),        # neutral grey
}

# Stage (bare logger name, after the "cleancensus." prefix) → phase.
PHASE_OF = {
    "merge": "acquire", "totals": "acquire", "destatis": "acquire",
    "ages": "transform", "gender": "transform", "topics8": "transform",
    "aggs": "transform", "regiostar": "transform", "harmonize": "transform",
    "extend": "transform", "tenure": "transform", "vacancy": "transform",
    "sanity": "validate",
    "gemeinde": "controls", "gemeinde-controls": "controls",
    "cli": "orchestrate", "pipeline": "orchestrate", "report": "orchestrate",
}


def phase_of(stage: str) -> str:
    """Pipeline phase for a bare stage name; unknown stages → 'misc'."""
    return PHASE_OF.get(stage, "misc")


def stage_color(stage: str) -> str:
    """ANSI colour for a stage tag, by its phase."""
    return PHASE_COLOR[phase_of(stage)]


def want_color(color="auto", stream=None) -> bool:
    """Whether to emit ANSI colour. ``stream`` defaults to sys.stderr (logs);
    progress passes sys.stdout. Evaluated at call time so pytest stream-swaps work."""
    if color == "auto" or color is None:
        if os.environ.get("NO_COLOR"):
            return False
        if os.environ.get("CLEANCENSUS_COLOR", "").lower() == "none":
            return False
        s = stream if stream is not None else sys.stderr
        return bool(getattr(s, "isatty", lambda: False)())
    return bool(color)
