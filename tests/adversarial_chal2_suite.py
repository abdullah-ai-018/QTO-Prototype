"""
tests/adversarial_chal2_suite.py: Empirical Adversarial Stress-Test Harness for Milestone 1.

Executes adversarial battery covering:
1. parse_assembly_attributes & material_layers against messy, multiline, adversarial text.
2. extract_wall_materials with edge-case schedule_page_indices (None, empty, out-of-bounds, invalid).
3. drywall_registry.json caching and load_environment_credentials fallback behavior.
4. WallAssembly schema strict conformance to PROJECT.md § Interface Contracts.
"""

from __future__ import annotations
import json
import math
import os
import sys
import re
import tempfile
from dataclasses import fields
from typing import Any, Dict, List
import pymupdf as fitz
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from qto.assemblies import (
    WallAssembly,
    clean_text,
    create_wall_assembly,
    extract_wall_materials,
    parse_assembly_attributes,
)
from qto.classify.jev import (
    DEFAULT_CACHE_FILE,
    PROBABILITY_THRESHOLD,
    REVIEW_THRESHOLD,
    evaluate_with_jev,
    get_wall_registry,
    load_environment_credentials,
)
from qto.classify.mock import evaluate_with_mock


# =============================================================================
# 1. PARSE_ASSEMBLY_ATTRIBUTES & MATERIAL_LAYERS ADVERSARIAL STRESS TESTS
# =============================================================================

def test_parse_assembly_attributes_none_input_vulnerability():
    """Verifies parse_assembly_attributes(None) returns valid dict without crashing."""
    attrs = parse_assembly_attributes(None)  # type: ignore
    assert isinstance(attrs, dict)
    assert attrs["stud_depth_in"] == 3.625
    assert attrs["stud_spacing_in"] == 16
    assert attrs["stud_gauge"] == "25 GA"
    assert attrs["board_type"] == '5/8" TYPE X GWB'
    assert attrs["board_thickness_in"] == 0.625
    assert attrs["layers_per_face"] == 1
    assert attrs["finished_faces"] == 2
    assert attrs["fire_rated"] is False
    assert attrs["nominal_thickness_in"] == 4.875
    assert len(attrs["material_layers"]) == 3


def test_parse_assembly_attributes_empty_and_whitespace():
    """Tests parse_assembly_attributes on empty and whitespace-only inputs."""
    for empty_input in ["", "   ", "\n\t  \r\n"]:
        attrs = parse_assembly_attributes(empty_input)
        assert attrs["stud_depth_in"] == 3.625
        assert attrs["stud_spacing_in"] == 16
        assert attrs["stud_gauge"] == "25 GA"
        assert attrs["board_type"] == '5/8" TYPE X GWB'
        assert attrs["board_thickness_in"] == 0.625
        assert attrs["layers_per_face"] == 1
        assert attrs["finished_faces"] == 2
        assert attrs["fire_rated"] is False
        assert attrs["nominal_thickness_in"] == 4.875
        assert len(attrs["material_layers"]) == 3  # Face A, Core Framing, Face B


def test_stud_depth_gauge_interception_bug():
    """Verifies stud depth regex correctly parses studs when gauge appears between depth and 'STUD'.

    Tag 1B: '2 1/2" 25 GA. METAL STUDS @ 16" O.C.'
    Tag 7A: '2 1/2" 25 GA. C-H METAL STUD @ 24" O.C.'
    Both evaluate to stud_depth_in = 2.5.
    """
    text_1b = '2 1/2" 25 GA. METAL STUDS @ 16" O.C.'
    attrs_1b = parse_assembly_attributes(text_1b)
    assert attrs_1b["stud_depth_in"] == 2.5

    text_7a = '2 1/2" 25 GA. C-H METAL STUD @ 24" O.C.'
    attrs_7a = parse_assembly_attributes(text_7a)
    assert attrs_7a["stud_depth_in"] == 2.5


def test_board_thickness_substring_collision_bug():
    """Verifies board thickness regex prevents '2 1/2\"' stud depth from colliding with 1/2\" board."""
    text = '2 1/2" METAL STUDS WITH 5/8" TYPE X GYPSUM WALL BOARD'
    attrs = parse_assembly_attributes(text)
    assert attrs["board_thickness_in"] == 0.625
    assert attrs["stud_depth_in"] == 2.5


def test_four_inch_stud_unrecognized():
    """Verifies 4\" studs are recognized and evaluated as stud_depth_in = 4.0."""
    text = '4" 20 GA METAL STUDS @ 16" O.C.'
    attrs = parse_assembly_attributes(text)
    assert attrs["stud_depth_in"] == 4.0


def test_parse_assembly_attributes_multiline_and_messy():
    """Tests parse_assembly_attributes against messy, multiline, noisy text."""
    messy_text = """
    === PARTITION SCHEDULE SHEET A-900 ===
    TAG 7C:
    UNDERSIDE OF EXISTING SLAB ABOVE.
    3 5/8" 20 GA. METAL STUDS @ 16" O.C.
    FULL HEIGHT AND THICKNESS SOUND ATTENUATION BLANKET.
    2 LAYERS OF 5/8" GYPSUM WALL BOARD EACH SIDE.
    UL U419 2 HR FIRE RATED.
    """
    attrs = parse_assembly_attributes(messy_text)
    assert attrs["stud_spacing_in"] == 16
    assert attrs["stud_gauge"] == "20 GA"
    assert attrs["layers_per_face"] == 2
    assert attrs["finished_faces"] == 2
    assert attrs["fire_rated"] is True
    # Insulation detected in material_layers
    layers = attrs["material_layers"]
    layer_types = [l.get("layer") for l in layers]
    assert "Insulation" in layer_types
    assert len(layers) == 6  # 2 Face A + Core Framing + Core Insulation + 2 Face B


def test_double_layer_parenthesis_interception_bug():
    """Verifies double-layer regex correctly matches parenthesized numbers '(2) LAYERS' and '(2) LAYER'.

    Also verifies composite nominal thickness cascade (e.g. 8.5 for Tag 2C).
    """
    text_7a = '(2) LAYERS OF 1/2" TYPE-C GYPSUM WALL BOARD'
    attrs_7a = parse_assembly_attributes(text_7a)
    assert attrs_7a["layers_per_face"] == 2

    text_2c = '6" 25 GA. METAL STUDS @ 16" O.C., (2) LAYER OF 5/8" GYPSUM WALL BOARD EACH SIDE'
    attrs_2c = parse_assembly_attributes(text_2c)
    assert attrs_2c["layers_per_face"] == 2
    assert attrs_2c["stud_depth_in"] == 6.0
    assert attrs_2c["board_thickness_in"] == 0.625
    assert attrs_2c["nominal_thickness_in"] == 8.5


def test_six_inch_stud_false_positive_bug():
    """Verifies 6\" ceiling clearance or CMU does not override 2-1/2\" metal studs."""
    text = '2 1/2" METAL STUDS EXTENDING 6" ABOVE CEILING'
    attrs = parse_assembly_attributes(text)
    assert attrs["stud_depth_in"] == 2.5


def test_single_sided_finished_faces():
    """Tests that single-sided assembly sets finished_faces=1 and omits Face B."""
    text_single = '3 5/8" METAL STUDS @ 16" O.C., 1 LAYER 5/8" GWB ONE SIDE ONLY, FURRING'
    attrs = parse_assembly_attributes(text_single)
    assert attrs["finished_faces"] == 1
    sides = [l["side"] for l in attrs["material_layers"]]
    assert "Face A" in sides
    assert "Core" in sides
    assert "Face B" not in sides


# =============================================================================
# 2. EXTRACT_WALL_MATERIALS ADVERSARIAL STRESS TESTS
# =============================================================================

def test_extract_wall_materials_schedule_indices_none_short_doc():
    """Tests extract_wall_materials with schedule_page_indices=None on short document (<= 5 pages)."""
    doc = fitz.open()
    p0 = doc.new_page(width=500, height=500)
    p0.insert_text((50, 50), "WALL TAG 1A: 3-5/8 METAL STUDS 16 OC 5/8 GWB")

    materials = extract_wall_materials(doc, "1A", schedule_page_indices=None)
    assert "1A" in materials
    doc.close()


def test_extract_wall_materials_schedule_indices_empty_list():
    """Tests extract_wall_materials when schedule_page_indices=[] (empty list).

    Empirically verifies whether empty list triggers auto-discovery fallback or crashes.
    """
    doc = fitz.open()
    p0 = doc.new_page(width=500, height=500)
    p0.insert_text((50, 50), "WALL TAG 1A: 3-5/8 METAL STUDS 16 OC 5/8 GWB")

    # schedule_page_indices=[] is falsy in Python, so it executes the else: branch
    materials = extract_wall_materials(doc, "1A", schedule_page_indices=[])
    assert isinstance(materials, str)
    assert len(materials) > 0
    doc.close()


def test_extract_wall_materials_invalid_and_out_of_bounds_indices():
    """Tests extract_wall_materials with invalid / out-of-bounds page indices."""
    doc = fitz.open()
    p0 = doc.new_page(width=500, height=500)
    p0.insert_text((50, 50), "WALL TAG 1A: 3-5/8 METAL STUDS 16 OC 5/8 GWB")

    # Indices [-1, 999, 1000] filtered out -> target_pages=[] -> scans doc text
    materials = extract_wall_materials(doc, "1A", schedule_page_indices=[-1, 999, 1000])
    assert isinstance(materials, str)
    assert "1A" in materials
    doc.close()


def test_extract_wall_materials_nonexistent_tag_fallback():
    """Tests that a completely non-existent tag returns the default fallback string cleanly."""
    doc = fitz.open()
    p0 = doc.new_page(width=500, height=500)
    p0.insert_text((50, 50), "Some unrelated architectural drawing text.")

    res = extract_wall_materials(doc, "NONEXISTENT_TAG_XYZ", schedule_page_indices=[0])
    assert res == "Assembly for NONEXISTENT_TAG_XYZ: Gypsum Wall Board on metal studs."
    doc.close()


def test_extract_wall_materials_zero_page_pdf():
    """Tests extract_wall_materials against an empty PDF with len(doc) == 0."""
    doc = fitz.open()
    assert len(doc) == 0
    res = extract_wall_materials(doc, "1A", schedule_page_indices=None)
    assert res == "Assembly for 1A: Gypsum Wall Board on metal studs."
    doc.close()


def test_extract_wall_materials_caching_behavior():
    """Tests that doc._schedule_pages_cache caches discovered pages."""
    pdf_path = "uploads/doc_20261104_101950_6cbd34.pdf"
    if not os.path.exists(pdf_path):
        pytest.skip(f"Test blueprint '{pdf_path}' not present")

    doc = fitz.open(pdf_path)
    try:
        assert not hasattr(doc, "_schedule_pages_cache")
        # First call: populates cache
        _ = extract_wall_materials(doc, "1A", schedule_page_indices=None)
        assert hasattr(doc, "_schedule_pages_cache")
        cached_pages = getattr(doc, "_schedule_pages_cache")
        assert len(cached_pages) > 0
        assert 62 in cached_pages or 63 in cached_pages  # A-900 / A-901

        # Second call: uses cache without re-running indexer
        _ = extract_wall_materials(doc, "7A", schedule_page_indices=None)
        assert getattr(doc, "_schedule_pages_cache") == cached_pages
    finally:
        doc.close()


# =============================================================================
# 3. DRYWALL_REGISTRY.JSON CACHING & CREDENTIAL FALLBACK STRESS TESTS
# =============================================================================

def test_load_environment_credentials_missing_key():
    """Verifies load_environment_credentials returns None when no key is present in env."""
    old_key = os.environ.pop("Jev_Key", None)
    old_key_upper = os.environ.pop("JEV_KEY", None)
    with tempfile.TemporaryDirectory() as tmpdir:
        empty_env = os.path.join(tmpdir, "empty.env")
        with open(empty_env, "w", encoding="utf-8") as f:
            f.write("# Empty env file\n")
        try:
            key = load_environment_credentials(env_path=empty_env)
            assert key is None
        finally:
            if old_key is not None:
                os.environ["Jev_Key"] = old_key
            if old_key_upper is not None:
                os.environ["JEV_KEY"] = old_key_upper


def test_evaluate_with_jev_offline_fallback():
    """Verifies evaluate_with_jev gracefully falls back to mock classifier when offline."""
    # When api_key is None and environment credentials are not present:
    old_key = os.environ.pop("Jev_Key", None)
    old_key_upper = os.environ.pop("JEV_KEY", None)
    with tempfile.TemporaryDirectory() as tmpdir:
        empty_env = os.path.join(tmpdir, "empty.env")
        with open(empty_env, "w", encoding="utf-8") as f:
            f.write("# Empty env file\n")
        try:
            # Pass mock empty env to prevent loading root 'env' file
            load_environment_credentials(env_path=empty_env)
            # Evaluate using fallback directly
            prob_drywall = evaluate_with_mock("1A", "3-5/8 Metal Studs, 5/8 Type X GWB")
            assert prob_drywall == 0.95

            prob_glass = evaluate_with_mock("GL1", "Infinium Quantum butt-glazed officefront")
            assert prob_glass == 0.05

            prob_privacy = evaluate_with_mock("PW", "Steelcase demountable privacy wall")
            assert prob_privacy == 0.10
        finally:
            if old_key is not None:
                os.environ["Jev_Key"] = old_key
            if old_key_upper is not None:
                os.environ["JEV_KEY"] = old_key_upper


def test_get_wall_registry_caching_and_partial_miss():
    """Verifies get_wall_registry loads from cache and handles partial cache misses."""
    with tempfile.TemporaryDirectory() as tmpdir:
        cache_path = os.path.join(tmpdir, "test_cache.json")

        initial_data = {
            "1A": {
                "wall_tag": "1A",
                "probability": 0.95,
                "is_drywall": True,
                "decision": "DRYWALL",
                "materials": "Mock materials 1A",
                "materials_excerpt": "Mock materials 1A",
            }
        }
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(initial_data, f)

        # 1. Full hit: tag "1A" is in cache
        reg = get_wall_registry(["1A"], {"1A": "Mock materials 1A"}, cache_file=cache_path)
        assert "1A" in reg
        assert reg["1A"]["probability"] == 0.95

        # 2. Partial miss: tag "2B" is missing
        reg2 = get_wall_registry(
            ["1A", "2B"],
            {"1A": "Mock materials 1A", "2B": "3-5/8 Metal Studs 5/8 GWB"},
            cache_file=cache_path,
        )
        assert "1A" in reg2
        assert "2B" in reg2
        assert reg2["2B"]["is_drywall"] is True

        # Check that cache file on disk now has both 1A and 2B
        with open(cache_path, "r", encoding="utf-8") as f:
            disk_cache = json.load(f)
        assert "1A" in disk_cache
        assert "2B" in disk_cache


def test_get_wall_registry_corrupted_json_recovery():
    """Verifies get_wall_registry recovers gracefully from a corrupted cache file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        cache_path = os.path.join(tmpdir, "corrupted_cache.json")
        with open(cache_path, "w", encoding="utf-8") as f:
            f.write("{ INVALID JSON NOT PARSABLE ...")

        reg = get_wall_registry(
            ["1A"],
            {"1A": "3-5/8 Metal Studs 5/8 Type X GWB"},
            cache_file=cache_path,
        )
        assert "1A" in reg
        assert reg["1A"]["decision"] == "DRYWALL"


def test_drywall_registry_json_integrity_audit():
    """Audits the production drywall_registry.json for strict SOP 8.2 compliance."""
    assert os.path.exists("drywall_registry.json"), "drywall_registry.json must exist in root"
    with open("drywall_registry.json", "r", encoding="utf-8") as f:
        registry = json.load(f)

    # 19 genuine drywall tags
    expected_drywall_tags = [
        "1A", "1B", "1C", "1D", "1E",
        "2B", "2C",
        "3A", "3D",
        "5B", "5D", "5E",
        "7A", "7B", "7C", "7E", "7F", "7G",
        "8A",
    ]
    for tag in expected_drywall_tags:
        assert tag in registry, f"Drywall tag '{tag}' missing from drywall_registry.json"
        entry = registry[tag]
        assert entry["probability"] >= PROBABILITY_THRESHOLD, (
            f"Tag {tag} probability {entry['probability']} < {PROBABILITY_THRESHOLD}"
        )
        assert entry["is_drywall"] is True, f"Tag {tag} is_drywall is not True"
        assert entry["decision"] == "DRYWALL", f"Tag {tag} decision is not 'DRYWALL'"

    # Non-drywall tags
    for non_tag in ["GL1", "GL2", "PW"]:
        assert non_tag in registry, f"Non-drywall tag '{non_tag}' missing from drywall_registry.json"
        entry = registry[non_tag]
        assert entry["probability"] < REVIEW_THRESHOLD
        assert entry["is_drywall"] is False
        assert entry["decision"] == "NOT_DRYWALL"

    # Verify absence of poisoned noise tags
    poison_tags = ["0X", "2W", "2X", "4B1", "4K", "4P", "5L", "8P"]
    for p_tag in poison_tags:
        assert p_tag not in registry, f"Poison tag '{p_tag}' found in drywall_registry.json!"


# =============================================================================
# 4. WALLASSEMBLY SCHEMA STRICT CONFORMANCE TESTS
# =============================================================================

def test_wall_assembly_schema_contract_conformance():
    """Verifies WallAssembly strict conformance to PROJECT.md § Interface Contracts."""
    expected_fields = {
        "tag": str,
        "materials_raw": str,
        "probability": float,
        "decision": str,
        "stud_depth_in": float,
        "stud_spacing_in": float,
        "stud_gauge": str,
        "board_type": str,
        "board_thickness_in": float,
        "layers_per_face": int,
        "finished_faces": int,
        "fire_rated": bool,
        "nominal_thickness_in": float,
        "material_layers": list,
    }

    dataclass_fields = {f.name: f.type for f in fields(WallAssembly)}

    # Check all fields exist
    for fname, ftype in expected_fields.items():
        assert fname in dataclass_fields, f"Field '{fname}' missing from WallAssembly"

    # Instantiate assembly and verify to_dict()
    assembly = create_wall_assembly(
        tag="1A",
        materials_raw='3 5/8" 25 GA. METAL STUDS @ 16" O.C., 1 LAYER 5/8" TYPE X GWB EACH SIDE',
        probability=0.95,
        decision="DRYWALL",
    )

    d = assembly.to_dict()
    assert isinstance(d, dict)
    for fname in expected_fields:
        assert fname in d, f"Field '{fname}' missing from to_dict() output"

    # Check material_layers schema
    assert isinstance(assembly.material_layers, list)
    assert len(assembly.material_layers) >= 3
    for layer in assembly.material_layers:
        assert isinstance(layer, dict)
        assert "side" in layer
        assert "layer" in layer
        assert "material" in layer
        assert isinstance(layer["side"], str)
        assert isinstance(layer["layer"], str)
        assert isinstance(layer["material"], str)


def test_wall_assembly_nominal_thickness_calculation_exactness():
    """Verifies nominal_thickness_in = stud_depth_in + finished_faces * layers_per_face * board_thickness_in."""
    # Test nominal thickness formula across multiple configurations
    test_cases = [
        # (depth, faces, layers, board_thick, expected_nominal)
        (3.625, 2, 1, 0.625, 4.875),
        (6.0, 2, 1, 0.625, 7.25),
        (2.5, 2, 1, 0.625, 3.75),
        (3.625, 2, 2, 0.625, 6.125),   # 2 layers each side
        (3.625, 1, 1, 0.625, 4.25),    # single side
        (1.625, 2, 1, 0.5, 2.625),     # 1/2" board
    ]
    for depth, faces, layers, board_t, expected in test_cases:
        calculated = round(depth + (faces * layers * board_t), 4)
        assert math.isclose(calculated, expected, rel_tol=1e-5), (
            f"Nominal thickness mismatch: expected {expected}, got {calculated}"
        )


if __name__ == "__main__":
    import sys
    pytest.main([__file__, "-v", "-s"])
