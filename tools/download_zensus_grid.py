"""Download official Zensus 2022 grid-data ZIPs from Destatis.

Usage:
  uv run python tools/download_zensus_grid.py --manifest tools/zensus_grid_manifest.toml --probe
  uv run python tools/download_zensus_grid.py --manifest tools/zensus_grid_manifest.toml [--out data/raw] [--only wohnungen_zahl_raeume ...]

Stdlib only (urllib, zipfile, tomllib / tomli fallback).  No additional dependencies.

Licence reminder printed at end of every run:
  dl-de/by-2-0
  Census content:  © Statistische Ämter des Bundes und der Länder, Zensus 2022
  Grid geometry:   © GeoBasis-DE / BKG 2023
"""
from __future__ import annotations

import argparse
import os
import sys
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# TOML loading — tomllib is stdlib in Python ≥ 3.11; fall back to tomli.
# ---------------------------------------------------------------------------
try:
    import tomllib  # type: ignore[import]
except ModuleNotFoundError:
    try:
        import tomli as tomllib  # type: ignore[import,no-redef]
    except ModuleNotFoundError:
        sys.exit(
            "ERROR: Python < 3.11 and 'tomli' not installed. "
            "Run: pip install tomli   or use Python 3.11+."
        )

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
USER_AGENT = (
    "Mozilla/5.0 (compatible; cleancensus-downloader/1.0; "
    "+https://github.com/bienzeisler/cleancensus)"
)
ATTRIBUTION = (
    "\nLicence: dl-de/by-2-0\n"
    "Census content : © Statistische Ämter des Bundes und der Länder, Zensus 2022\n"
    "Grid geometry  : © GeoBasis-DE / BKG 2023 (https://www.bkg.bund.de)\n"
)
PROGRESS_EVERY_BYTES = 50 * 1024 * 1024  # 50 MB
MAX_RETRIES = 3
RETRY_BACKOFF = [5, 15, 30]  # seconds between retries
PROBE_READ_BYTES = 8192  # bytes read in probe mode to confirm not HTML


# ---------------------------------------------------------------------------
# Manifest helpers
# ---------------------------------------------------------------------------

def load_manifest(path: Path) -> dict[str, Any]:
    with open(path, "rb") as f:
        return tomllib.load(f)


def build_url(base: str, blob: str, zip_slug: str) -> str:
    return f"{base}/{zip_slug}{blob}"


def get_topics(manifest: dict[str, Any], only: list[str] | None) -> list[dict[str, Any]]:
    topics = manifest.get("topic", [])
    if only:
        topics = [t for t in topics if t["name"] in only]
    return topics


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def _make_request(url: str, extra_headers: dict[str, str] | None = None):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    if extra_headers:
        for k, v in extra_headers.items():
            req.add_header(k, v)
    return req


def probe_url(url: str) -> dict[str, Any]:
    """HEAD then minimal GET to check if URL resolves to a ZIP (not HTML/404)."""
    result: dict[str, Any] = {"url": url, "status": None, "size": None, "content_type": None, "note": ""}
    try:
        req = _make_request(url)
        with urllib.request.urlopen(req, timeout=20) as resp:
            ct = resp.headers.get("Content-Type", "")
            cl = resp.headers.get("Content-Length", "")
            status = resp.status
            # Read a small chunk to detect HTML landing pages
            chunk = resp.read(PROBE_READ_BYTES)
            result["status"] = status
            result["content_type"] = ct
            result["size"] = cl
            # HTML detection: either Content-Type says text/html, or content starts with <!
            is_html = "text/html" in ct.lower() or chunk.lstrip()[:2] in (b"<!", b"<!")
            if is_html:
                result["note"] = "redirect-to-html (JS portal landing, not a data file)"
            elif "zip" in ct.lower() or "octet" in ct.lower() or "application" in ct.lower():
                size_str = f"{int(cl):,} bytes" if cl.isdigit() else "size unknown"
                result["note"] = f"OK  {size_str}"
            else:
                result["note"] = f"unexpected Content-Type: {ct!r}"
    except urllib.error.HTTPError as e:
        result["status"] = e.code
        result["note"] = f"HTTP {e.code} {e.reason}"
    except urllib.error.URLError as e:
        result["note"] = f"URLError: {e.reason}"
    except Exception as e:
        result["note"] = f"error: {e}"
    return result


# ---------------------------------------------------------------------------
# Download helpers
# ---------------------------------------------------------------------------

def _download_stream(url: str, dest: Path, expected_bytes: int | None) -> None:
    """Stream-download url to dest with optional resume."""
    resume_pos = 0
    if dest.exists():
        resume_pos = dest.stat().st_size
        if expected_bytes is not None and resume_pos >= expected_bytes:
            print(f"  [skip] already complete ({resume_pos:,} bytes)")
            return

    headers: dict[str, str] = {}
    if resume_pos > 0:
        headers["Range"] = f"bytes={resume_pos}-"
        print(f"  [resume] from byte {resume_pos:,}")

    req = _make_request(url, headers)
    mode = "ab" if resume_pos else "wb"
    written = resume_pos
    last_progress = resume_pos

    with urllib.request.urlopen(req, timeout=60) as resp:
        ct = resp.headers.get("Content-Type", "")
        if "text/html" in ct.lower():
            raise ValueError(
                f"Response is HTML, not a ZIP (JS portal redirect?). URL: {url}"
            )
        cl_header = resp.headers.get("Content-Length", "")
        total = int(cl_header) + resume_pos if cl_header.isdigit() else None
        dest.parent.mkdir(parents=True, exist_ok=True)
        with open(dest, mode) as fh:
            while True:
                chunk = resp.read(1024 * 1024)  # 1 MB chunks
                if not chunk:
                    break
                fh.write(chunk)
                written += len(chunk)
                if written - last_progress >= PROGRESS_EVERY_BYTES:
                    pct = f"{100*written/total:.1f}%" if total else "?%"
                    print(f"  ... {written/1024/1024:.0f} MB / {total/1024/1024:.0f} MB  ({pct})")
                    last_progress = written

    print(f"  downloaded {written/1024/1024:.1f} MB to {dest}")


def download_topic(url: str, zip_path: Path, csv_out: Path) -> str:
    """Download + unzip one topic.  Returns 'downloaded', 'skipped', or 'failed:<msg>'."""
    # --- Determine expected size first (HEAD request) ---
    expected: int | None = None
    try:
        req = _make_request(url)
        with urllib.request.urlopen(req, timeout=20) as resp:
            cl = resp.headers.get("Content-Length", "")
            ct = resp.headers.get("Content-Type", "")
            if "text/html" in ct.lower():
                return "failed:URL resolves to HTML (JS portal redirect — update manifest slug)"
            expected = int(cl) if cl.isdigit() else None
    except urllib.error.HTTPError as e:
        return f"failed:HTTP {e.code}"
    except Exception as e:
        return f"failed:{e}"

    if zip_path.exists() and expected is not None and zip_path.stat().st_size >= expected:
        print(f"  [skip] ZIP already complete: {zip_path}")
    else:
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                _download_stream(url, zip_path, expected)
                break
            except Exception as e:
                if attempt < MAX_RETRIES:
                    wait = RETRY_BACKOFF[attempt - 1]
                    print(f"  [warn] attempt {attempt} failed ({e}); retrying in {wait}s …")
                    time.sleep(wait)
                else:
                    return f"failed:{e}"

    # --- Unzip CSV members ---
    csv_out.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(zip_path) as zf:
            csv_members = [m for m in zf.namelist() if m.lower().endswith(".csv")]
            if not csv_members:
                print(f"  [warn] no CSV members found in {zip_path.name}")
            for member in csv_members:
                flat_name = Path(member).name
                target = csv_out / flat_name
                with zf.open(member) as src, open(target, "wb") as dst:
                    dst.write(src.read())
                print(f"  extracted: {flat_name}")
    except zipfile.BadZipFile as e:
        return f"failed:BadZipFile — {e} (partial download?)"

    return "downloaded"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def cmd_probe(manifest: dict[str, Any], topics: list[dict[str, Any]]) -> None:
    base = manifest["base"]
    blob = manifest["blob"]

    col_w = max(len(t["name"]) for t in topics)
    header = f"{'topic':<{col_w}}  {'status / note'}"
    print(header)
    print("-" * (col_w + 60))

    for t in topics:
        name = t["name"]
        zip_slug = t.get("zip", "")
        if not zip_slug:
            print(f"{name:<{col_w}}  [skip] no slug — add zip= in manifest (see TODO entries)")
            continue
        url = build_url(base, blob, zip_slug)
        result = probe_url(url)
        note = result["note"]
        print(f"{name:<{col_w}}  {note}")
        print(f"  {'URL:':<6} {url}")

    print("\nProbe complete.  Fill in missing zip= slugs from the live portal:")
    print("  https://www.zensus2022.de/DE/Ergebnisse-des-Zensus/gitterzellen.html")


def cmd_download(
    manifest: dict[str, Any],
    topics: list[dict[str, Any]],
    out_dir: Path,
) -> None:
    base = manifest["base"]
    blob = manifest["blob"]
    zip_dir = out_dir / "zips"
    csv_dir = out_dir / "csv"
    zip_dir.mkdir(parents=True, exist_ok=True)
    csv_dir.mkdir(parents=True, exist_ok=True)

    results: dict[str, str] = {}
    for t in topics:
        name = t["name"]
        zip_slug = t.get("zip", "")
        if not zip_slug:
            print(f"\n[skip] {name}: no slug in manifest (TODO)")
            results[name] = "skipped:no_slug"
            continue
        url = build_url(base, blob, zip_slug)
        zip_path = zip_dir / zip_slug
        print(f"\n[{name}] {url}")
        status = download_topic(url, zip_path, csv_dir)
        results[name] = status
        print(f"  -> {status}")

    # Summary
    downloaded = [n for n, s in results.items() if s == "downloaded"]
    skipped    = [n for n, s in results.items() if s.startswith("skipped")]
    failed     = [n for n, s in results.items() if s.startswith("failed")]

    print("\n" + "=" * 60)
    print(f"Summary: {len(downloaded)} downloaded, {len(skipped)} skipped, {len(failed)} failed")
    if failed:
        print("Failed topics:")
        for n in failed:
            print(f"  {n}: {results[n]}")

    print(f"\nUnzipped CSVs are in: {csv_dir.resolve()}")
    print(
        "The merge stage expects *_<level>-Gitter*.csv files in the directory\n"
        "pointed to by raw_dir in your config (e.g. data/raw/csv)."
    )
    print(ATTRIBUTION)


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Download Zensus 2022 grid-data ZIPs from Destatis.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  uv run python tools/download_zensus_grid.py --manifest tools/zensus_grid_manifest.toml --probe\n"
            "  uv run python tools/download_zensus_grid.py --manifest tools/zensus_grid_manifest.toml\n"
            "  uv run python tools/download_zensus_grid.py --manifest tools/zensus_grid_manifest.toml "
            "--out data/raw --only wohnungen_zahl_raeume gebaeude_baujahr\n"
        ),
    )
    ap.add_argument(
        "--manifest", required=True, type=Path,
        help="Path to zensus_grid_manifest.toml",
    )
    ap.add_argument(
        "--probe", action="store_true",
        help="Only check which candidate URLs resolve to ZIPs; do not download.",
    )
    ap.add_argument(
        "--out", type=Path, default=Path("data/raw"),
        help="Output directory; ZIPs go to <out>/zips/, unzipped CSVs to <out>/csv/. "
             "Default: data/raw",
    )
    ap.add_argument(
        "--only", nargs="+", metavar="NAME",
        help="Restrict to these topic name(s) from the manifest.",
    )
    args = ap.parse_args()

    if not args.manifest.exists():
        ap.error(f"Manifest not found: {args.manifest}")

    manifest = load_manifest(args.manifest)
    topics = get_topics(manifest, args.only)

    if not topics:
        print("No topics selected (check --only filter or manifest content).")
        return 1

    if args.probe:
        cmd_probe(manifest, topics)
    else:
        cmd_download(manifest, topics, args.out)

    return 0


if __name__ == "__main__":
    sys.exit(main())
