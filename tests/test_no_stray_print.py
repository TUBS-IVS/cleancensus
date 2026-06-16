"""Guard: pipeline modules log through cleancensus.logsetup; only the presentation
modules (report = banner/summary, progress = the bar) may call print()."""
from __future__ import annotations

import re
from pathlib import Path

_PKG = Path(__file__).resolve().parent.parent / "cleancensus"
_ALLOWED = {"report.py", "progress.py"}
_PRINT = re.compile(r"^\s*print\(", re.MULTILINE)


def test_no_bare_print_in_pipeline_modules():
    offenders = []
    for py in _PKG.glob("*.py"):
        if py.name in _ALLOWED:
            continue
        if _PRINT.search(py.read_text(encoding="utf-8")):
            offenders.append(py.name)
    assert offenders == [], f"bare print() in pipeline modules: {offenders}"
