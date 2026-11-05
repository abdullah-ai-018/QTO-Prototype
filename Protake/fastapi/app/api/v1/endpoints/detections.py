from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import CurrentUser, DbSession
from app.api.v1.endpoints.pages import OwnedPage
from app.models.detection import Detection
from app.models.enums import AuditAction, ReviewStatus
from app.repositories.blueprint_repository import BlueprintRepository
from app.repositories.detection_repository import DetectionRepository
from app.repositories.page_repository import PageRepository
from app.schemas.detection import BulkReviewRequest, BulkReviewResponse, DetectionRead, DetectionReviewRequest, DetectionUpdate
from app.services.audit_service import AuditService
from app.utils.pagination import Page as Paginated
from app.utils.pagination import PageParams, page_params, paginate

router = APIRouter(tags=["Detections"])


def _project_id_for_detection(db: DbSession, detection: Detection) -> int:
    page = PageRepository(db).get_or_404(detection.page_id)
    blueprint = BlueprintRepository(db).get_or_404(page.blueprint_id)
    return blueprint.project_id


def _review(db: DbSession, user: CurrentUser, detection: Detection, new_status: ReviewStatus, reason: str | None) -> Detection:
    repo = DetectionRepository(db)
    previous_status = detection.status

    updated = repo.update(detection, status=new_status, reviewed_by_id=user.id, reviewed_at=datetime.now(timezone.utc))

    project_id = _project_id_for_detection(db, updated)
    action = AuditAction.APPROVED if new_status == ReviewStatus.APPROVED else AuditAction.REJECTED
    AuditService(db).log_field_change(
        project_id=project_id,
        user_id=user.id,
        entity_type="Detection",
        entity_id=updated.id,
        field_name="status",
        previous_value=previous_status.value,
        new_value=new_status.value,
        action=action,
        reason=reason,
    )
    return updated


@router.get("/pages/{page_id}/detections", response_model=Paginated[DetectionRead])
def list_detections(
    page: OwnedPage,
    db: DbSession,
    params: Annotated[PageParams, Depends(page_params)],
    status_filter: ReviewStatus | None = None,
) -> Paginated[DetectionRead]:
    repo = DetectionRepository(db)
    stmt = repo.for_page(page.id, status=status_filter)
    return paginate(db, stmt, params, Detection, DetectionRead)


def _get_owned_detection(detection_id: int, db: DbSession, user: CurrentUser) -> Detection:
    from app.api.deps import get_owned_project

    detection = DetectionRepository(db).get_or_404(detection_id)
    project_id = _project_id_for_detection(db, detection)
    get_owned_project(project_id, db, user)
    return detection


OwnedDetection = Annotated[Detection, Depends(_get_owned_detection)]


@router.post("/detections/{detection_id}/approve", response_model=DetectionRead)
def approve_detection(detection: OwnedDetection, payload: DetectionReviewRequest, db: DbSession, user: CurrentUser) -> DetectionRead:
    updated = _review(db, user, detection, ReviewStatus.APPROVED, payload.reason)
    return DetectionRead.model_validate(updated)


@router.post("/detections/{detection_id}/reject", response_model=DetectionRead)
def reject_detection(detection: OwnedDetection, payload: DetectionReviewRequest, db: DbSession, user: CurrentUser) -> DetectionRead:
    updated = _review(db, user, detection, ReviewStatus.REJECTED, payload.reason)
    return DetectionRead.model_validate(updated)


@router.post("/pages/{page_id}/detections/bulk-approve", response_model=BulkReviewResponse)
def bulk_approve(page: OwnedPage, payload: BulkReviewRequest, db: DbSession, user: CurrentUser) -> BulkReviewResponse:
    return _bulk_review(page, payload, db, user, ReviewStatus.APPROVED)


@router.post("/pages/{page_id}/detections/bulk-reject", response_model=BulkReviewResponse)
def bulk_reject(page: OwnedPage, payload: BulkReviewRequest, db: DbSession, user: CurrentUser) -> BulkReviewResponse:
    return _bulk_review(page, payload, db, user, ReviewStatus.REJECTED)


def _bulk_review(page, payload: BulkReviewRequest, db: DbSession, user: CurrentUser, new_status: ReviewStatus) -> BulkReviewResponse:
    repo = DetectionRepository(db)
    updated_ids = []
    for detection_id in payload.detection_ids:
        detection = repo.get(detection_id)
        if detection is None or detection.page_id != page.id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"Detection {detection_id} not found on this page")
        _review(db, user, detection, new_status, payload.reason)
        updated_ids.append(detection_id)
    return BulkReviewResponse(updated=len(updated_ids), detection_ids=updated_ids)


@router.patch("/detections/{detection_id}", response_model=DetectionRead)
def update_detection(detection: OwnedDetection, payload: DetectionUpdate, db: DbSession, user: CurrentUser) -> DetectionRead:
    repo = DetectionRepository(db)
    changes = payload.model_dump(exclude_unset=True)
    previous = {field: getattr(detection, field) for field in changes}
    
    updated = repo.update(detection, **changes)
    
    if "status" in changes:
        project_id = _project_id_for_detection(db, updated)
        action = AuditAction.APPROVED if changes["status"] == ReviewStatus.APPROVED else AuditAction.REJECTED
        AuditService(db).log_field_change(
            project_id=project_id,
            user_id=user.id,
            entity_type="Detection",
            entity_id=updated.id,
            field_name="status",
            previous_value=previous["status"].value if previous.get("status") else None,
            new_value=changes["status"].value,
            action=action,
            reason=None,
        )
    return DetectionRead.model_validate(updated)
