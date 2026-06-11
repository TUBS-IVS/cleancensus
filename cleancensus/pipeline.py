"""Stage registry and runner for the full cleancensus pipeline.

The pipeline is an ordered list of stages spanning the whole path from the raw
Zensus 2022 grid CSVs to the final prepared/harmonized cell table:

    merge -> totals -> ages -> gemeinde -> gender -> topics8 -> aggs -> regiostar
          -> extend -> tenure -> vacancy -> sanity

Each stage declares whether it is enabled (from the resolved Config), whether its
output already exists (caching), and how to run. Stages whose port from the archived
notebooks is not finished yet are marked ``implemented=False`` and raise a clear error
only if a config actually enables them — so the framework is complete and honest while
the heavy raw->prepared stages are still being ported.

Implemented raw->prepared stages (R3, R4, R5, R6):
  - merge     : ingest from z22data GitHub mirror (JsLth), build merged per-level tables (R3)
  - totals    : collapse population total columns + proportional cross-level adjustment (R3)
  - ages      : single-year age decomposition AGE_0..AGE_100 via trust-mixed IPF (R4)
  - gemeinde  : spatial join of BKG VG250 Gemeinde polygons -> ARS/Land/Kreis/... (R5)
  - gender    : male/female split via GENESIS 1000A-2027 Gemeinde shares + orphan backfill (R5)
  - topics8   : port of notebooks_archive/other_binned_data.ipynb
  - aggs      : decade-binned gendered age aggregates + totals (reconstructed, R6)
  - regiostar : BBSR RegioStaR 2022 municipality classification join (reconstructed, R6)

tenure, vacancy and sanity are not "producer" stages: tenure is gated by
``[harmonize].derived_tenure``, vacancy by ``[harmonize].derived_vacancy``,
and sanity by ``[run].sanity`` (skip = off).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from cleancensus.config import Config


@dataclass(frozen=True)
class Stage:
    name: str
    desc: str
    enabled: Callable[[Config], bool]
    run: Callable[[Config], object]          # returns None, or int (sanity failure count)
    is_complete: Callable[[Config], bool] = lambda cfg: False
    implemented: bool = True


# --- helpers ---------------------------------------------------------------

def _final_100m_path(cfg: Config):
    """Where the 100m output of the extend stage lands (subset writes a *_SUBSET file)."""
    if cfg.mode == "subset":
        return cfg.out_100.with_name(cfg.out_100.stem + "_SUBSET.parquet")
    return cfg.out_100


def _extend_complete(cfg: Config) -> bool:
    out100 = _final_100m_path(cfg)
    return cfg.out_1.exists() and out100.exists()


def _tenure_complete(cfg: Config) -> bool:
    import pyarrow.parquet as pq

    out100 = _final_100m_path(cfg)
    if not out100.exists():
        return False
    names = set(pq.ParquetFile(out100).schema_arrow.names)
    return "EigentuemerHH_Tenure_100m-Gitter" in names


def _vacancy_complete(cfg: Config) -> bool:
    import pyarrow.parquet as pq

    out100 = _final_100m_path(cfg)
    if not out100.exists():
        return False
    names = set(pq.ParquetFile(out100).schema_arrow.names)
    return "BewohntWhg_Leerstand_100m-Gitter" in names


def _not_implemented(stage_name: str, phase: str):
    def _run(cfg: Config):
        raise NotImplementedError(
            f"stage '{stage_name}' is planned (refactor phase {phase}) but not yet "
            f"implemented. Disable it in [stages] or supply the prepared input files "
            f"and run only 'extend'."
        )
    return _run


# --- registry --------------------------------------------------------------

def _producer_enabled(name: str):
    return lambda cfg: cfg.stages.get(name, False)


REGISTRY: tuple[Stage, ...] = (
    Stage("merge", "z22data parquets -> merged per-level tables (10km/1km/100m)",
          _producer_enabled("merge"), None),  # run set below
    Stage("totals", "collapse pop totals + proportional adjustment across levels",
          _producer_enabled("totals"), None),  # run set below
    Stage("ages", "single-year age columns AGE_0..AGE_100 via trust-mixed IPF",
          _producer_enabled("ages"), None),  # run set below
    Stage("gemeinde", "join Gemeinde/Kreis/ARS attributes onto 100m cells",
          _producer_enabled("gemeinde"), None),  # run set below
    Stage("gender", "male/female age split at 100m + orphan backfill",
          _producer_enabled("gender"), None),  # run set below
    Stage("topics8", "harmonize the 8 original categorical topics + orphan pass",
          _producer_enabled("topics8"), None),  # run set below
    Stage("aggs", "M_AGE/F_AGE binned aggregate columns",
          _producer_enabled("aggs"), None),  # run set below
    Stage("regiostar", "join RegioStaR 2022 classification",
          _producer_enabled("regiostar"), None),  # run set below
    Stage("extend", "harmonize the additional topics (stage_a 10km->1km, stage_b 1km->100m)",
          _producer_enabled("extend"), None, _extend_complete),  # run set below
    Stage("tenure", "derive owner/renter households from Eigentuemerquote",
          lambda cfg: cfg.derived_tenure, None, _tenure_complete),  # run set below
    Stage("vacancy", "derive occupied/vacant dwellings from Leerstandsquote",
          lambda cfg: cfg.derived_vacancy, None, _vacancy_complete),  # run set below
    Stage("sanity", "invariant checks on the produced output",
          lambda cfg: cfg.sanity != "skip", None,
          lambda cfg: False),  # run set below; never cached
)


def _run_totals(cfg: Config):
    from cleancensus.ingest_totals import run_totals
    run_totals(cfg)


def _totals_complete(cfg: Config) -> bool:
    from cleancensus.ingest_totals import totals_complete
    return totals_complete(cfg)


def _run_ages(cfg: Config):
    from cleancensus.ages_stage import run_ages
    run_ages(cfg)


def _ages_complete(cfg: Config) -> bool:
    from cleancensus.ages_stage import ages_complete
    return ages_complete(cfg)


def _run_merge(cfg: Config):
    from cleancensus.z22 import run_merge_z22
    run_merge_z22(cfg)


def _merge_complete(cfg: Config) -> bool:
    from cleancensus.z22 import merge_complete
    return merge_complete(cfg)


def _run_gemeinde(cfg: Config):
    from cleancensus.gemeinde_stage import run_gemeinde
    run_gemeinde(cfg)


def _gemeinde_complete(cfg: Config) -> bool:
    from cleancensus.gemeinde_stage import gemeinde_complete
    return gemeinde_complete(cfg)


def _run_gender(cfg: Config):
    from cleancensus.gender_stage import run_gender
    run_gender(cfg)


def _gender_complete(cfg: Config) -> bool:
    from cleancensus.gender_stage import gender_complete
    return gender_complete(cfg)


def _run_topics8(cfg: Config):
    from cleancensus.topics8 import run_topics8
    run_topics8(cfg)


def _topics8_complete(cfg: Config) -> bool:
    out_100 = cfg.work_dir / "cells_100m_with_gender_backf_binneds_happyorphans.parquet"
    return out_100.exists()


def _run_aggs(cfg: Config):
    from cleancensus.enrich import run_aggs
    run_aggs(cfg)


def _run_regiostar(cfg: Config):
    from cleancensus.enrich import run_regiostar
    run_regiostar(cfg)


def _aggs_complete(cfg: Config) -> bool:
    from cleancensus.enrich import aggs_complete
    return aggs_complete(cfg)


def _regiostar_complete(cfg: Config) -> bool:
    from cleancensus.enrich import regiostar_complete
    return regiostar_complete(cfg)


def _run_extend(cfg: Config):
    from cleancensus.stages import run_stage_a, run_stage_b
    run_stage_a(cfg)
    run_stage_b(cfg)


def _run_tenure(cfg: Config):
    from cleancensus.tenure import run_tenure
    run_tenure(cfg)


def _run_vacancy(cfg: Config):
    from cleancensus.vacancy import run_vacancy
    run_vacancy(cfg)


def _run_sanity(cfg: Config) -> int:
    from cleancensus.sanity import run_sanity
    return run_sanity(cfg)


# wire the implemented run callables (kept out of the literal to avoid import cost on import)
_RUN = {
    "merge": _run_merge,
    "totals": _run_totals,
    "ages": _run_ages,
    "gemeinde": _run_gemeinde,
    "gender": _run_gender,
    "topics8": _run_topics8,
    "aggs": _run_aggs,
    "regiostar": _run_regiostar,
    "extend": _run_extend,
    "tenure": _run_tenure,
    "vacancy": _run_vacancy,
    "sanity": _run_sanity,
}
_IS_COMPLETE = {
    "merge": _merge_complete,
    "totals": _totals_complete,
    "ages": _ages_complete,
    "gemeinde": _gemeinde_complete,
    "gender": _gender_complete,
    "topics8": _topics8_complete,
    "aggs": _aggs_complete,
    "regiostar": _regiostar_complete,
    "vacancy": _vacancy_complete,
}
REGISTRY = tuple(
    Stage(s.name, s.desc, s.enabled, _RUN.get(s.name, s.run),
          _IS_COMPLETE.get(s.name, s.is_complete), s.implemented)
    for s in REGISTRY
)

STAGE_NAMES = tuple(s.name for s in REGISTRY)


# --- planning & execution --------------------------------------------------

def plan(cfg: Config, force: bool = False, from_stage: str | None = None) -> list[dict]:
    """Return the resolved execution plan: one entry per stage with its action.

    action in {"run", "skip-disabled", "skip-cached", "planned"}.
    """
    if from_stage is not None and from_stage not in STAGE_NAMES:
        raise ValueError(f"--from: unknown stage {from_stage!r}; valid: {list(STAGE_NAMES)}")
    from_idx = STAGE_NAMES.index(from_stage) if from_stage else 0

    out = []
    for i, s in enumerate(REGISTRY):
        if not s.enabled(cfg):
            action = "skip-disabled"
        elif i < from_idx:
            action = "skip-cached"  # before the --from window: treated as already done
        elif not s.implemented:
            action = "planned"
        elif not force and s.is_complete(cfg):
            action = "skip-cached"
        else:
            action = "run"
        out.append({"name": s.name, "desc": s.desc, "action": action})
    return out


def run_pipeline(cfg: Config, force: bool = False, from_stage: str | None = None):
    """Execute the enabled stages in order. Returns (timings, sanity_failures).

    Raises NotImplementedError if a config enables a not-yet-implemented stage.
    """
    import time

    from cleancensus.progress import format_duration, load_stage_timings, save_stage_timings

    steps = plan(cfg, force=force, from_stage=from_stage)
    by_name = {s.name: s for s in REGISTRY}
    timings: dict[str, float] = {}
    sanity_failures = 0

    # Load previous per-stage timings for ETA estimation
    timings_path = cfg.outputs_dir / ".stage_timings.json"
    try:
        cfg.outputs_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    prev_timings = load_stage_timings(timings_path)

    # Determine which stages will actually run (for k-of-N banner)
    running_stages = [s["name"] for s in steps if s["action"] == "run"]
    N = len(running_stages)
    k = 0  # 1-based counter, incremented before each run

    pipeline_t0 = time.perf_counter()

    for step in steps:
        name, action = step["name"], step["action"]
        if action == "planned":
            # an enabled-but-unimplemented stage is a hard error (don't silently skip)
            by_name[name].run(cfg)  # raises NotImplementedError
        if action != "run":
            print(f"[pipeline] {name}: {action}")
            continue

        k += 1
        # --- pre-stage banner -----------------------------------------------
        prev_dur = prev_timings.get(name)
        prev_str = f"~{format_duration(prev_dur)}" if prev_dur is not None else "n/a"
        print(f"[pipeline] ===== stage {k}/{N}: {name} ===== (last run: {prev_str})")

        t0 = time.perf_counter()
        result = by_name[name].run(cfg)
        stage_dur = round(time.perf_counter() - t0, 1)
        timings[name] = stage_dur

        # --- post-stage summary ---------------------------------------------
        pipeline_elapsed = time.perf_counter() - pipeline_t0
        # ETA: sum of previous-run durations for stages not yet run
        not_yet_run = running_stages[k:]  # stages after the current one (k is 1-based, list is 0-based)
        remaining_known = [prev_timings.get(s) for s in not_yet_run]
        if all(v is not None for v in remaining_known) and remaining_known:
            eta_str = f"~{format_duration(sum(remaining_known))}"  # type: ignore[arg-type]
        elif remaining_known:
            eta_str = "n/a (some stages have no prior timing)"
        else:
            eta_str = "n/a"

        print(
            f"[pipeline] {name} done in {format_duration(stage_dur)} "
            f"| pipeline elapsed {format_duration(pipeline_elapsed)} "
            f"| remaining ETA {eta_str}"
        )

        if name == "sanity" and isinstance(result, int):
            sanity_failures = result

    # Persist updated timings (merge: only overwrite stages that ran)
    save_stage_timings(timings_path, timings)

    return timings, sanity_failures
