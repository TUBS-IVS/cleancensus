"""Log-friendly progress reporting for the cleancensus pipeline.

Provides:
  - format_duration(seconds) -> str          H:MM:SS or M:SS
  - progress_iter(iterable, label, ...)      yields items + prints progress lines
  - load_stage_timings(path) -> dict         JSON persistence (tolerates missing/corrupt)
  - save_stage_timings(path, timings)        JSON persistence
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Iterable, Iterator, TypeVar

T = TypeVar("T")

# ---------------------------------------------------------------------------
# Fancy (TTY) bar rendering — colour + partial-block precision + spinner.
# Used ONLY when stdout is a real terminal; redirected/piped output keeps the
# plain, greppable lines below so log files stay clean.
# ---------------------------------------------------------------------------

_PARTIALS = "▏▎▍▌▋▊▉"   # 1/8 .. 7/8 block
_SPIN = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
_CYAN, _DIM, _BOLD, _RESET = "\x1b[36m", "\x1b[2m", "\x1b[1m", "\x1b[0m"


def _stdout_is_tty() -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    return bool(getattr(sys.stdout, "isatty", lambda: False)())


def _bar(frac: float, width: int = 22) -> str:
    """A coloured unicode bar of *width* cells at fill fraction *frac* (eighth precision)."""
    frac = max(0.0, min(1.0, frac))
    eighths = round(frac * width * 8)
    full, rem = divmod(eighths, 8)
    part = _PARTIALS[rem - 1] if rem else ""
    empty = max(0, width - full - (1 if part else 0))
    return f"{_CYAN}{'█' * full}{part}{_RESET}{_DIM}{'░' * empty}{_RESET}"


# ---------------------------------------------------------------------------
# Duration formatter
# ---------------------------------------------------------------------------


def format_duration(seconds: float) -> str:
    """Format a duration in seconds as H:MM:SS (>= 1 hour) or M:SS.

    Examples
    --------
    >>> format_duration(65)
    '1:05'
    >>> format_duration(3725)
    '1:02:05'
    >>> format_duration(0)
    '0:00'
    """
    seconds = max(0.0, float(seconds))
    total_s = int(round(seconds))
    h = total_s // 3600
    m = (total_s % 3600) // 60
    s = total_s % 60
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


# ---------------------------------------------------------------------------
# progress_iter
# ---------------------------------------------------------------------------


def progress_iter(
    iterable: Iterable[T],
    label: str,
    *,
    total: int | None = None,
    min_interval: float = 15.0,
) -> Iterator[T]:
    """Yield items from *iterable* unchanged, printing log-friendly progress lines.

    Progress is printed:
      - at start (0 / first item processed)
      - whenever ``min_interval`` seconds have elapsed since the last print
      - whenever a new 10%-milestone is crossed (only if total is known)
      - always at completion (100% / final count)

    Line format (with total):
      ``[<label>] <pct>% (<i>/<total>) | elapsed <dur> | ETA <dur> | <rate> it/s``

    Line format (without total):
      ``[<label>] <i> items | elapsed <dur> | <rate> it/s``

    Parameters
    ----------
    iterable : Iterable[T]
      Items to iterate over.
    label : str
      Short name shown in brackets.
    total : int or None
      Number of items; if None/unknown, ETA and % are omitted.
    min_interval : float
      Minimum seconds between progress prints (default 15.0).
    """
    t_start = time.perf_counter()
    t_last_print = t_start
    last_milestone = -1
    i = 0
    tty = _stdout_is_tty()
    spin_i = 0

    def _print_line(i: int, final: bool = False) -> None:
        """Print one plain, greppable progress line to stdout (non-TTY / log files)."""
        elapsed = time.perf_counter() - t_start
        rate = i / elapsed if elapsed > 0 else 0.0

        if total is not None and total > 0:
            pct = int(100 * i / total)
            if final:
                pct = 100
            remaining = (total - i) / rate if (rate > 0 and not final) else 0.0
            eta_str = format_duration(remaining) if not final else "0:00"
            print(
                f"[{label}] {pct}% ({i}/{total}) | elapsed {format_duration(elapsed)} "
                f"| ETA {eta_str} | {rate:.1f} it/s",
                flush=True,
            )
        else:
            print(
                f"[{label}] {i} items | elapsed {format_duration(elapsed)} "
                f"| {rate:.1f} it/s",
                flush=True,
            )

    def _draw(i: int, final: bool = False) -> None:
        """Redraw the fancy in-place coloured bar on the current TTY line."""
        nonlocal spin_i
        spin_i += 1
        elapsed = time.perf_counter() - t_start
        rate = i / elapsed if elapsed > 0 else 0.0
        spin = " " if final else _SPIN[spin_i % len(_SPIN)]
        if total is not None and total > 0:
            pct = 100 if final else int(100 * i / total)
            remaining = (total - i) / rate if (rate > 0 and not final) else 0.0
            eta = "0:00" if final else format_duration(remaining)
            line = (f"{_CYAN}{spin}{_RESET} {_DIM}{label}{_RESET} "
                    f"{_DIM}│{_RESET}{_bar(1.0 if final else i / total)}{_DIM}│{_RESET} "
                    f"{_BOLD}{pct:3d}%{_RESET} {_DIM}({i}/{total}) · "
                    f"{format_duration(elapsed)} · ETA {eta} · {rate:.1f}/s{_RESET}")
        else:
            line = (f"{_CYAN}{spin}{_RESET} {_DIM}{label}{_RESET} {_BOLD}{i}{_RESET} "
                    f"{_DIM}items · {format_duration(elapsed)} · {rate:.1f}/s{_RESET}")
        sys.stdout.write("\r\x1b[2K" + line)
        sys.stdout.flush()

    (_draw if tty else _print_line)(0)

    for item in iterable:
        yield item
        i += 1
        now = time.perf_counter()

        if tty:
            is_last = total is not None and total > 0 and i >= total
            if now - t_last_print >= 0.066 or is_last:
                _draw(i)
                t_last_print = now
        else:
            interval_elapsed = now - t_last_print >= min_interval
            milestone_crossed = False
            if total is not None and total > 0:
                current_milestone = int(100 * i / total) // 10
                if current_milestone > last_milestone:
                    last_milestone = current_milestone
                    milestone_crossed = True
            if interval_elapsed or milestone_crossed:
                _print_line(i)
                t_last_print = now

    if tty:
        _draw(i, final=True)
        sys.stdout.write("\n")
        sys.stdout.flush()
    else:
        _print_line(i, final=True)


# ---------------------------------------------------------------------------
# Stage-timing persistence
# ---------------------------------------------------------------------------


def load_stage_timings(path: str | Path) -> dict[str, float]:
    """Load per-stage timing dict from a JSON file.

    Returns {} if the file is missing or contains invalid JSON.

    Parameters
    ----------
    path : str or Path
      Path to the JSON file (e.g. ``.stage_timings.json``).
    """
    p = Path(path)
    try:
        text = p.read_text(encoding="utf-8")
        data = json.loads(text)
        if isinstance(data, dict):
            return {str(k): float(v) for k, v in data.items() if isinstance(v, (int, float))}
        return {}
    except (FileNotFoundError, OSError, json.JSONDecodeError, ValueError):
        return {}


def save_stage_timings(path: str | Path, timings: dict[str, float]) -> None:
    """Write per-stage timing dict to a JSON file (merge: only overwrites given keys).

    Creates parent directories as needed.

    Parameters
    ----------
    path : str or Path
      Destination JSON file path.
    timings : dict[str, float]
      Mapping of stage name -> duration in seconds.
    """
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    # Merge: load existing, overwrite only provided keys
    existing = load_stage_timings(p)
    existing.update({str(k): float(v) for k, v in timings.items()})
    p.write_text(json.dumps(existing, indent=2), encoding="utf-8")
