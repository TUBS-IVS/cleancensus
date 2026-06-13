# Pipeline Polish Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the cleancensus pipeline a professional, consistent CLI experience — unified stdlib logging with a colorized formatter, a single source of truth for file names, an elegant startup banner + closing summary — plus a docs cleanup. Behaviour-preserving.

**Architecture:** Two new foundation modules: `logsetup.py` (central logging config + `ColorFormatter` + `get_logger`) and `names.py` (all artifact filenames + legacy read-fallback aliases). `config.py` and every stage delegate to these. `cli.py` configures logging once, prints the banner and the closing summary. All `print()` / ad-hoc `log.*("[tag] …")` calls become per-stage `log.<level>(…)` on `cleancensus.<stage>` loggers.

**Tech Stack:** Python 3.13, stdlib `logging`, pandas/pyarrow (unchanged), pytest.

---

### Task 1: `names.py` — single source of truth for file names

**Files:**
- Create: `cleancensus/names.py`
- Test: `tests/test_names.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_names.py
import pytest
from cleancensus import names

def test_output_schema_unchanged():
    assert names.output(1, "e2e") == "zensus2022_grid_1km_de_e2e.parquet"
    assert names.output(100, "e2e") == "zensus2022_grid_100m_de_e2e.parquet"

def test_subset_output():
    assert names.output(100, "e2e", subset=True) == "zensus2022_grid_100m_de_e2e_subset.parquet"

def test_canonical_input_unchanged():
    assert names.canonical_input("10km") == "zensus2022_grid_10km_de_prepared.parquet"

def test_workfile_numbered_scheme():
    assert names.work("merge", "10km") == "01_merge_10km.parquet"
    assert names.work("topics8", "100m") == "06_topics8_100m.parquet"

def test_legacy_aliases_for_regiostar_workfile():
    al = names.legacy_aliases(names.work("regiostar", "100m"))
    assert "cells_100m_with_gender_backf_binneds_happyorphans_with_aggs_regiostar.parquet" in al

def test_legacy_alias_for_merge():
    assert "merged_10km_gitter.parquet" in names.legacy_aliases(names.work("merge", "10km"))
```

- [ ] **Step 2: Run test, expect fail (module missing).** `python -m pytest tests/test_names.py -q`

- [ ] **Step 3: Implement `cleancensus/names.py`**

```python
"""Single source of truth for cleancensus artifact file names.

Public output schema is FIXED: zensus2022_grid_{level}_de_{tag}.parquet.
work_dir intermediates use a stage-numbered scheme. Every renamed file keeps a
legacy alias so existing artifacts, gate references and downstream consumers still
resolve (read "new name first, then aliases").
"""
from __future__ import annotations

# canonical level spellings
LEVELS = ("10km", "1km", "100m")

def _lvl(level) -> str:
    s = f"{level}km" if isinstance(level, int) else str(level)
    s = {"1000m": "1km", "10000m": "10km"}.get(s, s)
    if s not in LEVELS:
        raise ValueError(f"unknown level {level!r}; expected one of {LEVELS}")
    return s

def canonical_input(level) -> str:
    return f"zensus2022_grid_{_lvl(level)}_de_prepared.parquet"

def output(level, tag: str, *, subset: bool = False) -> str:
    suffix = "_subset" if subset else ""
    return f"zensus2022_grid_{_lvl(level)}_de_{tag}{suffix}.parquet"

# work_dir intermediates: NN_<stage>_<level>.parquet
_WORK_NUM = {
    "merge": "01", "totals": "02", "ages": "03", "gemeinde": "04",
    "gender": "05", "topics8": "06", "aggs": "07", "regiostar": "08",
}

def work(stage: str, level=None) -> str:
    num = _WORK_NUM[stage]
    if level is None:
        return f"{num}_{stage}.parquet"
    return f"{num}_{stage}_{_lvl(level)}.parquet"

# historical (notebook-era) names, keyed by the NEW name -> list of old names
_LEGACY = {
    "01_merge_10km.parquet":  ["merged_10km_gitter.parquet"],
    "01_merge_1km.parquet":   ["merged_1km_gitter.parquet"],
    "01_merge_100m.parquet":  ["merged_100m_gitter.parquet"],
    "02_totals_10km.parquet": ["totals_10km.parquet"],
    "02_totals_1km.parquet":  ["totals_1km.parquet"],
    "02_totals_100m.parquet": ["totals_100m.parquet"],
    "03_ages_10km.parquet":   ["df10_with_single_years.parquet", "df10_with_single_years.pickle"],
    "03_ages_1km.parquet":    ["df1_with_single_years.parquet", "df1_with_single_years.pickle"],
    "03_ages_100m.parquet":   ["df100_with_single_years.parquet"],
    "04_gemeinde_100m.parquet": ["cells_100m_with_gemeinde.parquet"],
    "05_gender_100m.parquet": ["cells_100m_with_gender_backfilled.parquet"],
    "06_topics8_1km.parquet": ["cells_1km_with_binneds.parquet"],
    "06_topics8_100m.parquet": ["cells_100m_with_gender_backf_binneds_happyorphans.parquet"],
    "07_aggs_100m.parquet":   ["cells_100m_with_gender_backf_binneds_happyorphans_with_aggs.parquet"],
    "08_regiostar_100m.parquet": ["cells_100m_with_gender_backf_binneds_happyorphans_with_aggs_regiostar.parquet"],
}

def legacy_aliases(new_name: str) -> list[str]:
    return list(_LEGACY.get(new_name, []))

def resolve(dir_path, new_name: str):
    """Return the first existing path among [new_name, *legacy_aliases] in dir_path,
    or dir_path/new_name if none exist (the path to write)."""
    from pathlib import Path
    d = Path(dir_path)
    for cand in (new_name, *legacy_aliases(new_name)):
        p = d / cand
        if p.exists():
            return p
    return d / new_name
```

- [ ] **Step 4: Run test, expect pass.** `python -m pytest tests/test_names.py -q`
- [ ] **Step 5: Commit.** `git add cleancensus/names.py tests/test_names.py && git commit -m "feat(names): single source of truth for artifact file names + legacy aliases"`

---

### Task 2: `logsetup.py` — central logging + color formatter

**Files:**
- Create: `cleancensus/logsetup.py`
- Test: `tests/test_logsetup.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_logsetup.py
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

def test_formatter_color_adds_ansi_when_enabled():
    rec = logging.LogRecord("cleancensus.x", logging.WARNING, __file__, 1,
                            "w", None, None)
    out = logsetup.ColorFormatter(color=True).format(rec)
    assert "\x1b[" in out  # contains ANSI escape

def test_setup_logging_idempotent():
    logsetup.setup_logging("INFO", color=False)
    logsetup.setup_logging("DEBUG", color=False)  # must not add duplicate handlers
    root = logging.getLogger("cleancensus")
    assert len(root.handlers) == 1
```

- [ ] **Step 2: Run test, expect fail.** `python -m pytest tests/test_logsetup.py -q`

- [ ] **Step 3: Implement `cleancensus/logsetup.py`**

```python
"""Central logging configuration for cleancensus.

One namespaced logger per stage (`cleancensus.<stage>`); a single colorized
formatter `HH:MM:SS │ LEVEL │ stage │ message`. Colour auto-off for non-TTY,
NO_COLOR, or redirected output, so log files stay clean.
"""
from __future__ import annotations

import logging
import os
import sys

_ROOT = "cleancensus"

_LEVEL_COLOR = {
    "DEBUG": "\x1b[2m",      # dim
    "INFO": "\x1b[32m",      # green
    "WARNING": "\x1b[33m",   # yellow
    "ERROR": "\x1b[31m",     # red
    "CRITICAL": "\x1b[1;31m",
}
_DIM = "\x1b[2m"
_ACCENT = "\x1b[36m"        # cyan stage tag
_RESET = "\x1b[0m"

def _want_color(color) -> bool:
    if color == "auto" or color is None:
        if os.environ.get("NO_COLOR"):
            return False
        return bool(getattr(sys.stderr, "isatty", lambda: False)())
    return bool(color)

class ColorFormatter(logging.Formatter):
    def __init__(self, color="auto"):
        super().__init__()
        self.color = _want_color(color)

    def format(self, record: logging.LogRecord) -> str:
        ts = self.formatTime(record, "%H:%M:%S")
        stage = record.name.split(".", 1)[-1] if record.name.startswith(_ROOT) else record.name
        level = record.levelname
        msg = record.getMessage()
        if record.exc_info:
            msg = msg + "\n" + self.formatException(record.exc_info)
        if self.color:
            lc = _LEVEL_COLOR.get(level, "")
            return (f"{_DIM}{ts}{_RESET} {_DIM}│{_RESET} {lc}{level:<7}{_RESET} "
                    f"{_DIM}│{_RESET} {_ACCENT}{stage:<10}{_RESET} {_DIM}│{_RESET} {msg}")
        return f"{ts} │ {level:<7} │ {stage:<10} │ {msg}"

def setup_logging(level: str = "INFO", color="auto") -> None:
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

def get_logger(stage: str) -> logging.Logger:
    return logging.getLogger(f"{_ROOT}.{stage}")
```

- [ ] **Step 4: Run test, expect pass.** `python -m pytest tests/test_logsetup.py -q`
- [ ] **Step 5: Commit.** `git add cleancensus/logsetup.py tests/test_logsetup.py && git commit -m "feat(logsetup): central logging config + colorized formatter"`

---

### Task 3: Wire `config.py` to `names.py`

**Files:**
- Modify: `cleancensus/config.py` (out_1, out_100, work_dir property helpers, canonical input lists)

- [ ] **Step 1:** Replace the literal filenames in `config.py` properties with calls to
  `names.output(...)`, `names.canonical_input(...)`, and `names.resolve(work_dir, names.work(...))`
  for each work_dir property. Keep the existing fallback behaviour by using `names.resolve`.
- [ ] **Step 2:** Run `python -m pytest tests/test_config*.py -q` (and any config-touching tests); expect pass.
- [ ] **Step 3:** Commit. `git commit -am "refactor(config): resolve all artifact paths via names.py"`

---

### Task 4: Banner + summary helper (`report.py`)

**Files:**
- Create: `cleancensus/report.py` (print_banner, print_summary, stage_frame)
- Test: `tests/test_report.py`

- [ ] **Step 1: Failing test** — assert `print_banner(cfg)` returns/prints a string containing
  `cleancensus`, the version, `config`, `scope`, and the stage count; `print_summary` contains
  `✓`/`✗` and each stage name. (Use capsys.)
- [ ] **Step 2:** run, expect fail.
- [ ] **Step 3:** Implement the elegant-box banner (from the spec mock), a `stage_frame(k, n, name)`
  one-liner, and a `print_summary(timings, failures, outputs)` box with a timings table and
  output paths+sizes. Colour via logsetup's decision (reuse `_want_color`).
- [ ] **Step 4:** run, expect pass.
- [ ] **Step 5:** Commit. `git commit -am "feat(report): startup banner + closing summary"`

---

### Task 5: CLI wiring (`cli.py`)

**Files:** Modify `cleancensus/cli.py`

- [ ] Add `--verbose/-v` (DEBUG), `--quiet/-q` (WARNING) args; call `setup_logging(level)` first.
- [ ] Replace the manual `print(...)` header block with `report.print_banner(cfg)`.
- [ ] After `run_pipeline`, call `report.print_summary(...)`; convert remaining `print` to `log`.
- [ ] Run `python -m cleancensus.cli --config config_e2e.toml --dry-run` → banner + plan render.
- [ ] Commit. `git commit -am "feat(cli): banner, summary, --verbose/--quiet, central logging"`

---

### Task 6..N: Convert stages to per-stage loggers (one commit per module)

For EACH of: `z22`, `ingest_totals`, `ages_stage`, `gemeinde_stage`, `gender_stage`,
`topics8`, `enrich`, `stages`, `tenure`, `vacancy`, `sanity`, `harmonization`,
`gemeinde_controls`, `pipeline`, `destatis_csv`:

- [ ] **Recipe (mechanical, behaviour-preserving):**
  1. At top: `from cleancensus.logsetup import get_logger` and `log = get_logger("<stage>")`
     (stage = the tag already used, e.g. `merge` for z22's `[merge/z22]`, `topics8`, `tenure`…).
     Remove any `import logging` / `log = logging.getLogger(__name__)` (replace usages).
  2. `print("[tag] msg")` → `log.info("msg")`; warnings (`[warn] …`) → `log.warning("…")`;
     per-cell harmonization dumps (`INFO: abs difference`, parent/child arrays) → `log.debug(...)`.
  3. Drop the `[tag]` prefix from messages (the formatter adds the stage).
  4. Use lazy `%`-style logging args where cheap (`log.info("level=%s rows=%d", lvl, n)`),
     but leaving f-strings is acceptable for non-hot paths.
- [ ] After each module: `python -m pytest -q` must stay green; then commit
  `git commit -am "refactor(<stage>): use central per-stage logger"`.
- [ ] Resolve work_dir paths in each stage via `names.resolve(cfg.work_dir, names.work("<stage>", level))`
  instead of literal filenames (keeps legacy reads working).

---

### Task FINAL-1: Docs cleanup

**Files:** `README.md`, `docs/DATA.md`, `CHANGELOG.md`, any doc referencing old work_dir names.

- [ ] Update README: pipeline section, file-name references, a short "Logging & output" note
  (mention `--verbose/--quiet`, the banner, the work_dir naming scheme), refresh any stage list.
- [ ] Update `docs/DATA.md` work_dir filename references to the new scheme (note legacy aliases).
- [ ] Add a CHANGELOG `[Unreleased]` entry: "Unified logging + file-naming registry + banner".
- [ ] grep the repo for old literal names in docs (`grep -rn "with_gender_backf_binneds" docs README.md`)
  and update; keep a one-line "legacy names still read" note.
- [ ] Commit. `git commit -am "docs: reflect unified logging + file naming"`

---

### Task FINAL-2: Verification

- [ ] `python -m pytest -q` → all green (update tests that asserted old printed strings / names).
- [ ] `python -m cleancensus.cli --config config_e2e.toml --dry-run` → banner + plan, colored on TTY.
- [ ] `python -u -m cleancensus.cli --config config_e2e.toml --dry-run > /tmp/x.log 2>&1` → plain (no ANSI) in file.
- [ ] Commit any test fixups. `git commit -am "test: update for unified logging + naming"`

## Self-Review (done)
- Spec coverage: logging (T2,T5,T6+), names (T1,T3,T6), banner/summary (T4,T5), docs (FINAL-1),
  behaviour-preserving verification (FINAL-2). ✓
- No placeholders in foundation modules (full code given). Stage conversion is a precise recipe
  over an explicit module list (mechanical, one pattern). ✓
- Type/name consistency: `get_logger`, `setup_logging`, `ColorFormatter`, `names.work/output/
  canonical_input/legacy_aliases/resolve` used consistently across tasks. ✓
