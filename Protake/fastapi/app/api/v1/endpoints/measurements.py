from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import CurrentUser, DbSession
from app.api.v1.endpoints.pages import OwnedPage, get_owned_page
from app.geometry.metrics import DEFAULT_SCALE_FT_PER_PX
from app.geometry.polygon_ops import to_valid_polygon
from app.models.enums import MeasurementTool
from app.models.measurement import Measurement
from app.repositories.measurement_repository import MeasurementRepository
from app.schemas.measurement import MeasurementCreate, MeasurementRead
from app.utils.pagination import Page as Paginated
from app.utils.pagination import PageParams, page_params, paginate

router = APIRouter(tags=["Measurements"])


def _compute_value(tool: MeasurementTool, points_norm: list[list[float]], scale_ft_per_px: float, width_px: int, height_px: int) -> tuple[float, str]:
    points_px = [(x * width_px, y * height_px) for x, y in points_norm]

    if tool == MeasurementTool.COUNT:
        return 1.0, "count"

    if tool == MeasurementTool.LINEAR:
        length_px = sum(
            ((points_px[i][0] - points_px[i - 1][0]) ** 2 + (points_px[i][1] - points_px[i - 1][1]) ** 2) ** 0.5
            for i in range(1, len(points_px))
        )
        return round(length_px * scale_ft_per_px, 2), "ft"

    # AREA or POLYGON
    polygon = to_valid_polygon(points_px)
    area_sqft = polygon.area * (scale_ft_per_px**2)
    return round(area_sqft, 2), "sq ft"


@router.post("/measurements", response_model=MeasurementRead, status_code=status.HTTP_201_CREATED)
def create_measurement(payload: MeasurementCreate, db: DbSession, user: CurrentUser) -> MeasurementRead:
    page = get_owned_page(payload.page_id, db, user)
    scale = page.scale_ft_per_px or DEFAULT_SCALE_FT_PER_PX

    if payload.tool in (MeasurementTool.LINEAR,) and len(payload.points_norm) < 2:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "A linear measurement needs at least 2 points")
    if payload.tool in (MeasurementTool.AREA, MeasurementTool.POLYGON) and len(payload.points_norm) < 3:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "An area/polygon measurement needs at least 3 points")

    value, unit = _compute_value(payload.tool, payload.points_norm, scale, page.width_px, page.height_px)

    measurement = MeasurementRepository(db).create(
        page_id=page.id,
        created_by_id=user.id,
        tool=payload.tool,
        points_norm=payload.points_norm,
        label=payload.label,
        value=value,
        unit=unit,
    )
    return MeasurementRead.model_validate(measurement)


@router.get("/pages/{page_id}/measurements", response_model=Paginated[MeasurementRead])
def list_measurements(page: OwnedPage, db: DbSession, params: Annotated[PageParams, Depends(page_params)]) -> Paginated[MeasurementRead]:
    repo = MeasurementRepository(db)
    return paginate(db, repo.for_page(page.id), params, Measurement, MeasurementRead)


@router.delete("/measurements/{measurement_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_measurement(measurement_id: int, db: DbSession, user: CurrentUser) -> None:
    repo = MeasurementRepository(db)
    measurement = repo.get_or_404(measurement_id)
    get_owned_page(measurement.page_id, db, user)
    repo.delete(measurement)
