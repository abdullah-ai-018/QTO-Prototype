from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import CurrentUser, DbSession
from app.api.v1.endpoints.pages import OwnedPage
from app.models.enums import ReviewStatus
from app.models.schedule_item import ScheduleItem
from app.repositories.blueprint_repository import BlueprintRepository
from app.repositories.page_repository import PageRepository
from app.repositories.schedule_item_repository import ScheduleItemRepository
from app.schemas.schedule_item import ScheduleItemRead, ScheduleItemReviewRequest
from app.services.audit_service import AuditService
from app.utils.pagination import Page as Paginated
from app.utils.pagination import PageParams, page_params, paginate

router = APIRouter(tags=["Schedule Items"])


def _project_id_for_schedule_item(db: DbSession, item: ScheduleItem) -> int:
    page = PageRepository(db).get_or_404(item.page_id)
    blueprint = BlueprintRepository(db).get_or_404(page.blueprint_id)
    return blueprint.project_id


def _review(db: DbSession, user: CurrentUser, item: ScheduleItem, new_status: ReviewStatus, reason: str | None) -> ScheduleItem:
    repo = ScheduleItemRepository(db)
    previous_status = item.status

    updated = repo.update(item, status=new_status, reviewed_by_id=user.id, reviewed_at=datetime.now(timezone.utc))

    from app.models.enums import AuditAction

    project_id = _project_id_for_schedule_item(db, updated)
    action = AuditAction.APPROVED if new_status == ReviewStatus.APPROVED else AuditAction.REJECTED
    AuditService(db).log_field_change(
        project_id=project_id,
        user_id=user.id,
        entity_type="ScheduleItem",
        entity_id=updated.id,
        field_name="status",
        previous_value=previous_status.value,
        new_value=new_status.value,
        action=action,
        reason=reason,
    )
    return updated


@router.get("/pages/{page_id}/schedule-items", response_model=Paginated[ScheduleItemRead])
def list_schedule_items(
    page: OwnedPage,
    db: DbSession,
    params: Annotated[PageParams, Depends(page_params)],
    status_filter: ReviewStatus | None = None,
) -> Paginated[ScheduleItemRead]:
    repo = ScheduleItemRepository(db)
    stmt = repo.for_page(page.id)
    if status_filter is not None:
        stmt = stmt.where(ScheduleItem.status == status_filter)
    return paginate(db, stmt, params, ScheduleItem, ScheduleItemRead)


def _get_owned_schedule_item(schedule_item_id: int, db: DbSession, user: CurrentUser) -> ScheduleItem:
    from app.api.deps import get_owned_project

    item = ScheduleItemRepository(db).get_or_404(schedule_item_id)
    project_id = _project_id_for_schedule_item(db, item)
    get_owned_project(project_id, db, user)
    return item


OwnedScheduleItem = Annotated[ScheduleItem, Depends(_get_owned_schedule_item)]


@router.post("/schedule-items/{schedule_item_id}/approve", response_model=ScheduleItemRead)
def approve_schedule_item(item: OwnedScheduleItem, payload: ScheduleItemReviewRequest, db: DbSession, user: CurrentUser) -> ScheduleItemRead:
    updated = _review(db, user, item, ReviewStatus.APPROVED, payload.reason)
    return ScheduleItemRead.model_validate(updated)


@router.post("/schedule-items/{schedule_item_id}/reject", response_model=ScheduleItemRead)
def reject_schedule_item(item: OwnedScheduleItem, payload: ScheduleItemReviewRequest, db: DbSession, user: CurrentUser) -> ScheduleItemRead:
    updated = _review(db, user, item, ReviewStatus.REJECTED, payload.reason)
    return ScheduleItemRead.model_validate(updated)
