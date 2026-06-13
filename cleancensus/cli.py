"""Pipeline entry point: run all configured stages in order with one config.

Usage:
  uv run cleancensus --config config.toml
  uv run cleancensus --config config.toml --dry-run
  uv run cleancensus --config config.toml --force
  uv run cleancensus --config config.toml --from gender
  uv run cleancensus --config config.toml --gemeinde-controls
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone

from cleancensus import __version__, report
from cleancensus.config import load_config
from cleancensus.logsetup import get_logger, setup_logging
from cleancensus.pipeline import plan, run_pipeline

log = get_logger("cli")


def _git_sha() -> str:
    try:
        out = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True,
                             text=True, timeout=10, check=True)
        return out.stdout.strip()
    except Exception:
        return "unknown"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="cleancensus")
    ap.add_argument("--config", required=True, help="path to the TOML config")
    ap.add_argument("--dry-run", action="store_true",
                    help="print the resolved plan and exit")
    ap.add_argument("--force", action="store_true",
                    help="re-run enabled stages even if their output already exists")
    ap.add_argument("--from", dest="from_stage", default=None,
                    help="run from this stage onward (earlier enabled stages are skipped)")
    ap.add_argument(
        "--gemeinde-controls",
        action="store_true",
        dest="gemeinde_controls",
        help=(
            "Parse Zensus Regionaltabellen (P2/P4) into Gemeinde-level control tables "
            "(Erwerbsstatus, Schulabschluss, berufl. Abschluss) and write parquets to "
            "outputs_dir/gemeinde_controls/. Also writes Kreis-level tables "
            "(kreis_erwerbsstatus, kreis_schulabschluss, kreis_berufl_abschluss) which "
            "have 0% suppression. Runs immediately after config load; "
            "skips all pipeline stages. Source file: "
            "data/raw/regionaltabellen/Regionaltabelle_Bildung_Erwerbstaetigkeit.xlsx "
            "(or set regionaltabellen_xlsx in your config)."
        ),
    )
    ap.add_argument(
        "--fill",
        dest="fill",
        choices=["none", "harmonize"],
        default="none",
        help=(
            "Suppression handling for Gemeinde tables (requires --gemeinde-controls). "
            "none (default): keep NaN for suppressed cells. "
            "harmonize: fill suppressed cells using Kreis-level distribution downscaling "
            "(population-weighted remainder allocation + trust-blended IPF). "
            "Adds is_estimated bool column. "
            "Requires data/raw/regionaltabellen/Regionaltabelle_Bevoelkerung.xlsx."
        ),
    )
    ap.add_argument("-v", "--verbose", action="store_true",
                    help="verbose logging (DEBUG): per-cell diagnostics, every detail")
    ap.add_argument("-q", "--quiet", action="store_true",
                    help="quiet logging (WARNING): only warnings and errors")
    args = ap.parse_args(argv)

    level = "DEBUG" if args.verbose else "WARNING" if args.quiet else "INFO"
    setup_logging(level)

    cfg = load_config(args.config)

    # --gemeinde-controls: parse Regionaltabellen and exit
    if args.gemeinde_controls:
        from cleancensus.gemeinde_controls import run_gemeinde_controls
        log.info("parsing Regionaltabelle_Bildung_Erwerbstaetigkeit.xlsx ...")
        run_gemeinde_controls(cfg, fill=args.fill)
        log.info("gemeinde-controls done")
        return 0

    steps = plan(cfg, force=args.force, from_stage=args.from_stage)

    report.print_banner(cfg, steps)
    log.info("topics : %s", ", ".join(cfg.topics))
    log.info("outputs: %s, %s  (dir: %s)", cfg.out_1.name, cfg.out_100.name, cfg.outputs_dir)
    for i, step in enumerate(steps, 1):
        log.info("  %2d. %-10s [%-13s] %s", i, step["name"], step["action"], step["desc"])
    if args.dry_run:
        return 0

    started = datetime.now(timezone.utc).isoformat()
    t0 = time.perf_counter()
    timings, failures = run_pipeline(cfg, force=args.force, from_stage=args.from_stage)
    total_elapsed = time.perf_counter() - t0

    if cfg.write_manifest:
        manifest = {
            "cleancensus_version": __version__,
            "git_sha": _git_sha(),
            "config_file": str(cfg.config_path),
            "config_resolved": {
                "version_tag": cfg.version_tag,
                "topics": cfg.topics,
                "derived_tenure": cfg.derived_tenure,
                "mode": cfg.mode,
                "ars_prefixes": cfg.ars_prefixes,
                "sanity": cfg.sanity,
                "stages": cfg.stages,
            },
            "started_utc": started,
            "finished_utc": datetime.now(timezone.utc).isoformat(),
            "timings_seconds": timings,
            "sanity_failures": failures,
            "outputs": {
                p.name: p.stat().st_size
                for p in (cfg.out_1, cfg.out_100,
                          cfg.out_100.with_name(cfg.out_100.stem + "_SUBSET.parquet"))
                if p.exists()
            },
        }
        mpath = cfg.outputs_dir / f"run_manifest_{cfg.version_tag}.json"
        mpath.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        log.info("wrote manifest %s", mpath.name)

    existing_outputs = [p for p in (cfg.out_1, cfg.out_100) if p.exists()]
    report.print_summary(cfg, timings, failures, existing_outputs, total_elapsed)
    return 1 if (failures and cfg.sanity == "fail") else 0


if __name__ == "__main__":
    sys.exit(main())
