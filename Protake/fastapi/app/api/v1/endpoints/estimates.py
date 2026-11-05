from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import CurrentUser, DbSession, OwnedProject
from app.models.enums import AuditAction
from app.models.estimate import Estimate
from app.repositories.blueprint_repository import BlueprintRepository
from app.repositories.estimate_repository import EstimateRepository
from app.schemas.estimate import EstimateGenerateRequest, EstimateRead, TradeBreakdown
from app.services.audit_service import AuditService
from app.services.estimate_service import EstimateService
from app.utils.pagination import Page as Paginated
from app.utils.pagination import PageParams, page_params, paginate

router = APIRouter(tags=["Estimates"])


def _to_estimate_read(estimate: Estimate, service: EstimateService) -> EstimateRead:
    read = EstimateRead.model_validate(estimate)
    read.scale_warnings = service.get_scale_warnings(estimate.blueprint_id)
    if estimate.blueprint_id:
        read.review_warnings = service.get_review_warnings(estimate.blueprint_id)
    return read


@router.post("/projects/{project_id}/estimates", response_model=EstimateRead, status_code=status.HTTP_201_CREATED)
def generate_estimate(payload: EstimateGenerateRequest, project: OwnedProject, db: DbSession, user: CurrentUser) -> EstimateRead:
    blueprint = BlueprintRepository(db).get_or_404(payload.blueprint_id)
    if blueprint.project_id != project.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "That blueprint does not belong to this project")

    service = EstimateService(db)
    estimate = service.generate_estimate(
        project.id, blueprint, user.id, payload.overhead_pct, payload.profit_pct, payload.contingency_pct
    )

    AuditService(db).log(
        project_id=project.id,
        user_id=user.id,
        entity_type="Estimate",
        entity_id=estimate.id,
        action=AuditAction.CREATED,
        new_value={"version": estimate.version, "final_bid_price": estimate.final_bid_price},
        reason="Estimate generated",
    )
    return _to_estimate_read(estimate, service)


@router.get("/projects/{project_id}/estimates", response_model=Paginated[EstimateRead])
def list_estimates(project: OwnedProject, db: DbSession, params: Annotated[PageParams, Depends(page_params)]) -> Paginated[EstimateRead]:
    repo = EstimateRepository(db)
    service = EstimateService(db)
    paginated = paginate(db, repo.for_project(project.id), params, Estimate, EstimateRead)
    for item in paginated.items:
        item.scale_warnings = service.get_scale_warnings(item.blueprint_id)
        if item.blueprint_id:
            item.review_warnings = service.get_review_warnings(item.blueprint_id)
    return paginated


@router.get("/projects/{project_id}/estimates/latest", response_model=EstimateRead)
def get_latest_estimate(project: OwnedProject, db: DbSession) -> EstimateRead:
    estimate = EstimateRepository(db).latest_for_project(project.id)
    if estimate is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No estimate has been generated for this project yet")
    service = EstimateService(db)
    return _to_estimate_read(estimate, service)


@router.get("/estimates/{estimate_id}", response_model=EstimateRead)
def get_estimate(estimate_id: int, db: DbSession, user: CurrentUser) -> EstimateRead:
    from app.api.deps import get_owned_project

    estimate = EstimateRepository(db).get_or_404(estimate_id)
    get_owned_project(estimate.project_id, db, user)
    service = EstimateService(db)
    return _to_estimate_read(estimate, service)


@router.get("/projects/{project_id}/blueprints/{blueprint_id}/live-breakdown", response_model=list[TradeBreakdown])
def live_trade_breakdown(project: OwnedProject, blueprint_id: int, db: DbSession) -> list[TradeBreakdown]:
    """Non-persisted, instant recompute of every trade's quantities from
    the current approved geometry — powers a live summary panel without
    requiring a formal (versioned) estimate to be generated each time.
    """
    blueprint = BlueprintRepository(db).get_or_404(blueprint_id)
    if blueprint.project_id != project.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "That blueprint does not belong to this project")

    service = EstimateService(db)
    results = service.compute_trade_results(blueprint, project.id)

    breakdowns = []
    for trade, result in results.items():
        breakdowns.append(
            TradeBreakdown(
                trade=trade,
                material_quantity=result.material_quantity,
                material_unit=result.material_unit,
                labor_hours=result.labor_hours,
                direct_cost=result.direct_cost,
                status=result.validation.status if result.validation else None,
                confidence=result.validation.confidence if result.validation else None,
                validation_reasons=result.validation.reasons if result.validation else None,
                line_items=[
                    {
                        "id": 0,
                        "trade": trade,
                        "category": "labor" if li.unit == "hrs" else "material",
                        "label": li.label,
                        "quantity": li.quantity,
                        "unit": li.unit,
                        "unit_cost": li.unit_cost,
                        "total_cost": li.total_cost,
                    }
                    for li in result.line_items
                ],
            )
        )
    return breakdowns
