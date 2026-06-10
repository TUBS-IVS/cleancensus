"""Single config contract for the cleancensus pipeline (TOML, stdlib tomllib)."""
from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Config:
    # [data]
    inputs_dir: Path
    outputs_dir: Path
    version_tag: str
    # [harmonize]
    topics: list[str]          # resolved topic names (after tiers/"all" expansion)
    derived_tenure: bool
    # [scope]
    mode: str                  # "national" | "subset"
    ars_prefixes: list[str]    # only for subset
    # [run]
    sanity: str                # "fail" | "warn" | "skip"
    write_manifest: bool
    # [stages] — on/off switches for the data-producing stages (full raw->final pipeline).
    # tenure is controlled by [harmonize].derived_tenure, sanity by [run].sanity.
    stages: dict             # {stage_name: bool} over PRODUCER_STAGES
    config_path: Path = field(compare=False)

    # canonical input file names (fixed contract)
    @property
    def path_10(self) -> Path:
        return self.inputs_dir / "df10_with_single_years.pickle"

    @property
    def path_1(self) -> Path:
        return self.inputs_dir / "cells_1km_with_binneds.parquet"

    @property
    def path_100(self) -> Path:
        return self.inputs_dir / "cells_100m_with_gender_backf_binneds_happyorphans_with_aggs_regiostar.parquet"

    @property
    def work_dir(self) -> Path:
        """Directory for chained intermediate artifacts of the full raw->prepared pipeline
        (S1..S8). Each producer stage reads its predecessor's output here and writes its own.
        Defaults to a sibling of inputs_dir so it is gitignored under data/."""
        return self.inputs_dir.parent / "work"

    @property
    def out_1(self) -> Path:
        return self.outputs_dir / f"cells_1km_with_binneds_{self.version_tag}.parquet"

    @property
    def out_100(self) -> Path:
        return self.outputs_dir / (
            "cells_100m_with_gender_backf_binneds_happyorphans_with_aggs_regiostar_"
            f"{self.version_tag}.parquet"
        )


# Data-producing stages, in execution order. The first 8 cover the full path from the
# raw Zensus 2022 grid CSVs to the prepared 100m cell table (ported from the archived
# notebooks); "extend" is the additional-topics harmonization. tenure/sanity are NOT
# here (driven by [harmonize].derived_tenure and [run].sanity respectively).
PRODUCER_STAGES = (
    "merge", "totals", "ages", "gemeinde", "gender", "topics8", "aggs", "regiostar",
    "extend",
)


def _resolve_stages(stages_cfg: dict) -> dict:
    unknown = set(stages_cfg) - set(PRODUCER_STAGES)
    if unknown:
        raise ValueError(
            f"[stages] unknown stage(s): {sorted(unknown)}; valid: {list(PRODUCER_STAGES)}")
    # default: only the additional-topics harmonization runs (today's behavior); the
    # raw->prepared stages are off until explicitly enabled (they consume raw CSVs).
    resolved = {s: False for s in PRODUCER_STAGES}
    resolved["extend"] = True
    for name, on in stages_cfg.items():
        resolved[name] = bool(on)
    return resolved


def _resolve_topics(harmonize: dict) -> list[str]:
    from cleancensus.topics import RAW_TOPICS, MID_CONTROLLABLE_DEFAULT

    all_names = [name for topics in RAW_TOPICS.values() for name, _, _, _ in topics]
    has_topics = "topics" in harmonize
    has_tiers = "tiers" in harmonize
    if has_topics and has_tiers:
        raise ValueError("[harmonize] set either 'topics' or 'tiers', not both")
    if has_topics:
        sel = harmonize["topics"]
        if sel == "all":
            return all_names
        unknown = set(sel) - set(all_names)
        if unknown:
            raise ValueError(f"Unknown topic names: {sorted(unknown)}; catalog has {sorted(all_names)}")
        return list(sel)
    if has_tiers:
        tiers = set(harmonize["tiers"])
        unknown_tiers = tiers - set(RAW_TOPICS)
        if unknown_tiers:
            raise ValueError(f"Unknown tiers: {sorted(unknown_tiers)}; catalog has {sorted(RAW_TOPICS)}")
        return [name for tier, topics in RAW_TOPICS.items() if tier in tiers
                for name, _, _, _ in topics]
    return list(MID_CONTROLLABLE_DEFAULT)


def load_config(path: str | Path) -> Config:
    path = Path(path).resolve()
    with open(path, "rb") as f:
        raw = tomllib.load(f)

    data = raw.get("data", {})
    harmonize = raw.get("harmonize", {})
    scope = raw.get("scope", {})
    run = raw.get("run", {})

    mode = scope.get("mode", "national")
    if mode not in ("national", "subset"):
        raise ValueError(f"[scope] mode must be 'national' or 'subset', got {mode!r}")
    ars = [str(a) for a in scope.get("ars_prefixes", [])]
    if mode == "subset" and not ars:
        raise ValueError("[scope] mode='subset' requires non-empty ars_prefixes")
    if mode == "national" and ars:
        raise ValueError("[scope] ars_prefixes is only allowed with mode='subset'")

    sanity = run.get("sanity", "fail")
    if sanity not in ("fail", "warn", "skip"):
        raise ValueError(f"[run] sanity must be 'fail'|'warn'|'skip', got {sanity!r}")

    repo_root = path.parent
    inputs_dir = (repo_root / data.get("inputs_dir", "data/inputs")).resolve()
    outputs_dir = (repo_root / data.get("outputs_dir", "data/outputs")).resolve()

    return Config(
        inputs_dir=inputs_dir,
        outputs_dir=outputs_dir,
        version_tag=str(data.get("version_tag", "v2")),
        topics=_resolve_topics(harmonize),
        derived_tenure=bool(harmonize.get("derived_tenure", False)),
        mode=mode,
        ars_prefixes=ars,
        sanity=sanity,
        write_manifest=bool(run.get("write_manifest", True)),
        stages=_resolve_stages(raw.get("stages", {})),
        config_path=path,
    )
