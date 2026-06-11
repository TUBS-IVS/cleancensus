import textwrap

import pytest

from cleancensus.config import load_config, PRODUCER_STAGES
from cleancensus.pipeline import REGISTRY, STAGE_NAMES, plan, run_pipeline


def _cfg(tmp_path, body=""):
    p = tmp_path / "config.toml"
    p.write_text(textwrap.dedent(body), encoding="utf-8")
    return load_config(p)


def test_registry_order_and_completeness():
    assert STAGE_NAMES == (
        "merge", "totals", "ages", "gemeinde", "gender", "topics8",
        "aggs", "regiostar", "extend", "tenure", "sanity",
    )
    # implemented stages (R3: merge+totals; R4: ages; R6: aggs + regiostar + topics8 + extend)
    impl = {s.name: s.implemented for s in REGISTRY}
    assert impl["merge"]  # R3: z22data ingest path
    assert impl["totals"]  # R3: population totals collapse + adjust
    assert impl["ages"]    # R4: single-year age decomposition
    assert impl["extend"] and impl["tenure"] and impl["sanity"]
    assert impl["topics8"] and impl["aggs"] and impl["regiostar"]
    # not yet implemented (R5 remaining)
    assert not any(impl[n] for n in ("gemeinde", "gender"))


def test_default_plan_only_extend_runs(tmp_path):
    # no data files in a fresh tmp inputs dir -> extend would run, tenure disabled, sanity runs
    cfg = _cfg(tmp_path, """
        [data]
        inputs_dir = "in"
        outputs_dir = "out"
    """)
    actions = {s["name"]: s["action"] for s in plan(cfg)}
    assert actions["extend"] == "run"
    assert actions["tenure"] == "skip-disabled"
    assert actions["sanity"] == "run"
    assert actions["merge"] == "skip-disabled"


def test_enabled_unimplemented_stage_is_planned(tmp_path):
    cfg = _cfg(tmp_path, """
        [stages]
        gender = true
    """)
    actions = {s["name"]: s["action"] for s in plan(cfg)}
    assert actions["gender"] == "planned"


def test_from_window_skips_earlier_even_if_enabled(tmp_path):
    cfg = _cfg(tmp_path, """
        [stages]
        gemeinde = true
        gender = true
    """)
    actions = {s["name"]: s["action"] for s in plan(cfg, from_stage="gender")}
    assert actions["gemeinde"] == "skip-cached"  # before the window, not "planned"
    assert actions["gender"] == "planned"         # in window, still unimplemented


def test_run_pipeline_raises_on_enabled_unimplemented(tmp_path):
    cfg = _cfg(tmp_path, """
        [stages]
        gender = true
        extend = false
    """)
    with pytest.raises(NotImplementedError, match="gender"):
        run_pipeline(cfg)


def test_unknown_stage_in_config_rejected(tmp_path):
    with pytest.raises(ValueError, match="unknown stage"):
        _cfg(tmp_path, """
            [stages]
            bogus = true
        """)


def test_producer_stages_constant_matches_registry():
    # every producer stage is in the registry; tenure/sanity are not producer stages
    assert set(PRODUCER_STAGES) <= set(STAGE_NAMES)
    assert "tenure" not in PRODUCER_STAGES and "sanity" not in PRODUCER_STAGES
