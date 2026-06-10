"""Pipeline entry point: run all configured stages in order with one config.

Usage:
  uv run cleancensus --config config.toml
  uv run cleancensus --config config.toml --dry-run
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone

from cleancensus import __version__
from cleancensus.config import load_config


def _git_sha() -> str:
    try:
        out = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True,
                             text=True, timeout=10, check=True)
        return out.stdout.strip()
    except Exception:
        return "unknown"


def _plan(cfg) -> list[str]:
    steps = ["stage_a (10km -> 1km)", "stage_b (1km -> 100m)"]
    if cfg.derived_tenure:
        steps.append("tenure (owner/renter from Eigentuemerquote)")
    if cfg.sanity != "skip":
        steps.append(f"sanity (mode={cfg.sanity})")
    return steps


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="cleancensus")
    ap.add_argument("--config", required=True, help="path to the TOML config")
    ap.add_argument("--dry-run", action="store_true",
                    help="print the resolved plan and exit")
    args = ap.parse_args(argv)

    cfg = load_config(args.config)

    print(f"cleancensus {__version__} | config: {cfg.config_path}")
    print(f"  scope   : {cfg.mode}"
          + (f" (ars_prefixes={cfg.ars_prefixes})" if cfg.mode == "subset" else ""))
    print(f"  topics  : {cfg.topics}")
    print(f"  tenure  : {cfg.derived_tenure}")
    print(f"  outputs : {cfg.out_1.name}, {cfg.out_100.name} (dir: {cfg.outputs_dir})")
    for i, step in enumerate(_plan(cfg), 1):
        print(f"  step {i} : {step}")
    if args.dry_run:
        return 0

    from cleancensus.sanity import run_sanity
    from cleancensus.stages import run_stage_a, run_stage_b
    from cleancensus.tenure import run_tenure

    started = datetime.now(timezone.utc).isoformat()
    timings: dict[str, float] = {}

    def timed(name, fn):
        t0 = time.perf_counter()
        fn(cfg)
        timings[name] = round(time.perf_counter() - t0, 1)

    timed("stage_a", run_stage_a)
    timed("stage_b", run_stage_b)
    if cfg.derived_tenure:
        timed("tenure", run_tenure)

    failures = 0
    if cfg.sanity != "skip":
        t0 = time.perf_counter()
        failures = run_sanity(cfg)
        timings["sanity"] = round(time.perf_counter() - t0, 1)

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
