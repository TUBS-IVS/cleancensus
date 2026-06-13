"""Single source of truth for cleancensus artifact file names.

Public output schema is FIXED: ``zensus2022_grid_{level}_de_{tag}.parquet``.
work_dir intermediates use a stage-numbered scheme (``NN_<stage>_<level>.parquet``).
Every renamed file keeps a legacy alias so existing artifacts, gate references and
downstream consumers still resolve — callers read "new name first, then aliases" via
:func:`resolve`.
"""
from __future__ import annotations

from pathlib import Path

# canonical level spellings
LEVELS = ("10km", "1km", "100m")


_INT_LEVEL = {10: "10km", 1: "1km", 100: "100m"}


def _lvl(level) -> str:
    """Normalise a level to '10km'/'1km'/'100m'.

    Accepts the canonical strings, the resolution strings ('1000m'/'10000m'), or the
    integer shorthands 10->10km, 1->1km, 100->100m.
    """
    if isinstance(level, bool):  # guard: bool is an int subclass
        raise ValueError(f"unknown level {level!r}; expected one of {LEVELS}")
    if isinstance(level, int):
        if level not in _INT_LEVEL:
            raise ValueError(f"unknown level {level!r}; expected one of {LEVELS}")
        return _INT_LEVEL[level]
    s = {"1000m": "1km", "10000m": "10km"}.get(str(level), str(level))
    if s not in LEVELS:
        raise ValueError(f"unknown level {level!r}; expected one of {LEVELS}")
    return s


def canonical_input(level) -> str:
    """Canonical prepared-input filename for a level."""
    return f"zensus2022_grid_{_lvl(level)}_de_prepared.parquet"


def output(level, tag: str, *, subset: bool = False) -> str:
    """Final output filename. Schema is fixed; subset gets a ``_subset`` suffix."""
    suffix = "_subset" if subset else ""
    return f"zensus2022_grid_{_lvl(level)}_de_{tag}{suffix}.parquet"


# work_dir intermediates: NN_<stage>_<level>.parquet
_WORK_NUM = {
    "merge": "01", "totals": "02", "ages": "03", "gemeinde": "04",
    "gender": "05", "topics8": "06", "aggs": "07", "regiostar": "08",
}


def work(stage: str, level=None) -> str:
    """work_dir intermediate filename for a stage (optionally per level)."""
    num = _WORK_NUM[stage]
    if level is None:
        return f"{num}_{stage}.parquet"
    return f"{num}_{stage}_{_lvl(level)}.parquet"


# historical (notebook-era) names, keyed by the NEW name -> list of old names
_LEGACY: dict[str, list[str]] = {
    "01_merge_10km.parquet":  ["merged_10km_gitter.parquet"],
    "01_merge_1km.parquet":   ["merged_1km_gitter.parquet"],
    "01_merge_100m.parquet":  ["merged_100m_gitter.parquet"],
    "02_totals_10km.parquet": ["totals_10km.parquet"],
    "02_totals_1km.parquet":  ["totals_1km.parquet"],
    "02_totals_100m.parquet": ["totals_100m.parquet"],
    "03_ages_10km.parquet":   ["df10_with_single_years.parquet", "df10_with_single_years.pickle"],
    "03_ages_1km.parquet":    ["df1_with_single_years.parquet", "df1_with_single_years.pickle"],
    "03_ages_100m.parquet":   ["df100_with_single_years.parquet"],
    "04_gemeinde_100m.parquet": ["cells_100m_with_gemeinde.parquet"],
    "05_gender_100m.parquet": ["cells_100m_with_gender_backfilled.parquet"],
    "06_topics8_1km.parquet": ["cells_1km_with_binneds.parquet"],
    "06_topics8_100m.parquet": ["cells_100m_with_gender_backf_binneds_happyorphans.parquet"],
    "07_aggs_100m.parquet":   ["cells_100m_with_gender_backf_binneds_happyorphans_with_aggs.parquet"],
    "08_regiostar_100m.parquet": ["cells_100m_with_gender_backf_binneds_happyorphans_with_aggs_regiostar.parquet"],
}


def legacy_aliases(new_name: str) -> list[str]:
    """Historical filenames for a current work_dir name (for read-fallback)."""
    return list(_LEGACY.get(new_name, []))


def resolve(dir_path, new_name: str) -> Path:
    """First existing path among [new_name, *legacy_aliases] in dir_path.

    Returns ``dir_path/new_name`` (the path to write) if none exist yet.
    """
    d = Path(dir_path)
    for cand in (new_name, *legacy_aliases(new_name)):
        p = d / cand
        if p.exists():
            return p
    return d / new_name
