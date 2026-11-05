from sqlalchemy import select

from app.models.audit_log import AuditLog
from app.repositories.base import BaseRepository


class AuditLogRepository(BaseRepository[AuditLog]):
    model = AuditLog

    def for_project(self, project_id: int):
        return select(AuditLog).where(AuditLog.project_id == project_id).order_by(AuditLog.created_at.desc())

    def last_active_for_project(self, project_id: int) -> AuditLog | None:
        """Most recent, not-already-undone log entry — the head of the undo stack."""
        stmt = (
            select(AuditLog)
            .where(AuditLog.project_id == project_id, AuditLog.is_undone.is_(False))
            .order_by(AuditLog.created_at.desc())
            .limit(1)
        )
        return self.db.execute(stmt).scalars().first()

    def last_undone_for_project(self, project_id: int) -> AuditLog | None:
        """Most recently undone entry — the head of the redo stack."""
        stmt = (
            select(AuditLog)
            .where(AuditLog.project_id == project_id, AuditLog.is_undone.is_(True))
            .order_by(AuditLog.created_at.desc())
            .limit(1)
        )
        return self.db.execute(stmt).scalars().first()
