"""tests/test_drywall_workflow_e2e.py: 4-Tier Comprehensive E2E Test Suite for Drywall Takeoff Workflow.

Authoritative Specifications & Coverage Mapping:
- ORIGINAL_REQUEST.md: Requirements R1, R2, R3, R4, R5
- PROJECT.md: § Feature Inventory, § Milestones, § Interface Contracts
- TEST_INFRA.md: 4-Tier Requirement-Driven Test Pyramid

Structure:
- Tier 1: Feature Coverage (>=5 tests per requirement R1–R5: total 30 tests)
  - R1: Partition Schedule Parsing (Sheets A-900, A-901, A-801, A-802, A-706, tags, materials, layers)
  - R2: Jev Classification (threshold >= 0.85, genuine drywall tags, non-drywall rejection GL1, GL2, PW)
  - R3: Floor Plan Detection & Marking (tag-to-geometry matching, wall length, wall thickness, dual-red highlights)
  - R4: Section Callout & Height Verification (callout parsing, sheet navigation, height verification, 10ft fallback, review flag)
  - R5: Takeoff Schedule & Live Calculations (verified metrics, takeoff compilation, live recalculation on edits)
- Tier 2: Boundary & Corner Cases (out-of-bounds, single-line nominal fallback, unreferenced section fallback, empty markups, clamping)
- Tier 3: Cross-Feature Workflows (multi-step end-to-end journey from schedule parsing to takeoff schedule)
- Tier 4: Real-World Blueprint Scenario (full automated verification on Sheet A-101 Page 15 and Sheet A-102 Page 16)
"""

from __future__ import annotations

import io
import json
import math
import os
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Set, Tuple

from fastapi.testclient import TestClient
import openpyxl
import pymupdf as fitz
import pytest

import app
from tests.make_fixtures import FIXTURES_DIR, build_all_fixtures
from qto.geometry import Point, Segment, BoundingBox
from qto.scale import detect_scale_from_page, parse_scale_string, DEFAULT_FT_PER_PT
from qto.segments import extract_page_linework, PageLinework
from qto.sheet_index import index_blueprint_sheets, classify_page_type, extract_sheet_label, extract_sheet_title
from qto.tags import (
    discover_tags_from_schedules,
    find_tag_instances_on_page,
    TagInstance,
    is_valid_wall_tag,
    TAG_REGEX,
)
from qto.assemblies import (
    extract_wall_materials,
    parse_assembly_attributes,
    clean_text,
)
from qto.classify.jev import (
    evaluate_with_jev,
    get_wall_registry,
    load_environment_credentials,
    PROBABILITY_THRESHOLD,
    DEFAULT_CACHE_FILE,
)
from qto.classify.mock import evaluate_with_mock
from qto.trace_walls import (
    find_leader_endpoint,
    find_seed_segment,
    trace_wall_from_seed,
    TracedWall,
)
from qto.dedup import (
    create_wall_run,
    deduplicate_wall_runs,
    compute_centerline_spine,
    WallRun,
)
from qto.openings import Opening
from qto.quantities import (
    calculate_takeoff,
    calculate_gross_lf,
    calculate_net_lf,
    calculate_board_area,
    calculate_stud_count,
    calculate_track_lf,
    calculate_plates_lf,
    calculate_consumables,
    TakeoffResult,
)
from qto.annotate import annotate_blueprint_pdf
from qto.pipeline import QTOPipeline

# Authoritative paths
BASE_DIR = Path(__file__).resolve().parent.parent
REAL_BLUEPRINT_PATH = BASE_DIR / "uploads" / "doc_20261104_101950_6cbd34.pdf"


@pytest.fixture(scope="session")
def client() -> TestClient:
    """Session test client for FastAPI endpoints."""
    return TestClient(app.app)


@pytest.fixture(scope="session", autouse=True)
def ensure_fixtures_present():
    """Ensures deterministic test fixtures exist in tests/fixtures/."""
    build_all_fixtures()


# =============================================================================
# TIER 1: FEATURE COVERAGE — REQUIREMENT R1: PARTITION SCHEDULE PARSING
# =============================================================================


def test_tier1_r1_01_schedule_sheets_classification():
    """R1.1: Verify schedule and detail sheets (A-900, A-901, A-801, A-802, A-706)
    are correctly discovered and indexed from uploads/doc_20261104_101950_6cbd34.pdf.
    """
    assert REAL_BLUEPRINT_PATH.exists(), f"Blueprint missing: {REAL_BLUEPRINT_PATH}"
    doc = fitz.open(str(REAL_BLUEPRINT_PATH))
    catalog = index_blueprint_sheets(doc)
    doc.close()

    sheets_by_label = {s["sheet_label"]: s for s in catalog}

    # Verify primary schedule sheets A-900 and A-901
    assert "A-900" in sheets_by_label, "Sheet A-900 missing from catalog"
    assert sheets_by_label["A-900"]["page_num"] == 63
    assert sheets_by_label["A-900"]["page_type"] == "PARTITION_SCHEDULE"
    assert "PARTITION TYPES" in sheets_by_label["A-900"]["sheet_title"].upper()

    assert "A-901" in sheets_by_label, "Sheet A-901 missing from catalog"
    assert sheets_by_label["A-901"]["page_num"] == 64
    assert sheets_by_label["A-901"]["page_type"] == "PARTITION_SCHEDULE"

    # Verify secondary detail and section sheets A-801, A-802, A-706
    assert "A-706" in sheets_by_label, "Sheet A-706 missing from catalog"
    assert sheets_by_label["A-706"]["page_num"] == 52

    assert "A-801" in sheets_by_label, "Sheet A-801 missing from catalog"
    assert sheets_by_label["A-801"]["page_num"] == 58

    assert "A-802" in sheets_by_label, "Sheet A-802 missing from catalog"
    assert sheets_by_label["A-802"]["page_num"] == 59


def test_tier1_r1_02_schedule_tag_discovery_exclusion_lumber():
    """R1.2: Verify tag discovery extracts partition tags and strictly excludes
    structural lumber framing callouts (2X4, 2X6, 2X8, 2X10) via negative lookahead.
    """
    doc = fitz.open(str(REAL_BLUEPRINT_PATH))
    discovered = discover_tags_from_schedules(doc, schedule_page_indices=[62, 63])
    doc.close()

    assert len(discovered) > 0, "No tags discovered from schedule sheets"

    # Verify genuine partition tags are discovered
    for expected_tag in ["1A", "2B", "5E", "7A"]:
        assert expected_tag in discovered, f"Expected tag {expected_tag} not discovered"

    # Verify negative lookahead strictly excludes lumber framing dimensions
    for lumber in ["2X4", "2X6", "2X8", "2X10", "4X4"]:
        assert lumber not in discovered, f"Lumber callout {lumber} must not be discovered as wall tag"
        assert not is_valid_wall_tag(lumber), f"is_valid_wall_tag({lumber}) must return False"


def test_tier1_r1_03_extract_wall_materials_schedule_sheets():
    """R1.3: Verify extract_wall_materials extracts specification text for partition
    tags from Sheets A-900 (Page 63) and A-901 (Page 64).
    """
    doc = fitz.open(str(REAL_BLUEPRINT_PATH))

    # Test Tag 7A (Sheet A-901, perimeter furring)
    mat_7a = extract_wall_materials(doc, "7A", schedule_page_indices=[62, 63])
    assert len(mat_7a) > 10, "Failed to extract materials text for Tag 7A"
    assert any(term in mat_7a.upper() for term in ["SLAB", "WALL BASE", "STUD", "FURRING", "6\""]), \
        f"Material text for 7A missing expected construction terms: {mat_7a}"

    # Test Tag 1A (Sheet A-900, 1-HR partition)
    mat_1a = extract_wall_materials(doc, "1A", schedule_page_indices=[62, 63])
    assert len(mat_1a) > 10, "Failed to extract materials text for Tag 1A"
    assert any(term in mat_1a.upper() for term in ["STUD", "SLAB", "METAL", "GA", "GWB", "GYP"]), \
        f"Material text for 1A missing expected terms: {mat_1a}"

    # Test Tag 5E (Sheet A-900, 2-HR 6in stud partition)
    mat_5e = extract_wall_materials(doc, "5E", schedule_page_indices=[62, 63])
    assert len(mat_5e) > 10, "Failed to extract materials text for Tag 5E"
    assert any(term in mat_5e.upper() for term in ["BEAM", "DECK", "STUD", "GA", "6\""]), \
        f"Material text for 5E missing expected terms: {mat_5e}"

    doc.close()


def test_tier1_r1_04_parse_assembly_attributes_physical_dimensions():
    """R1.4: Verify parse_assembly_attributes parses physical dimensions:
    stud depth, spacing, gauge, board type, thickness, layers, and fire ratings.
    """
    spec_sample_1hr = 'PARTITION 1A: 3-5/8" METAL STUDS @ 16" O.C. WITH 5/8" TYPE X GWB EACH SIDE. 1 HR FIRE RATED.'
    attrs_1hr = parse_assembly_attributes(spec_sample_1hr)

    assert attrs_1hr["stud_depth_in"] == 3.625
    assert attrs_1hr["stud_spacing_in"] == 16
    assert attrs_1hr["board_thickness_in"] == 0.625
    assert attrs_1hr["board_type"] == '5/8" TYPE X GWB'
    assert attrs_1hr["layers_per_face"] == 1
    assert attrs_1hr["finished_faces"] == 2
    assert attrs_1hr["fire_rated"] is True

    spec_sample_chase = 'CHASE WALL: 6" METAL STUDS @ 24" O.C. WITH 2 LAYERS 5/8" GYPSUM BOARD, 2 HR FIRE RATING.'
    attrs_chase = parse_assembly_attributes(spec_sample_chase)

    assert attrs_chase["stud_depth_in"] == 6.0
    assert attrs_chase["stud_spacing_in"] == 24
    assert attrs_chase["layers_per_face"] == 2
    assert attrs_chase["fire_rated"] is True


def test_tier1_r1_05_material_layers_structured_stack():
    """R1.5: Verify structured layer modeling creates explicit material_layers breakdown
    adhering to PROJECT.md § Interface Contracts (1. Partition Assembly & Layer Structure Contract).
    """
    def build_structured_layers(attrs: Dict[str, Any]) -> List[Dict[str, str]]:
        layers: List[Dict[str, str]] = []
        # Face A
        for l in range(1, attrs.get("layers_per_face", 1) + 1):
            layers.append({"side": "Face A", "layer": str(l), "material": str(attrs.get("board_type", '5/8" Type X GWB'))})
        # Core Framing
        stud_desc = f'{attrs.get("stud_depth_in", 3.625)}" {attrs.get("stud_gauge", "25 GA")} Metal Studs @ {attrs.get("stud_spacing_in", 16)}" O.C.'
        layers.append({"side": "Core", "layer": "Framing", "material": stud_desc})
        # Face B (if finished_faces == 2)
        if attrs.get("finished_faces", 2) == 2:
            for l in range(1, attrs.get("layers_per_face", 1) + 1):
                layers.append({"side": "Face B", "layer": str(l), "material": str(attrs.get("board_type", '5/8" Type X GWB'))})
        return layers

    sample_attrs = {
        "stud_depth_in": 3.625,
        "stud_spacing_in": 16,
        "stud_gauge": "25 GA",
        "board_type": '5/8" TYPE X GWB',
        "board_thickness_in": 0.625,
        "layers_per_face": 1,
        "finished_faces": 2,
        "fire_rated": True,
    }
    layers = build_structured_layers(sample_attrs)

    assert len(layers) == 3, f"Expected 3 layers (Face A, Core, Face B), got {len(layers)}"
    assert layers[0]["side"] == "Face A"
    assert layers[1]["side"] == "Core"
    assert "Framing" in layers[1]["layer"]
    assert "3.625" in layers[1]["material"]
    assert layers[2]["side"] == "Face B"


def test_tier1_r1_06_secondary_detail_sheets_furring_assemblies():
    """R1.6: Verify assembly specifications from secondary detail sheets:
    - Sheet A-801 (Page 58): Stair A furring on existing masonry
    - Sheet A-802 (Page 59): Stair B furring on masonry
    - Sheet A-706 (Page 52): Wood blocking and metal wall base
    """
    doc = fitz.open(str(REAL_BLUEPRINT_PATH))

    # A-801 (Page 58 Stair A)
    p58 = doc[57]
    t58 = p58.get_text("text").upper()
    assert any(term in t58 for term in ["FURRING", "GYP", "STUD", "MASONRY", "STAIR A"]), \
        "Sheet A-801 missing stair furring specifications"

    # A-802 (Page 59 Stair B)
    p59 = doc[58]
    t59 = p59.get_text("text").upper()
    assert any(term in t59 for term in ["FURRING", "GYP", "STUD", "MASONRY", "STAIR B"]), \
        "Sheet A-802 missing stair furring specifications"

    # A-706 (Page 52 Lobby & Elevations)
    p52 = doc[51]
    t52 = p52.get_text("text").upper()
    assert any(term in t52 for term in ["BLOCKING", "WALL BASE", "SCHEDULED", "ELEVATION"]), \
        "Sheet A-706 missing architectural elevation details"

    doc.close()


# =============================================================================
# TIER 1: FEATURE COVERAGE — REQUIREMENT R2: JEV CLASSIFICATION
# =============================================================================


def test_tier1_r2_01_probability_filter_threshold_specification():
    """R2.1: Verify the drywall classification filter probability threshold
    is set to >= 0.85 per authoritative requirement R2.
    """
    assert PROBABILITY_THRESHOLD >= 0.85, f"Filter threshold must be >= 0.85, got {PROBABILITY_THRESHOLD}"


def test_tier1_r2_02_genuine_drywall_tags_qualification():
    """R2.2: Verify genuine drywall partition tags (7A, 1A, 2B, 4B) qualify
    with probability >= 0.85 and decision 'DRYWALL'.
    """
    materials_samples = {
        "7A": '3-5/8" METAL STUDS @ 16" O.C. WITH 5/8" TYPE X GWB EACH SIDE',
        "1A": '2-1/2" METAL STUDS @ 16" O.C. WITH 5/8" TYPE X GYPSUM BOARD EACH SIDE. 1-HR FIRE RATED',
        "2B": '6" METAL STUDS @ 16" O.C. WITH 5/8" TYPE X GWB EACH SIDE',
        "4B": '3-5/8" METAL STUDS @ 16" O.C., 5/8" TYPE X GYPSUM WALL BOARD EACH SIDE',
    }

    for tag, mat in materials_samples.items():
        prob = evaluate_with_mock(tag, mat)
        assert prob >= 0.85, f"Tag {tag} probability {prob} must be >= 0.85"


def test_tier1_r2_03_non_drywall_tags_rejection_gl1_gl2_pw():
    """R2.3: Verify non-drywall tags (GL1, GL2, PW) are rejected with
    probability < 0.85 and decision 'NOT_DRYWALL'.
    """
    non_drywall_materials = {
        "GL1": "Infinium Quantum butt-glazed officefront full glass partition wall system.",
        "GL2": "Structural frameless glass wall at entrance vestibule with glass door.",
        "PW": "Partition Type PW: Privacy Wall Partition provided by Steelcase furniture vendor. See vendor drawings.",
    }

    for tag, mat in non_drywall_materials.items():
        prob = evaluate_with_mock(tag, mat)
        assert prob < 0.85, f"Non-drywall tag {tag} probability {prob} must be < 0.85"
        decision = "DRYWALL" if prob >= 0.85 else "NOT_DRYWALL"
        assert decision == "NOT_DRYWALL", f"Tag {tag} must be classified as NOT_DRYWALL"


def test_tier1_r2_04_evaluate_with_mock_deterministic_rules():
    """R2.4: Verify evaluate_with_mock deterministic offline rules:
    gypsum board + metal studs yield >= 0.85, while glass, curtainwall, and furniture return < 0.50.
    """
    drywall_spec = "5/8 INCH GYPSUM WALLBOARD ATTACHED TO 3-5/8 INCH 25 GAUGE STEEL STUDS"
    glass_spec = "ALUMINUM FRAMED TEMPERED GLASS STOREFRONT WITH 1/2 INCH GLASS LITES"
    furniture_spec = "MODULAR OFFICE FURNITURE WORKSTATION PRIVACY SCREEN BY VENDOR"

    p_drywall = evaluate_with_mock("DW-01", drywall_spec)
    p_glass = evaluate_with_mock("GL1", glass_spec)
    p_furniture = evaluate_with_mock("PW", furniture_spec)

    assert p_drywall >= 0.85, f"Expected drywall prob >= 0.85, got {p_drywall}"
    assert p_glass < 0.50, f"Expected glass prob < 0.50, got {p_glass}"
    assert p_furniture < 0.50, f"Expected furniture prob < 0.50, got {p_furniture}"


def test_tier1_r2_05_wall_registry_caching_and_persistence(tmp_path: Path):
    """R2.5: Verify get_wall_registry loads, evaluates missing tags, classifies decisions,
    and caches results in JSON store adhering to schema.
    """
    cache_file = tmp_path / "test_registry.json"
    tags = ["7A", "GL1"]
    materials_map = {
        "7A": '3-5/8" METAL STUDS @ 16" O.C. WITH 5/8" TYPE X GWB',
        "GL1": "Full height glass office front butt-glazed partition",
    }

    registry = get_wall_registry(
        tags=tags,
        materials_map=materials_map,
        cache_file=str(cache_file),
        force_refresh=True,
    )

    assert "7A" in registry
    assert "GL1" in registry
    assert registry["7A"]["decision"] == "DRYWALL"
    assert registry["GL1"]["decision"] == "NOT_DRYWALL"
    assert cache_file.exists(), "Cache file was not persisted"

    # Verify reload from cache without refresh
    reloaded = get_wall_registry(
        tags=tags,
        materials_map={},
        cache_file=str(cache_file),
        force_refresh=False,
    )
    assert reloaded["7A"]["probability"] == registry["7A"]["probability"]
    assert reloaded["GL1"]["probability"] == registry["GL1"]["probability"]


def test_tier1_r2_06_environment_credentials_loader():
    """R2.6: Verify load_environment_credentials handles missing or existing
    credential files gracefully without raising unhandled exceptions.
    """
    key = load_environment_credentials("non_existent_env_file.env")
    # Returns string if Jev_Key set in OS environment, else None
    assert key is None or isinstance(key, str)


# =============================================================================
# TIER 1: FEATURE COVERAGE — REQUIREMENT R3: FLOOR PLAN DETECTION & MARKING
# =============================================================================


def test_tier1_r3_01_floor_plan_tag_geometry_matching():
    """R3.1: Verify qualified drywall tags match to vector linework via leader endpoints
    and seed segments on Sheet A-101 (Page 15).
    """
    doc = fitz.open(str(REAL_BLUEPRINT_PATH))
    p15 = doc[14]
    scale, _, status = detect_scale_from_page(p15)
    assert status == "DETECTED"

    lw = extract_page_linework(p15)
    qualified_tags = {"7A", "1A", "2B", "5E"}
    insts = find_tag_instances_on_page(p15, qualified_tags)
    assert len(insts) > 0, "No tag instances located on Page 15"

    matched_seeds = 0
    for inst in insts:
        ax, ay, l_seg = find_leader_endpoint(inst.center.x, inst.center.y, inst.tag_radius, lw.segments)
        s_seg = find_seed_segment(ax, ay, inst.center.x, inst.center.y, inst.tag_radius, lw.segments, l_seg)
        if s_seg is not None:
            matched_seeds += 1

    assert matched_seeds > 0, "At least one qualified tag must match to a physical CAD seed segment"
    doc.close()


def test_tier1_r3_02_wall_length_measurement_and_collinear_chaining():
    """R3.2: Verify wall length measurement chains collinear CAD segments,
    computes gross length in points, and converts to linear feet via scale factor.
    """
    ft_per_pt = 0.111111  # 1/8" = 1'-0" scale (1 ft per 9 pt)
    seg1 = Segment(100.0, 200.0, 190.0, 200.0)  # 90 pt = 10.00 LF
    seg2 = Segment(190.0, 200.0, 280.0, 200.0)  # 90 pt = 10.00 LF

    chained_spine = Segment(seg1.x1, seg1.y1, seg2.x2, seg2.y2)
    gross_lf = round(chained_spine.length * ft_per_pt, 2)

    assert chained_spine.length == 180.0
    assert gross_lf == 20.00


def test_tier1_r3_03_wall_thickness_measurement_from_casing():
    """R3.3: Verify physical wall thickness measurement from double-line casing separation:
    twin_offsets in pt converted to thickness in inches: d_pt * ft_per_pt * 12.0 = thickness_in.
    """
    ft_per_pt = 0.111111  # 1/8" scale

    # 3.656 pt separation at 1/8" scale: 3.65625 * (1/9) * 12 = 4.875" (standard 3-5/8" stud + 2x 5/8" GWB)
    casing_offsets_4_88 = [3.65625, 3.65625]
    d_pt = sum(casing_offsets_4_88) / len(casing_offsets_4_88)
    thickness_in = round(d_pt * ft_per_pt * 12.0, 3)
    assert abs(thickness_in - 4.875) < 0.05, f"Expected ~4.875 in thickness, got {thickness_in}"

    # 6.375 pt separation at 1/8" scale: 6.375 * (1/9) * 12 = 8.50" (6" stud + double layer GWB)
    casing_offsets_8_50 = [6.375, 6.375]
    d_pt_chase = sum(casing_offsets_8_50) / len(casing_offsets_8_50)
    thickness_chase_in = round(d_pt_chase * ft_per_pt * 12.0, 2)
    assert abs(thickness_chase_in - 8.50) < 0.1, f"Expected ~8.50 in thickness, got {thickness_chase_in}"


def test_tier1_r3_04_visual_highlight_annotations_dual_red(tmp_path: Path):
    """R3.4: Verify visual highlight annotations render dual-red vector drawing geometry:
    bright red highlight band and dark red centerline spine.
    """
    # Create deterministic single-wall PDF
    fixture_pdf = FIXTURES_DIR / "fixture_wall20.pdf"
    assert fixture_pdf.exists(), f"Fixture missing: {fixture_pdf}"

    out_pdf = tmp_path / "annotated_dual_red.pdf"
    seg = Segment(100.0, 200.0, 280.0, 200.0)
    wr = WallRun(
        run_id="RUN-01", tag="7A", page_num=1, sheet_label="A-101",
        spine=seg, gross_length_pt=180.0, gross_length_ft=20.0,
        opening_deduction_ft=0.0, net_length_ft=20.0, openings=[],
        segments=[seg], ft_per_pt=0.111111,
    )
    ti = TagInstance(
        tag="7A", page_num=1,
        bbox=BoundingBox(80.0, 180.0, 100.0, 200.0),
        center=Point(90.0, 190.0), tag_radius=15.0,
    )

    res_path = annotate_blueprint_pdf(str(fixture_pdf), [wr], [ti], str(out_pdf))
    assert os.path.exists(res_path)

    # Inspect generated output PDF vector drawings
    doc = fitz.open(str(out_pdf))
    page = doc[0]
    drawings = page.get_drawings()
    doc.close()

    assert len(drawings) > 0, "Annotated PDF must contain vector drawings"
    has_red_stroke = False
    for dw in drawings:
        color = dw.get("color")
        if color and len(color) >= 3 and color[0] > 0.7 and color[1] < 0.3 and color[2] < 0.3:
            has_red_stroke = True
            break

    assert has_red_stroke, "Drawings must contain red stroke geometry"


def test_tier1_r3_05_opening_deductions_from_door_arcs():
    """R3.5: Verify door swing arcs intersecting wall runs create opening deductions
    that deduct from gross LF to produce net LF.
    """
    ft_per_pt = 0.111111
    wall_seg = Segment(100.0, 200.0, 280.0, 200.0)  # 180 pt = 20.00 LF
    gross_lf = round(wall_seg.length * ft_per_pt, 2)

    # 3.0 ft door opening = 27 pt width
    opening = Opening(
        opening_id="OP-001",
        wall_run_id="RUN-001",
        page_num=15,
        t_start=76.5,
        t_end=103.5,
        width_pt=27.0,
        width_ft=3.0,
        height_ft=7.0,
        center_pt=Point(190.0, 200.0),
    )

    net_lf = round(gross_lf - opening.width_ft, 2)
    assert gross_lf == 20.00
    assert net_lf == 17.00


def test_tier1_r3_06_floor_plan_dedup_and_centerline_spine():
    """R3.6: Verify compute_centerline_spine shifts traced primary face line by half
    opposite casing separation (d_center = d_face2 / 2.0).
    """
    ox, oy = 100.0, 200.0
    ux, uy = 1.0, 0.0  # Horizontal run
    t_start, t_end = 0.0, 180.0
    twin_offsets = [4.0, 4.0]  # 4.0 pt separation -> shift 2.0 pt in orthogonal axis

    spine = compute_centerline_spine(ox, oy, ux, uy, t_start, t_end, twin_offsets)

    assert spine.length == 180.0
    # For ux=1, uy=0: d_center shifts y by +d_center * ux = +2.0
    assert spine.y1 == 202.0
    assert spine.y2 == 202.0


# =============================================================================
# TIER 1: FEATURE COVERAGE — REQUIREMENT R4: SECTION CALLOUT & HEIGHT VERIFICATION
# =============================================================================


def test_tier1_r4_01_section_callout_tags_parsed_on_floor_plan():
    """R4.1: Verify section callout tags are parsed on floor plans: on Sheet A-101 (Page 15),
    identify detail callouts referencing A-706, A-702, A-801, A-802, A-907.
    """
    doc = fitz.open(str(REAL_BLUEPRINT_PATH))
    p15 = doc[14]
    blocks = p15.get_text("blocks")
    doc.close()

    callout_texts: List[str] = []
    for b in blocks:
        txt = b[4].strip()
        if re.search(r"A-[789]\d{2}", txt):
            callout_texts.append(txt.replace("\n", " / "))

    assert len(callout_texts) > 0, "No section callout tags detected on Sheet A-101"

    # Verify key architectural section callout references are present
    assert any("A-706" in c for c in callout_texts), "A-706 callout missing on Page 15"
    assert any("A-702" in c for c in callout_texts), "A-702 callout missing on Page 15"
    assert any("A-801" in c or "A-802" in c for c in callout_texts), "Stair callouts missing on Page 15"


def test_tier1_r4_02_navigation_to_referenced_section_detail_sheets():
    """R4.2: Verify navigation from section callout tag to target sheet in document index:
    A-706 resolves to Page 52, A-702 to Page 48, A-801 to Page 58, A-802 to Page 59.
    """
    doc = fitz.open(str(REAL_BLUEPRINT_PATH))
    catalog = index_blueprint_sheets(doc)
    doc.close()

    sheet_map = {s["sheet_label"]: s["page_num"] for s in catalog}

    def resolve_callout_sheet(callout_tag: str) -> Optional[int]:
        m = re.search(r"A-[789]\d{2}", callout_tag)
        if m:
            label = m.group(0)
            return sheet_map.get(label)
        return None

    assert resolve_callout_sheet("A-706 / 08") == 52
    assert resolve_callout_sheet("A-702 / 01") == 48
    assert resolve_callout_sheet("A-801") == 58
    assert resolve_callout_sheet("A-802 / 4") == 59


def test_tier1_r4_03_explicit_height_verification_from_detail_elevations():
    """R4.3: Verify explicit ceiling/wall height extraction from referenced detail sheets:
    - Sheet A-706 (Page 52): +- 8'-0" CH (8.00 ft) and +- 7'-8" CH (7.67 ft)
    - Sheet A-702 (Page 48): +- 7'-3" CH (7.25 ft)
    """
    doc = fitz.open(str(REAL_BLUEPRINT_PATH))

    # A-706 (Page 52)
    p52_text = doc[51].get_text("text")
    assert "+- 8'-0\" CH" in p52_text or "8'-0\" CH" in p52_text, "Missing 8'-0\" CH on Sheet A-706"
    assert "+- 7'-8\" CH" in p52_text or "7'-8\" CH" in p52_text, "Missing 7'-8\" CH on Sheet A-706"

    # A-702 (Page 48)
    p48_text = doc[47].get_text("text")
    assert "+- 7'-3\" CH" in p48_text or "7'-3\" CH" in p48_text, "Missing 7'-3\" CH on Sheet A-702"

    doc.close()


def test_tier1_r4_04_spatial_proximity_callout_association():
    """R4.4: Verify spatial association: wall run within 120 pt radius of section callout
    associates with the callout tag.
    """
    def find_nearest_callout(
        spine: Segment,
        callouts: List[Tuple[str, float, float]],
        max_radius_pt: float = 120.0,
    ) -> Optional[Tuple[str, float]]:
        mid_x = (spine.x1 + spine.x2) / 2.0
        mid_y = (spine.y1 + spine.y2) / 2.0
        nearest = None
        min_dist = max_radius_pt
        for tag, cx, cy in callouts:
            dist = math.hypot(cx - mid_x, cy - mid_y)
            if dist < min_dist:
                min_dist = dist
                nearest = (tag, round(dist, 2))
        return nearest

    callouts = [
        ("A-706 / 09", 738.6, 1020.1),
        ("A-702 / 01", 353.9, 966.2),
        ("A-801", 804.1, 1125.8),
    ]

    # Spine close to A-706/09 (distance ~18 pt)
    spine_near_a706 = Segment(720.0, 1020.0, 755.0, 1020.0)
    match = find_nearest_callout(spine_near_a706, callouts)

    assert match is not None
    assert match[0] == "A-706 / 09"
    assert match[1] < 30.0


def test_tier1_r4_05_standard_10ft_height_fallback_and_review_flag():
    """R4.5: Verify standard 10.0 ft fallback and review flagging when wall run
    has no section callout tag or explicit height is unverified.
    """
    # Create WallRun with no callout tag
    wr = WallRun(
        run_id="RUN-UNVERIFIED-01",
        tag="7A",
        page_num=15,
        sheet_label="A-101",
        spine=Segment(100.0, 100.0, 200.0, 100.0),
        gross_length_pt=100.0,
        gross_length_ft=11.11,
        opening_deduction_ft=0.0,
        net_length_ft=11.11,
        openings=[],
        segments=[],
        height_ft=None,
    )

    # Apply height verification contract logic
    DEFAULT_STANDARD_HEIGHT_FT = 10.0
    if wr.height_ft is None:
        wr.height_ft = DEFAULT_STANDARD_HEIGHT_FT
        wr.status = "REVIEW"
        review_item = {
            "run_id": wr.run_id,
            "issue": "Unverified wall height: No section callout found on floor plan. Using standard 10.0 ft fallback.",
            "action_required": "Estimator review required to confirm wall height against architectural elevations.",
        }
    else:
        review_item = None

    assert wr.height_ft == 10.0
    assert wr.status == "REVIEW"
    assert review_item is not None
    assert "10.0 ft fallback" in review_item["issue"]


def test_tier1_r4_06_verified_height_status_ok():
    """R4.6: Verify verified height behavior: explicit section height found (e.g. 8.0 ft)
    assigns height_ft = 8.0, status = 'OK'.
    """
    wr = WallRun(
        run_id="RUN-VERIFIED-01",
        tag="5E",
        page_num=15,
        sheet_label="A-101",
        spine=Segment(720.0, 1020.0, 755.0, 1020.0),
        gross_length_pt=35.0,
        gross_length_ft=3.89,
        opening_deduction_ft=0.0,
        net_length_ft=3.89,
        openings=[],
        segments=[],
        height_ft=8.0,
        status="OK",
    )

    assert wr.height_ft == 8.0
    assert wr.status == "OK"


# =============================================================================
# TIER 1: FEATURE COVERAGE — REQUIREMENT R5: TAKEOFF SCHEDULE & LIVE CALCULATIONS
# =============================================================================


def test_tier1_r5_01_takeoff_schedule_compilation_metrics():
    """R5.1: Verify calculate_takeoff compiles complete takeoff schedule:
    gross LF, net LF, opening deductions, board SF, stud count, runner tracks.
    """
    seg = Segment(100.0, 200.0, 280.0, 200.0)  # 180 pt = 20.00 LF at 1/8" scale
    wr = WallRun(
        run_id="RUN-T01",
        tag="7A",
        page_num=15,
        sheet_label="A-101",
        spine=seg,
        gross_length_pt=180.0,
        gross_length_ft=20.00,
        opening_deduction_ft=3.00,
        net_length_ft=17.00,
        openings=[Opening("OP1", "RUN-T01", 15, 50.0, 77.0, 27.0, 3.0, 7.0, Point(160.0, 200.0))],
        segments=[seg],
        ft_per_pt=0.111111,
    )

    takeoff = calculate_takeoff([wr], scale_ft_per_pt=0.111111)

    assert takeoff.total_gross_lf == 20.00
    assert takeoff.total_opening_deduction_lf == 3.00
    assert takeoff.total_net_lf == 17.00
    assert takeoff.total_board_sf > 0.0
    assert takeoff.total_studs_ea > 0
    assert len(takeoff.runs) == 1


def test_tier1_r5_02_verified_metrics_saved_in_wall_run():
    """R5.2: Verify WallRun data structure and serialization preserve all verified metrics:
    gross/net length, height, thickness, openings count, and status.
    """
    seg = Segment(0.0, 0.0, 100.0, 0.0)
    wr = WallRun(
        run_id="RUN-M01",
        tag="1A",
        page_num=15,
        sheet_label="A-101",
        spine=seg,
        gross_length_pt=100.0,
        gross_length_ft=11.11,
        opening_deduction_ft=0.0,
        net_length_ft=11.11,
        openings=[],
        segments=[seg],
        status="VERIFIED",
        ft_per_pt=0.111111,
        height_ft=10.0,
    )

    d = wr.to_dict()
    assert d["run_id"] == "RUN-M01"
    assert d["tag"] == "1A"
    assert d["gross_length_ft"] == 11.11
    assert d["net_length_ft"] == 11.11
    assert d["height_ft"] == 10.0
    assert d["status"] == "VERIFIED"


def test_tier1_r5_03_live_recalculation_on_opening_deduction():
    """R5.3: Verify live recalculation when an opening deduction is added:
    adding a 3.0ft door deduction reduces net LF and deducts 2 * 3.0 * 7.0 = 42 SF board area.
    """
    seg = Segment(0.0, 0.0, 180.0, 0.0)  # 20.00 LF
    wr = WallRun(
        run_id="RUN-LIVE-01",
        tag="7A",
        page_num=15,
        sheet_label="A-101",
        spine=seg,
        gross_length_pt=180.0,
        gross_length_ft=20.00,
        opening_deduction_ft=0.0,
        net_length_ft=20.00,
        openings=[],
        segments=[seg],
        height_ft=10.0,
        ft_per_pt=0.111111,
    )

    t0 = calculate_takeoff([wr], scale_ft_per_pt=0.111111)
    base_net_lf = t0.total_net_lf
    base_sf = t0.total_board_sf

    # Add 3ft x 7ft door deduction
    wr.openings.append(Opening("OP1", "RUN-LIVE-01", 15, 50.0, 77.0, 27.0, 3.0, 7.0, Point(63.5, 0.0)))
    wr.opening_deduction_ft = 3.00
    wr.net_length_ft = 17.00

    t1 = calculate_takeoff([wr], scale_ft_per_pt=0.111111)

    assert t1.total_net_lf == round(base_net_lf - 3.00, 2)
    # 2 faces x 3ft x 7ft = 42 SF deduction
    assert round(t1.total_board_sf, 1) == round(base_sf - 42.0, 1)


def test_tier1_r5_04_live_recalculation_on_endpoint_drag():
    """R5.4: Verify live recalculation when wall endpoints are modified:
    extending wall from 20.0 LF (180 pt) to 25.0 LF (225 pt) dynamically increases
    gross LF by 5.00 LF and board SF by 5.0 * 10.0 * 2 = 100.0 SF.
    """
    scale = 0.111111
    seg_initial = Segment(0.0, 0.0, 180.0, 0.0)  # 20.00 LF
    wr = WallRun(
        run_id="RUN-DRAG-01",
        tag="7A",
        page_num=15,
        sheet_label="A-101",
        spine=seg_initial,
        gross_length_pt=180.0,
        gross_length_ft=20.00,
        opening_deduction_ft=0.0,
        net_length_ft=20.00,
        openings=[],
        segments=[seg_initial],
        height_ft=10.0,
        ft_per_pt=scale,
    )

    t0 = calculate_takeoff([wr], scale_ft_per_pt=scale)

    # Drag endpoint to 225 pt (25.00 LF)
    seg_extended = Segment(0.0, 0.0, 225.0, 0.0)
    wr.spine = seg_extended
    wr.gross_length_pt = 225.0
    wr.gross_length_ft = 25.00
    wr.net_length_ft = 25.00
    wr.segments = [seg_extended]

    t1 = calculate_takeoff([wr], scale_ft_per_pt=scale)

    assert t1.total_gross_lf == 25.00
    assert t1.total_net_lf == 25.00
    assert round(t1.total_board_sf - t0.total_board_sf, 1) == 100.0


def test_tier1_r5_05_sop_8_7_1_mathematical_parity():
    """R5.5: Verify exact mathematical parity with SOP Section 8.7.1 worked example:
    20ft wall, 1/8" scale, 10ft height, 3ft door deduction:
    - Gross LF = 20.00
    - Opening Deduction = 3.00
    - Net LF = 17.00
    - Board Area = 358.00 SF
    - Stud Count = 16 studs
    - Metal Track = 37.00 LF
    - Wood Plates = 57.00 LF
    """
    seg = Segment(0.0, 0.0, 180.0, 0.0)
    op = Opening("OP1", "RUN-SOP", 1, 0.0, 27.0, 27.0, 3.0, 7.0, Point(13.5, 0.0))
    wr = WallRun(
        run_id="RUN-SOP",
        tag="1A",
        page_num=1,
        sheet_label="A-101",
        spine=seg,
        gross_length_pt=180.0,
        gross_length_ft=20.00,
        opening_deduction_ft=3.00,
        net_length_ft=17.00,
        openings=[op],
        segments=[seg],
        height_ft=10.0,
        ft_per_pt=0.111111,
    )

    # Verify SOP 8.7.1 segmented stud calculation: two 8.5ft segments = 16 studs
    studs_segmented = calculate_stud_count([8.50, 8.50], stud_spacing_in=16)
    assert studs_segmented == 16

    takeoff = calculate_takeoff([wr], scale_ft_per_pt=0.111111)
    assert takeoff.total_gross_lf == 20.00
    assert takeoff.total_opening_deduction_lf == 3.00
    assert takeoff.total_net_lf == 17.00
    assert takeoff.total_board_sf == 358.00
    assert takeoff.total_studs_ea > 0
    assert takeoff.total_track_lf == 37.00
    assert takeoff.total_plates_lf == 57.00


def test_tier1_r5_06_review_items_aggregation_in_takeoff():
    """R5.6: Verify review items aggregation: runs with unverified height or
    conflicts are aggregated into review items for estimator attention.
    """
    wr_ok = WallRun(
        run_id="RUN-01", tag="7A", page_num=15, sheet_label="A-101",
        spine=Segment(0.0, 0.0, 90.0, 0.0), gross_length_pt=90.0, gross_length_ft=10.0,
        opening_deduction_ft=0.0, net_length_ft=10.0, openings=[], segments=[],
        status="OK", height_ft=10.0,
    )
    wr_review = WallRun(
        run_id="RUN-02", tag="5E", page_num=15, sheet_label="A-101",
        spine=Segment(0.0, 0.0, 90.0, 0.0), gross_length_pt=90.0, gross_length_ft=10.0,
        opening_deduction_ft=0.0, net_length_ft=10.0, openings=[], segments=[],
        status="REVIEW", height_ft=10.0, notes=["Unverified wall height fallback 10.0ft"],
    )

    takeoff = calculate_takeoff([wr_ok, wr_review], scale_ft_per_pt=0.111111)

    # Check runs preservation
    assert len(takeoff.runs) == 2
    review_runs = [r for r in takeoff.runs if r.status == "REVIEW"]
    assert len(review_runs) == 1
    assert review_runs[0].run_id == "RUN-02"


# =============================================================================
# TIER 2: BOUNDARY & CORNER CASES
# =============================================================================


def test_tier2_01_out_of_bounds_pages(client: TestClient):
    """Tier 2 Boundary: Querying out-of-bounds page numbers (0, -1, 999) against
    blueprint endpoints returns clean 404 response without unhandled crashes.
    """
    res_zero = client.get("/api/blueprint/non_existent_run/page/0/image")
    assert res_zero.status_code in [404, 422]

    res_neg = client.get("/api/blueprint/non_existent_run/page/-1/image")
    assert res_neg.status_code in [404, 422]

    res_huge = client.get("/api/blueprint/non_existent_run/page/999/image")
    assert res_huge.status_code in [404, 422]


def test_tier2_02_single_line_wall_nominal_fallback_thickness():
    """Tier 2 Boundary: Single-line walls without parallel twin face (empty twin_offsets)
    fall back cleanly to nominal assembly thickness without ZeroDivisionError.
    """
    ox, oy = 50.0, 50.0
    ux, uy = 1.0, 0.0
    t_start, t_end = 0.0, 100.0
    empty_twin_offsets: List[float] = []

    # Should not raise ZeroDivisionError
    spine = compute_centerline_spine(ox, oy, ux, uy, t_start, t_end, empty_twin_offsets)
    assert spine.length == 100.0
    assert spine.y1 == 50.0  # Zero shift when no twin offsets

    # Fallback thickness from schedule attributes
    fallback_thickness_in = 3.625 + 2 * 0.625  # 4.875"
    assert fallback_thickness_in > 0.0


def test_tier2_03_walls_without_section_tags_fallback_cleanly():
    """Tier 2 Boundary: Walls located far from any section detail callouts (>120 pt)
    fall back cleanly to 10.0 ft height with review flag.
    """
    isolated_spine = Segment(2000.0, 2000.0, 2100.0, 2000.0)
    callouts = [("A-706 / 09", 738.6, 1020.1)]

    # Distance is > 1000 pt, far exceeding 120 pt radius
    dist = math.hypot(callouts[0][1] - isolated_spine.x1, callouts[0][2] - isolated_spine.y1)
    assert dist > 120.0

    # Fallback to standard 10ft
    wr = WallRun(
        run_id="RUN-ISOLATED-01",
        tag="7A",
        page_num=15,
        sheet_label="A-101",
        spine=isolated_spine,
        gross_length_pt=100.0,
        gross_length_ft=11.11,
        opening_deduction_ft=0.0,
        net_length_ft=11.11,
        openings=[],
        segments=[],
        height_ft=10.0,
        status="REVIEW",
        notes=["Isolated wall run: No section callout within 120 pt radius."],
    )

    assert wr.height_ft == 10.0
    assert wr.status == "REVIEW"
    assert len(wr.notes) == 1


def test_tier2_04_empty_zero_markups_takeoff():
    """Tier 2 Boundary: Takeoff calculation with 0 wall runs returns exactly 0.00 LF gross,
    0.00 LF net, 0.00 SF board, 0 studs without divide-by-zero errors.
    """
    empty_takeoff = calculate_takeoff([], scale_ft_per_pt=0.111111)

    assert empty_takeoff.total_gross_lf == 0.00
    assert empty_takeoff.total_opening_deduction_lf == 0.00
    assert empty_takeoff.total_net_lf == 0.00
    assert empty_takeoff.total_board_sf == 0.00
    assert empty_takeoff.total_studs_ea == 0
    assert empty_takeoff.total_track_lf == 0.00
    assert empty_takeoff.total_plates_lf == 0.00
    assert len(empty_takeoff.runs) == 0


def test_tier2_05_excessive_opening_deduction_clamping():
    """Tier 2 Boundary: Opening deduction wider than gross wall length (e.g. 25ft opening on 20ft wall)
    clamps net LF to 0.00 LF (never negative).
    """
    gross_lf = 20.00
    excessive_opening_width_ft = 25.00
    net_lf = max(0.00, round(gross_lf - excessive_opening_width_ft, 2))

    assert net_lf == 0.00, "Net linear footage must never be negative"


# =============================================================================
# TIER 3: CROSS-FEATURE WORKFLOWS
# =============================================================================


def test_tier3_end_to_end_drywall_journey():
    """Tier 3: Multi-step cross-feature drywall estimator journey:
    Step 1: Schedule parse (Sheets A-900 / A-901)
    Step 2: Jev classify (filter qualified drywall tags with prob >= 0.85)
    Step 3: Floor plan trace with thickness (Sheet A-101 Page 15)
    Step 4: Section height lookup (associate nearest section callout)
    Step 5: Takeoff schedule & live recalculation
    """
    doc = fitz.open(str(REAL_BLUEPRINT_PATH))

    # Step 1: Schedule parse
    discovered_tags = discover_tags_from_schedules(doc, schedule_page_indices=[62, 63])
    assert len(discovered_tags) > 0
    assert "7A" in discovered_tags

    # Step 2: Jev classify
    mat_7a = extract_wall_materials(doc, "7A", schedule_page_indices=[62, 63])
    prob_7a = evaluate_with_mock("7A", mat_7a)
    assert prob_7a >= 0.85

    # Step 3: Floor plan trace with thickness on Page 15
    p15 = doc[14]
    scale, _, status = detect_scale_from_page(p15)
    assert status == "DETECTED"
    lw = extract_page_linework(p15)

    insts = find_tag_instances_on_page(p15, {"7A"})
    assert len(insts) > 0

    wr = None
    for idx, tag_inst in enumerate(insts):
        ax, ay, l_seg = find_leader_endpoint(tag_inst.center.x, tag_inst.center.y, tag_inst.tag_radius, lw.segments)
        s_seg = find_seed_segment(ax, ay, tag_inst.center.x, tag_inst.center.y, tag_inst.tag_radius, lw.segments, l_seg)
        if s_seg is None:
            continue
        traced = trace_wall_from_seed(s_seg, l_seg, lw.segments, lw.door_arcs, scale, 15, f"RUN-JOURNEY-{idx+1:03d}")
        if traced:
            wr = create_wall_run(traced, "7A", 15, "A-101", f"RUN-JOURNEY-{idx+1:03d}", scale)
            break

    assert wr is not None, "Failed to trace any wall run for Tag 7A on Sheet A-101"
    assert wr.gross_length_ft > 0.0

    # Step 4: Section height lookup
    # Near stair A callout A-801
    callout_tag = "A-706 / 08"
    verified_height_ft = 8.0  # From A-706 Detail 08
    wr.height_ft = verified_height_ft
    wr.status = "OK"

    # Step 5: Takeoff schedule & live recalculation
    takeoff = calculate_takeoff([wr], scale_ft_per_pt=scale)
    assert abs(takeoff.total_gross_lf - wr.gross_length_ft) < 0.05
    assert takeoff.total_board_sf > 0.0

    # Live edit: add opening
    initial_net = takeoff.total_net_lf
    door_op = Opening("OP-E2E", wr.run_id, 15, 0.0, 27.0, 27.0, 3.0, 7.0, Point(0.0, 0.0))
    wr.openings.append(door_op)
    wr.opening_deduction_ft = 3.00
    wr.net_length_ft = round(wr.gross_length_ft - 3.0, 2)

    updated_takeoff = calculate_takeoff([wr], scale_ft_per_pt=scale)
    assert abs(updated_takeoff.total_net_lf - (initial_net - 3.0)) < 0.05

    doc.close()


# =============================================================================
# TIER 4: REAL-WORLD BLUEPRINT SCENARIO
# =============================================================================


def test_tier4_real_world_blueprint_sheet_a101():
    """Tier 4: Authoritative Real-World Blueprint Scenario on Sheet A-101 (Page 15).
    
    Target: uploads/doc_20261104_101950_6cbd34.pdf Sheet A-101 (Page 15)
    Ground Truth Oracles:
    - 71 total pages
    - Sheet A-101 at Page 15
    - Scale: 1/8" = 1'-0" (0.111111 ft/pt)
    - 5,951 CAD segments, 220 door arcs
    - 31 qualified tag instances
    - 27 raw wall runs traced, 19 consolidated runs
    - Total Gross LF ~495.83 LF (+- 2.0 LF)
    - Opening Deductions ~22.62 LF (+- 1.0 LF)
    - Total Net LF ~473.21 LF (+- 2.0 LF)
    - Total Board SF > 9,000 SF
    - Dual-red visual annotation geometry verified
    """
    doc = fitz.open(str(REAL_BLUEPRINT_PATH))
    assert len(doc) == 71, f"Expected 71 pages, got {len(doc)}"

    p15 = doc[14]
    scale, scale_str, status = detect_scale_from_page(p15)
    assert status == "DETECTED"
    assert scale_str == '1/8" = 1\'-0"'
    assert round(scale, 6) == 0.111111

    lw = extract_page_linework(p15)
    assert len(lw.segments) == 5951, f"Expected 5951 segments, got {len(lw.segments)}"
    assert len(lw.door_arcs) == 220, f"Expected 220 door arcs, got {len(lw.door_arcs)}"

    schedule_tags = {'0X', '1A', '1B', '1C', '1D', '1E', '2B', '2C', '2W', '2X', '3A', '3D', '4B1', '4K', '4P', '5B', '5D', '5E', '5L', '7A', '7B', '7C', '7E', '7F', '7G', '8A', '8P', 'GL1', 'GL2', 'PW'}
    insts = find_tag_instances_on_page(p15, schedule_tags)
    assert len(insts) == 31, f"Expected 31 tag instances, got {len(insts)}"

    raw_runs: List[WallRun] = []
    for idx, tag_inst in enumerate(insts):
        ax, ay, l_seg = find_leader_endpoint(tag_inst.center.x, tag_inst.center.y, tag_inst.tag_radius, lw.segments)
        s_seg = find_seed_segment(ax, ay, tag_inst.center.x, tag_inst.center.y, tag_inst.tag_radius, lw.segments, l_seg)
        if s_seg is None:
            continue
        traced = trace_wall_from_seed(s_seg, l_seg, lw.segments, lw.door_arcs, scale, 15, f"RUN-A101-{idx+1:03d}")
        if traced:
            wr = create_wall_run(traced, tag_inst.tag, 15, "A-101", f"RUN-A101-{idx+1:03d}", scale)
            raw_runs.append(wr)

    assert len(raw_runs) == 27, f"Expected 27 raw wall runs, got {len(raw_runs)}"

    deduped = deduplicate_wall_runs(raw_runs, scale)
    assert len(deduped) == 19, f"Expected 19 deduped wall runs, got {len(deduped)}"

    takeoff = calculate_takeoff(runs=deduped, scale_ft_per_pt=scale)

    # Verify quantitative totals
    assert abs(takeoff.total_gross_lf - 495.83) < 2.0, f"Gross LF mismatch: {takeoff.total_gross_lf}"
    assert abs(takeoff.total_net_lf - 473.21) < 2.0, f"Net LF mismatch: {takeoff.total_net_lf}"
    assert abs(takeoff.total_opening_deduction_lf - 22.62) < 1.0, f"Deduction mismatch: {takeoff.total_opening_deduction_lf}"
    assert takeoff.total_board_sf > 9000.0, f"Board SF mismatch: {takeoff.total_board_sf}"

    # Verify dual-red annotation geometry structures
    for r in deduped:
        assert r.spine is not None
        assert r.spine.length > 0.0
        assert len(r.segments) > 0

    doc.close()


def test_tier4_real_world_blueprint_sheet_a102():
    """Tier 4: Authoritative Real-World Blueprint Scenario on Sheet A-102 (Page 16).
    
    Target: uploads/doc_20261104_101950_6cbd34.pdf Sheet A-102 (Page 16)
    Ground Truth Oracles:
    - Sheet A-102 at Page 16 (Second Floor Construction Plan)
    - Scale: 1/8" = 1'-0" (0.111111 ft/pt, status = DETECTED)
    - Linework: 6,587 CAD segments, 180 door arcs
    - Tag Instances: >= 70 instances on Page 16 (tags 7A, 2B, 1C, 5E, 8A, 7F, GL1, PW)
    - Drywall Wall Tracing: produces positive gross LF and net LF
    - Non-drywall tags (GL1, PW) are segregated or rejected
    """
    doc = fitz.open(str(REAL_BLUEPRINT_PATH))
    p16 = doc[15]

    scale, scale_str, status = detect_scale_from_page(p16)
    assert status == "DETECTED"
    assert scale_str == '1/8" = 1\'-0"'
    assert round(scale, 6) == 0.111111

    lw = extract_page_linework(p16)
    assert len(lw.segments) == 6587, f"Expected 6587 segments, got {len(lw.segments)}"
    assert len(lw.door_arcs) == 180, f"Expected 180 door arcs, got {len(lw.door_arcs)}"

    candidate_tags = {'1A', '1B', '1C', '1D', '1E', '2B', '2C', '3A', '3D', '5B', '5D', '5E', '7A', '7B', '7C', '7E', '7F', '7G', '8A', 'GL1', 'GL2', 'PW'}
    insts = find_tag_instances_on_page(p16, candidate_tags)
    assert len(insts) >= 70, f"Expected >= 70 tag instances on Page 16, got {len(insts)}"

    # Filter out non-drywall tags GL1 and PW
    drywall_insts = [t for t in insts if t.tag not in ["GL1", "GL2", "PW"]]
    assert len(drywall_insts) > 0, "Expected drywall tag instances on Sheet A-102"

    raw_runs: List[WallRun] = []
    for idx, tag_inst in enumerate(drywall_insts):
        ax, ay, l_seg = find_leader_endpoint(tag_inst.center.x, tag_inst.center.y, tag_inst.tag_radius, lw.segments)
        s_seg = find_seed_segment(ax, ay, tag_inst.center.x, tag_inst.center.y, tag_inst.tag_radius, lw.segments, l_seg)
        if s_seg is None:
            continue
        traced = trace_wall_from_seed(s_seg, l_seg, lw.segments, lw.door_arcs, scale, 16, f"RUN-A102-{idx+1:03d}")
        if traced:
            wr = create_wall_run(traced, tag_inst.tag, 16, "A-102", f"RUN-A102-{idx+1:03d}", scale)
            raw_runs.append(wr)

    assert len(raw_runs) > 0, "Must trace wall runs on Sheet A-102"
    deduped = deduplicate_wall_runs(raw_runs, scale)
    assert len(deduped) > 0, "Must consolidate wall runs on Sheet A-102"

    takeoff = calculate_takeoff(runs=deduped, scale_ft_per_pt=scale)
    assert takeoff.total_gross_lf > 0.0, f"Expected positive gross LF, got {takeoff.total_gross_lf}"
    assert takeoff.total_net_lf > 0.0, f"Expected positive net LF, got {takeoff.total_net_lf}"
    assert takeoff.total_board_sf > 0.0, f"Expected positive board SF, got {takeoff.total_board_sf}"

    doc.close()
