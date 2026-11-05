from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import CurrentUser, DbSession, OwnedProject
from app.models.audit_log import AuditLog
from app.repositories.audit_repository import AuditLogRepository
from app.schemas.audit import AuditLogRead, UndoRedoResponse
from app.services.audit_service import AuditService
from app.utils.pagination import Page as Paginated
from app.utils.pagination import PageParams, page_params, paginate

router = APIRouter(prefix="/projects/{project_id}", tags=["Audit & History"])


@router.get("/audit-log", response_model=Paginated[AuditLogRead])
def get_audit_log(project: OwnedProject, db: DbSession, params: Annotated[PageParams, Depends(page_params)]) -> Paginated[AuditLogRead]:
    repo = AuditLogRepository(db)
    return paginate(db, repo.for_project(project.id), params, AuditLog, AuditLogRead)


@router.post("/undo", response_model=UndoRedoResponse)
def undo(project: OwnedProject, db: DbSession, user: CurrentUser) -> UndoRedoResponse:
    entry = AuditService(db).undo(project.id, user.id)
    return UndoRedoResponse(audit_log=AuditLogRead.model_validate(entry), message="Last action undone")


@router.post("/redo", response_model=UndoRedoResponse)
def redo(project: OwnedProject, db: DbSession, user: CurrentUser) -> UndoRedoResponse:
    entry = AuditService(db).redo(project.id, user.id)
    return UndoRedoResponse(audit_log=AuditLogRead.model_validate(entry), message="Last undone action redone")
