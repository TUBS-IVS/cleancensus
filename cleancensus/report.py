"""Presentation layer for the cleancensus CLI: startup banner, per-stage frame,
and the closing run summary. Pure formatting — no pipeline logic.

Colour follows the same decision as logging (TTY / NO_COLOR / redirect), via
``logsetup.color_enabled``. All width maths is done on the *visible* (plain) text so
zero-width ANSI codes never break box alignment.
"""
from __future__ import annotations

import sys

from cleancensus import __version__
from cleancensus.logsetup import color_enabled

_W = 60  # inner content width

_PAL = {
    "border": "\x1b[2m",
    "title": "\x1b[1;36m",
    "key": "\x1b[2m",
    "ok": "\x1b[32m",
    "warn": "\x1b[33m",
    "err": "\x1b[31m",
    "accent": "\x1b[36m",
    "reset": "\x1b[0m",
}


_UNI2ASCII = str.maketrans({
    "╭": "+", "╮": "+", "╰": "+", "╯": "+", "─": "-", "│": "|",
    "✓": "OK", "✗": "x", "→": "->", "·": "-", "▶": ">", "…": "...",
})


def _fold_if_needed(text: str, out) -> str:
    """Fold unicode glyphs to ASCII when *out* cannot encode them (defensive;
    setup_logging already reconfigures streams to UTF-8 in the normal path)."""
    enc = getattr(out, "encoding", None) or "ascii"
    try:
        "╭✓→·▶".encode(enc)
        return text
    except (UnicodeEncodeError, LookupError):
        return text.translate(_UNI2ASCII)


def _c(text: str, key: str, color: bool) -> str:
    return f"{_PAL[key]}{text}{_PAL['reset']}" if color else text


def _bar(color: bool) -> str:
    return _c("│", "border", color)


def _row(text: str, color: bool, paint: str | None = None) -> str:
    inner = text.ljust(_W)
    if paint and color:
        inner = f"{_PAL[paint]}{inner}{_PAL['reset']}"
    return f"{_bar(color)} {inner} {_bar(color)}"


def _top(color: bool) -> str:
    return _c("╭" + "─" * (_W + 2) + "╮", "border", color)


def _bot(color: bool) -> str:
    return _c("╰" + "─" * (_W + 2) + "╯", "border", color)


def _fmt_duration(seconds: float) -> str:
    seconds = int(round(seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def _fmt_size(num_bytes: int) -> str:
    val = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if val < 1024 or unit == "TB":
            return f"{val:.1f} {unit}"
        val /= 1024
    return f"{val:.1f} TB"


def render_banner(cfg, steps, *, color: bool) -> str:
    enabled = [s["name"] for s in steps if s["action"] in ("run", "skip-cached")]
    if len(enabled) > 4:
        chain = f"{enabled[0]} → … → {enabled[-1]}  ({len(enabled)})"
    else:
        chain = " → ".join(enabled) + f"  ({len(enabled)})"
    opts = f"tenure={'on' if cfg.derived_tenure else 'off'}  " \
           f"vacancy={'on' if getattr(cfg, 'derived_vacancy', False) else 'off'}  " \
           f"sanity={cfg.sanity}"
    scope = cfg.mode + (f"  ·  version_tag = {cfg.version_tag}")
    def kv(key, val):
        return f"  {_c(key, 'key', color)}  {val}"

    lines = [
        _top(color),
        _row(f"cleancensus {__version__}", color, paint="title"),
        _row("Zensus 2022 grid harmonization pipeline", color),
        _bot(color),
        kv("config :", cfg.config_path.name),
        kv("scope  :", scope),
        kv("options:", opts),
        kv("stages :", chain),
    ]
    return "\n".join(lines)


def print_banner(cfg, steps, *, color=None, out=None) -> None:
    out = out or sys.stderr
    color = color_enabled() if color is None else color
    print(_fold_if_needed(render_banner(cfg, steps, color=color), out), file=out)


def stage_frame(k: int, n: int, name: str, last: str | None = None, *, color=None) -> str:
    color = color_enabled() if color is None else color
    head = _c(f"▶ stage {k}/{n}", "accent", color)
    nm = _c(name, "title", color)
    tail = _c(f"(last run: {last})", "key", color) if last else ""
    return f"{head} · {nm}  {tail}".rstrip()


def _row_token(prefix: str, token_plain: str, color: bool, paint: str) -> str:
    """A row whose ``token_plain`` (after ``prefix``) is colourised in place.

    Width is computed on the plain text; the zero-width ANSI codes are substituted
    afterwards so box alignment is preserved.
    """
    plain = f"{prefix}{token_plain}"
    inner = plain.ljust(_W)
    if color:
        inner = inner.replace(token_plain, f"{_PAL[paint]}{token_plain}{_PAL['reset']}", 1)
    return f"{_bar(color)} {inner} {_bar(color)}"


def render_summary(cfg, timings: dict, failures: int, outputs, total_elapsed: float,
                   *, color: bool) -> str:
    if failures == 0:
        status_plain, paint = "✓ completed, all checks passed", "ok"
    else:
        status_plain, paint = f"✗ {failures} sanity failure(s)", "err"
    lines = [
        _top(color),
        _row(f"cleancensus · run {cfg.version_tag}", color, paint="title"),
        _bot(color),
        _row_token("status :  ", status_plain, color, paint),
        _row("", color),
        _row("timings:", color),
    ]
    for name, dur in timings.items():
        lines.append(_row(f"  {name:<10}  {_fmt_duration(dur):>8}", color))
    lines.append(_row(f"  {'total':<10}  {_fmt_duration(total_elapsed):>8}", color))
    if outputs:
        lines.append(_row("", color))
        for p in outputs:
            try:
                sz = _fmt_size(p.stat().st_size)
            except OSError:
                sz = "—"
            lines.append(_row(f"output :  {p.name}  ({sz})", color))
    lines.append(_bot(color))
    return "\n".join(lines)


def print_summary(cfg, timings, failures, outputs, total_elapsed, *, color=None, out=None) -> None:
    out = out or sys.stderr
    color = color_enabled() if color is None else color
    print(_fold_if_needed(render_summary(cfg, timings, failures, outputs, total_elapsed, color=color), out), file=out)
