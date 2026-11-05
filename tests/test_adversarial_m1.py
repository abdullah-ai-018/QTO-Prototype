"""
Adversarial Verification & Stress Test Suite for Milestone 1 (qto/ package).

EMPIRICAL CHALLENGER TEST BATTERY:
1. Scale variations: unusual scales, fractional formats, missing scales, zero scales, negative scales, extreme values.
2. Tag extraction: regex challenge with tricky strings (2X4, 2X6, 2X10, 4X4, 3X7, 1A, 2B, GL1, PW, 1A-1, W-1, etc.).
3. Door deduction: 1 door, 2 doors, door at start, door at end, door wider than wall, arc tolerance, zero clamping.
4. Vector linework: collinear chaining across micro joints (<0.5'), overlap merging, gap termination (>4').
"""

from __future__ import annotations
import math
import re
from typing import List, Tuple
import pytest
import pymupdf as fitz

from qto.scale import (
    parse_fraction,
    parse_scale_string,
    detect_scale_from_page,
    pt_to_ft,
    ft_to_pt,
    DEFAULT_FT_PER_PT,
    DEFAULT_SCALE_STR,
)
from qto.tags import (
    TAG_REGEX,
    EXCLUSION_TOKENS,
    is_valid_wall_tag,
    discover_tags_from_schedules,
    find_tag_instances_on_page,
    TagInstance,
)
from qto.geometry import Point, Segment, BoundingBox
from qto.segments import DoorArc
from qto.openings import (
    Opening,
    find_matching_door_arc,
    is_opposite_face_continuous,
    process_wall_gaps,
)
from qto.trace_walls import (
    find_leader_endpoint,
    find_seed_segment,
    trace_wall_from_seed,
    TracedWall,
)
from qto.dedup import (
    WallRun,
    compute_centerline_spine,
    create_wall_run,
    are_runs_overlapping,
    deduplicate_wall_runs,
)


# =============================================================================
# 1. SCALE VARIATIONS & STRESS TESTS
# =============================================================================

class TestScaleVariations:
    """Stress tests for scale detection, string parsing, and conversion factors."""

    @pytest.mark.parametrize(
        "scale_str,expected_ft_per_pt",
        [
            # Standard architectural
            ('1/8" = 1\'-0"', 1.0 / (72.0 * 0.125)),
            ('1/4" = 1\'-0"', 1.0 / (72.0 * 0.25)),
            ('3/16" = 1\'-0"', 1.0 / (72.0 * 0.1875)),
            ('3/32" = 1\'-0"', 1.0 / (72.0 * 0.09375)),
            ('1/2" = 1\'-0"', 1.0 / (72.0 * 0.5)),
            ('3/4" = 1\'-0"', 1.0 / (72.0 * 0.75)),
            ('1" = 1\'-0"', 1.0 / (72.0 * 1.0)),
            ('3" = 1\'-0"', 1.0 / (72.0 * 3.0)),
            # Mixed fraction formats
            ('1 1/2" = 1\'-0"', 1.0 / (72.0 * 1.5)),
            ('1-1/2" = 1\'-0"', 1.0 / (72.0 * 1.5)),
            ('3/8" = 1\'-0"', 1.0 / (72.0 * 0.375)),
            # Architectural with extra inches in target feet
            ('1/4" = 1\'-6"', 1.5 / (72.0 * 0.25)),
            ('1/8" = 2\'-0"', 2.0 / (72.0 * 0.125)),
            # Engineering scales
            ('1" = 10\'', 10.0 / 72.0),
            ('1" = 20\'', 20.0 / 72.0),
            ('1" = 30\'', 30.0 / 72.0),
            ('1" = 40\'', 40.0 / 72.0),
            ('1" = 50\'', 50.0 / 72.0),
            ('1" = 100\'', 100.0 / 72.0),
            # Metric ratios
            ('1:50', 50.0 / (72.0 * 12.0)),
            ('1:100', 100.0 / (72.0 * 12.0)),
            ('1:20', 20.0 / (72.0 * 12.0)),
            ('1:200', 200.0 / (72.0 * 12.0)),
            ('1/50', 50.0 / (72.0 * 12.0)),
            # Typographic variations (curly quotes, colons, spaces)
            ('1/8” = 1’-0”', 1.0 / (72.0 * 0.125)),
            ('1/8" : 1\'-0"', 1.0 / (72.0 * 0.125)),
            ('  1/8"   =   1\'-0"  ', 1.0 / (72.0 * 0.125)),
        ],
    )
    def test_valid_scale_variations(self, scale_str: str, expected_ft_per_pt: float):
        result = parse_scale_string(scale_str)
        assert result is not None, f"Failed to parse valid scale string: {scale_str!r}"
        assert math.isclose(result, expected_ft_per_pt, rel_tol=1e-5), (
            f"Scale mismatch for {scale_str!r}: expected {expected_ft_per_pt}, got {result}"
        )

    @pytest.mark.parametrize(
        "invalid_str",
        [
            None,
            "",
            "   ",
            "SCALE: NONE",
            "SCALE: NTS",
            "NOT TO SCALE",
            "AS NOTED",
            "DO NOT SCALE DRAWING",
            "SCALE: VERIFY IN FIELD",
            "12345",
            "!@#$%^&*",
            "0",
            '0" = 1\'-0"',       # Zero drawing length safely rejected by Pattern 1
        ],
    )
    def test_invalid_scales_safely_return_none(self, invalid_str: any):
        """Ensures parser never throws unhandled exceptions and safely returns None."""
        result = parse_scale_string(invalid_str)
        assert result is None, f"Expected None for invalid scale {invalid_str!r}, got {result}"

    def test_scale_metric_pattern_overlap_bug_empirically(self):
        """
        EMPIRICAL FINDING: Pattern 3 in qto/scale.py regex:
        r'\\b1\\s*[:/]\\s*(\\d+)\\b'
        contains an unintended vulnerability: because it matches [:/],
        any architectural fraction starting with '1/' that fails Pattern 1
        (e.g., zero target feet '1/8\" = 0\\'-0\"' or negative '-1/8\" = 1\\'-0\"')
        is erroneously captured by Pattern 3 as a 1:8 metric ratio, returning 0.009259 ft/pt!
        Furthermore, '1:0' returns 0.0 instead of None.
        """
        # 1. Zero target feet: should ideally be None, but Pattern 3 matches '1/8' as 1:8 ratio!
        res_zero_ft = parse_scale_string('1/8" = 0\'-0"')
        # Empirically document the exact value returned: 8 / (72 * 12) = 1/108
        assert math.isclose(res_zero_ft, 8.0 / (72.0 * 12.0)), "Pattern 3 intercepts 1/8 as 1:8 metric ratio"

        # 2. Negative scale: '-1/8" = 1'-0"' is intercepted by Pattern 3 as 1:8 metric ratio!
        res_neg = parse_scale_string('-1/8" = 1\'-0"')
        assert math.isclose(res_neg, 8.0 / (72.0 * 12.0))

        # 3. Metric 1:0 ratio: returns 0.0 instead of None
        res_zero_ratio = parse_scale_string("1:0")
        assert res_zero_ratio == 0.0

    def test_fraction_parsing_adversarial(self):
        """Adversarial stress testing on parse_fraction."""
        assert parse_fraction("1/8") == 0.125
        assert parse_fraction("3/16") == 0.1875
        assert parse_fraction("1-1/2") == 1.5
        assert parse_fraction("1 1/2") == 1.5
        assert parse_fraction("0.125") == 0.125
        assert parse_fraction("0") == 0.0
        assert parse_fraction("0/8") == 0.0
        # Denominator zero safety
        assert parse_fraction("1/0") is None
        assert parse_fraction("1-1/0") == 1.0  # Safe fallback (num/den if den!=0 else 0)
        assert parse_fraction("") is None
        assert parse_fraction("   ") is None
        assert parse_fraction("abc/def") is None

    def test_conversion_functions_boundary_safety(self):
        """Verify pt_to_ft and ft_to_pt boundary resilience."""
        ft_factor = 1.0 / (72.0 * 0.125)  # 1/8" scale -> 9 pt = 1 ft
        # Normal
        assert math.isclose(pt_to_ft(180.0, ft_factor), 20.0)
        assert math.isclose(ft_to_pt(20.0, ft_factor), 180.0)

        # Zero points / feet
        assert pt_to_ft(0.0, ft_factor) == 0.0
        assert ft_to_pt(0.0, ft_factor) == 0.0

        # Zero conversion factor (guard against ZeroDivisionError)
        assert ft_to_pt(20.0, 0.0) == 0.0
        assert ft_to_pt(20.0, -1.0) == 0.0

    def test_detect_scale_from_page_fallback(self):
        """Verify detect_scale_from_page falls back gracefully on blank pages."""
        doc = fitz.open()
        page = doc.new_page(width=612, height=792)
        factor, scale_str, status = detect_scale_from_page(page)
        assert status == "DEFAULT_ASSUMED"
        assert scale_str == DEFAULT_SCALE_STR
        assert math.isclose(factor, DEFAULT_FT_PER_PT)
        doc.close()


# =============================================================================
# 2. TAG EXTRACTION & REGEX ADVERSARIAL CHALLENGES
# =============================================================================

class TestTagExtractionAdversarial:
    """Stress testing regex tag extraction against framing lumber, tricky tokens, and false positives."""

    @pytest.mark.parametrize(
        "valid_tag",
        [
            "1A", "2B", "7A", "5E", "9Z", "0A", "3C",
            "1A2", "2B1", "4C3", "9Z9",
            "GL1", "GL2", "GL9",
            "PW",
        ],
    )
    def test_valid_wall_tags_accepted(self, valid_tag: str):
        assert TAG_REGEX.fullmatch(valid_tag) is not None, f"TAG_REGEX failed to match valid tag: {valid_tag}"
        assert is_valid_wall_tag(valid_tag) is True, f"is_valid_wall_tag rejected valid tag: {valid_tag}"

    @pytest.mark.parametrize(
        "lumber_or_door",
        [
            "2X4", "2X6", "2X8", "2X10", "2X12",
            "1X2", "1X3", "1X4", "1X6", "1X8",
            "4X4", "4X6", "4X8",
            "3X7", "3X6", "6X7", "6X8",
            "2x4", "2x6", "2x10", "4x4", "3x7",
        ],
    )
    def test_strictly_rejects_lumber_and_door_dimensions(self, lumber_or_door: str):
        """Negative lookahead must reject framing dimensions and door sizes."""
        # Standalone string must not be accepted by is_valid_wall_tag
        assert is_valid_wall_tag(lumber_or_door) is False, (
            f"Adversarial dimension '{lumber_or_door}' was erroneously accepted as a wall tag!"
        )
        # TAG_REGEX on uppercase must not match
        assert TAG_REGEX.fullmatch(lumber_or_door.upper()) is None

    @pytest.mark.parametrize(
        "exclusion",
        ["GA", "DC", "HR", "SF", "LF", "OC", "MAX", "MIN", "TYP", "SIM", "NTS", "REF", "DET"],
    )
    def test_exclusion_tokens_rejected(self, exclusion: str):
        assert is_valid_wall_tag(exclusion) is False

    @pytest.mark.parametrize(
        "tricky_string,should_be_valid",
        [
            ("1A", True),
            ("2B", True),
            ("GL1", True),
            ("PW", True),
            ("1A-1", False),  # Punctuation in token
            ("W-1", False),   # Letter then digit not supported by canonical regex
            ("W1", False),    # 'W1' does not match [0-9][A-Z]
            ("10A", False),   # 2 digits + 1 letter not supported
            ("A1", False),    # Letter then digit not supported
            ("1", False),
            ("A", False),
            ("WALL", False),
            ("2X4", False),
            ("3X7", False),
        ],
    )
    def test_tricky_string_fullmatch(self, tricky_string: str, should_be_valid: bool):
        result = is_valid_wall_tag(tricky_string)
        assert result == should_be_valid, (
            f"Token '{tricky_string}' expected valid={should_be_valid}, got {result}"
        )

    def test_schedule_text_search_extracts_only_valid_tags(self):
        """Simulate realistic partition schedule and drawing text blocks."""
        doc = fitz.open()
        page = doc.new_page(width=1000, height=1000)

        # Inject realistic text block containing both legitimate tags and tricky noise
        sample_text = """
        GENERAL NOTES & PARTITION SCHEDULE:
        WALL TYPE 1A: 2X4 WOOD STUDS @ 16" O.C. WITH 5/8" TYPE X GYP BD EA SIDE.
        PARTITION 2B: 2X6 METAL STUDS @ 24" O.C., 2 LAYERS GYP BD.
        GL1: INTERIOR FULL HEIGHT GLAZED SYSTEM.
        PW: PLUMBING WET WALL WITH 2X8 STUDS.
        FRAMING: USE 4X4 POSTS AT CORNERS AND 2X10 HEADERS OVER OPENINGS.
        DOORS: PROVIDE 3X7 HM DOORS AT ALL OFFICES.
        EXCLUSIONS: VERIFY MAX 1 HR FIRE RATING (100 SF MIN).
        SUB-ASSEMBLY: 1A-1 AND WINDOW W-1 DETAIL REF.
        """
        page.insert_text(fitz.Point(50, 50), sample_text, fontsize=10)

        discovered = discover_tags_from_schedules(doc)
        doc.close()

        # Must discover legitimate tags
        assert "1A" in discovered
        assert "2B" in discovered
        assert "GL1" in discovered
        assert "PW" in discovered

        # Must NOT discover lumber, door sizes, or non-wall notes
        assert "2X4" not in discovered
        assert "2X6" not in discovered
        assert "2X8" not in discovered
        assert "2X10" not in discovered
        assert "4X4" not in discovered
        assert "3X7" not in discovered
        assert "HR" not in discovered
        assert "SF" not in discovered
        assert "MIN" not in discovered
        assert "MAX" not in discovered
        assert "1A-1" not in discovered
        assert "W-1" not in discovered


# =============================================================================
# 3. DOOR DEDUCTION & OPENING ENGINE STRESS TESTS
# =============================================================================

class TestDoorDeductionAdversarial:
    """Stress tests for opening deduction, door arc matching, and multi-door geometry."""

    FT_PER_PT = 1.0 / (72.0 * 0.125)  # 9 pt = 1 ft

    def test_single_door_in_middle_exact_deduction(self):
        """20ft wall with 3ft door in the middle (Worked Example 8.7.1)."""
        # Segments: 0 to 76.5 pt (8.5 ft), door 76.5 to 103.5 pt (3.0 ft), 103.5 to 180.0 pt (8.5 ft)
        collinear_spans = [(0.0, 76.5), (103.5, 180.0)]
        door_arc = DoorArc(
            start=Point(76.5, 0.0),
            end=Point(103.5, 27.0),
            c1=Point(76.5, 15.0),
            c2=Point(90.0, 27.0),
            chord_length=math.hypot(27.0, 27.0),
            approx_radius=27.0,
            bbox=BoundingBox(76.5, 0.0, 103.5, 27.0),
        )

        t_start, t_end, openings, active_spans = process_wall_gaps(
            collinear_spans=collinear_spans,
            ox=0.0,
            oy=0.0,
            ux=1.0,
            uy=0.0,
            ft_per_pt=self.FT_PER_PT,
            door_arcs=[door_arc],
            parallel_spans=[],
            wall_run_id="RUN-001",
        )

        assert t_start == 0.0
        assert t_end == 180.0
        assert len(openings) == 1

        op = openings[0]
        assert op.classification == "CONFIRMED"
        assert op.evidence == "DOOR_SWING_ARC"
        assert math.isclose(op.width_ft, 3.0, rel_tol=1e-4)

        # Test WallRun computation
        dummy_traced = TracedWall(
            seed_segment=Segment(0, 0, 76.5, 0),
            leader_segment=None,
            traced_segments=[Segment(0, 0, 76.5, 0), Segment(103.5, 0, 180, 0)],
            collinear_segments=[],
            parallel_segments=[],
            twin_offsets=[0.0],
            t_start=t_start,
            t_end=t_end,
            openings=openings,
            ox=0.0,
            oy=0.0,
            ux=1.0,
            uy=0.0,
        )
        wall_run = create_wall_run(dummy_traced, "1A", 1, "A-101", "RUN-001", self.FT_PER_PT)
        assert math.isclose(wall_run.gross_length_ft, 20.0, rel_tol=1e-4)
        assert math.isclose(wall_run.opening_deduction_ft, 3.0, rel_tol=1e-4)
        assert math.isclose(wall_run.net_length_ft, 17.0, rel_tol=1e-4)

    def test_two_doors_on_same_wall_run(self):
        """40ft wall with two 3ft doors."""
        # 0 to 76.5 (8.5'), door 1: 76.5 to 103.5 (3'), 103.5 to 229.5 (14'), door 2: 229.5 to 256.5 (3'), 256.5 to 360.0 (11.5')
        collinear_spans = [(0.0, 76.5), (103.5, 229.5), (256.5, 360.0)]
        arc1 = DoorArc(
            start=Point(76.5, 0.0),
            end=Point(103.5, 27.0),
            c1=Point(76.5, 15.0),
            c2=Point(90.0, 27.0),
            chord_length=math.hypot(27.0, 27.0),
            approx_radius=27.0,
            bbox=BoundingBox(76.5, 0.0, 103.5, 27.0),
        )
        arc2 = DoorArc(
            start=Point(229.5, 0.0),
            end=Point(256.5, 27.0),
            c1=Point(229.5, 15.0),
            c2=Point(243.0, 27.0),
            chord_length=math.hypot(27.0, 27.0),
            approx_radius=27.0,
            bbox=BoundingBox(229.5, 0.0, 256.5, 27.0),
        )

        t_start, t_end, openings, active_spans = process_wall_gaps(
            collinear_spans=collinear_spans,
            ox=0.0,
            oy=0.0,
            ux=1.0,
            uy=0.0,
            ft_per_pt=self.FT_PER_PT,
            door_arcs=[arc1, arc2],
            parallel_spans=[],
            wall_run_id="RUN-TWO-DOORS",
        )

        assert t_start == 0.0
        assert t_end == 360.0
        assert len(openings) == 2
        total_open_ft = sum(op.width_ft for op in openings)
        assert math.isclose(total_open_ft, 6.0, rel_tol=1e-4)

        # Net length should be 40 - 6 = 34 LF
        gross_ft = (t_end - t_start) * self.FT_PER_PT
        assert math.isclose(gross_ft, 40.0, rel_tol=1e-4)
        net_ft = gross_ft - total_open_ft
        assert math.isclose(net_ft, 34.0, rel_tol=1e-4)

    def test_door_at_start_with_starter_stub(self):
        """Wall starting with a return stub followed immediately by a door."""
        # Stub from 0 to 9 pt (1 ft), door 9 to 36 pt (3 ft), remainder 36 to 180 pt (16 ft)
        collinear_spans = [(0.0, 9.0), (36.0, 180.0)]
        door_arc = DoorArc(
            start=Point(9.0, 0.0),
            end=Point(36.0, 27.0),
            c1=Point(9.0, 15.0),
            c2=Point(22.5, 27.0),
            chord_length=math.hypot(27.0, 27.0),
            approx_radius=27.0,
            bbox=BoundingBox(9.0, 0.0, 36.0, 27.0),
        )

        t_start, t_end, openings, _ = process_wall_gaps(
            collinear_spans=collinear_spans,
            ox=0.0,
            oy=0.0,
            ux=1.0,
            uy=0.0,
            ft_per_pt=self.FT_PER_PT,
            door_arcs=[door_arc],
            parallel_spans=[],
        )

        assert t_start == 0.0
        assert t_end == 180.0
        assert len(openings) == 1
        assert math.isclose(openings[0].width_ft, 3.0, rel_tol=1e-4)

    def test_door_at_end_with_corner_stub(self):
        """Wall ending with a door and a corner stub."""
        # Main run 0 to 144 pt (16 ft), door 144 to 171 pt (3 ft), corner stub 171 to 180 pt (1 ft)
        collinear_spans = [(0.0, 144.0), (171.0, 180.0)]
        door_arc = DoorArc(
            start=Point(144.0, 0.0),
            end=Point(171.0, 27.0),
            c1=Point(144.0, 15.0),
            c2=Point(157.5, 27.0),
            chord_length=math.hypot(27.0, 27.0),
            approx_radius=27.0,
            bbox=BoundingBox(144.0, 0.0, 171.0, 27.0),
        )

        t_start, t_end, openings, _ = process_wall_gaps(
            collinear_spans=collinear_spans,
            ox=0.0,
            oy=0.0,
            ux=1.0,
            uy=0.0,
            ft_per_pt=self.FT_PER_PT,
            door_arcs=[door_arc],
            parallel_spans=[],
        )

        assert t_start == 0.0
        assert t_end == 180.0
        assert len(openings) == 1
        assert math.isclose(openings[0].width_ft, 3.0, rel_tol=1e-4)

    def test_gap_wider_than_max_door_terminates_chain(self):
        """A gap of 12ft (corridor/hallway) without arc must terminate the wall run, not deduct as a door."""
        # 0 to 45 pt (5 ft), gap 45 to 153 pt (12 ft), 153 to 198 pt (5 ft)
        collinear_spans = [(0.0, 45.0), (153.0, 198.0)]

        t_start, t_end, openings, active_spans = process_wall_gaps(
            collinear_spans=collinear_spans,
            ox=0.0,
            oy=0.0,
            ux=1.0,
            uy=0.0,
            ft_per_pt=self.FT_PER_PT,
            door_arcs=[],
            parallel_spans=[],
        )

        # The chain must terminate at the first segment (0 to 45 pt)
        assert t_start == 0.0
        assert t_end == 45.0
        assert len(openings) == 0
        assert len(active_spans) == 1

    def test_net_length_zero_clamping_safety(self):
        """Ensure net_length_ft is strictly clamped to >= 0.0 even under pathological opening cases."""
        dummy_traced = TracedWall(
            seed_segment=Segment(0, 0, 10, 0),
            leader_segment=None,
            traced_segments=[Segment(0, 0, 10, 0)],
            collinear_segments=[],
            parallel_segments=[],
            twin_offsets=[0.0],
            t_start=0.0,
            t_end=10.0,
            openings=[
                Opening(
                    opening_id="OP-OVERSIZE",
                    wall_run_id="RUN-OVER",
                    page_num=1,
                    t_start=0.0,
                    t_end=10.0,
                    width_pt=10.0,
                    width_ft=20.0,  # Pathological: 20 LF opening on 1.1 LF wall
                )
            ],
            ox=0.0,
            oy=0.0,
            ux=1.0,
            uy=0.0,
        )
        wall_run = create_wall_run(dummy_traced, "1A", 1, "A-101", "RUN-OVER", self.FT_PER_PT)
        assert wall_run.net_length_ft == 0.0  # Must not be negative!


# =============================================================================
# 4. VECTOR LINEWORK & COLLINEAR CHAINING STRESS TESTS
# =============================================================================

class TestVectorLineworkAdversarial:
    """Stress tests for collinear chaining across joints (<0.5'), overlap merging, and gap termination."""

    FT_PER_PT = 1.0 / (72.0 * 0.125)  # 9 pt = 1 ft

    def test_collinear_chaining_across_micro_joints(self):
        """Gaps < 0.5 ft (joints) must bridge without opening deduction."""
        # 1/8" scale: 0.5 ft = 4.5 pt
        # Segment 1: (0, 50 pt), gap: 2.7 pt (0.3 ft < 0.5 ft), Segment 2: (52.7, 100 pt)
        collinear_spans = [(0.0, 50.0), (52.7, 100.0)]

        t_start, t_end, openings, active_spans = process_wall_gaps(
            collinear_spans=collinear_spans,
            ox=0.0,
            oy=0.0,
            ux=1.0,
            uy=0.0,
            ft_per_pt=self.FT_PER_PT,
            door_arcs=[],
            parallel_spans=[],
        )

        assert t_start == 0.0
        assert t_end == 100.0
        assert len(openings) == 0  # No opening deduction for micro joint!
        assert len(active_spans) == 1  # Successfully chained into a single span

    def test_collinear_chaining_overlapping_and_touching_segments(self):
        """Overlapping and contiguous line segments must merge seamlessly."""
        # Touching at 50.0, and overlapping from 90.0 to 100.0
        collinear_spans = [(0.0, 50.0), (50.0, 100.0), (90.0, 150.0)]

        t_start, t_end, openings, active_spans = process_wall_gaps(
            collinear_spans=collinear_spans,
            ox=0.0,
            oy=0.0,
            ux=1.0,
            uy=0.0,
            ft_per_pt=self.FT_PER_PT,
            door_arcs=[],
            parallel_spans=[],
        )

        assert t_start == 0.0
        assert t_end == 150.0
        assert len(openings) == 0
        assert len(active_spans) == 1

    def test_non_standard_gap_terminates_chain(self):
        """Gap of 4.2 ft (non-standard double door, no arc) must terminate chaining."""
        # 0 to 50 pt (5.55 ft), gap = 37.8 pt (4.2 ft), 87.8 to 150 pt
        collinear_spans = [(0.0, 50.0), (87.8, 150.0)]

        t_start, t_end, openings, active_spans = process_wall_gaps(
            collinear_spans=collinear_spans,
            ox=0.0,
            oy=0.0,
            ux=1.0,
            uy=0.0,
            ft_per_pt=self.FT_PER_PT,
            door_arcs=[],
            parallel_spans=[],
        )

        # Must terminate at 50.0 pt!
        assert t_start == 0.0
        assert t_end == 50.0
        assert len(openings) == 0
        assert len(active_spans) == 1

    def test_standard_double_door_gap_without_arc_chains_as_suspected(self):
        """Gap of 6.0 ft (standard double door) without CAD arc chains as SUSPECTED opening."""
        # 6.0 ft = 54.0 pt
        collinear_spans = [(0.0, 90.0), (144.0, 234.0)]

        t_start, t_end, openings, active_spans = process_wall_gaps(
            collinear_spans=collinear_spans,
            ox=0.0,
            oy=0.0,
            ux=1.0,
            uy=0.0,
            ft_per_pt=self.FT_PER_PT,
            door_arcs=[],
            parallel_spans=[],
        )

        assert t_start == 0.0
        assert t_end == 234.0
        assert len(openings) == 1
        assert openings[0].classification == "SUSPECTED"
        assert openings[0].evidence == "DOUBLE_DOOR_GAP"
        assert math.isclose(openings[0].width_ft, 6.0, rel_tol=1e-4)

    def test_t_junction_opposite_face_continuous_bridges(self):
        """When the opposite face is continuous across the gap, it's a T-junction, not an opening."""
        # Primary face gap from 40 to 60 pt
        collinear_spans = [(0.0, 40.0), (60.0, 100.0)]
        # Opposite parallel face runs continuously from 0 to 100 pt
        parallel_spans = [(0.0, 100.0)]

        t_start, t_end, openings, active_spans = process_wall_gaps(
            collinear_spans=collinear_spans,
            ox=0.0,
            oy=0.0,
            ux=1.0,
            uy=0.0,
            ft_per_pt=self.FT_PER_PT,
            door_arcs=[],
            parallel_spans=parallel_spans,
        )

        assert t_start == 0.0
        assert t_end == 100.0
        assert len(openings) == 0  # Bridged without deduction!

    def test_wall_run_deduplication_thresholds(self):
        """
        Verify deduplication thresholds:
        - Overlapping >= 40% merges into single run.
        - Overlapping < 40% remains two separate runs.
        """
        # Case A: 50% overlap (spans [0, 100] and [50, 150] -> overlap 50pt / 100pt = 50% >= 40%)
        spine_a1 = Segment(0, 0, 100, 0)
        spine_a2 = Segment(50, 0, 150, 0)

        run_a1 = WallRun(
            run_id="RUN-A1",
            tag="1A",
            page_num=1,
            sheet_label="A-101",
            spine=spine_a1,
            gross_length_pt=100.0,
            gross_length_ft=11.11,
            opening_deduction_ft=0.0,
            net_length_ft=11.11,
            openings=[],
            segments=[spine_a1],
            tag_instances=["TAG-1A-1"],
        )
        run_a2 = WallRun(
            run_id="RUN-A2",
            tag="1A",
            page_num=1,
            sheet_label="A-101",
            spine=spine_a2,
            gross_length_pt=100.0,
            gross_length_ft=11.11,
            opening_deduction_ft=0.0,
            net_length_ft=11.11,
            openings=[],
            segments=[spine_a2],
            tag_instances=["TAG-1A-2"],
        )

        deduped_a = deduplicate_wall_runs([run_a1, run_a2], self.FT_PER_PT)
        assert len(deduped_a) == 1, "Expected 50% overlap to merge into 1 run"
        assert math.isclose(deduped_a[0].spine.length, 150.0, rel_tol=1e-4)

        # Case B: 20% overlap (spans [0, 100] and [80, 180] -> overlap 20pt / 100pt = 20% < 40%)
        spine_b1 = Segment(0, 0, 100, 0)
        spine_b2 = Segment(80, 0, 180, 0)

        run_b1 = WallRun(
            run_id="RUN-B1",
            tag="1A",
            page_num=1,
            sheet_label="A-101",
            spine=spine_b1,
            gross_length_pt=100.0,
            gross_length_ft=11.11,
            opening_deduction_ft=0.0,
            net_length_ft=11.11,
            openings=[],
            segments=[spine_b1],
        )
        run_b2 = WallRun(
            run_id="RUN-B2",
            tag="1A",
            page_num=1,
            sheet_label="A-101",
            spine=spine_b2,
            gross_length_pt=100.0,
            gross_length_ft=11.11,
            opening_deduction_ft=0.0,
            net_length_ft=11.11,
            openings=[],
            segments=[spine_b2],
        )

        deduped_b = deduplicate_wall_runs([run_b1, run_b2], self.FT_PER_PT)
        assert len(deduped_b) == 2, "Expected 20% overlap (<40% threshold) to remain separate runs"

    def test_wall_run_conflict_flagging_different_tags(self):
        """Overlapping runs with DIFFERENT tags are flagged as CONFLICT."""
        spine1 = Segment(0, 0, 100, 0)
        spine2 = Segment(20, 0, 120, 0)

        run1 = WallRun(
            run_id="RUN-01",
            tag="1A",
            page_num=1,
            sheet_label="A-101",
            spine=spine1,
            gross_length_pt=100.0,
            gross_length_ft=11.11,
            opening_deduction_ft=0.0,
            net_length_ft=11.11,
            openings=[],
            segments=[spine1],
        )
        run2 = WallRun(
            run_id="RUN-02",
            tag="2B",
            page_num=1,
            sheet_label="A-101",
            spine=spine2,
            gross_length_pt=100.0,
            gross_length_ft=11.11,
            opening_deduction_ft=0.0,
            net_length_ft=11.11,
            openings=[],
            segments=[spine2],
        )

        deduped = deduplicate_wall_runs([run1, run2], self.FT_PER_PT)
        assert len(deduped) == 1
        assert deduped[0].status == "CONFLICT"
        assert "2B" in deduped[0].conflict_tags
