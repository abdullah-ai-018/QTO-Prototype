from datetime import datetime

from app.models.enums import AuditAction
from app.schemas.common import ORMModel


class AuditLogRead(ORMModel):
    id: int
    project_id: int
    user_id: int
    entity_type: str
    entity_id: int
    action: AuditAction
    field_name: str | None
    previous_value: dict | None
    new_value: dict | None
    reason: str | None
    version: str
    is_undone: bool
    created_at: datetime


class UndoRedoResponse(ORMModel):
    audit_log: AuditLogRead
    message: str
