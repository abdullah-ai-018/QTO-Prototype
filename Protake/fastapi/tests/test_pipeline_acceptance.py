"""
Pipeline Acceptance Test Suite — DEF-01 through DEF-11
=======================================================
Independent deterministic tests for the full detection → QTO pipeline.

Every defect from PIPELINE_FORENSIC_AUDIT_FULL.md is represented here as a
concrete failing assertion. Tests marked xfail document confirmed defects that
are NOT YET FIXED in production code. Tests marked skip require manual human
action. All remaining tests must pass before any production-readiness claim.

Defect map:
  DEF-01 CRITICAL  height_ft hardcoded 9.0 for every wall
  DEF-02 CRITICAL  ASSUMED-scale pages not QTO-blocked
  DEF-03 HIGH      Detection source tag lost at DB persist
  DEF-04 HIGH      PENDING walls can slip through to QTO
  DEF-05 HIGH      Implicit gap bridging (≤3.5 ft) without opening evidence
  DEF-06 MEDIUM    Layer name "layer" substring match admits non-wall layers
  DEF-07 MEDIUM    MEP layer names missing from NEGATIVE_LAYER_TOKENS
  DEF-08 MEDIUM    Opening deduction uses sides_to_hang not total_layers
  DEF-09 MEDIUM    NEEDS_REVIEW pool bridges with D1 candidates
  DEF-10 LOW       assumed_height hardcoded True even when RCP data exists
  DEF-11 LOW       DrywallScopeDecision.CONFIRMED == REQUIRED (enum collision)
"""

import inspect
import pytest
import psycopg2

DB_CONN = dict(host="localhost", dbname="QTO", user="postgres", password="ali980", port=5432)


def _db_conn():
    return psycopg2.connect(**DB_CONN)


# ══════════════════════════════════════════════════════════════════
# Group A — QTO Gate Invariants   [CODE]
# Tests the status-to-QTO eligibility invariant
# ══════════════════════════════════════════════════════════════════

class TestQtoGateInvariants:

    def _make_wall(self, status, face_b_id=None, length_ft=18.0, room_id=None,
                   height_ft=9.0, confidence=0.55):
        from app.models.enums import ReviewStatus
        from app.models.wall import Wall

        wall = Wall()
        wall.id = 999
        wall.page_id = 1
        wall.start_norm = {"x": 0.0, "y": 0.5}
        wall.end_norm = {"x": 0.5, "y": 0.5}
        wall.length_ft = length_ft
        wall.height_ft = height_ft
        wall.thickness_ft = 0.4
        wall.thickness_measured = False
        wall.wall_type = "interior"
        wall.confidence = confidence
        wall.status = status
        wall.face_a_segment_id = 42
        wall.face_b_segment_id = face_b_id
        wall.face_a_coords = None
        wall.face_b_coords = None
        wall.overlap_ratio = None
        wall.room_id = room_id
        return wall

    def _evaluate(self, wall):
        from app.trades.drywall_semantic import DrywallSemanticWallPipeline
        pipeline = DrywallSemanticWallPipeline()
        arch_walls = pipeline.process_architectural_walls(
            rooms=[], raw_walls=[wall], include_rejected=True
        )
        assert len(arch_walls) >= 1
        return arch_walls[0]

    def test_needs_review_wall_is_not_qto_eligible(self):
        """DEF-04/D1 guard: NEEDS_REVIEW wall must NOT be QTO-eligible through assumed-assembly path."""
        from app.models.enums import ReviewStatus
        wall = self._make_wall(ReviewStatus.NEEDS_REVIEW)
        aw = self._evaluate(wall)

        assert aw.qto_eligible is False, (
            f"NEEDS_REVIEW wall must not be QTO-eligible. "
            f"qto_eligible={aw.qto_eligible}, block={aw.qto_block_reason}"
        )

    def test_needs_review_wall_block_reason_is_set(self):
        """QTO block reason must be non-empty for NEEDS_REVIEW walls."""
        from app.models.enums import ReviewStatus
        wall = self._make_wall(ReviewStatus.NEEDS_REVIEW)
        aw = self._evaluate(wall)

        assert aw.qto_block_reason is not None and len(aw.qto_block_reason) > 0, (
            f"qto_block_reason must be non-empty for NEEDS_REVIEW walls. Got: {aw.qto_block_reason}"
        )

    def test_pending_wall_is_not_qto_eligible(self):
        """
        DEF-04 FIXED: PENDING walls must never become QTO-eligible regardless of
        room support. The assumed-assembly path now guards on is_approved_entity,
        not just is_needs_review_input.
        """
        from app.models.enums import ReviewStatus
        wall = self._make_wall(ReviewStatus.PENDING)
        aw = self._evaluate(wall)

        assert aw.qto_eligible is False, (
            f"DEF-04 REGRESSION: PENDING wall is QTO-eligible. "
            f"qto_block_reason={aw.qto_block_reason}"
        )

    def test_rejected_wall_has_zero_gross_sf(self):
        """REJECTED wall must contribute 0.0 to gross_sf."""
        from app.models.enums import ReviewStatus
        wall = self._make_wall(ReviewStatus.REJECTED)
        aw = self._evaluate(wall)

        gross = aw.calculate_hang_area()
        assert gross == 0.0, f"REJECTED wall gross_sf must be 0.0, got {gross}"

    def test_short_needs_review_wall_also_blocked(self):
        """NEEDS_REVIEW wall shorter than 3 ft (non-architectural scale) is also QTO-blocked."""
        from app.models.enums import ReviewStatus
        wall = self._make_wall(ReviewStatus.NEEDS_REVIEW, length_ft=2.0)
        aw = self._evaluate(wall)

        assert aw.qto_eligible is False, (
            f"Short NEEDS_REVIEW wall must not be QTO-eligible. Got qto_eligible={aw.qto_eligible}"
        )


# ══════════════════════════════════════════════════════════════════
# Group B — QTO Formula Correctness   [CODE]
# ══════════════════════════════════════════════════════════════════

class TestQtoFormulas:

    def _make_arch_wall(self, length_ft, height_ft, layers_a, layers_b, sides,
                        opening_area_sqft=0.0, qto_eligible=True):
        from app.models.architectural_wall import (
            ArchitecturalWall, WallAssemblySpec, WallClassification, DrywallScopeDecision
        )
        assembly = WallAssemblySpec(
            tag="TEST",
            layers_side_a=layers_a,
            layers_side_b=layers_b,
            sides_to_hang=sides,
        )
        return ArchitecturalWall(
            id="test-formula",
            page_id=1,
            start_norm={"x": 0.0, "y": 0.5},
            end_norm={"x": 0.5, "y": 0.5},
            length_ft=length_ft,
            height_ft=height_ft,
            classification=WallClassification.INTERIOR,
            assembly=assembly,
            qto_eligible=qto_eligible,
            drywall_scope=DrywallScopeDecision.REQUIRED,
            status="approved",
            opening_area_sqft=opening_area_sqft,
        )

    def test_gross_sf_standard_assembly(self):
        """gross = L × H × (layers_a + layers_b) for standard W1 (1+1=2)."""
        aw = self._make_arch_wall(20.0, 9.0, 1, 1, 2)
        expected = 20.0 * 9.0 * 2
        actual = aw.calculate_hang_area()
        assert abs(actual - expected) < 0.02, f"Expected {expected}, got {actual}"

    def test_gross_sf_multilayer_assembly(self):
        """gross = L × H × total_layers for W2 (2+1=3), not sides_to_hang (2)."""
        aw = self._make_arch_wall(10.0, 9.0, 2, 1, 2)
        expected = 10.0 * 9.0 * 3   # total_layers = 3
        wrong   = 10.0 * 9.0 * 2   # would use sides_to_hang
        actual  = aw.calculate_hang_area()
        assert abs(actual - expected) < 0.02, (
            f"Multi-layer gross SF wrong. Expected {expected} (total_layers=3), "
            f"got {actual}. If got {wrong}, sides_to_hang is being used instead of total_layers."
        )

    def test_gross_sf_respects_actual_height(self):
        """
        DEF-01 formula impact: ArchitecturalWall.calculate_hang_area() must use
        the actual height_ft field, not silently substitute 9.0.

        This test verifies the formula is height-aware. The companion defect
        (documented by test_height_always_9_ft_at_db_persist) is that
        blueprint_service always writes height_ft=9.0, so the semantic engine
        never actually receives any other value from production data.
        """
        aw_10ft = self._make_arch_wall(20.0, 10.0, 1, 1, 2)  # 10 ft ceiling
        aw_9ft  = self._make_arch_wall(20.0, 9.0,  1, 1, 2)  # 9 ft ceiling

        gross_10 = aw_10ft.calculate_hang_area()
        gross_9  = aw_9ft.calculate_hang_area()

        expected_10 = 20.0 * 10.0 * 2   # 400 SF
        expected_9  = 20.0 * 9.0  * 2   # 360 SF

        assert abs(gross_10 - expected_10) < 0.02, (
            f"10 ft ceiling: expected gross={expected_10}, got {gross_10}. "
            f"calculate_hang_area() must use the actual height_ft, not 9.0."
        )
        assert abs(gross_9 - expected_9) < 0.02, (
            f"9 ft ceiling: expected gross={expected_9}, got {gross_9}."
        )
        assert gross_10 > gross_9, (
            "10 ft gross must exceed 9 ft gross for same wall length. "
            "If equal, height_ft is being ignored."
        )

    def test_net_sf_equals_gross_minus_deduction(self):
        """net = gross - (opening_area × total_layers)."""
        aw = self._make_arch_wall(20.0, 9.0, 1, 1, 2, opening_area_sqft=24.0)
        gross = aw.calculate_hang_area()
        net = aw.calculate_net_hang_area()
        deduction = aw.opening_area_deduction_sqft
        assert abs(net - (gross - deduction)) < 0.02, (
            f"net != gross - deduction. gross={gross}, deduction={deduction}, net={net}"
        )

    def test_net_sf_never_negative(self):
        """net_sf must never go below 0, even with a very large opening."""
        aw = self._make_arch_wall(5.0, 9.0, 1, 1, 2, opening_area_sqft=999.0)
        net = aw.calculate_net_hang_area()
        assert net >= 0.0, f"net_sf must not be negative, got {net}"

    def test_net_sf_leq_gross_sf(self):
        """net_sf ≤ gross_sf always."""
        aw = self._make_arch_wall(20.0, 9.0, 1, 1, 2, opening_area_sqft=24.0)
        gross = aw.calculate_hang_area()
        net = aw.calculate_net_hang_area()
        assert net <= gross + 0.02, f"net_sf ({net}) must not exceed gross_sf ({gross})"

    def test_zero_qto_eligible_wall_has_zero_gross(self):
        """qto_eligible=False walls must contribute 0.0 to gross."""
        aw = self._make_arch_wall(20.0, 9.0, 1, 1, 2, qto_eligible=False)
        gross = aw.calculate_hang_area()
        assert gross == 0.0, f"Non-QTO-eligible wall must have gross=0, got {gross}"

    def test_opening_deduction_uses_total_layers_for_multilayer(self):
        """
        DEF-08: Opening deduction = opening_area × total_layers (not × sides_to_hang).
        W2 (layers_a=2, layers_b=1, sides_to_hang=2, total_layers=3):
          correct deduction = opening_area × 3
          wrong deduction   = opening_area × 2
        """
        aw = self._make_arch_wall(20.0, 9.0, 2, 1, 2, opening_area_sqft=10.0)
        deduction = aw.opening_area_deduction_sqft
        expected_correct = 10.0 * 3  # total_layers
        expected_wrong = 10.0 * 2   # sides_to_hang

        assert abs(deduction - expected_correct) < 0.02, (
            f"Opening deduction must use total_layers=3: expected={expected_correct}, "
            f"got={deduction}. If got {expected_wrong}, DEF-08 is still present."
        )

    def test_orm_conversion_preserves_net_sf(self):
        """to_orm() must persist the same net_sf as calculate_net_hang_area()."""
        aw = self._make_arch_wall(20.0, 9.0, 1, 1, 2, opening_area_sqft=24.0)
        expected_net = aw.calculate_net_hang_area()
        orm = aw.to_orm()
        assert abs(orm.net_sf - expected_net) < 0.02, (
            f"to_orm() net_sf ({orm.net_sf}) differs from calculate_net_hang_area() ({expected_net})"
        )

    def test_height_always_9_ft_at_db_persist(self):
        """
        DEF-01 FIXED: blueprint_service must pass wall.height_ft (from GeometryWall),
        not a hardcoded 9.0, and GeometryWall must carry height_ft + height_source.
        """
        from app.services import blueprint_service
        from app.geometry.engine import GeometryWall

        # 1. blueprint_service must NOT hardcode height_ft=9.0 at the persist call.
        src = inspect.getsource(blueprint_service.BlueprintService.run_geometry_analysis)
        assert "height_ft=9.0" not in src, (
            "DEF-01 REGRESSION: blueprint_service still hardcodes height_ft=9.0. "
            "It must pass wall.height_ft from GeometryWall."
        )
        assert "height_ft=wall.height_ft" in src, (
            "DEF-01: Expected 'height_ft=wall.height_ft' in blueprint_service.run_geometry_analysis."
        )

        # 2. GeometryWall must carry height_ft and height_source fields.
        import dataclasses
        gw_fields = {f.name for f in dataclasses.fields(GeometryWall)}
        assert "height_ft" in gw_fields, "DEF-01: GeometryWall is missing 'height_ft' field."
        assert "height_source" in gw_fields, "DEF-01: GeometryWall is missing 'height_source' field."


# ══════════════════════════════════════════════════════════════════
# Group C — Database Invariants   [DB]
# Require live DB. Run after at least one blueprint reprocess.
# ══════════════════════════════════════════════════════════════════

@pytest.mark.db
class TestDatabaseInvariants:

    def test_no_needs_review_wall_is_qto_eligible(self):
        """Hard invariant: qto_eligible=True → status='approved' in DB."""
        conn = _db_conn()
        cur = conn.cursor()
        cur.execute("""
            SELECT id, status, qto_block_reason
            FROM architectural_walls
            WHERE qto_eligible = true AND status != 'approved'
            LIMIT 5
        """)
        rows = cur.fetchall()
        conn.close()
        assert len(rows) == 0, (
            f"Found {len(rows)} architectural_walls that are qto_eligible but not approved: {rows}"
        )

    def test_gross_sf_matches_formula(self):
        """gross_sf in DB = length_ft × 9.0 × (layers_side_a + layers_side_b) ±0.02."""
        conn = _db_conn()
        cur = conn.cursor()
        cur.execute("""
            SELECT id, length_ft, gross_sf,
                   (length_ft * 9.0 * (layers_side_a + layers_side_b)) as expected
            FROM architectural_walls
            WHERE qto_eligible = true AND gross_sf > 0
              AND ABS(gross_sf - length_ft * 9.0 * (layers_side_a + layers_side_b)) > 0.02
            LIMIT 5
        """)
        mismatches = cur.fetchall()
        conn.close()
        assert len(mismatches) == 0, (
            f"Gross SF formula violations:\n" +
            "\n".join(f"  id={r[0]} length={r[1]} gross={r[2]} expected={r[3]}" for r in mismatches)
        )

    def test_net_sf_non_negative(self):
        """net_sf >= 0 for all QTO-eligible walls."""
        conn = _db_conn()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM architectural_walls WHERE qto_eligible=true AND net_sf < 0")
        count = cur.fetchone()[0]
        conn.close()
        assert count == 0, f"{count} QTO-eligible architectural_walls have negative net_sf."

    def test_net_sf_not_exceeds_gross_sf(self):
        """net_sf ≤ gross_sf for all QTO-eligible walls."""
        conn = _db_conn()
        cur = conn.cursor()
        cur.execute("""
            SELECT COUNT(*) FROM architectural_walls
            WHERE qto_eligible=true AND net_sf > gross_sf + 0.02
        """)
        count = cur.fetchone()[0]
        conn.close()
        assert count == 0, f"{count} QTO-eligible walls have net_sf > gross_sf."

    def test_no_hardcoded_total(self):
        """Sum of net_sf must not equal the old hardcoded PROJECT_TOTALS value (43,651 SF)."""
        conn = _db_conn()
        cur = conn.cursor()
        cur.execute("SELECT COALESCE(SUM(net_sf), 0) FROM architectural_walls WHERE qto_eligible=true")
        total = float(cur.fetchone()[0])
        conn.close()
        assert abs(total - 43651.0) > 1.0, (
            f"QTO total is {total} SF which matches the hardcoded PROJECT_TOTALS constant (43,651 SF). "
            f"Investigate whether hardcoding has leaked back into the pipeline."
        )

    def test_dual_face_walls_not_pending_post_reprocess(self):
        """After D4 fix + reprocess: distinct-face walls must NOT be PENDING (should be APPROVED)."""
        conn = _db_conn()
        cur = conn.cursor()
        cur.execute("""
            SELECT COUNT(*) FROM walls
            WHERE face_b_segment_id IS NOT NULL
              AND face_b_segment_id != face_a_segment_id
              AND status = 'PENDING'
        """)
        count = cur.fetchone()[0]
        conn.close()
        if count > 0:
            pytest.fail(
                f"{count} dual-face walls still have PENDING status. "
                f"D4 fix requires a reprocess to take effect."
            )

    def test_no_zero_area_qto_walls(self):
        """All QTO-eligible walls must have gross_sf > 0."""
        conn = _db_conn()
        cur = conn.cursor()
        cur.execute("""
            SELECT COUNT(*) FROM architectural_walls
            WHERE qto_eligible=true AND (gross_sf = 0.0 OR gross_sf IS NULL)
        """)
        count = cur.fetchone()[0]
        conn.close()
        assert count == 0, f"{count} QTO-eligible walls have zero or null gross_sf."


# ══════════════════════════════════════════════════════════════════
# Group D — Scale Guard   [CODE]
# ══════════════════════════════════════════════════════════════════

class TestScaleGuard:

    def test_assumed_scale_blocks_qto(self):
        """
        DEF-02 FIXED: process_architectural_walls() must contain a scale guard that
        sets qto_eligible=False for walls on ASSUMED-scale pages.

        The guard is verified two ways:
        1. Source inspection — the guard code must be present in the function.
        2. Behavioral — a QTO-eligible ArchitecturalWall whose page has assumed
           scale must not be qto_eligible after the pipeline runs.
        """
        from app.trades.drywall_semantic import DrywallSemanticWallPipeline
        from app.geometry.metrics import SCALE_SOURCE_ASSUMED

        # 1. Source inspection: scale guard code must be in the function.
        src = inspect.getsource(DrywallSemanticWallPipeline.process_architectural_walls)
        assert "SCALE_UNVERIFIED" in src, (
            "DEF-02 REGRESSION: 'SCALE_UNVERIFIED' guard is missing from "
            "process_architectural_walls."
        )
        assert "scale_source" in src, (
            "DEF-02 REGRESSION: scale_source check is missing from process_architectural_walls."
        )
        assert (
            "SCALE_SOURCE_ASSUMED" in src or '"assumed_default"' in src
        ), (
            "DEF-02 REGRESSION: assumed-scale literal is missing from the scale guard."
        )

        # 2. Behavioral: the guard correctly sets qto_eligible=False on a wall
        # that IS QTO-eligible before the guard fires.
        # Inject an ArchitecturalWall that is pre-marked qto_eligible=True,
        # bypass the evaluation phase by monkeypatching _evaluate_architectural_wall.
        from app.models.architectural_wall import ArchitecturalWall, DrywallScopeDecision

        pre_eligible = ArchitecturalWall(
            id="scale-test-888",
            page_id=42,
            start_norm={"x": 0.3, "y": 0.5},
            end_norm={"x": 0.5, "y": 0.5},
            length_ft=8.0,
            qto_eligible=True,
            drywall_scope=DrywallScopeDecision.REQUIRED,
            status="approved",
        )

        pipeline = DrywallSemanticWallPipeline()
        original_evaluate = pipeline._evaluate_architectural_wall

        def _mock_evaluate(wall, *args, **kwargs):
            return pre_eligible

        pipeline._evaluate_architectural_wall = _mock_evaluate

        page_scale_info = {
            42: {
                "scale_ft_per_px": 0.02,
                "width_px": 1000,
                "height_px": 1000,
                "scale_source": "assumed_default",
            }
        }

        from app.models.enums import ReviewStatus
        from app.models.wall import Wall
        wall = Wall()
        wall.id = 888
        wall.page_id = 42
        wall.start_norm = {"x": 0.3, "y": 0.5}
        wall.end_norm = {"x": 0.5, "y": 0.5}
        wall.length_ft = 8.0
        wall.height_ft = 9.0
        wall.thickness_ft = 0.4
        wall.thickness_measured = True
        wall.wall_type = "interior"
        wall.confidence = 0.90
        wall.status = ReviewStatus.APPROVED
        wall.face_a_segment_id = 10
        wall.face_b_segment_id = None
        wall.face_a_coords = None
        wall.face_b_coords = None
        wall.overlap_ratio = None
        wall.room_id = None

        arch_walls = pipeline.process_architectural_walls(
            rooms=[], raw_walls=[wall], include_rejected=True,
            page_scale_info=page_scale_info,
        )

        pipeline._evaluate_architectural_wall = original_evaluate  # restore

        assert len(arch_walls) >= 1
        aw = arch_walls[0]
        assert not aw.qto_eligible, (
            f"DEF-02 REGRESSION: wall on ASSUMED-scale page is still QTO-eligible. "
            f"qto_block_reason={getattr(aw, 'qto_block_reason', None)!r}"
        )
        assert getattr(aw, "qto_block_reason", None) == "SCALE_UNVERIFIED", (
            f"DEF-02: expected qto_block_reason='SCALE_UNVERIFIED', "
            f"got {getattr(aw, 'qto_block_reason', None)!r}"
        )


# ══════════════════════════════════════════════════════════════════
# Group E — Ground Truth   [HUMAN REQUIRED]
# ══════════════════════════════════════════════════════════════════

class TestGroundTruth:

    @pytest.mark.skip(reason=(
        "MANUAL ACTION REQUIRED: "
        "Open LSFC page 1, Surf Ave page 1, FATIMA page 1 in the inspector. "
        "Count every physical wall visible in each drawing. Record: "
        "actual_walls, detected_approved, detected_needs_review, missed. "
        "Recall = (approved + nr_that_are_real_walls) / actual_walls. "
        "Precision = real_walls_detected / all_detected. "
        "Production gate: recall >= 95%, precision >= 98%."
    ))
    def test_recall_and_precision_manual_ground_truth(self):
        """
        Manual ground truth gate. Fill in after annotation:

        RESULTS = {
            'lsfc_page_1':     {'actual': ?, 'approved': ?, 'needs_review': ?, 'missed': ?},
            'surf_ave_page_1': {'actual': ?, 'approved': ?, 'needs_review': ?, 'missed': ?},
            'fatima_page_1':   {'actual': ?, 'approved': ?, 'needs_review': ?, 'missed': ?},
        }
        Acceptance: ALL recall >= 0.95, ALL precision >= 0.98
        """
        pytest.skip("Manual ground truth required.")


# ══════════════════════════════════════════════════════════════════
# Group F — Detection Admission Defects   [CODE]
# Covers DEF-03, DEF-05, DEF-06, DEF-07
# ══════════════════════════════════════════════════════════════════

class TestDetectionAdmission:

    def test_def03_source_tag_lost_at_db_persist(self):
        """
        DEF-03 FIXED: Wall model must have a source_tag column, and blueprint_service
        must persist GeometryWall.source string into it.
        """
        from app.services import blueprint_service
        from app.models.wall import Wall

        # 1. Wall model must expose source_tag attribute.
        assert hasattr(Wall, "source_tag"), (
            "DEF-03: Wall model is missing 'source_tag' column. "
            "Run migration f1a2b3c4d5e7_add_wall_height_source_and_source_tag."
        )

        # 2. blueprint_service must write db_wall.source_tag = ...
        src = inspect.getsource(blueprint_service.BlueprintService.run_geometry_analysis)
        assert "db_wall.source_tag" in src, (
            "DEF-03 REGRESSION: blueprint_service does not persist source_tag. "
            "Verify 'db_wall.source_tag = getattr(wall, \"source\", None)' is present."
        )

    def test_def05_implicit_gap_bridge_fires_without_opening_evidence(self):
        """
        DEF-05 FIXED: classify_gap() must return G_TRUE_WALL_TERMINATION for gaps
        with no detected opening evidence — threshold-alone bridging is prohibited.
        """
        from app.geometry.wall_entity_reconstruction import classify_gap

        # Gap of 3.0 ft, no openings detected.
        scale_ft_per_px = 1.0 / 12.0
        gap_px = 3.0 / scale_ft_per_px

        result = classify_gap(
            gap_px=gap_px,
            gap_mid=500.0,
            ax_val=0.5,
            orient="H",
            openings=[],
            scale_ft_per_px=scale_ft_per_px,
        )

        assert result == "G_TRUE_WALL_TERMINATION", (
            f"DEF-05 REGRESSION: classify_gap returned {result!r} for a 3.0 ft gap with no "
            f"opening evidence. Must return 'G_TRUE_WALL_TERMINATION'."
        )

    def test_def06_layer_substring_admits_electrical_layer(self):
        """
        DEF-06: is_architectural_wall_candidate() admits CAD layers whose name contains
        the word 'layer' (e.g. 'ELECTRICAL LAYER') due to the 'layer' in l substring check.
        This is a false positive admission path.
        """
        from app.geometry.wall_entity_reconstruction import is_architectural_wall_candidate

        segment = {
            "layer": "ELECTRICAL LAYER",  # should NOT be treated as a wall candidate
            "width_pt": 1.5,
            "length_ft": 8.0,             # long enough to pass the 1.2 ft gate
            "p1": [0.1, 0.5],
            "p2": [0.9, 0.5],
            "is_in_title_block": False,
            "is_outside_envelope": False,
        }

        admitted = is_architectural_wall_candidate(segment, [], [], (1000, 1000), 0.02)

        # DEF-06 FIXED: exact/prefix match must not admit "ELECTRICAL LAYER".
        assert admitted is False, (
            "DEF-06 REGRESSION: 'ELECTRICAL LAYER' is incorrectly admitted as a wall candidate. "
            "The 'layer' substring check was replaced by exact-match; recheck is_architectural_wall_candidate."
        )

    def test_def07_mep_layer_not_rejected_by_negative_tokens(self):
        """
        DEF-07: MEP/HVAC/plumbing layer names are missing from NEGATIVE_LAYER_TOKENS.
        A segment on an 'ELECTRICAL' or 'PLUMBING' layer passes through the candidate
        filter without rejection.
        """
        from app.geometry.wall_entity_reconstruction import (
            NEGATIVE_LAYER_TOKENS, is_architectural_wall_candidate
        )

        mep_layers = ["electrical", "plumbing", "mep", "mechanical", "hvac",
                      "pipe", "conduit", "duct", "sprinkler"]

        missing_from_tokens = [
            tok for tok in mep_layers
            if not any(tok in existing for existing in NEGATIVE_LAYER_TOKENS)
        ]

        # DEF-07 FIXED: all MEP tokens must be present in NEGATIVE_LAYER_TOKENS.
        assert not missing_from_tokens, (
            f"DEF-07 REGRESSION: The following MEP tokens are absent from NEGATIVE_LAYER_TOKENS "
            f"and will NOT reject MEP-layer segments: {missing_from_tokens}."
        )

        # Secondary check: 'ELECTRICAL' segment must be rejected.
        segment = {
            "layer": "ELECTRICAL",
            "width_pt": 1.5,
            "length_ft": 8.0,
            "p1": [0.1, 0.5],
            "p2": [0.9, 0.5],
            "is_in_title_block": False,
            "is_outside_envelope": False,
        }
        admitted = is_architectural_wall_candidate(segment, [], [], (1000, 1000), 0.02)
        assert not admitted, (
            "DEF-07 REGRESSION: 'ELECTRICAL' layer must not be admitted as a wall candidate."
        )


# ══════════════════════════════════════════════════════════════════
# Group G — Pipeline Integrity Defects   [CODE]
# Covers DEF-09, DEF-10, DEF-11
# ══════════════════════════════════════════════════════════════════

class TestPipelineIntegrity:

    def test_def09_needs_review_pool_is_independently_bridged(self):
        """
        DEF-09 FIXED: NEEDS_REVIEW walls must NOT be collinearly merged.
        bridged_needs_review must equal the unmodified needs_review list.
        """
        from app.trades.drywall_semantic import DrywallSemanticWallPipeline
        src = inspect.getsource(DrywallSemanticWallPipeline.process_architectural_walls)
        assert "bridged_needs_review = self._bridge_architectural_walls(needs_review)" not in src, (
            "DEF-09 REGRESSION: NEEDS_REVIEW pool is still being independently bridged. "
            "It must pass through unmerged: 'bridged_needs_review = needs_review'."
        )
        assert "bridged_needs_review = needs_review" in src, (
            "DEF-09: Expected 'bridged_needs_review = needs_review' in process_architectural_walls."
        )

    def test_def10_assumed_height_always_true_in_source_evidence(self):
        """
        DEF-10 FIXED: assumed_height must be derived from wall.height_source,
        not hardcoded True. Verified via source inspection.
        """
        from app.trades import drywall_semantic
        src = inspect.getsource(drywall_semantic)
        # After fix, '"assumed_height": True' hardcode is gone; replaced by conditional.
        assert '"assumed_height": True' not in src and "'assumed_height': True" not in src, (
            "DEF-10 REGRESSION: 'assumed_height' is still hardcoded True in drywall_semantic. "
            "It must be derived from wall.height_source."
        )
        assert "assumed_height" in src and "height_source" in src, (
            "DEF-10: assumed_height expression must reference height_source."
        )

    def test_def11_drywallscopedecision_confirmed_collides_with_required(self):
        """
        DEF-11 FIXED: DrywallScopeDecision.CONFIRMED must have value 'confirmed',
        distinct from REQUIRED='required'. Both are DB-distinguishable.
        """
        from app.models.architectural_wall import DrywallScopeDecision

        confirmed_value = DrywallScopeDecision.CONFIRMED.value
        required_value = DrywallScopeDecision.REQUIRED.value

        assert confirmed_value != required_value, (
            f"DEF-11 REGRESSION: DrywallScopeDecision.CONFIRMED='{confirmed_value}' and "
            f"REQUIRED='{required_value}' must have distinct string values."
        )
        assert confirmed_value == "confirmed", (
            f"DEF-11: Expected CONFIRMED.value='confirmed', got '{confirmed_value}'."
        )
        assert required_value == "required", (
            f"DEF-11: Expected REQUIRED.value='required', got '{required_value}'."
        )
