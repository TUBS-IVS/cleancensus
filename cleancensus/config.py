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
    derived_vacancy: bool
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
    # [data] RegioStaR reference — override the BBSR Gebietsstand 31.12.2022 default.
    # Default is the BBSR Referenz Gemeinden Gebietsstand 31.12.2022 workbook in
    # data/raw/regiostar/. Fall back to the BMDV Gebietsstand2020 file if absent.
    regiostar_ref: Path | None = field(default=None, compare=False)
    regiostar_sheet: str = field(default="", compare=False)
    # [data] external reference file paths for the gemeinde and gender stages.
    # Resolution order: (1) config key if set, (2) data/raw/ local copy, (3) T: legacy path.
    # Both default to None — the stages resolve them via _resolve_vg250 / _resolve_1000a_csv.
    vg250_gpkg_path: Path | None = field(default=None, compare=False)
    gemeinde_age_csv_path: Path | None = field(default=None, compare=False)

    # canonical input file names — prefer new clean names, fall back to legacy names.
    @property
    def path_10(self) -> Path:
        """Return the 10 km input path.

        Preference order (first that exists wins; if neither exists, return the
        canonical clean name so downstream code gets a clear missing-file error):
          1. zensus2022_grid_10km_de_prepared.parquet
          2. zensus2022_grid_10km_de_prepared.pickle  (pickle fallback for parquet)
          3. df10_with_single_years.pickle             (legacy notebook-era name)
        """
        for name in (
            "zensus2022_grid_10km_de_prepared.parquet",
            "zensus2022_grid_10km_de_prepared.pickle",
            "df10_with_single_years.pickle",
        ):
            p = self.inputs_dir / name
            if p.exists():
                return p
        # Neither exists — return canonical clean name (clear error on open)
        return self.inputs_dir / "zensus2022_grid_10km_de_prepared.parquet"

    @property
    def path_1(self) -> Path:
        """Return the 1 km input path.

        Preference order:
          1. zensus2022_grid_1km_de_prepared.parquet
          2. cells_1km_with_binneds.parquet  (legacy notebook-era name)
        """
        for name in (
            "zensus2022_grid_1km_de_prepared.parquet",
            "cells_1km_with_binneds.parquet",
        ):
            p = self.inputs_dir / name
            if p.exists():
                return p
        return self.inputs_dir / "zensus2022_grid_1km_de_prepared.parquet"

    @property
    def path_100(self) -> Path:
        """Return the 100 m input path.

        Preference order:
          1. zensus2022_grid_100m_de_prepared.parquet
          2. cells_100m_with_gender_backf_binneds_happyorphans_with_aggs_regiostar.parquet
             (legacy notebook-era name)
        """
        for name in (
            "zensus2022_grid_100m_de_prepared.parquet",
            "cells_100m_with_gender_backf_binneds_happyorphans_with_aggs_regiostar.parquet",
        ):
            p = self.inputs_dir / name
            if p.exists():
                return p
        return self.inputs_dir / "zensus2022_grid_100m_de_prepared.parquet"

    @property
    def work_dir(self) -> Path:
        """Directory for chained intermediate artifacts of the full raw->prepared pipeline
        (S1..S8). Each producer stage reads its predecessor's output here and writes its own.
        Defaults to a sibling of inputs_dir so it is gitignored under data/."""
        return self.inputs_dir.parent / "work"

    @property
    def resolved_path_10(self) -> Path:
        """Prefer the work_dir artifact when the producer stage is enabled (full-mode chain),
        else fall back to the prepared file in inputs_dir.

        When stage 'ages' is enabled, the ages stage writes
        work_dir/df10_with_single_years.parquet (parquet format).
        Otherwise falls back to cfg.path_10 (pickle in inputs_dir).
        """
        if self.stages.get("ages", False):
            return self.work_dir / "df10_with_single_years.parquet"
        return self.path_10

    @property
    def resolved_path_1(self) -> Path:
        """Prefer the work_dir artifact when the producer stage is enabled (full-mode chain),
        else fall back to the prepared file in inputs_dir.

        When stage 'topics8' is enabled, the topics8 stage writes
        work_dir/cells_1km_with_binneds.parquet.
        Otherwise falls back to cfg.path_1.
        """
        if self.stages.get("topics8", False):
            return self.work_dir / "cells_1km_with_binneds.parquet"
        return self.path_1

    @property
    def resolved_path_100(self) -> Path:
        """Prefer the work_dir artifact when the producer stage is enabled (full-mode chain),
        else fall back to the prepared file in inputs_dir.

        When stage 'regiostar' is enabled, the regiostar stage writes
        work_dir/cells_100m_with_gender_backf_binneds_happyorphans_with_aggs_regiostar.parquet.
        Otherwise falls back to cfg.path_100.
        """
        if self.stages.get("regiostar", False):
            return (
                self.work_dir
                / "cells_100m_with_gender_backf_binneds_happyorphans_with_aggs_regiostar.parquet"
            )
        return self.path_100

    @property
    def destatis_raw_dir(self) -> Path:
        """Directory containing the 6 Destatis CSV ZIPs (copied from Downloads).
        Defaults to data/raw/destatis (sibling of inputs_dir, gitignored).
        Create it and populate it before enabling the merge stage.
        """
        return self.inputs_dir.parent / "raw" / "destatis"

    @property
    def out_1(self) -> Path:
        return self.outputs_dir / f"zensus2022_grid_1km_de_{self.version_tag}.parquet"

    @property
    def out_100(self) -> Path:
        return self.outputs_dir / f"zensus2022_grid_100m_de_{self.version_tag}.parquet"


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

    # RegioStaR reference: explicit TOML override, otherwise None (enrich.py auto-discovers)
    regiostar_ref_raw = data.get("regiostar_ref", None)
    regiostar_ref: Path | None = (
        (repo_root / regiostar_ref_raw).resolve() if regiostar_ref_raw is not None else None
    )
    regiostar_sheet: str = str(data.get("regiostar_sheet", ""))

    # External reference file paths for gemeinde and gender stages.
    # None means the stage will use the data/raw/ local copy or the T: legacy path.
    vg250_raw = data.get("vg250_gpkg_path", None)
    vg250_gpkg_path: Path | None = (
        (repo_root / vg250_raw).resolve() if vg250_raw is not None else None
    )
    gemeinde_csv_raw = data.get("gemeinde_age_csv_path", None)
    gemeinde_age_csv_path: Path | None = (
        (repo_root / gemeinde_csv_raw).resolve() if gemeinde_csv_raw is not None else None
    )

    return Config(
        inputs_dir=inputs_dir,
        outputs_dir=outputs_dir,
        version_tag=str(data.get("version_tag", "v2")),
        topics=_resolve_topics(harmonize),
        derived_tenure=bool(harmonize.get("derived_tenure", False)),
        derived_vacancy=bool(harmonize.get("derived_vacancy", False)),
        mode=mode,
        ars_prefixes=ars,
        sanity=sanity,
        write_manifest=bool(run.get("write_manifest", True)),
        stages=_resolve_stages(raw.get("stages", {})),
        config_path=path,
        regiostar_ref=regiostar_ref,
        regiostar_sheet=regiostar_sheet,
        vg250_gpkg_path=vg250_gpkg_path,
        gemeinde_age_csv_path=gemeinde_age_csv_path,
    )
