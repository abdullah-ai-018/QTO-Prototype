from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.api.deps import CurrentUser, DbSession, OwnedProject
from app.models.enums import ProjectStatus, UserRole
from app.models.project import Project
from app.repositories.project_repository import ProjectRepository
from app.schemas.project import ProjectCreate, ProjectRead, ProjectUpdate
from app.utils.pagination import Page, PageParams, page_params, paginate

router = APIRouter(prefix="/projects", tags=["Projects"])


@router.post("", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
def create_project(payload: ProjectCreate, db: DbSession, user: CurrentUser) -> ProjectRead:
    data = payload.model_dump()
    selected_trade = data.pop("selected_trade", None)
    project = ProjectRepository(db).create(owner_id=user.id, **data)
    project.owner = user
    if selected_trade:
        from app.trades.pricing_service import PricingService
        try:
            pricing = PricingService(db)
            pricing.upsert_project_override(project.id, {"trade": selected_trade})
        except Exception:
            db.rollback()
    return ProjectRead.model_validate(project)


@router.get("", response_model=Page[ProjectRead])
def list_projects(
    db: DbSession,
    user: CurrentUser,
    params: Annotated[PageParams, Depends(page_params)],
    status_filter: ProjectStatus | None = None,
) -> Page[ProjectRead]:
    repo = ProjectRepository(db)
    stmt = repo.query() if user.role == UserRole.ADMIN else repo.for_owner(user.id)
    if status_filter is not None:
        stmt = stmt.where(Project.status == status_filter)
    return paginate(db, stmt, params, Project, ProjectRead)


@router.get("/{project_id}", response_model=ProjectRead)
def get_project(project: OwnedProject) -> ProjectRead:
    return ProjectRead.model_validate(project)


@router.patch("/{project_id}", response_model=ProjectRead)
def update_project(payload: ProjectUpdate, project: OwnedProject, db: DbSession) -> ProjectRead:
    updated = ProjectRepository(db).update(project, **payload.model_dump(exclude_unset=True))
    return ProjectRead.model_validate(updated)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(project: OwnedProject, db: DbSession) -> None:
    ProjectRepository(db).delete(project)
