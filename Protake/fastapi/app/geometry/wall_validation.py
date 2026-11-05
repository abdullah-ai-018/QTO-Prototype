"""Context-aware acceptance gate for a wall candidate.

Sits between raw segment extraction (line_extraction.py, vector_walls.py,
wall_band.py, double_line_walls.py — all unchanged by this module) and
persistence (blueprint_service.py). `wall_confidence()` (wall_graph.py)
still computes the plausibility score exactly as before; what was missing
was anything that turned that score, plus the page context that was being
computed elsewhere and never consulted here, into an accept/review
decision — see FORENSIC_AUDIT_REPORT.md for the traced case this closes
(Wall id 77333: an isolated, unlinked, non-exterior vector segment that
reached the database with confidence 0.25 and no gate ever checked it).

Two context-driven gates, both built entirely from evidence
`analyze_page()` already computes for `wall_confidence()` and
`classify_page_content()` — no new numeric threshold is introduced here:

1. Drawing-zone containment (drawing_zone.py, MIN_DRAWING_ZONE_OVERLAP)
   — the exact same check and constant rooms and AI findings already use,
   simply never applied to a wall candidate before.
2. The "isolated, unlinked, non-exterior" evidence triple that
   wall_confidence()'s own docstring and engine.py's isolated-segment
   comment already name as the signature of a text underline / fixture
   symbol stroke / dimension witness line, not a real wall — promoted from
   "confidence penalty" (still scored, still visible) to "needs review, not
   an ordinary accepted wall" (see WallDecision.status).

Connectivity is deliberately NOT an absolute requirement: a wall that is
unconnected but genuinely borders a detected room, or sits on the
building's exterior envelope, is real evidence a legitimate wall can
terminate at a door, opening, or the building edge — only the triple
negative is treated as review-worthy.

A third, separate adjustment — trade-aware confidence weighting — nudges
the numeric confidence score (never the accept/reject status, which is
decided entirely by the two gates above and stays identical regardless of
trade) based on `PageContext.selected_trade`. See TRADE_CONFIDENCE_WEIGHT
below for the reasoning and why it is deliberately small and symmetric.
"""

from dataclasses import dataclass, field

from app.geometry.drawing_zone import MIN_DRAWING_ZONE_OVERLAP, zone_overlap_ratio
from app.geometry.page_context import PageContext
from app.geometry.wall_graph import wall_confidence
from app.models.enums import ReviewStatus

# A wall IS the billable surface for these trades (drywall board coverage,
# paint area) — their own review depends on this exact geometry being
# right, so an already-plausible wall's confidence is nudged up slightly
# when one of them is selected.
WALL_PRIMARY_TRADES = {"drywall", "painting"}

# A wall is secondary evidence for these — flooring measures the room
# boundary a wall happens to help form, roofing measures roof planes, not
# walls — so the same wall is nudged down slightly, reflecting that it
# matters less to that trade's own takeoff. Never hidden or suppressed:
# per the spec this implements, "flooring -> ignore walls" is exactly what
# this must NOT do. The wall stays in the database, in the review queue,
# at the same status, just deprioritized.
WALL_SECONDARY_TRADES = {"flooring", "roofing"}

# Deliberately small and within wall_confidence()'s own existing bounds
# (0.15-0.98, wall_graph.py) — see WallDecision.status: this is the ONLY
# effect selected_trade is allowed to have on a wall candidate. It never
# changes which candidates get generated, never flips a REJECTED wall to
# PENDING or vice versa (status is decided before this weight is applied,
# from evidence that has nothing to do with trade), and stays small enough
# that it cannot on its own move a wall across any existing confidence
# bucket used elsewhere (e.g. the >=0.8 "HIGH" convention) by more than one
# step. No trade selected -> no adjustment at all (0.0), never a default.
TRADE_CONFIDENCE_WEIGHT = 0.05


# Physical plausibility bounds — intentionally wide to accommodate
# non-standard construction (CMU = 7.6 in, curtain wall = 1–2 in framing,
# staggered stud = 8.5 in). Only outright impossible geometry is rejected;
# edge cases are promoted to NEEDS_REVIEW so a human can confirm.
MIN_PHYSICAL_THICKNESS_IN = 1.5   # absolute lower bound — thinner = annotation/hatch
MAX_PHYSICAL_THICKNESS_IN = 24.0  # absolute upper bound — thicker = structural/shear wall
NEEDS_REVIEW_THICKNESS_MAX_IN = 18.0  # anything between 18–24 in is valid but rare → flag

# Off-axis angle tolerance. Walls within ±MANHATTAN_TOLERANCE_DEG of 0°,
# 45°, or 90° are treated as on-axis; anything outside is flagged only when
# the wall is also short (length < OFFAXIS_MIN_LENGTH_FT). Diagonal fire
# stairs and angled curtain walls are real; a 23° stub is probably dimension
# line hatching. Applied as NEEDS_REVIEW, not REJECTED, to preserve recall.
MANHATTAN_TOLERANCE_DEG = 12.0
OFFAXIS_MIN_LENGTH_FT = 5.0      # short off-axis wall → needs human review


@dataclass
class WallEvidence:
    length_ft: float
    connected: bool
    linked_room_index: int | None
    exterior: bool
    bbox_norm: dict
    # Which extraction path produced this candidate's final segment —
    # "vector_layer" (drafter-declared wall layer / lineweight-recovered
    # mixed layer), "raster_band" (stroke-thickness heuristic),
    # "hough_segment_fallback" / "thicker_hough_fallback" (line-derived
    # mask retries), "morph_ink_fallback" (last-resort morphology), or
    # "vector_raw"/"hough_raw" when no wall-band mask exists at all.
    # Recorded for provenance/logging only — does not itself gate
    # acceptance, since a fallback path already exists precisely because
    # it recovered real walls a better source missed.
    source: str
    # ── Physics evidence (optional — absent when not computed by caller) ──
    # Wall angle in degrees from horizontal [0, 180). Derived from the
    # segment's own dx/dy on both the Hough and reconstruction paths.
    angle_deg: float | None = None
    # Measured face-to-face thickness in inches. Only set when a parallel
    # face pair was detected (double_line_walls or reconstruction). Absent
    # for single-face / raster-only candidates.
    thickness_in: float | None = None
    # True when both Face A and Face B were independently detected.
    # Controls whether the impossible-thickness gate fires (no point
    # rejecting a single-face wall for "wrong" thickness — it has none).
    face_pair_detected: bool = False
    # D-010: False when thickness varied >35% along the wall run (WallPair
    # _check_thickness_consistency). Triggers NEEDS_REVIEW, not REJECTED,
    # because a real wall with a door opening in the middle can show apparent
    # thickness variation when one face is interrupted.
    thickness_consistent: bool = True


@dataclass
class WallDecision:
    confidence: float
    status: ReviewStatus
    reasons: list[str] = field(default_factory=list)
    zone_overlap: float = 1.0
    # Signed delta actually applied by trade weighting — 0.0 whenever no
    # trade was selected or the base wall_confidence() score was already
    # clamped at a bound the weight would have pushed past. Kept separate
    # from `confidence` (the final, already-weighted score) so a caller can
    # tell "what trade weighting did" from "what the geometry evidence
    # alone said" without recomputing anything.
    trade_weight: float = 0.0

    @property
    def accepted(self) -> bool:
        return self.status != ReviewStatus.REJECTED


def _trade_confidence_weight(selected_trade: str | None) -> float:
    if selected_trade in WALL_PRIMARY_TRADES:
        return TRADE_CONFIDENCE_WEIGHT
    if selected_trade in WALL_SECONDARY_TRADES:
        return -TRADE_CONFIDENCE_WEIGHT
    return 0.0


def _angle_is_off_axis(angle_deg: float, tolerance: float = MANHATTAN_TOLERANCE_DEG) -> bool:
    """True when the angle is not within `tolerance` degrees of 0°, 45°, or 90°."""
    import math
    a = angle_deg % 180.0
    for axis in (0.0, 45.0, 90.0, 135.0, 180.0):
        if abs(a - axis) <= tolerance or abs(a - axis) >= 180.0 - tolerance:
            return False
    return True


@dataclass
class DiagonalEvaluationResult:
    is_valid_diagonal_wall: bool
    confidence: float
    reasons: list[str] = field(default_factory=list)
    has_parallel_faces: bool = False
    has_valid_thickness: bool = False
    has_room_topology: bool = False
    has_valid_junction: bool = False


def evaluate_diagonal_evidence(evidence: WallEvidence) -> DiagonalEvaluationResult:
    """Evaluates the multi-signal evidence ladder for diagonal/arbitrary-angle wall candidates:
      diagonal candidate
             ↓
      parallel faces?
             ↓
      thickness valid?
             ↓
      room topology?
             ↓
      junction valid?
             ↓
      confidence & decision
    """
    reasons: list[str] = []
    score = 0.0

    # 1. Parallel Faces Check
    has_parallel_faces = bool(evidence.face_pair_detected)
    if has_parallel_faces:
        score += 0.35
        reasons.append("diagonal_parallel_faces_verified")

    # 2. Thickness Bounds Check [1.5" - 24.0"]
    has_valid_thickness = False
    if evidence.thickness_in is not None:
        if MIN_PHYSICAL_THICKNESS_IN <= evidence.thickness_in <= MAX_PHYSICAL_THICKNESS_IN:
            has_valid_thickness = True
            score += 0.25
            reasons.append(f"diagonal_valid_thickness:{evidence.thickness_in:.2f}in")
        else:
            reasons.append(f"diagonal_invalid_thickness:{evidence.thickness_in:.2f}in")

    # 3. Room Topology Check
    has_room_topology = (evidence.linked_room_index is not None) or evidence.exterior
    if has_room_topology:
        score += 0.25
        reasons.append("diagonal_room_boundary_attached")

    # 4. Junction / Graph Connectivity Check
    has_valid_junction = bool(evidence.connected)
    if has_valid_junction:
        score += 0.15
        reasons.append("diagonal_junction_connected")

    # 5. Long Physical Run Bonus (> 5.0 ft)
    if evidence.length_ft >= OFFAXIS_MIN_LENGTH_FT:
        score += 0.10
        reasons.append(f"diagonal_substantial_length:{evidence.length_ft:.1f}ft")

    confidence = round(min(0.98, max(0.15, score)), 2)
    # A diagonal wall is confirmed if it has parallel faces + valid thickness, OR room/junction proof
    is_valid = (
        (has_parallel_faces and has_valid_thickness)
        or (has_room_topology and (has_valid_junction or has_valid_thickness))
        or (evidence.length_ft >= OFFAXIS_MIN_LENGTH_FT and has_valid_junction)
    )

    return DiagonalEvaluationResult(
        is_valid_diagonal_wall=is_valid,
        confidence=confidence,
        reasons=reasons,
        has_parallel_faces=has_parallel_faces,
        has_valid_thickness=has_valid_thickness,
        has_room_topology=has_room_topology,
        has_valid_junction=has_valid_junction,
    )


def evaluate_wall_candidate(evidence: WallEvidence, context: PageContext) -> WallDecision:
    base_confidence = wall_confidence(
        evidence.length_ft, evidence.connected, evidence.linked_room_index, evidence.exterior
    )
    reasons: list[str] = []

    overlap = zone_overlap_ratio(evidence.bbox_norm, context.drawing_zone)
    outside_zone = overlap < MIN_DRAWING_ZONE_OVERLAP
    if outside_zone:
        reasons.append("outside_drawing_zone")

    isolated_unlinked_interior = (
        not evidence.connected and evidence.linked_room_index is None and not evidence.exterior
    )
    if isolated_unlinked_interior:
        reasons.append("isolated_unlinked_interior_segment")

    isolated_short_stub = (
        evidence.length_ft < 3.5 and not evidence.connected and not evidence.face_pair_detected and not evidence.exterior
    )
    if isolated_short_stub:
        reasons.append("isolated_short_non_wall_stroke")

    # Structural grid lines / dimension witness lines spanning >35% of page width/height without bounding a room or having a face pair
    span_x = evidence.bbox_norm.get("maxX", 0) - evidence.bbox_norm.get("minX", 0)
    span_y = evidence.bbox_norm.get("maxY", 0) - evidence.bbox_norm.get("minY", 0)
    line_span = max(span_x, span_y)
    is_structural_grid_line = (
        line_span > 0.35 and evidence.linked_room_index is None and not evidence.connected and not evidence.face_pair_detected
    )
    if is_structural_grid_line:
        reasons.append("structural_grid_or_dimension_line")

    # ── Physics Gate 1: Impossible thickness (hard reject) ────────────────
    implausible_thickness = False
    if evidence.face_pair_detected and evidence.thickness_in is not None:
        t = evidence.thickness_in
        if t < MIN_PHYSICAL_THICKNESS_IN or t > MAX_PHYSICAL_THICKNESS_IN:
            reasons.append(f"impossible_thickness:{t:.2f}in")
            implausible_thickness = True

    # ── Physics Gate 1b: Inconsistent thickness (soft flag → NEEDS_REVIEW) ─
    thickness_inconsistent = evidence.face_pair_detected and not evidence.thickness_consistent
    if thickness_inconsistent:
        reasons.append("thickness_inconsistent_along_run")

    # ── Physics Gate 2: Diagonal / Off-Axis Evidence Ladder ───────────────
    off_axis_short = False
    is_off_axis = evidence.angle_deg is not None and _angle_is_off_axis(evidence.angle_deg)
    if is_off_axis and not evidence.exterior:
        diag_eval = evaluate_diagonal_evidence(evidence)
        reasons.extend(diag_eval.reasons)
        if not diag_eval.is_valid_diagonal_wall and evidence.length_ft < OFFAXIS_MIN_LENGTH_FT:
            reasons.append(f"off_axis_unsupported_stub:{evidence.angle_deg:.1f}deg:{evidence.length_ft:.1f}ft")
            off_axis_short = True
        elif diag_eval.is_valid_diagonal_wall:
            base_confidence = max(base_confidence, diag_eval.confidence)

    hard_reject = outside_zone or isolated_unlinked_interior or isolated_short_stub or is_structural_grid_line or implausible_thickness
    soft_flag = off_axis_short or thickness_inconsistent

    if hard_reject:
        status = ReviewStatus.REJECTED
    elif soft_flag:
        status = ReviewStatus.NEEDS_REVIEW
    else:
        status = ReviewStatus.PENDING

    weight = _trade_confidence_weight(context.selected_trade)
    # Reuse wall_confidence()'s own existing bounds rather than introduce a
    # new clamp range.
    confidence = round(max(0.15, min(0.98, base_confidence + weight)), 2)
    applied_weight = round(confidence - base_confidence, 2)
    if applied_weight != 0.0:
        reasons.append(f"trade_weight:{applied_weight:+.2f}:{context.selected_trade}")

    return WallDecision(
        confidence=confidence, status=status, reasons=reasons, zone_overlap=overlap, trade_weight=applied_weight
    )
