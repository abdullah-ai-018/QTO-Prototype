"""Audit log service: records every mutating action with enough detail
(previous/new value per field) to deterministically undo or redo it,
and to reconstruct full version history for a project.
"""

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.database import Base
from app.models.audit_log import AuditLog
from app.models.detection import Detection
from app.models.enums import AuditAction
from app.models.measurement import Measurement
from app.models.room import Room
from app.models.wall import Wall
from app.repositories.audit_repository import AuditLogRepository

ENTITY_MODEL_MAP: dict[str, type[Base]] = {
    "Detection": Detection,
    "Room": Room,
    "Wall": Wall,
    "Measurement": Measurement,
}


def _next_version(previous: str | None) -> str:
    if not previous:
        return "v1.00"
    major, minor = previous.replace("v", "").split(".")
    return f"v{major}.{int(minor) + 1:02d}"


class AuditService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = AuditLogRepository(db)

    def _current_version(self, project_id: int) -> str:
        latest = self.repo.db.execute(
            self.repo.for_project(project_id).limit(1)
        ).scalars().first()
        return latest.version if latest else "v1.00"

    def log(
        self,
        project_id: int,
        user_id: int,
        entity_type: str,
        entity_id: int,
        action: AuditAction,
        field_name: str | None = None,
        previous_value: dict | None = None,
        new_value: dict | None = None,
        reason: str | None = None,
    ) -> AuditLog:
        version = _next_version(self._current_version(project_id))
        return self.repo.create(
            project_id=project_id,
            user_id=user_id,
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            field_name=field_name,
            previous_value=previous_value,
            new_value=new_value,
            reason=reason,
            version=version,
            is_undone=False,
        )

    def log_field_change(
        self, project_id: int, user_id: int, entity_type: str, entity_id: int, field_name: str, previous_value, new_value, action: AuditAction, reason: str | None = None
    ) -> AuditLog:
        return self.log(
            project_id,
            user_id,
            entity_type,
            entity_id,
            action,
            field_name=field_name,
            previous_value={field_name: previous_value},
            new_value={field_name: new_value},
            reason=reason,
        )

    def history(self, project_id: int) -> list[AuditLog]:
        return list(self.repo.db.execute(self.repo.for_project(project_id)).scalars().all())

    def _apply_value(self, log_entry: AuditLog, value: dict | None) -> None:
        model = ENTITY_MODEL_MAP.get(log_entry.entity_type)
        if model is None or value is None:
            return
        instance = self.db.get(model, log_entry.entity_id)
        if instance is None:
            return
        for field_name, field_value in value.items():
            setattr(instance, field_name, field_value)
        self.db.add(instance)
        self.db.flush()

    def undo(self, project_id: int, user_id: int) -> AuditLog:
        target = self.repo.last_active_for_project(project_id)
        if target is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Nothing to undo")

        self._apply_value(target, target.previous_value)
        target.is_undone = True
        self.db.add(target)
        self.db.flush()

        return self.log(
            project_id,
            user_id,
            target.entity_type,
            target.entity_id,
            AuditAction.UNDO,
            field_name=target.field_name,
            previous_value=target.new_value,
            new_value=target.previous_value,
            reason=f"Undo of audit log #{target.id}",
        )

    def redo(self, project_id: int, user_id: int) -> AuditLog:
        target = self.repo.last_undone_for_project(project_id)
        if target is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Nothing to redo")

        self._apply_value(target, target.new_value)
        target.is_undone = False
        self.db.add(target)
        self.db.flush()

        return self.log(
            project_id,
            user_id,
            target.entity_type,
            target.entity_id,
            AuditAction.REDO,
            field_name=target.field_name,
            previous_value=target.previous_value,
            new_value=target.new_value,
            reason=f"Redo of audit log #{target.id}",
        )
