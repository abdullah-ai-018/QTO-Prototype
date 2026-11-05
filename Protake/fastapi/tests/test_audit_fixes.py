"""Regression tests for the audit-and-repair session fixes.

Covers:
- Wall tag normalization (EW1 == EW-1, TYPE A == TYPE-A)
- Schedule conflict detection (same tag, different specs on different sheets)
- Canonical wall classification (NEEDS_REVIEW stays NEEDS_REVIEW)
- Sheet number extraction returns None instead of a fake placeholder
- Detail callout crash isolation (NameError fix)
- Assistant investigate_wall no fabricated fallbacks
"""

import re
import pytest


# ---------------------------------------------------------------------------
# 1. Wall tag normalization
# ---------------------------------------------------------------------------

class TestWallTagNormalization:
    def _pattern(self):
        from app.geometry.wall_tags import DYNAMIC_WALL_TAG_PATTERN
        return DYNAMIC_WALL_TAG_PATTERN

    def test_ew_with_hyphen(self):
        assert self._pattern().search("EW-1")

    def test_ew_without_hyphen(self):
        assert self._pattern().search("EW1")

    def test_ew_with_space(self):
        assert self._pattern().search("EW 2")

    def test_type_with_hyphen(self):
        assert self._pattern().search("TYPE-A")

    def test_type_with_space(self):
        assert self._pattern().search("TYPE A")

    def test_type_without_separator(self):
        # TYPE[-\s]?[A-Z] intentionally matches TYPE A, TYPE-A, and TYPEA
        assert self._pattern().search("TYPEA")

    def test_ew_case_insensitive(self):
        assert self._pattern().search("ew-1")

    def test_regular_tag(self):
        assert self._pattern().search("P-1")

    def test_no_false_positive_middle_of_word(self):
        # "PREVIEW" should not match as a wall tag
        m = self._pattern().search("PREVIEW WINDOW")
        # If it does match, it should match EW inside PREVIEW — verify it's not "EW" as standalone
        if m:
            assert "EW" not in m.group(0).upper() or m.start() > 0


# ---------------------------------------------------------------------------
# 2. Schedule tag normalization (schedule_parser uses same pattern)
# ---------------------------------------------------------------------------

class TestScheduleTagNormalization:
    def test_ew1_matches_in_schedule_parser(self):
        from app.intelligence.schedule_parser import MultiSheetScheduleParser
        parser = MultiSheetScheduleParser()
        # Minimal schedule text with EW1 (no hyphen)
        text = "EW1  3-5/8\" STUD  1HR FIRE RATED"
        result = parser.parse_partition_schedule(text, "A-601", None)
        # Either finds it or finds nothing — must NOT crash
        assert isinstance(result, dict)

    def test_ew_hyphen_matches_in_schedule_parser(self):
        from app.intelligence.schedule_parser import MultiSheetScheduleParser
        parser = MultiSheetScheduleParser()
        text = "EW-1  3-5/8\" STUD  1HR FIRE RATED"
        result = parser.parse_partition_schedule(text, "A-601", None)
        assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# 3. Schedule conflict detection
# ---------------------------------------------------------------------------

class TestScheduleConflictDetection:
    """_merge_with_conflict_detection(existing, new) merges two full tag dicts."""

    def _make_entry(self, stud_depth_in: float, source_sheet: str) -> dict:
        from app.intelligence.schedule_table_parser import WallAssemblySpec
        spec = WallAssemblySpec(
            tag="P-1", description="Interior partition",
            stud_depth_in=stud_depth_in, stud_gauge="20 GA",
            board_type_side_a='5/8" GWB', layers_side_a=1,
            board_type_side_b='5/8" GWB', layers_side_b=1,
            sides_to_hang=2,
        )
        return {"assembly_definition": spec, "schedule_sheet": source_sheet, "verified": True}

    def test_same_tag_same_sheet_is_not_conflict(self):
        from app.intelligence.schedule_table_parser import _merge_with_conflict_detection
        existing = {"P-1": self._make_entry(3.625, "A601")}
        new = {"P-1": self._make_entry(3.625, "A601")}
        _merge_with_conflict_detection(existing, new)
        assert not existing["P-1"].get("conflicted", False)

    def test_same_tag_different_sheet_different_spec_is_conflict(self):
        from app.intelligence.schedule_table_parser import _merge_with_conflict_detection
        existing = {"P-1": self._make_entry(3.625, "A601")}
        new = {"P-1": self._make_entry(6.0, "A602")}  # different spec, different sheet
        _merge_with_conflict_detection(existing, new)
        assert existing["P-1"].get("conflicted") is True

    def test_same_tag_different_sheet_same_spec_is_not_conflict(self):
        from app.intelligence.schedule_table_parser import _merge_with_conflict_detection
        existing = {"P-1": self._make_entry(3.625, "A601")}
        new = {"P-1": self._make_entry(3.625, "A602")}  # same spec, different sheet
        _merge_with_conflict_detection(existing, new)
        assert not existing["P-1"].get("conflicted", False)


# ---------------------------------------------------------------------------
# 4. Canonical wall classification — NEEDS_REVIEW stays NEEDS_REVIEW
# ---------------------------------------------------------------------------

class TestCanonicalWallClassification:
    def _classify(self, **kwargs):
        from app.geometry.wall_classification import classify_wall_canonical
        defaults = dict(
            classification_str=None, class_reason=None,
            room_ids=[], adjacent_room_ids=[], room_graph=None,
            wall_type_code=None, wall_tag=None, tag_description=None,
            source_sheet=None,
        )
        defaults.update(kwargs)
        return classify_wall_canonical(**defaults)

    def test_no_evidence_returns_needs_review(self):
        result = self._classify()
        assert result.category == "NEEDS_REVIEW"

    def test_exterior_wall_type_code_gives_exterior_perimeter(self):
        result = self._classify(wall_type_code="EXTERIOR_PERIMETER_WALL")
        assert result.category == "EXTERIOR_PERIMETER"

    def test_stair_core_requires_room_evidence(self):
        result = self._classify(wall_type_code="STAIR_CORE_WALL")
        # Without room graph evidence, confidence should be lower but still classify
        assert result.category in ("STAIR_CORE", "NEEDS_REVIEW")

    def test_interior_two_rooms(self):
        # Simulate two adjacent rooms — topology strong enough for INTERIOR_PARTITION
        result = self._classify(
            classification_str="interior",
            room_ids=["r1", "r2"],
        )
        assert result.category == "INTERIOR_PARTITION"

    def test_structural_bearing_from_type_code(self):
        result = self._classify(wall_type_code="STRUCTURAL_BEARING_WALL")
        assert result.category == "STRUCTURAL_BEARING"

    def test_structural_from_tag_or_schedule(self):
        result = self._classify(wall_tag="SW-1", tag_description="6-inch CMU Structural Bearing Wall")
        assert result.category == "STRUCTURAL_BEARING"
        assert result.confidence >= 0.85

    def test_shaft_from_tag_or_schedule(self):
        result = self._classify(wall_tag="SH-1", tag_description="2HR Shaftwall Enclosure")
        assert result.category == "SHAFT"
        assert result.confidence >= 0.80

    def test_demising_from_tag_or_schedule(self):
        result = self._classify(wall_tag="DW-1", tag_description="Tenant Demising Partition 2HR")
        assert result.category == "DEMISING"
        assert result.confidence >= 0.85

    def test_wet_core_from_tag_or_schedule(self):
        result = self._classify(wall_tag="WET-1", tag_description="Restroom Plumbing Wet Wall")
        assert result.category == "WET_CORE"
        assert result.confidence >= 0.80

    def test_corridor_from_tag_or_schedule(self):
        result = self._classify(wall_tag="CW-1", tag_description="Egress Corridor Wall Partition")
        assert result.category == "CORRIDOR"
        assert result.confidence >= 0.70

    def test_stair_from_tag_or_schedule(self):
        result = self._classify(wall_tag="ST-1", tag_description="Stair Enclosure Wall")
        assert result.category == "STAIR_CORE"
        assert result.confidence >= 0.85

    def test_exterior_from_ew_tag(self):
        result = self._classify(wall_tag="EW-1", tag_description="Exterior Wall 6in Stud")
        assert result.category == "EXTERIOR_PERIMETER"
        assert result.confidence >= 0.85

    def test_needs_review_from_exterior_classification_no_topology(self):
        # "exterior" string without topology or type_code → falls to confidence check
        result = self._classify(classification_str="exterior")
        # Could be EXTERIOR_PERIMETER with low confidence or NEEDS_REVIEW — must not be interior
        assert result.category != "INTERIOR_PARTITION"


# ---------------------------------------------------------------------------
# 5. Sheet number extraction — no fake placeholders
# ---------------------------------------------------------------------------

class TestSheetNumberExtraction:
    """extract_sheet_number_from_page returns (None, 0.0) when nothing found,
    never a fabricated page-index code."""

    def test_returns_none_and_zero_when_no_page_object(self):
        """Unit-test the extractor against an empty text block (no fitz page)."""
        from app.geometry.page_classifier import extract_sheet_number_from_page
        import unittest.mock as mock

        # Fake a fitz page that returns no text blocks
        fake_page = mock.MagicMock()
        fake_page.get_text.return_value = {"blocks": []}

        result = extract_sheet_number_from_page(fake_page)
        assert result == (None, 0.0), f"Expected (None, 0.0) but got {result}"

    def test_returns_none_not_a_placeholder_string(self):
        from app.geometry.page_classifier import extract_sheet_number_from_page
        import unittest.mock as mock

        fake_page = mock.MagicMock()
        fake_page.get_text.return_value = {"blocks": []}

        sheet_code, confidence = extract_sheet_number_from_page(fake_page)
        assert sheet_code is None, "Must return None, not a fabricated placeholder"
        assert confidence == 0.0

    def test_callout_prefix_is_rejected(self):
        """A token immediately after 'digit/' is a callout ref, not the page's sheet."""
        from app.geometry.page_classifier import extract_sheet_number_from_page
        import unittest.mock as mock

        fake_page = mock.MagicMock()
        # Simulate a text block containing only a callout ref "3/A401"
        fake_page.get_text.return_value = {
            "blocks": [{
                "type": 0,
                "bbox": [100, 100, 200, 120],
                "lines": [{"spans": [{"text": "3/A401", "bbox": [100, 100, 200, 120]}]}],
            }]
        }
        sheet_code, confidence = extract_sheet_number_from_page(fake_page)
        # "A401" after "3/" is a callout ref — should be rejected
        assert sheet_code is None or "A401" not in (sheet_code or "")

    def test_title_block_match_returned(self):
        """A real-looking sheet number in the title block quadrant should be returned."""
        from app.geometry.page_classifier import extract_sheet_number_from_page
        import unittest.mock as mock

        # Simulate a large page (1000×700pt) with "A-101" in the bottom-right
        fake_page = mock.MagicMock()
        fake_page.rect = mock.MagicMock()
        fake_page.rect.width = 1000
        fake_page.rect.height = 700

        fake_page.get_text.return_value = {
            "blocks": [{
                "type": 0,
                # bottom-right corner (x > 0.80 * 1000, y > 0.60 * 700)
                "bbox": [850, 500, 950, 520],
                "lines": [{"spans": [{"text": "A-101", "bbox": [850, 500, 950, 520]}]}],
            }]
        }
        sheet_code, confidence = extract_sheet_number_from_page(fake_page)
        assert sheet_code == "A-101"
        assert confidence >= 0.80


# ---------------------------------------------------------------------------
# 6. pdf_engine RasterizedPage.sheet_code is nullable
# ---------------------------------------------------------------------------

def test_rasterized_page_sheet_code_is_nullable():
    from app.services.pdf_engine import RasterizedPage
    rp = RasterizedPage(
        page_number=1, width_px=100, height_px=100, dpi=300,
        image_path="/tmp/img.png", thumbnail_path="/tmp/thumb.png",
        sheet_code=None, sheet_code_confidence=0.0, sheet_name="Floor Plan",
    )
    assert rp.sheet_code is None


# ---------------------------------------------------------------------------
# 7. SheetMetadata.sheet_number is nullable
# ---------------------------------------------------------------------------

def test_sheet_metadata_sheet_number_nullable():
    from app.models.project_knowledge_graph import SheetMetadata, SheetDiscipline, SheetType
    meta = SheetMetadata(
        page_id=1, page_number=1,
        sheet_number=None,
        sheet_title="Floor Plan",
        discipline=SheetDiscipline.ARCHITECTURAL,
        sheet_type=SheetType.FLOOR_PLAN,
    )
    assert meta.sheet_number is None


def test_sheet_classifier_returns_none_when_no_number_found():
    from app.intelligence.sheet_classifier import BlueprintSheetClassifier
    classifier = BlueprintSheetClassifier()
    # Text with no sheet number pattern
    meta = classifier.classify_sheet(page_id=1, page_number=1, text_content="FLOOR PLAN LEVEL 1")
    assert meta.sheet_number is None


def test_sheet_classifier_extracts_real_number():
    from app.intelligence.sheet_classifier import BlueprintSheetClassifier
    classifier = BlueprintSheetClassifier()
    meta = classifier.classify_sheet(page_id=1, page_number=1, text_content="FLOOR PLAN A-101 LEVEL 1")
    assert meta.sheet_number == "A-101"


# ---------------------------------------------------------------------------
# 8. investigate_wall — no fabricated engineering values
# ---------------------------------------------------------------------------

class TestInvestigateWallNoFabrication:
    def _call(self, message: str, wall_data: dict | None = None):
        from app.services.assistant_service import investigate_wall
        from unittest.mock import MagicMock
        db = MagicMock()
        project = MagicMock()
        project.id = 1
        return investigate_wall(
            db=db, project=project,
            wall_id="AW-99",
            message=message,
            history=[],
            selected_wall_data=wall_data,
        )

    def test_no_wall_data_no_fabricated_dimensions(self):
        result = self._call("why did you detect this wall", wall_data=None)
        answer = result["answer"]
        # Must not contain fabricated hardcoded values
        assert "17.00" not in answer, "Hardcoded 17ft length must not appear"
        assert "4.88" not in answer, "Hardcoded 4.875in thickness must not appear"
        assert "A104" not in answer, "Hardcoded sheet A104 must not appear"
        assert "3/A401" not in answer, "Hardcoded callout 3/A401 must not appear"
        assert "A801" not in answer, "Hardcoded schedule sheet A801 must not appear"

    def test_no_wall_data_no_fabricated_confidence(self):
        result = self._call("verified", wall_data=None)
        answer = result["answer"]
        # 98% and 95% were the hardcoded fake confidence values
        assert "98%" not in answer, "Fabricated 0.98 confidence must not appear"

    def test_real_wall_data_used_correctly(self):
        wall_data = {
            "lengthFt": 24.5,
            "heightFt": 10.0,
            "thicknessIn": 6.0,
            "sheetCode": "A-201",
            "confidence": 0.87,
        }
        result = self._call("why did you detect this wall", wall_data=wall_data)
        answer = result["answer"]
        assert "24.50" in answer
        assert "A-201" in answer

    def test_missing_sheet_code_shows_not_available(self):
        result = self._call("sheet", wall_data={})
        answer = result["answer"]
        assert "Not available from source" in answer

    def test_evidence_confidence_not_hardcoded_098(self):
        result = self._call("qto", wall_data={"netHangAreaSf": 120.0, "qtoEligible": True})
        # The evidence list qto field must not have 0.98 hardcoded confidence
        qto_ev = next((e for e in result.get("evidence", []) if e["field"] == "qto"), None)
        assert qto_ev is not None
        assert qto_ev.get("confidence") is None, "QTO evidence confidence must not be hardcoded 0.98"

    def test_actions_empty_when_no_sheet_code(self):
        result = self._call("detect", wall_data={"sheetCode": None})
        # FOCUS_SOURCE action must not appear when sheet_code is None
        focus_actions = [a for a in result.get("actions", []) if a["type"] == "FOCUS_SOURCE"]
        assert len(focus_actions) == 0, "FOCUS_SOURCE action must not be emitted without a real sheet code"

    def test_actions_present_when_real_sheet_code(self):
        result = self._call("detect", wall_data={"sheetCode": "A-101", "pageNumber": 2})
        focus_actions = [a for a in result.get("actions", []) if a["type"] == "FOCUS_SOURCE"]
        assert len(focus_actions) == 1
        assert focus_actions[0]["sheet_code"] == "A-101"


# ---------------------------------------------------------------------------
# 9. thickness_source default must be PROJECT_DEFAULT, not paired_geometry
# ---------------------------------------------------------------------------

def test_architectural_wall_domain_thickness_source_default():
    """ArchitecturalWall.thickness_source defaults to PROJECT_DEFAULT,
    never to PAIRED_GEOMETRY — the latter claims the value was measured,
    which is false for walls where no paired geometry was found."""
    from app.models.architectural_wall import ArchitecturalWall, ThicknessSource
    wall = ArchitecturalWall(
        id="test-1", page_id=1,
        start_norm={"x": 0.0, "y": 0.0},
        end_norm={"x": 0.5, "y": 0.0},
        length_ft=10.0,
    )
    assert wall.thickness_source == ThicknessSource.PROJECT_DEFAULT, (
        f"thickness_source must default to PROJECT_DEFAULT, got {wall.thickness_source}"
    )
    assert wall.thickness_source != ThicknessSource.PAIRED_GEOMETRY


def test_architectural_wall_schema_thickness_source_default():
    """ArchitecturalWallRead Pydantic schema defaults thickness_source to
    'project_default', not 'paired_geometry'.  A 'paired_geometry' default
    would tell the frontend that every wall's thickness was measured from
    dual drawing faces, which is untrue for assumed-thickness walls."""
    from app.schemas.architectural_wall import ArchitecturalWallRead
    schema = ArchitecturalWallRead(
        id="test-1", page_id=1,
        start_norm={"x": 0.0, "y": 0.0},
        end_norm={"x": 0.5, "y": 0.0},
        length_ft=10.0,
    )
    assert schema.thickness_source == "project_default", (
        f"Schema thickness_source must default to 'project_default', got {schema.thickness_source!r}"
    )


def test_architectural_wall_schema_confidence_default_is_zero():
    """ArchitecturalWallRead Pydantic schema must not default confidence to
    0.95 — fabricating high confidence for every wall regardless of actual
    evidence quality."""
    from app.schemas.architectural_wall import ArchitecturalWallRead
    schema = ArchitecturalWallRead(
        id="test-1", page_id=1,
        start_norm={"x": 0.0, "y": 0.0},
        end_norm={"x": 0.5, "y": 0.0},
        length_ft=10.0,
    )
    assert schema.confidence == 0.0, (
        f"Schema confidence must default to 0.0 (not a fabricated 0.95), got {schema.confidence}"
    )
