"""Shared FastAPI dependencies: DB session, current user resolution, and
simple role-based access control.
"""

from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.enums import UserRole
from app.models.project import Project
from app.models.user import User
from app.repositories.project_repository import ProjectRepository
from app.repositories.user_repository import UserRepository
from app.utils.security import TokenError, decode_token

_bearer_scheme = HTTPBearer(auto_error=False)

DbSession = Annotated[Session, Depends(get_db)]


def get_current_user(
    db: DbSession,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)],
) -> User:
    if credentials is None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Missing bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        user_id = decode_token(credentials.credentials, expected_type="access")
    except TokenError as exc:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, str(exc), headers={"WWW-Authenticate": "Bearer"}
        ) from exc

    user = UserRepository(db).get(user_id)
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found or inactive")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_roles(*roles: UserRole):
    def _dependency(user: CurrentUser) -> User:
        if user.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "You do not have permission to perform this action")
        return user

    return _dependency


def get_owned_project(project_id: int, db: DbSession, user: CurrentUser) -> Project:
    """Resolve a project the current user owns, or 404/403 otherwise.

    Admins may access any project; estimators/viewers only their own.
    """
    project = ProjectRepository(db).get(project_id)
    if project is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Project {project_id} not found")
    if project.owner_id != user.id and user.role != UserRole.ADMIN:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You do not have access to this project")
    return project


OwnedProject = Annotated[Project, Depends(get_owned_project)]
