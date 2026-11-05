"""QA & verification services: the tools a human reviewer (or a senior
estimator doing QC before a bid goes out) uses to answer three
questions the deterministic pipeline alone can't answer for them:

  1. "What's left for me to look at?"        -> coverage_report()
  2. "Does the AI's room boundary agree with -> variance_check()
      what I measured by hand?"
  3. "Can I hand-verify this formula with     -> rule_engine calculator
      my own calculator?"                        (app/api/v1/endpoints/qa.py)
"""

from shapely.geometry import Point, Polygon
from sqlalchemy.orm import Session

from app.geometry.metrics import SCALE_SOURCE_ASSUMED
from app.models.enums import DetectionKind, QAFlagLevel, ReviewStatus, TradeKey
from app.models.measurement import Measurement
from app.models.page import Page
from app.models.room import Room
from app.models.schedule_item import ScheduleItem
from app.models.wall import Wall
from app.repositories.detection_repository import DetectionRepository
from app.repositories.measurement_repository import MeasurementRepository
from app.repositories.page_repository import PageRepository
from app.repositories.room_repository import RoomRepository
from app.repositories.schedule_item_repository import ScheduleItemRepository
from app.repositories.wall_repository import WallRepository
from app.rules.constraint_engine import validate_construction_constraints
from app.schemas.qa import (
    CoverageReport,
    CrossValidationFlag,
    CrossValidationResponse,
    EntityCoverage,
    QAEngineFlag,
    QAEngineResponse,
    VarianceCheckResponse,
    VarianceFlag,
)

VARIANCE_TOLERANCE_PCT = 8.0
LOW_CONFIDENCE_THRESHOLD = 0.6


def _tally(rows: list, status_attr: str = "status") -> tuple[int, int, int]:
    approved = sum(1 for r in rows if getattr(r, status_attr) == ReviewStatus.APPROVED)
    rejected = sum(1 for r in rows if getattr(r, status_attr) == ReviewStatus.REJECTED)
    pending = sum(1 for r in rows if getattr(r, status_attr) == ReviewStatus.PENDING)
    return approved, pending, rejected


def _entity_coverage(entity_type: str, rows: list) -> EntityCoverage:
    approved, pending, rejected = _tally(rows)
    return EntityCoverage(entity_type=entity_type, approved=approved, pending=pending, rejected=rejected, total=len(rows))


def build_coverage_report(db: Session, blueprint_id: int) -> CoverageReport:
    pages: list[Page] = PageRepository(db).find(blueprint_id=blueprint_id)
    page_ids = [p.id for p in pages]

    rooms: list[Room] = []
    walls: list[Wall] = []
    detections: list[Detection] = []
    for page_id in page_ids:
        rooms.extend(RoomRepository(db).find(page_id=page_id))
        walls.extend(WallRepository(db).find(page_id=page_id))
        detections.extend(DetectionRepository(db).find(page_id=page_id))

    room_cov = _entity_coverage("Room", rooms)
    wall_cov = _entity_coverage("Wall", walls)
    detection_cov = _entity_coverage("Detection", detections)

    reviewable_total = room_cov.approved + room_cov.pending + wall_cov.approved + wall_cov.pending
    reviewed = room_cov.approved + wall_cov.approved
    readiness_pct = round((reviewed / reviewable_total * 100) if reviewable_total else 100.0, 1)

    gaps: list[str] = []
    if room_cov.pending:
        gaps.append(f"{room_cov.pending} room(s) still awaiting approval")
    if wall_cov.pending:
        gaps.append(f"{wall_cov.pending} wall(s) still awaiting approval")
    if detection_cov.pending:
        gaps.append(f"{detection_cov.pending} AI detection(s) awaiting review")
    if room_cov.total and room_cov.approved == 0:
        gaps.append("No rooms approved yet — flooring, ceiling drywall/paint, and roofing quantities will read zero")
    if wall_cov.total and wall_cov.approved == 0:
        gaps.append("No walls approved yet — drywall and wall-paint quantities will read zero")
    if not pages:
        gaps.append("Blueprint has not been processed yet — run /process before reviewing")

    return CoverageReport(
        blueprint_id=blueprint_id,
        rooms=room_cov,
        walls=wall_cov,
        detections=detection_cov,
        overall_readiness_pct=readiness_pct,
        gaps=gaps,
    )


def run_variance_check(db: Session, page_id: int) -> VarianceCheckResponse:
    """Cross-check every approved Room's geometry-computed area against
    any manual 'area' measurement a reviewer drew over roughly the same
    spot. This is the fastest way for a human to sanity-check the
    automated geometry engine without re-measuring the whole sheet.
    """
    rooms: list[Room] = RoomRepository(db).find(page_id=page_id, status=ReviewStatus.APPROVED)
    measurements: list[Measurement] = [
        m for m in MeasurementRepository(db).find(page_id=page_id) if m.tool == MeasurementTool.AREA
    ]

    flags: list[VarianceFlag] = []
    for room in rooms:
        room_poly = Polygon([(p[0], p[1]) for p in room.polygon_norm])
        for measurement in measurements:
            centroid_x = sum(p[0] for p in measurement.points_norm) / len(measurement.points_norm)
            centroid_y = sum(p[1] for p in measurement.points_norm) / len(measurement.points_norm)
            if not room_poly.contains(Point(centroid_x, centroid_y)):
                continue

            if room.area_sqft <= 0:
                continue
            deviation_pct = abs(room.area_sqft - measurement.value) / room.area_sqft * 100
            if deviation_pct > VARIANCE_TOLERANCE_PCT:
                flags.append(
                    VarianceFlag(
                        room_id=room.id,
                        room_name=room.name,
                        geometry_area_sqft=room.area_sqft,
                        manual_measurement_id=measurement.id,
                        manual_area_sqft=measurement.value,
                        deviation_pct=round(deviation_pct, 1),
                    )
                )

    return VarianceCheckResponse(page_id=page_id, checked_rooms=len(rooms), flags=flags)


def run_cross_validation(db: Session, blueprint_id: int) -> CrossValidationResponse:
    """Compares schedule item table quantities vs AI-detected bounding boxes."""
    pages = PageRepository(db).find(blueprint_id=blueprint_id)
    page_ids = [p.id for p in pages]

    sched_repo = ScheduleItemRepository(db)
    det_repo = DetectionRepository(db)

    flags: list[CrossValidationFlag] = []
    for kind in [DetectionKind.DOOR, DetectionKind.WINDOW]:
        sched_qty = sched_repo.approved_quantity_for_pages(page_ids, kind)
        ai_qty = det_repo.approved_count_by_kind(page_ids, kind)

        if sched_qty > 0 and sched_qty != ai_qty:
            discrepancy = abs(sched_qty - ai_qty)
            flags.append(
                CrossValidationFlag(
                    schedule_type=kind.value.capitalize(),
                    schedule_quantity=sched_qty,
                    ai_quantity=ai_qty,
                    discrepancy=discrepancy,
                    message=f"{kind.value.capitalize()} count mismatch: Schedule specifies {sched_qty}, but AI/geometry detected {ai_qty} (discrepancy: {discrepancy}).",
                )
            )

    return CrossValidationResponse(blueprint_id=blueprint_id, flags=flags)


def run_pre_estimate_qa(db: Session, blueprint_id: int) -> QAEngineResponse:
    """Pre-estimate checks for missing plans, uncalibrated scale, zero quantities."""
    pages = PageRepository(db).find(blueprint_id=blueprint_id)
    page_ids = [p.id for p in pages]

    flags: list[QAEngineFlag] = []

    if not pages:
        flags.append(QAEngineFlag(level=QAFlagLevel.ERROR, message="No blueprint pages found."))
        return QAEngineResponse(blueprint_id=blueprint_id, flags=flags)

    # Check for plan types
    page_types = {p.page_type for p in pages if p.page_type}
    if "floor_plan" not in page_types and "architectural" not in page_types:
        flags.append(QAEngineFlag(level=QAFlagLevel.WARNING, message="No Floor Plan sheet found in blueprint."))
    if "roof_plan" not in page_types:
        flags.append(QAEngineFlag(level=QAFlagLevel.WARNING, message="No Roof Plan sheet found in blueprint."))

    # Check scale. ERROR, not WARNING: an assumed scale isn't just an
    # unconfirmed number, it directly drives the watershed room-detection
    # core radius — measured on a real sheet, a wrong/assumed scale
    # collapsed detected room count from 17 to 4 with no error raised
    # anywhere else in the pipeline (see room-recall diagnostic). A room or
    # wall count built on this is not a "probably fine, just double check"
    # situation the way a low-confidence single room is.
    assumed_scale_pages = [p for p in pages if p.scale_source == SCALE_SOURCE_ASSUMED]
    if assumed_scale_pages:
        names = ", ".join(
            f"page {p.page_number} ({p.sheet_name or p.sheet_code or 'unnamed'})" for p in assumed_scale_pages[:5]
        )
        more = f" and {len(assumed_scale_pages) - 5} more" if len(assumed_scale_pages) > 5 else ""
        flags.append(
            QAEngineFlag(
                level=QAFlagLevel.ERROR,
                message=(
                    f"{len(assumed_scale_pages)} page(s) have no confirmed scale (printed note unreadable, "
                    f"no dimension gridlines found, no user calibration) — room/wall counts on these pages "
                    f"may be significantly wrong: {names}{more}."
                ),
            )
        )

    # Check zero quantities in approved rooms
    rooms = []
    walls = []
    for pid in page_ids:
        rooms.extend(RoomRepository(db).approved_for_pages([pid]))
        walls.extend(WallRepository(db).approved_for_pages([pid]))
    zero_area_rooms = [r for r in rooms if r.area_sqft <= 0]
    if zero_area_rooms:
        flags.append(
            QAEngineFlag(
                level=QAFlagLevel.ERROR,
                message=f"{len(zero_area_rooms)} approved room(s) have 0 area.",
            )
        )

    # Low-confidence approved rooms/walls: the geometry engine now scores
    # each detection's plausibility (area/vertex-count for rooms, length/
    # connectivity for walls — see room_confidence/wall_confidence) instead
    # of a fixed confidence on every detection. A room or wall that made it
    # to APPROVED with a low score most likely wasn't actually inspected —
    # this is exactly how a title-block logo or stray Hough line turns into
    # phantom Flooring/Painting/Drywall quantity if nobody catches it.
    low_confidence_rooms = [r for r in rooms if r.confidence < LOW_CONFIDENCE_THRESHOLD]
    if low_confidence_rooms:
        names = ", ".join(f"{r.name} ({r.area_sqft} sqft, {r.confidence:.2f} confidence)" for r in low_confidence_rooms[:5])
        more = f" and {len(low_confidence_rooms) - 5} more" if len(low_confidence_rooms) > 5 else ""
        flags.append(
            QAEngineFlag(
                level=QAFlagLevel.WARNING,
                message=(
                    f"{len(low_confidence_rooms)} approved room(s) have low geometry confidence "
                    f"(possible false detection, not a real room): {names}{more}."
                ),
            )
        )

    low_confidence_walls = [w for w in walls if w.confidence < LOW_CONFIDENCE_THRESHOLD]
    if low_confidence_walls:
        flags.append(
            QAEngineFlag(
                level=QAFlagLevel.WARNING,
                message=(
                    f"{len(low_confidence_walls)} approved wall(s) have low geometry confidence "
                    "(short, unconnected, or not bordering any detected room) — verify before finalizing."
                ),
            )
        )

    # Run construction physical constraint engine
    violations = validate_construction_constraints(rooms, walls)
    for v in violations:
        flags.append(QAEngineFlag(level=v.level, message=v.message))

    return QAEngineResponse(blueprint_id=blueprint_id, flags=flags)
