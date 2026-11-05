"""Per-trade takeoff endpoints — the isolated counterpart to the combined
POST /projects/{id}/estimates: each call computes and persists exactly
one trade's snapshot, so a client asking about drywall never depends on
painting/flooring/roofing succeeding.
"""

from fastapi import APIRouter, HTTPException, status

from app.api.deps import CurrentUser, DbSession, OwnedProject
from app.models.blueprint import Blueprint
from app.models.enums import TradeKey, TradeTakeoffStatus
from app.repositories.blueprint_repository import BlueprintRepository
from app.repositories.page_repository import PageRepository
from app.schemas.takeoff import (
    PageTradeTakeoffItemRead,
    PageTradeTakeoffRead,
    TradeTakeoffItemRead,
    TradeTakeoffRead,
)
from app.services.trade_takeoff_service import TradeTakeoffService

router = APIRouter(tags=["Takeoffs"])


def _to_takeoff_read(trade: TradeKey, takeoff) -> TradeTakeoffRead:
    return TradeTakeoffRead(
        id=takeoff.id,
        project_id=takeoff.project_id,
        blueprint_id=takeoff.blueprint_id,
        trade=trade,
        material_quantity=takeoff.material_quantity,
        material_unit=takeoff.material_unit,
        labor_hours=takeoff.labor_hours,
        material_cost=takeoff.material_cost,
        labor_cost=takeoff.labor_cost,
        direct_cost=takeoff.direct_cost,
        status=takeoff.status,
        confidence=takeoff.confidence,
        evidence=takeoff.evidence,
        validation_reasons=takeoff.validation_reasons,
        geometry_version=takeoff.geometry_version,
        scale_version=takeoff.scale_version,
        engine_version=takeoff.engine_version,
        items=[TradeTakeoffItemRead.model_validate(item) for item in takeoff.items],
    )


def _get_blueprint_in_project(project, blueprint_id: int, db) -> Blueprint:
    blueprint = BlueprintRepository(db).get_or_404(blueprint_id)
    if blueprint.project_id != project.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "That blueprint does not belong to this project")
    return blueprint


def _service_or_404(db: DbSession, trade: TradeKey) -> TradeTakeoffService:
    service = TradeTakeoffService(db)
    if not service.is_supported(trade):
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Per-trade takeoff persistence isn't available for '{trade.value}' yet")
    return service


@router.post(
    "/projects/{project_id}/blueprints/{blueprint_id}/takeoffs/{trade}",
    response_model=TradeTakeoffRead,
    status_code=status.HTTP_201_CREATED,
)
def compute_trade_takeoff(
    trade: TradeKey, blueprint_id: int, project: OwnedProject, db: DbSession, user: CurrentUser
) -> TradeTakeoffRead:
    """Compute + persist a new snapshot for one trade. Never raises on an
    engine crash — the response comes back with status="error" and the
    exception message in validation_reasons instead (still HTTP 201), so
    one trade's failure can never break a caller that only asked about
    that one trade.
    """
    blueprint = _get_blueprint_in_project(project, blueprint_id, db)
    service = _service_or_404(db, trade)
    takeoff = service.compute_and_persist(trade, blueprint, project.id, user.id)
    return _to_takeoff_read(trade, takeoff)


@router.get(
    "/projects/{project_id}/blueprints/{blueprint_id}/takeoffs/{trade}",
    response_model=TradeTakeoffRead,
)
def get_latest_trade_takeoff(trade: TradeKey, blueprint_id: int, project: OwnedProject, db: DbSession) -> TradeTakeoffRead:
    """Read-only: the most recently persisted snapshot. Does not recompute
    — call POST first if nothing has been persisted yet.
    """
    _get_blueprint_in_project(project, blueprint_id, db)
    service = _service_or_404(db, trade)
    takeoff = service.latest(trade, blueprint_id)
    if takeoff is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No {trade.value} takeoff has been computed for this blueprint yet")
    return _to_takeoff_read(trade, takeoff)


@router.get(
    "/projects/{project_id}/blueprints/{blueprint_id}/pages/{page_id}/takeoffs/{trade}",
    response_model=PageTradeTakeoffRead,
)
def get_page_trade_takeoff(
    trade: TradeKey, blueprint_id: int, page_id: int, project: OwnedProject, db: DbSession
) -> PageTradeTakeoffRead:
    """Non-persisted, instant recompute of one trade's quantities scoped to
    a single page (sheet) — the sheet-scoped counterpart to the blueprint-
    level takeoff below. Runs the exact same engine and carries the same
    evidence/formula_breakdown provenance as a persisted takeoff, filtered
    to this one page's approved rooms/walls/detections, instead of the
    frontend's separate unaudited client-side recomputation.
    """
    blueprint = _get_blueprint_in_project(project, blueprint_id, db)
    service = _service_or_404(db, trade)

    page = PageRepository(db).get_or_404(page_id)
    if page.blueprint_id != blueprint.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "That page does not belong to this blueprint")

    result = service.compute(trade, blueprint, project.id, page_id=page_id)
    validation = result.validation

    return PageTradeTakeoffRead(
        page_id=page_id,
        blueprint_id=blueprint_id,
        trade=trade,
        material_quantity=result.material_quantity,
        material_unit=result.material_unit,
        labor_hours=result.labor_hours,
        material_cost=result.material_cost,
        labor_cost=result.labor_cost,
        direct_cost=result.direct_cost,
        status=validation.status if validation else TradeTakeoffStatus.NEEDS_REVIEW,
        confidence=validation.confidence if validation else 0.0,
        evidence=result.evidence,
        validation_reasons=validation.reasons if validation else None,
        items=[
            PageTradeTakeoffItemRead(
                label=li.label,
                quantity=li.quantity,
                unit=li.unit,
                unit_cost=li.unit_cost,
                total_cost=li.total_cost,
                source_proof=li.source_proof,
                formula_breakdown=li.formula_breakdown,
            )
            for li in result.line_items
        ],
    )


@router.get(
    "/projects/{project_id}/blueprints/{blueprint_id}/takeoffs/drywall/wall-ledger",
    response_model=dict,
    summary="Drywall wall-by-wall reconciliation ledger",
)
def get_drywall_wall_ledger(blueprint_id: int, project: OwnedProject, db: DbSession) -> dict:
    """Returns the wall-by-wall reconciliation ledger from the most recently
    persisted drywall takeoff.

    The ledger contains one entry per ArchitecturalWall with:
      - wall_id, start_norm, end_norm, length_ft
      - height_ft, height_provenance (VERIFIED | ASSUMED)
      - assembly_tag, assembly_description, sides_to_hang, layers_side_a/b
      - schedule_sheet, assembly_verified
      - gross_sf, opening_deduction_sf, net_sf
      - qto_eligible (True/False), qto_block_reason
      - decision_state, confidence

    The sum of net_sf for qto_eligible=True entries must equal the
    primary wall_hang_area_sqft reported in the takeoff evidence.

    Also includes independent_qto_recomputation from the engine run:
      - primary_wall_area_sqft vs independent_wall_area_sqft
      - agreement=True/False
    """
    _get_blueprint_in_project(project, blueprint_id, db)
    service = _service_or_404(db, TradeKey.DRYWALL)
    takeoff = service.latest(TradeKey.DRYWALL, blueprint_id)
    if takeoff is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "No drywall takeoff has been computed for this blueprint yet. "
            "POST /takeoffs/drywall first."
        )
    evidence = takeoff.evidence or {}
    ledger = evidence.get("wall_reconciliation_ledger", [])
    recompute = evidence.get("independent_qto_recomputation", {})
    framing = evidence.get("framing_qto", {})

    included = [e for e in ledger if e.get("qto_eligible")]
    excluded = [e for e in ledger if not e.get("qto_eligible")]

    return {
        "takeoff_id": takeoff.id,
        "blueprint_id": blueprint_id,
        "total_walls_analyzed": len(ledger),
        "walls_included_in_qto": len(included),
        "walls_excluded_from_qto": len(excluded),
        "independent_qto_recomputation": recompute,
        "framing_qto": framing,
        "wall_ledger": ledger,
        "exclusion_summary": _summarise_exclusions(excluded),
    }


def _summarise_exclusions(excluded: list[dict]) -> dict:
    """Counts excluded walls by block reason to give an auditable summary."""
    by_reason: dict[str, int] = {}
    for entry in excluded:
        reason = entry.get("qto_block_reason") or entry.get("status") or "unknown"
        by_reason[reason] = by_reason.get(reason, 0) + 1
    return by_reason
