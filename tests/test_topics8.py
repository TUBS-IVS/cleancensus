"""Unit tests for the topics8 stage (no heavy IO)."""
from __future__ import annotations


def test_topics8_uses_original_8_specs():
    """Verify build_topic_specs_for_level returns exactly the 8 original topic names."""
    from cleancensus.harmonization import build_topic_specs_for_level

    specs = build_topic_specs_for_level("100m")
    names = {s.name for s in specs}
    expected = {
        "Familienstand",
        "Energietraeger",
        "Heizungsart",
        "Haushaltsgroesse",
        "Lebensform",
        "Raeume",
        "Wohnflaeche",
        "Geburtsland",
    }
    assert names == expected, f"Got {names}, expected {expected}"


def test_topics8_stage_implemented():
    """Verify the topics8 stage is registered as implemented in the pipeline."""
    from cleancensus.pipeline import REGISTRY

    matches = [s for s in REGISTRY if s.name == "topics8"]
    assert len(matches) == 1, "topics8 stage not found in REGISTRY"
    assert matches[0].implemented, "topics8 stage is not marked as implemented"
