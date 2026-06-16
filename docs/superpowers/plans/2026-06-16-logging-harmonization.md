# Logging & Terminal-UX Harmonization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make cleancensus's terminal output "from one mold" — one palette + one stage→phase map, phase-coloured stage tags (Scheme B), adaptive progress rate — without changing the log format or the plain-text/log-file guarantee.

**Architecture:** Introduce `cleancensus/theme.py` as the single source of ANSI colour + the stage→phase map. Rewire `logsetup.py`, `report.py`, `progress.py` to consume it and delete their local palettes. The stage tag is coloured by pipeline phase; severity colours stay on the LEVEL column. eqasim-bs gets a verbatim copy in a separate PR.

**Tech Stack:** Python 3, stdlib `logging`, pytest (run via `uv run pytest`). ANSI 256-colour.

**Spec:** `docs/superpowers/specs/2026-06-16-logging-harmonization-design.md`
**Branch:** `feature/logging-harmonization` (off `main`).

---

## File Structure

- **Create** `cleancensus/theme.py` — palette + phase map + `want_color`/`phase_of`/`stage_color`. The only place ANSI codes live.
- **Create** `tests/test_theme.py` — phase map + colour-decision tests.
- **Modify** `cleancensus/logsetup.py` — `ColorFormatter` pulls colours from `theme`; stage tag uses `theme.stage_color(stage)`; delete `_LEVEL_COLOR/_ACCENT/_DIM/_want_color`.
- **Modify** `cleancensus/report.py` — drop `_PAL`; pull colours from `theme`; `stage_frame` colours the name with `theme.stage_color`.
- **Modify** `cleancensus/progress.py` — colours from `theme`; add `format_rate`; never print `0.0 it/s`.
- **Modify** `tests/test_logsetup.py`, `tests/test_progress.py` — extend for the new behaviour (keep existing assertions green).
- **Create** `tests/test_no_stray_print.py` — guard: only `progress`/`report` may call `print(`.

---

## Task 1: `theme.py` — single-source palette + stage→phase map

**Files:**
- Create: `cleancensus/theme.py`
- Test: `tests/test_theme.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_theme.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_theme.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'cleancensus.theme'`.

- [ ] **Step 3: Write minimal implementation**

```python
# cleancensus/theme.py
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_theme.py -v`
Expected: PASS (all 8).

- [ ] **Step 5: Commit**

```bash
git add cleancensus/theme.py tests/test_theme.py
git commit -m "feat(theme): single-source palette + stage→phase map (scheme B)"
```

---

## Task 2: `logsetup.py` consumes `theme`; stage tag uses phase colour

**Files:**
- Modify: `cleancensus/logsetup.py`
- Test: `tests/test_logsetup.py`

- [ ] **Step 1: Write the failing test (append to tests/test_logsetup.py)**

```python
from cleancensus import theme as _theme


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
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_logsetup.py -v`
Expected: FAIL — `AttributeError`/wrong colour (logsetup still uses constant `_ACCENT`).

- [ ] **Step 3: Edit `logsetup.py`**

Delete `_LEVEL_COLOR`, `_DIM`, `_ACCENT`, `_RESET`, `_want_color` (lines 16-33). Replace the
`ColorFormatter.format` colour branch and `color_enabled` to use `theme`:

```python
from cleancensus import theme

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


def color_enabled(color="auto") -> bool:
    """Whether ANSI colour should be emitted (shared by report.py banner/summary)."""
    return theme.want_color(color)
```

Keep `_force_utf8_streams`, `setup_logging`, `get_logger` unchanged. (`setup_logging` still passes `color` into `ColorFormatter`.)

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_logsetup.py -v`
Expected: PASS — including the existing `test_formatter_plain_*` (no-colour path is byte-identical).

- [ ] **Step 5: Commit**

```bash
git add cleancensus/logsetup.py tests/test_logsetup.py
git commit -m "refactor(logsetup): pull colours from theme; phase-coloured stage tag"
```

---

## Task 3: `report.py` consumes `theme`

**Files:**
- Modify: `cleancensus/report.py`
- Test: `tests/test_report.py` (exists)

- [ ] **Step 1: Write the failing test (append to tests/test_report.py)**

```python
from cleancensus import report as _report
from cleancensus import theme as _theme


def test_stage_frame_colours_name_by_phase():
    out = _report.stage_frame(2, 9, "sanity", color=True)
    assert _theme.stage_color("sanity") in out


def test_report_uses_no_local_palette():
    # _PAL must be gone — colours come from theme now.
    assert not hasattr(_report, "_PAL")
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_report.py -v`
Expected: FAIL — `_PAL` still present / name not phase-coloured.

- [ ] **Step 3: Edit `report.py`**

Delete the `_PAL` dict (lines 17-26). Add `from cleancensus import theme` and a local key→theme map so `_c`/`_row_token` keep working:

```python
from cleancensus import theme
from cleancensus.logsetup import color_enabled

_W = 60  # inner content width

_KEYMAP = {
    "border": theme.BORDER, "title": theme.TITLE, "key": theme.DIM,
    "ok": theme.LEVEL_COLOR["INFO"], "warn": theme.LEVEL_COLOR["WARNING"],
    "err": theme.LEVEL_COLOR["ERROR"], "accent": theme.ACCENT, "reset": theme.RESET,
}
```

Change `_c` and `_row_token` to read from `_KEYMAP` instead of `_PAL`:

```python
def _c(text: str, key: str, color: bool) -> str:
    return f"{_KEYMAP[key]}{text}{_KEYMAP['reset']}" if color else text
```
```python
    if color:
        inner = inner.replace(token_plain, f"{_KEYMAP[paint]}{token_plain}{_KEYMAP['reset']}", 1)
```

In `stage_frame`, colour the stage name by phase instead of the generic title:

```python
def stage_frame(k: int, n: int, name: str, last: str | None = None, *, color=None) -> str:
    color = color_enabled() if color is None else color
    head = _c(f"▶ stage {k}/{n}", "accent", color)
    nm = f"{theme.stage_color(name)}{name}{theme.RESET}" if color else name
    tail = _c(f"(last run: {last})", "key", color) if last else ""
    return f"{head} · {nm}  {tail}".rstrip()
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_report.py -v`
Expected: PASS (incl. existing banner/summary tests — box alignment computed on plain text, unaffected).

- [ ] **Step 5: Commit**

```bash
git add cleancensus/report.py tests/test_report.py
git commit -m "refactor(report): pull colours from theme; phase-coloured stage frame"
```

---

## Task 4: `progress.py` — theme colours + adaptive rate (no more `0.0 it/s`)

**Files:**
- Modify: `cleancensus/progress.py`
- Test: `tests/test_progress.py`

- [ ] **Step 1: Write the failing test (append to tests/test_progress.py)**

```python
from cleancensus.progress import format_rate


def test_format_rate_per_second():
    assert format_rate(12.3) == "12.3/s"
    assert format_rate(1.0) == "1.0/s"


def test_format_rate_per_minute():
    assert format_rate(0.75) == "45.0/min"   # 0.75/s = 45/min


def test_format_rate_per_item_duration():
    # 1 item every 3120s = 52:00 → "~52:00/it"
    assert format_rate(1.0 / 3120.0) == "~52:00/it"


def test_format_rate_zero_is_none():
    assert format_rate(0.0) is None
    assert format_rate(-1.0) is None


def test_progress_never_prints_zero_rate(capsys):
    # An iterable whose first line (i=0) used to show "0.0 it/s".
    list(progress_iter(range(3), "lbl", total=3, min_interval=0.0))
    out = capsys.readouterr().out
    assert "0.0 it/s" not in out
    assert "0.0/s" not in out
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_progress.py -v`
Expected: FAIL — `format_rate` undefined; `0.0 it/s` still printed at start.

- [ ] **Step 3: Edit `progress.py`**

Replace the module colour constants `_CYAN/_DIM/_BOLD/_RESET` (line 28) with theme imports, and add `format_rate`. Update `_print_line` and `_draw` to use `format_rate` and omit the rate token when it is `None`.

```python
from cleancensus import theme
from cleancensus.theme import want_color

_PARTIALS = "▏▎▍▌▋▊▉"
_SPIN = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
_CYAN, _DIM, _BOLD, _RESET = theme.ACCENT, theme.DIM, theme.BOLD, theme.RESET


def format_rate(rate: float) -> str | None:
    """Human-friendly throughput, or None when there's nothing meaningful to show.

    >>> format_rate(12.3)
    '12.3/s'
    >>> format_rate(0.75)
    '45.0/min'
    >>> format_rate(1/3120)
    '~52:00/it'
    >>> format_rate(0.0) is None
    True
    """
    if rate <= 0:
        return None
    if rate >= 1.0:
        return f"{rate:.1f}/s"
    per_min = rate * 60.0
    if per_min >= 1.0:
        return f"{per_min:.1f}/min"
    return f"~{format_duration(1.0 / rate)}/it"
```

In `_stdout_is_tty`, delegate the NO_COLOR/tty decision to theme:

```python
def _stdout_is_tty() -> bool:
    return want_color("auto", stream=sys.stdout)
```

In `_print_line`, build the rate token conditionally (both the with-total and no-total branches):

```python
        rate_str = format_rate(rate)
        rate_tok = f" | {rate_str.replace('/s', ' it/s').replace('/min', ' it/min')}" if rate_str else ""
```

then append `rate_tok` instead of the hard-coded `| {rate:.1f} it/s`. (Plain log lines keep "it/s"/"it/min" wording; the TTY bar uses the compact `/s` form.) In `_draw`, use:

```python
        rate_str = format_rate(rate)
        rate_tok = f" · {rate_str}" if rate_str else ""
```

and append `rate_tok` to the bar line in place of `· {rate:.1f}/s`.

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_progress.py -v`
Expected: PASS — incl. existing line/label/100%/items assertions and the new rate tests.

- [ ] **Step 5: Commit**

```bash
git add cleancensus/progress.py tests/test_progress.py
git commit -m "feat(progress): theme colours + adaptive rate (no more 0.0 it/s)"
```

---

## Task 5: stray-`print` guard test

**Files:**
- Create: `tests/test_no_stray_print.py`

- [ ] **Step 1: Write the test (passes immediately — codifies the rule)**

```python
# tests/test_no_stray_print.py
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
```

- [ ] **Step 2: Run to verify it passes**

Run: `uv run pytest tests/test_no_stray_print.py -v`
Expected: PASS (cleancensus has no stray prints today).

- [ ] **Step 3: Run the whole suite**

Run: `uv run pytest -q`
Expected: all green (no regressions).

- [ ] **Step 4: Commit**

```bash
git add tests/test_no_stray_print.py
git commit -m "test: guard against stray print() in pipeline modules"
```

---

## Task 6: Live-demo check + push + PR

**Files:** none (verification + integration)

- [ ] **Step 1: See Scheme B live**

Run (in a real terminal, not piped): `uv run cleancensus --config config_demo.toml`
Expected: banner + per-stage frames + log lines where the **stage tag colour differs by phase**
(merge azure, extend/tenure/vacancy teal, sanity violet), progress bar with a sane rate,
clean summary box. Tune `theme.PHASE_COLOR` if a hue is off, re-run.

- [ ] **Step 2: Push + open PR**

```bash
git push -u origin feature/logging-harmonization
gh pr create --base main --head feature/logging-harmonization \
  --title "Logging & terminal-UX harmonization (scheme B)" \
  --body "Single-source theme.py + phase-coloured stage tags + adaptive progress rate. See docs/superpowers/specs/2026-06-16-logging-harmonization-design.md."
```
Merge via the GitHub button.

---

## Task 7: eqasim-bs mirror (separate repo / PR — do NOT do on this branch)

In `C:/Users/bienzeisler/Documents/GitHub/eqasim-bs` (origin = TUBS-IVS, never upstream):
- [ ] Copy `cleancensus/theme.py` → `braunschweig/theme.py`, header `# Ported from cleancensus/theme.py — keep in sync.` Extend `PHASE_OF` with the popsim loggers (seed/member_completion=acquire; stage/mid/batch/merge/expand/missing/attributes=transform; income*=controls; synpp=orchestrate).
- [ ] Rewire `braunschweig/logging_setup.py` + `braunschweig/popsim/progress.py` onto `theme` (same edits as Tasks 2 & 4).
- [ ] Sweep popsim for the bare `print(` lines (e.g. the `socioprofessional_class` line) → route through the stage logger.
- [ ] Run the eqasim test suite (787 tests) green; new branch → PR on origin.

---

## Self-Review

- **Spec coverage:** theme.py (§1)→T1; phase map/colours (§2)→T1; log line (§3)→T2; progress adaptive rate (§4)→T4; stray-print guard (§5)→T5; report (§6)→T3; eqasim mirror (§7)→T7; live demo→T6. ✓ All covered.
- **Deferred (YAGNI, noted vs spec):** basic-16 fallback — modern terminals (Windows Terminal, VS Code, iTerm) all do 256-colour; ship 256 + `none` off-switch, add `basic` only if a real non-256 terminal appears. EWMA ETA — keep the cumulative-average rate (already stable); revisit only if ETA still swings on a real run.
- **Type consistency:** `phase_of`/`stage_color`/`want_color(color, stream)`/`format_rate` names are used identically across T1–T4; `LEVEL_COLOR`/`PHASE_COLOR`/`DIM`/`RESET`/`BORDER`/`TITLE`/`ACCENT` referenced consistently. ✓
- **No placeholders:** every code/command step is concrete. ✓
