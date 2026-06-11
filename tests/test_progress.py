"""Tests for cleancensus.progress module."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from cleancensus.progress import (
    format_duration,
    load_stage_timings,
    progress_iter,
    save_stage_timings,
)


# ---------------------------------------------------------------------------
# format_duration
# ---------------------------------------------------------------------------


def test_format_duration_minutes_seconds():
    assert format_duration(65) == "1:05"


def test_format_duration_hours():
    assert format_duration(3725) == "1:02:05"


def test_format_duration_zero():
    assert format_duration(0) == "0:00"


def test_format_duration_exact_minute():
    assert format_duration(60) == "1:00"


def test_format_duration_one_hour():
    assert format_duration(3600) == "1:00:00"


# ---------------------------------------------------------------------------
# progress_iter — yield correctness
# ---------------------------------------------------------------------------


def test_progress_iter_yields_all_items():
    result = list(progress_iter(range(5), "x"))
    assert result == [0, 1, 2, 3, 4]


def test_progress_iter_yields_all_items_with_total():
    result = list(progress_iter(range(5), "x", total=5))
    assert result == [0, 1, 2, 3, 4]


def test_progress_iter_empty():
    result = list(progress_iter([], "empty", total=0))
    assert result == []


def test_progress_iter_single_item():
    result = list(progress_iter([42], "single", total=1))
    assert result == [42]


# ---------------------------------------------------------------------------
# progress_iter — output lines
# ---------------------------------------------------------------------------


def test_progress_iter_prints_lines(capsys):
    """With min_interval=0, every step triggers a print; final line is always printed."""
    items = list(range(20))
    result = list(progress_iter(items, "test-label", total=20, min_interval=0.0))

    assert result == items

    captured = capsys.readouterr()
    lines = [l for l in captured.out.splitlines() if l.strip()]

    # At least 2 lines (start + completion)
    assert len(lines) >= 2

    # A 100% line must appear
    assert any("100%" in line for line in lines)

    # Label must appear in every line
    for line in lines:
        assert "[test-label]" in line


def test_progress_iter_prints_without_total(capsys):
    """Without total: no pct/ETA, but still prints at start and end."""
    result = list(progress_iter(range(5), "no-total", total=None, min_interval=0.0))

    assert result == [0, 1, 2, 3, 4]

    captured = capsys.readouterr()
    lines = [l for l in captured.out.splitlines() if l.strip()]

    assert len(lines) >= 2
    # No percentage sign expected
    for line in lines:
        assert "%" not in line
    # "items" should appear
    assert any("items" in line for line in lines)


def test_progress_iter_final_line_always_printed(capsys):
    """Even with a very long min_interval, the final line is always printed."""
    list(progress_iter(range(3), "final-check", total=3, min_interval=999999.0))

    captured = capsys.readouterr()
    lines = [l for l in captured.out.splitlines() if l.strip()]

    # At minimum: start (0%) and final (100%) lines
    assert len(lines) >= 2
    assert any("100%" in line for line in lines)


# ---------------------------------------------------------------------------
# Stage timings persistence
# ---------------------------------------------------------------------------


def test_save_load_round_trip():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "timings.json"
        timings = {"merge": 10.5, "totals": 5.0, "ages": 120.3}
        save_stage_timings(path, timings)
        loaded = load_stage_timings(path)
        assert loaded == timings


def test_load_missing_file_returns_empty():
    path = Path("/nonexistent/path/does/not/exist/.stage_timings.json")
    result = load_stage_timings(path)
    assert result == {}


def test_load_corrupt_file_returns_empty():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "bad.json"
        path.write_text("not valid json {{{{", encoding="utf-8")
        result = load_stage_timings(path)
        assert result == {}


def test_save_merges_existing_keys():
    """save_stage_timings should merge: only overwrite the keys provided."""
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "timings.json"
        # First save
        save_stage_timings(path, {"merge": 10.0, "totals": 5.0})
        # Second save: only update 'merge', keep 'totals' from first save
        save_stage_timings(path, {"merge": 12.0})
        loaded = load_stage_timings(path)
        assert loaded["merge"] == 12.0
        assert loaded["totals"] == 5.0


def test_save_creates_parent_dirs():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "nested" / "dirs" / "timings.json"
        save_stage_timings(path, {"x": 1.0})
        assert path.exists()
        loaded = load_stage_timings(path)
        assert loaded["x"] == 1.0
