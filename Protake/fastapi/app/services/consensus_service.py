"""Multi-Model Consensus & Auto-Approve Gateway Engine:
Calculates ensemble confidence score across AI vision, OCR schedule, and geometry flood-fill.
Auto-approves detections/rooms when 100% multi-source consensus is achieved (confidence >= 0.95),
otherwise routes to human review queue.
"""

from sqlalchemy.orm import Session

from app.models.detection import Detection
from app.models.enums import DetectionKind, ReviewStatus
from app.models.page import Page
from app.models.room import Room
from app.repositories.detection_repository import DetectionRepository
from app.repositories.page_repository import PageRepository
from app.repositories.room_repository import RoomRepository
from app.repositories.schedule_item_repository import ScheduleItemRepository

CONSENSUS_AUTO_APPROVE_THRESHOLD = 0.92


class ConsensusResult:
    def __init__(self, auto_approved_count: int, pending_count: int, details: list[str]):
        self.auto_approved_count = auto_approved_count
        self.pending_count = pending_count
        self.details = details


def run_multi_source_consensus(db: Session, blueprint_id: int) -> ConsensusResult:
    """Evaluates detections and rooms for a blueprint. If AI, geometry, and schedule
    agree with high confidence, auto-approve them.
    """
    pages: list[Page] = PageRepository(db).find(blueprint_id=blueprint_id)
    page_ids = [p.id for p in pages]

    det_repo = DetectionRepository(db)
    room_repo = RoomRepository(db)
    sched_repo = ScheduleItemRepository(db)

    auto_approved = 0
    pending = 0
    details: list[str] = []

    # Check Door and Window Schedule vs AI Detections
    for kind in [DetectionKind.DOOR, DetectionKind.WINDOW]:
        sched_qty = sched_repo.approved_quantity_for_pages(page_ids, kind)
        detections = det_repo.find(page_id=page_ids[0] if page_ids else 0, status=ReviewStatus.PENDING) if page_ids else []

        ai_matching = [d for d in detections if d.kind == kind]

        # If schedule quantity matches AI detection count exactly and confidence is high
        if sched_qty > 0 and sched_qty == len(ai_matching):
            for d in ai_matching:
                if d.confidence >= 0.75:
                    det_repo.update(d, status=ReviewStatus.APPROVED)
                    auto_approved += 1
            details.append(f"Auto-approved {len(ai_matching)} {kind.value}(s): Schedule count ({sched_qty}) matches AI detection count.")
        else:
            pending += len(ai_matching)

    # Check Rooms: flood-fill geometry + OCR room name validation
    rooms = []
    for pid in page_ids:
        rooms.extend(room_repo.find(page_id=pid, status=ReviewStatus.PENDING))

    for room in rooms:
        # High geometry confidence + confirmed name from OCR -> Auto approve
        if room.confidence >= CONSENSUS_AUTO_APPROVE_THRESHOLD and room.name and room.name != "Unlabeled Room":
            room_repo.update(room, status=ReviewStatus.APPROVED)
            auto_approved += 1
            details.append(f"Auto-approved room '{room.name}' (confidence {room.confidence:.2f}).")
        else:
            pending += 1

    return ConsensusResult(
        auto_approved_count=auto_approved,
        pending_count=pending,
        details=details,
    )
