from fastapi import APIRouter, HTTPException, Response, status

from app.api.deps import CurrentUser, DbSession, get_owned_project
from app.repositories.estimate_repository import EstimateRepository
from app.repositories.project_repository import ProjectRepository
from app.services.report_service import render_report

router = APIRouter(tags=["Reports"])

_VALID_FORMATS = {"pdf", "csv", "xlsx"}


@router.get("/estimates/{estimate_id}/report/{fmt}")
def download_report(estimate_id: int, fmt: str, db: DbSession, user: CurrentUser) -> Response:
    if fmt not in _VALID_FORMATS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Unsupported format '{fmt}'. Use one of {sorted(_VALID_FORMATS)}.")

    estimate = EstimateRepository(db).get_or_404(estimate_id)
    get_owned_project(estimate.project_id, db, user)
    project = ProjectRepository(db).get_or_404(estimate.project_id)

    content, content_type, filename = render_report(project, estimate, fmt)  # type: ignore[arg-type]
    return Response(
        content=content,
        media_type=content_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
