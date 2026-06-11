"""Log-friendly progress reporting for the cleancensus pipeline.

Provides:
  - format_duration(seconds) -> str          H:MM:SS or M:SS
  - progress_iter(iterable, label, ...)      yields items + prints progress lines
  - load_stage_timings(path) -> dict         JSON persistence (tolerates missing/corrupt)
  - save_stage_timings(path, timings)        JSON persistence
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Iterable, Iterator, TypeVar

T = TypeVar("T")


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

    def _print_line(i: int, final: bool = False) -> None:
        """Print one progress line to stdout (flush for log redirection)."""
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

    # Print start line immediately (before first item)
    _print_line(0)

    for item in iterable:
        yield item
        i += 1

        now = time.perf_counter()
        interval_elapsed = now - t_last_print >= min_interval

        # Check 10%-milestone crossing
        milestone_crossed = False
        if total is not None and total > 0:
            current_milestone = int(100 * i / total) // 10
            if current_milestone > last_milestone:
                last_milestone = current_milestone
                milestone_crossed = True

        if interval_elapsed or milestone_crossed:
            _print_line(i)
            t_last_print = now

    # Always print final line
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
