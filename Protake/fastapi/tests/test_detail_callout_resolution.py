"""Tests for detail/section callout resolution ("3/A401" -> real content or
an honest REFERENCE_UNRESOLVED flag) — app.geometry.detail_callouts and its
wiring into DrywallSemanticWallPipeline.process_architectural_walls().
"""

from app.geometry.detail_callouts import (
    DETAIL_CALLOUT_PATTERN,
    extract_detail_callouts_from_text,
    extract_engineering_info_from_detail_text,
    find_nearest_callout,
    normalize_sheet_ref,
    resolve_height_from_sheet_text,
)
from app.models.architectural_wall import HeightSource, WallAssemblySpec
from app.models.enums import WallType
from app.models.project_knowledge_graph import DetailSheetEntry
from app.models.room import Room
from app.models.wall import Wall
from app.trades.drywall_semantic import DrywallSemanticWallPipeline


# ── Unit tests: callout parsing / normalization / height extraction ────────

def test_normalize_sheet_ref_equivalence():
    assert normalize_sheet_ref("A401") == normalize_sheet_ref("A-401") == normalize_sheet_ref("a 401")


def test_detail_callout_pattern_matches_common_formats():
    assert DETAIL_CALLOUT_PATTERN.search("3/A401")
    assert DETAIL_CALLOUT_PATTERN.search("5/A-502")
    assert DETAIL_CALLOUT_PATTERN.search("12 / A601")
    assert DETAIL_CALLOUT_PATTERN.search("Room 204 - Office") is None


def test_extract_detail_callouts_from_text_finds_real_callout_and_ignores_noise():
    items = [
        (0.40, 0.30, 0.44, 0.31, "3/A401"),
        (0.10, 0.10, 0.20, 0.11, "OFFICE 204"),
        (0.50, 0.50, 0.55, 0.51, "W2"),
    ]
    found = extract_detail_callouts_from_text(items)
    assert len(found) == 1
    assert found[0]["detail_num"] == "3"
    assert found[0]["sheet_ref"] == "A401"
    assert found[0]["callout"] == "3/A401"
    assert found[0]["sheet_ref_normalized"] == "A401"


def test_find_nearest_callout_respects_max_dist():
    callouts = [
        {"center": (0.9, 0.9), "callout": "1/A999"},
        {"center": (0.41, 0.30), "callout": "3/A401"},
    ]
    wall_seg = ((0.40, 0.30), (0.40, 0.40))
    nearest = find_nearest_callout(wall_seg, callouts, max_dist=0.08)
    assert nearest is not None
    assert nearest["callout"] == "3/A401"

    far_wall_seg = ((0.0, 0.0), (0.01, 0.0))
    assert find_nearest_callout(far_wall_seg, callouts, max_dist=0.08) is None


def test_resolve_height_from_sheet_text_finds_plausible_height():
    text = "WALL SECTION - DETAIL 3\nTYPICAL INTERIOR PARTITION\n9'6\" AFF TO DECK\nSEE PLAN FOR LOCATION"
    assert resolve_height_from_sheet_text(text) == 9.5


def test_resolve_height_from_sheet_text_returns_none_when_nothing_extractable():
    text = "WALL SECTION - DETAIL 7\nMISCELLANEOUS FRAMING NOTES\nSEE STRUCTURAL FOR SIZES"
    assert resolve_height_from_sheet_text(text) is None


# ── Integration tests: pipeline wiring ──────────────────────────────────────

def _make_wall_and_room():
    """A real, dual-face, room-bounded wall — the strongest evidence tier —
    so status/qto_eligible are stable and the test isolates detail-callout
    behavior rather than incidentally exercising the 5-state machine.
    """
    rooms = [
        Room(id=1, page_id=1, name="Office 1", area_sqft=200.0, perimeter_ft=60.0,
             polygon_norm=[{"x": 0.2, "y": 0.2}, {"x": 0.4, "y": 0.2}, {"x": 0.4, "y": 0.4}, {"x": 0.2, "y": 0.4}]),
        Room(id=2, page_id=1, name="Office 2", area_sqft=200.0, perimeter_ft=60.0,
             polygon_norm=[{"x": 0.4, "y": 0.2}, {"x": 0.6, "y": 0.2}, {"x": 0.6, "y": 0.4}, {"x": 0.4, "y": 0.4}]),
    ]
    wall = Wall(
        id=10, page_id=1, length_ft=20.0, height_ft=9.0, wall_type=WallType.INTERIOR,
        start_norm={"x": 0.4, "y": 0.2}, end_norm={"x": 0.4, "y": 0.4}, confidence=0.95,
        face_a_segment_id=101, face_b_segment_id=102, thickness_measured=True,
    )
    return rooms, wall


def test_wall_with_no_nearby_callout_is_unaffected():
    """The common case: no callout near the wall -> no detail_reference* keys
    added at all, confirming the feature is fully opt-in/non-disruptive.
    """
    pipeline = DrywallSemanticWallPipeline()
    rooms, wall = _make_wall_and_room()
    text_items_by_page = {1: [(0.05, 0.05, 0.10, 0.06, "GENERAL NOTES")]}

    results = pipeline.process_architectural_walls(
        rooms, [wall], text_items_by_page=text_items_by_page, detail_sheets={},
    )
    assert len(results) == 1
    assert "detail_reference" not in results[0].source_evidence


def test_callout_resolves_to_real_sheet_with_extractable_height():
    pipeline = DrywallSemanticWallPipeline()
    rooms, wall = _make_wall_and_room()
    # Callout sits right at the wall's midpoint (0.4, 0.3).
    text_items_by_page = {1: [(0.40, 0.295, 0.43, 0.305, "3/A401")]}
    detail_sheets = {
        "A401": DetailSheetEntry(
            sheet_number="A401",
            page_id=2,
            sheet_type="wall_sections",
            text_content_full="WALL SECTION DETAIL 3 - TYPICAL PARTITION - 9'6\" AFF TO DECK",
        )
    }

    results = pipeline.process_architectural_walls(
        rooms, [wall], text_items_by_page=text_items_by_page, detail_sheets=detail_sheets,
    )
    assert len(results) == 1
    aw = results[0]
    assert aw.source_evidence["detail_reference"] == "3/A401"
    assert aw.source_evidence["detail_reference_status"] == "RESOLVED_WITH_HEIGHT"
    assert aw.height_source == HeightSource.SECTION_DETAIL
    assert aw.height_ft == 9.5
    assert aw.source_evidence["assumed_height"] is False


def test_callout_resolves_to_real_sheet_with_no_height_data():
    pipeline = DrywallSemanticWallPipeline()
    rooms, wall = _make_wall_and_room()
    text_items_by_page = {1: [(0.40, 0.295, 0.43, 0.305, "3/A401")]}
    detail_sheets = {
        "A401": DetailSheetEntry(
            sheet_number="A401",
            page_id=2,
            sheet_type="wall_sections",
            text_content_full="WALL SECTION DETAIL 3 - SEE STRUCTURAL FOR STUD SIZE",
        )
    }

    results = pipeline.process_architectural_walls(
        rooms, [wall], text_items_by_page=text_items_by_page, detail_sheets=detail_sheets,
    )
    aw = results[0]
    assert aw.source_evidence["detail_reference"] == "3/A401"
    assert aw.source_evidence["detail_reference_status"] == "RESOLVED_NO_HEIGHT_DATA"
    # Height must be left untouched — no fabricated value.
    assert aw.height_source != HeightSource.SECTION_DETAIL


def test_callout_to_missing_sheet_is_honestly_unresolved_and_does_not_block_qto():
    """A wall referencing "3/A401" when A401 isn't in this drawing set must be
    flagged REFERENCE_UNRESOLVED, never silently dropped and never faked —
    and must not retroactively block an otherwise-eligible wall's QTO.
    """
    pipeline = DrywallSemanticWallPipeline()
    rooms, wall = _make_wall_and_room()
    text_items_by_page = {1: [(0.40, 0.295, 0.43, 0.305, "3/A401")]}

    results = pipeline.process_architectural_walls(
        rooms, [wall], text_items_by_page=text_items_by_page, detail_sheets={},
    )
    aw = results[0]
    assert aw.source_evidence["detail_reference"] == "3/A401"
    assert aw.source_evidence["detail_reference_status"] == "REFERENCE_UNRESOLVED"
    # This wall independently qualifies for QTO via real room-boundary support
    # (see _make_wall_and_room) — the unresolved reference must not block it.
    assert aw.qto_eligible is True


# ── Real detail-bubble shape: word-pair, not slash-token ────────────────────
# Confirmed against an actual 18-page architectural PDF's raw extracted
# text (see plan doc / final report) — a real detail bubble extracts as two
# separate adjacent word tokens, not one "N/SHEET" string.

def test_word_pair_callout_detection_matches_real_bubble_shape():
    items = [
        (0.500, 0.300, 0.510, 0.310, "1"),
        (0.500, 0.311, 0.512, 0.320, "S302"),
        (0.10, 0.10, 0.12, 0.11, "204"),  # an unrelated room number, must be ignored
    ]
    found = extract_detail_callouts_from_text(items)
    assert len(found) == 1
    assert found[0]["callout"] == "1/S302"
    assert found[0]["match_method"] == "word_pair"


def test_word_pair_callout_detection_ignores_distant_pairs():
    items = [
        (0.10, 0.10, 0.11, 0.11, "1"),
        (0.90, 0.90, 0.92, 0.91, "A999"),  # far away — must not pair
    ]
    assert extract_detail_callouts_from_text(items) == []


# ── Engineering-info extraction ─────────────────────────────────────────────

def test_extract_engineering_info_synthetic_fixture():
    text = '4" 16GA GAL\'V STEEL STUDS @ 16" O.C. — (2) LAYER OF 5/8" TYPE X GYP BOARD — STC-50 — 2 HOUR FIRE RATED'
    info = extract_engineering_info_from_detail_text(text)
    assert info["stud_depth_in"]["value"] == 4.0
    assert info["stud_gauge"]["value"] == "16 GA"
    assert info["stud_spacing_in"]["value"] == 16.0
    assert info["layers"]["value"] == 2
    assert info["board_type"]["value"] == '5/8" Type X GWB'
    assert info["fire_rating_hr"]["value"] == 2.0
    assert info["sound_rating_stc"]["value"] == 50.0


def test_extract_engineering_info_against_real_architectural_legend_text():
    """Literal excerpt of a real 18-page architectural blueprint's own
    wall-type legend sheet (not a synthetic fixture) — proves the
    extractor works on genuine construction-document language.
    """
    real_text = (
        'EXTERIOR WALL - 1:\n'
        '- 4" FACE BRICK FINISH\n'
        '- 2" INSULATION BOARD\n'
        '- 5/8" EXTERIOR SHEATHING\n'
        '- 4" 16GA GAL\'V STEEL STUDS @ 16" O.C. (MAX.)\n'
        '- 3 5/8" (R-19) BATT INSULATION WITH VAPOR BARRIER\n'
        '- 5/8" GYP. BOARD 2PLY FINISH @ INTERIOR\n'
        '\n'
        'NON BEARING INTERIOR PARTITION (2 HOUR FIRE RATED)\n'
        '(2) LAYER OF 5/8" THK TYPE X GYP BOARD'
    )
    info = extract_engineering_info_from_detail_text(real_text)
    assert info["stud_depth_in"]["value"] == 4.0
    assert info["stud_gauge"]["value"] == "16 GA"
    assert info["stud_spacing_in"]["value"] == 16.0
    assert info["insulation"]["value"] == "R-19"
    assert info["fire_rating_hr"]["value"] == 2.0
    assert info["board_type"]["value"] == '5/8" GWB'
    assert info["layers"]["value"] == 2
    # This excerpt never states a single overall "X\" WALL" figure —
    # correctly absent, not guessed.
    assert "thickness_in" not in info


def test_extract_engineering_info_finds_nothing_extractable_returns_empty():
    text = "SEE STRUCTURAL DRAWINGS FOR ADDITIONAL INFORMATION"
    assert extract_engineering_info_from_detail_text(text) == {}


# ── Conflict detection: schedule vs. detail-sheet disagreement ─────────────

def _schedule_verified_wall_and_pipeline(detail_sheet_text: str):
    """A wall tagged 'W2', resolved against a verified 6\" partition
    schedule entry (total assembly thickness 7.25\"), with a nearby detail
    callout "3/A401" resolving to a sheet whose text states its own
    thickness — the two-source setup conflict detection is built for.
    """
    rooms = [
        Room(id=1, page_id=1, name="Office 1", area_sqft=200.0, perimeter_ft=60.0,
             polygon_norm=[{"x": 0.2, "y": 0.2}, {"x": 0.4, "y": 0.2}, {"x": 0.4, "y": 0.4}, {"x": 0.2, "y": 0.4}]),
        Room(id=2, page_id=1, name="Office 2", area_sqft=200.0, perimeter_ft=60.0,
             polygon_norm=[{"x": 0.4, "y": 0.2}, {"x": 0.6, "y": 0.2}, {"x": 0.6, "y": 0.4}, {"x": 0.4, "y": 0.4}]),
    ]
    wall = Wall(
        id=20, page_id=1, length_ft=20.0, height_ft=9.0, wall_type=WallType.INTERIOR,
        start_norm={"x": 0.4, "y": 0.2}, end_norm={"x": 0.4, "y": 0.4}, confidence=0.95,
        face_a_segment_id=201, face_b_segment_id=202, thickness_measured=True,
    )
    text_items_by_page = {
        1: [
            (0.40, 0.295, 0.42, 0.305, "W2"),
            (0.395, 0.31, 0.43, 0.32, "3/A401"),
        ]
    }
    schedule_spec = WallAssemblySpec(
        tag="W2", description="6\" Metal Stud Partition, 5/8\" GWB Each Side",
        stud_depth_in=6.0, stud_gauge="20 GA",
        board_type_side_a="5/8\" GWB", layers_side_a=1,
        board_type_side_b="5/8\" GWB", layers_side_b=1,
        sides_to_hang=2, source="partition_schedule_A801",
    )
    schedule_evidence = {
        "W2": {"verified": True, "assembly_definition": schedule_spec, "schedule_sheet": "A801"},
    }
    detail_sheets = {
        "A401": DetailSheetEntry(sheet_number="A401", page_id=2, sheet_type="wall_sections", text_content_full=detail_sheet_text),
    }
    pipeline = DrywallSemanticWallPipeline(schedule_evidence=schedule_evidence)
    results = pipeline.process_architectural_walls(
        rooms, [wall], text_items_by_page=text_items_by_page, detail_sheets=detail_sheets,
    )
    return results[0]


def test_conflicting_schedule_and_detail_thickness_produces_needs_review_not_a_silent_choice():
    # Schedule total = 6.0 + (1+1)*0.625 = 7.25". Detail says 9" — a real,
    # material disagreement (>1.5" apart).
    aw = _schedule_verified_wall_and_pipeline('TYPICAL PARTITION DETAIL - 9" WALL - SEE PLAN')

    assert aw.assembly_verified is True  # schedule resolution still succeeded
    conflicts = aw.source_evidence.get("conflicts")
    assert conflicts, "expected a recorded conflict, not a silent choice"
    thickness_conflict = next(c for c in conflicts if c["field"] == "thickness_in")
    values = {s["method"]: s["value"] for s in thickness_conflict["sources"]}
    assert values["partition_schedule"] == 7.25
    assert values["detail_text"] == 9.0
    assert aw.source_evidence["detail_reference_status"] == "CONFLICT"
    # The engineer must see this, not have the system quietly pick one:
    assert aw.status == "needs_review"
    assert aw.qto_eligible is False
    assert aw.qto_block_reason == "ASSEMBLY_SOURCE_CONFLICT"


def test_agreeing_schedule_and_detail_thickness_no_conflict_and_records_provenance():
    # Detail says 7" — within 1.5" of the schedule's 7.25" total, i.e. the
    # same real assembly described two ways, not a genuine disagreement.
    aw = _schedule_verified_wall_and_pipeline('TYPICAL PARTITION DETAIL - 7" WALL - SEE PLAN')

    assert "conflicts" not in aw.source_evidence
    assert aw.qto_eligible is True
    assert aw.status == "approved"
    fp = aw.source_evidence["field_provenance"]
    assert fp["thickness_in"]["value"] == 7.0
    assert fp["thickness_in"]["source_sheet"] == "A401"
    assert fp["thickness_in"]["method"] == "detail_text"
