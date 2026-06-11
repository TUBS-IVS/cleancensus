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
from datetime import datetime, timezone

from cleancensus import __version__
from cleancensus.config import load_config
from cleancensus.pipeline import plan, run_pipeline


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
    args = ap.parse_args(argv)

    cfg = load_config(args.config)

    # --gemeinde-controls: parse Regionaltabellen and exit
    if args.gemeinde_controls:
        from cleancensus.gemeinde_controls import run_gemeinde_controls
        print(f"cleancensus {__version__} | config: {cfg.config_path}")
        print("[gemeinde-controls] parsing Regionaltabelle_Bildung_Erwerbstaetigkeit.xlsx ...")
        run_gemeinde_controls(cfg, fill=args.fill)
        print("[gemeinde-controls] done")
        return 0

    steps = plan(cfg, force=args.force, from_stage=args.from_stage)

    print(f"cleancensus {__version__} | config: {cfg.config_path}")
    print(f"  scope   : {cfg.mode}"
          + (f" (ars_prefixes={cfg.ars_prefixes})" if cfg.mode == "subset" else ""))
    print(f"  topics  : {cfg.topics}")
    print(f"  tenure  : {cfg.derived_tenure} | sanity: {cfg.sanity}")
    print(f"  outputs : {cfg.out_1.name}, {cfg.out_100.name} (dir: {cfg.outputs_dir})")
    print("  plan:")
    for i, step in enumerate(steps, 1):
        print(f"    {i:>2}. {step['name']:<10} [{step['action']:<13}] {step['desc']}")
    if args.dry_run:
        return 0

    started = datetime.now(timezone.utc).isoformat()
    timings, failures = run_pipeline(cfg, force=args.force, from_stage=args.from_stage)

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
        print(f"[manifest] wrote {mpath}")

    if failures and cfg.sanity == "fail":
        print(f"[cleancensus] FAILED: {failures} sanity failure(s)")
        return 1
    if failures:
        print(f"[cleancensus] completed with {failures} sanity warning(s)")
    else:
        print("[cleancensus] completed, all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
