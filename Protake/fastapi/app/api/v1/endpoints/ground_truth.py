"""Ground-truth reference CRUD + variance reporting. No data is seeded
anywhere in this system (see app/services/ground_truth_service.py) —
these endpoints are how real, human-verified reference quantities get
added, and how a computed trade result gets checked against them.
"""

from fastapi import APIRouter, HTTPException, status

from app.api.deps import CurrentUser, DbSession, OwnedProject
from app.models.blueprint import Blueprint
from app.models.enums import TradeKey
from app.repositories.blueprint_repository import BlueprintRepository
from app.repositories.ground_truth_repository import GroundTruthReferenceRepository
from app.schemas.ground_truth import (
    GroundTruthReferenceCreate,
    GroundTruthReferenceRead,
    TradeVarianceReportRead,
)
from app.services.ground_truth_service import GroundTruthService
from app.services.trade_takeoff_service import TradeTakeoffService

router = APIRouter(tags=["Ground Truth"])


def _get_blueprint_in_project(project, blueprint_id: int, db) -> Blueprint:
    blueprint = BlueprintRepository(db).get_or_404(blueprint_id)
    if blueprint.project_id != project.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "That blueprint does not belong to this project")
    return blueprint


@router.post(
    "/projects/{project_id}/blueprints/{blueprint_id}/ground-truth",
    response_model=GroundTruthReferenceRead,
    status_code=status.HTTP_201_CREATED,
)
def add_ground_truth_reference(
    payload: GroundTruthReferenceCreate, blueprint_id: int, project: OwnedProject, db: DbSession, user: CurrentUser
) -> GroundTruthReferenceRead:
    _get_blueprint_in_project(project, blueprint_id, db)
    repo = GroundTruthReferenceRepository(db)
    reference = repo.create(blueprint_id=blueprint_id, created_by_id=user.id, **payload.model_dump())
    return GroundTruthReferenceRead.model_validate(reference)


@router.get(
    "/projects/{project_id}/blueprints/{blueprint_id}/ground-truth",
    response_model=list[GroundTruthReferenceRead],
)
def list_ground_truth_references(blueprint_id: int, project: OwnedProject, db: DbSession) -> list[GroundTruthReferenceRead]:
    _get_blueprint_in_project(project, blueprint_id, db)
    repo = GroundTruthReferenceRepository(db)
    return [GroundTruthReferenceRead.model_validate(r) for r in repo.for_blueprint(blueprint_id)]


@router.get(
    "/projects/{project_id}/blueprints/{blueprint_id}/ground-truth/{trade}/report",
    response_model=TradeVarianceReportRead,
)
def get_trade_variance_report(trade: TradeKey, blueprint_id: int, project: OwnedProject, db: DbSession) -> TradeVarianceReportRead:
    """Computes the trade fresh (same path as the live-breakdown/takeoff
    endpoints) and compares it against whatever reference rows exist for
    this blueprint+trade. `has_ground_truth: false` and an empty
    `comparisons` list means exactly that — no accuracy claim can be made
    yet, not that accuracy is unknown-but-fine.
    """
    blueprint = _get_blueprint_in_project(project, blueprint_id, db)
    takeoff_service = TradeTakeoffService(db)
    result = takeoff_service.compute(trade, blueprint, project.id)

    ground_truth_service = GroundTruthService(db)
    report = ground_truth_service.compare(trade, blueprint_id, result.material_quantity, result.material_unit)
    return TradeVarianceReportRead(
        trade=report.trade,
        computed_quantity=report.computed_quantity,
        computed_unit=report.computed_unit,
        has_ground_truth=report.has_ground_truth,
        comparisons=[
            {
                "item_label": c.item_label,
                "reference_quantity": c.reference_quantity,
                "unit": c.unit,
                "source": c.source,
                "verified_by": c.verified_by,
                "variance_pct": c.variance_pct,
            }
            for c in report.comparisons
        ],
    )
