import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse

from app.api.deps import CurrentUser, DbSession, get_owned_project
from app.api.v1.endpoints.blueprints import OwnedBlueprint
from app.models.enums import AuditAction, ReviewStatus, TradeKey
from app.models.architectural_wall import ArchitecturalWall
from app.models.page import Page
from app.repositories.blueprint_repository import BlueprintRepository
from app.repositories.page_repository import PageRepository
from app.repositories.room_repository import RoomRepository
from app.repositories.wall_repository import WallRepository
from app.schemas.detection import DetectionRead
from app.schemas.page import CalibrationRequest, PageRead, PageBulkReviewRequest
from app.schemas.room import RoomRead, RoomUpdate
from app.schemas.wall import BatchApplyWallsRequest, BatchApplyWallsResponse, WallRead, WallUpdate
from app.services.analysis_service import AnalysisService
from app.services.audit_service import AuditService
from app.services.blueprint_service import BlueprintService
from app.services.trade_takeoff_service import TradeTakeoffService
from app.utils.pagination import Page as Paginated
from app.utils.pagination import PageParams, page_params, paginate

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Pages"])


def get_owned_page(page_id: int, db: DbSession, user: CurrentUser) -> Page:
    page = PageRepository(db).get(page_id)
    if page is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Page {page_id} not found")
    blueprint = BlueprintRepository(db).get_or_404(page.blueprint_id)
    get_owned_project(blueprint.project_id, db, user)
    return page


def _project_id_for_page(db: DbSession, page: Page) -> int:
    blueprint = BlueprintRepository(db).get_or_404(page.blueprint_id)
    return blueprint.project_id


OwnedPage = Annotated[Page, Depends(get_owned_page)]


@router.get("/blueprints/{blueprint_id}/pages", response_model=Paginated[PageRead])
def list_pages(blueprint: OwnedBlueprint, db: DbSession, params: Annotated[PageParams, Depends(page_params)]) -> Paginated[PageRead]:
    repo = PageRepository(db)
    return paginate(db, repo.for_blueprint(blueprint.id), params, Page, PageRead)


import os
from pathlib import Path
from app.config import get_settings

settings = get_settings()

def get_resolved_path(path: str) -> str:
    if not path:
        return path
    if os.path.exists(path):
        return path
    
    # Handle relocated workspace projects by checking relative storage subdirectories
    try:
        path_parts = Path(path).parts
        if "storage" in path_parts:
            idx = path_parts.index("storage")
            relative_suffix = Path(*path_parts[idx+1:])
            resolved = Path(settings.storage_dir) / relative_suffix
            if resolved.exists():
                return str(resolved.resolve())
                
        for folder in ["uploads", "thumbnails", "reports"]:
            if folder in path_parts:
                idx = path_parts.index(folder)
                relative_suffix = Path(*path_parts[idx:])
                resolved = Path(settings.storage_dir) / relative_suffix
                if resolved.exists():
                    return str(resolved.resolve())
    except Exception:
        pass
        
    return path


@router.get("/pages/{page_id}", response_model=PageRead)
def get_page(page: OwnedPage) -> PageRead:
    return PageRead.model_validate(page)


@router.get("/pages/{page_id}/image")
def get_page_image(page: OwnedPage) -> FileResponse:
    resolved_path = get_resolved_path(page.image_path)
    if not resolved_path or not os.path.exists(resolved_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Page image file not found on disk: {page.image_path}"
        )
    return FileResponse(resolved_path, media_type="image/png")


@router.get("/pages/{page_id}/thumbnail")
def get_page_thumbnail(page: OwnedPage) -> FileResponse:
    path = page.thumbnail_path or page.image_path
    resolved_path = get_resolved_path(path)
    if not resolved_path or not os.path.exists(resolved_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Page thumbnail file not found on disk: {path}"
        )
    return FileResponse(resolved_path, media_type="image/png")


@router.post("/pages/{page_id}/calibrate", response_model=PageRead)
def calibrate_page(payload: CalibrationRequest, page: OwnedPage, db: DbSession) -> PageRead:
    service = BlueprintService(db)
    try:
        updated = service.calibrate_page(
            page, payload.point_a, payload.point_b, payload.real_world_feet, unit=payload.unit, reprocess=True
        )
        db.commit()
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return PageRead.model_validate(updated)


@router.post("/pages/{page_id}/ocr")
def run_ocr(page: OwnedPage, db: DbSession) -> dict:
    result = AnalysisService(db).run_ocr(page)
    return {
        "room_names_confirmed": len(result.room_name_overrides),
        "dimension_flags": result.dimension_flags,
        "detected_scale": result.detected_scale.text if result.detected_scale else None,
        "grid_refs": result.grid_refs,
        "tokens_read": result.token_count,
    }


@router.post("/pages/{page_id}/ai-validate", response_model=list[DetectionRead])
def run_ai_validation(page: OwnedPage, db: DbSession) -> list[DetectionRead]:
    detections = AnalysisService(db).run_ai_validation(page)
    return [DetectionRead.model_validate(d) for d in detections]


@router.get("/pages/{page_id}/rooms", response_model=Paginated[RoomRead])
def list_rooms(page: OwnedPage, db: DbSession, params: Annotated[PageParams, Depends(page_params)]) -> Paginated[RoomRead]:
    from app.models.room import Room

    repo = RoomRepository(db)
    return paginate(db, repo.for_page(page.id), params, Room, RoomRead)


@router.patch("/rooms/{room_id}", response_model=RoomRead)
def update_room(room_id: int, payload: RoomUpdate, db: DbSession, user: CurrentUser) -> RoomRead:
    repo = RoomRepository(db)
    room = repo.get_or_404(room_id)
    page = get_owned_page(room.page_id, db, user)
    changes = payload.model_dump(exclude_unset=True)

    previous = {field: getattr(room, field) for field in changes}
    updated = repo.update(room, **changes)

    if "status" in changes:
        project_id = _project_id_for_page(db, page)
        action = AuditAction.APPROVED if changes["status"].value == "approved" else (
            AuditAction.REJECTED if changes["status"].value == "rejected" else AuditAction.UPDATED
        )
        AuditService(db).log(
            project_id=project_id,
            user_id=user.id,
            entity_type="Room",
            entity_id=updated.id,
            action=action,
            previous_value={k: (v.value if hasattr(v, "value") else v) for k, v in previous.items()},
            new_value={k: (v.value if hasattr(v, "value") else v) for k, v in changes.items()},
        )
    return RoomRead.model_validate(updated)


from app.models.architectural_wall import ArchitecturalWallModel
from app.repositories.architectural_wall_repository import ArchitecturalWallRepository
from app.schemas.architectural_wall import ArchitecturalWallRead


@router.get("/pages/{page_id}/architectural-walls", response_model=Paginated[ArchitecturalWallRead])
def list_architectural_walls(
    page: OwnedPage,
    db: DbSession,
    params: Annotated[PageParams, Depends(page_params)],
    include_rejected: bool = Query(False, description="Whether to include rejected walls"),
) -> Paginated[ArchitecturalWallRead]:
    repo = ArchitecturalWallRepository(db)
    stmt = repo.for_page(page.id)
    if not include_rejected:
        stmt = stmt.where(ArchitecturalWallModel.status != "rejected")
    return paginate(db, stmt, params, ArchitecturalWallModel, ArchitecturalWallRead)


@router.get("/pages/{page_id}/walls", response_model=Paginated[WallRead])
def list_walls(
    page: OwnedPage,
    db: DbSession,
    params: Annotated[PageParams, Depends(page_params)],
    include_rejected: bool = Query(False, description="Whether to include rejected wall candidates"),
    status: ReviewStatus | None = Query(None, description="Filter walls by specific review status"),
) -> Paginated[WallRead]:
    from app.models.wall import Wall

    repo = WallRepository(db)
    stmt = repo.for_page(page.id)
    if status is not None:
        stmt = stmt.where(Wall.status == status)
    elif not include_rejected:
        stmt = stmt.where(Wall.status != ReviewStatus.REJECTED)
    return paginate(db, stmt, params, Wall, WallRead)


@router.patch("/walls/{wall_id}", response_model=WallRead)
def update_wall(wall_id: int, payload: WallUpdate, db: DbSession, user: CurrentUser) -> WallRead:

    repo = WallRepository(db)
    wall = repo.get_or_404(wall_id)
    page = get_owned_page(wall.page_id, db, user)
    changes = payload.model_dump(exclude_unset=True)

    previous = {field: getattr(wall, field) for field in changes}
    updated = repo.update(wall, **changes)

    if "status" in changes:
        project_id = _project_id_for_page(db, page)
        action = AuditAction.APPROVED if changes["status"].value == "approved" else (
            AuditAction.REJECTED if changes["status"].value == "rejected" else AuditAction.UPDATED
        )
        AuditService(db).log(
            project_id=project_id,
            user_id=user.id,
            entity_type="Wall",
            entity_id=updated.id,
            action=action,
            previous_value={k: (v.value if hasattr(v, "value") else v) for k, v in previous.items()},
            new_value={k: (v.value if hasattr(v, "value") else v) for k, v in changes.items()},
        )
    return WallRead.model_validate(updated)


@router.post("/pages/{page_id}/bulk-review")
def bulk_review_page(
    page: OwnedPage,
    payload: PageBulkReviewRequest,
    db: DbSession,
    user: CurrentUser,
) -> dict:
    from app.repositories.detection_repository import DetectionRepository
    from app.repositories.room_repository import RoomRepository
    from app.repositories.wall_repository import WallRepository
    from datetime import datetime, timezone
    from app.models.enums import ReviewStatus, AuditAction
    from app.services.audit_service import AuditService

    new_status = ReviewStatus(payload.status)
    project_id = _project_id_for_page(db, page)

    # 1. Update rooms on this page that aren't already in the target status
    room_repo = RoomRepository(db)
    rooms = db.query(room_repo.model).filter(
        room_repo.model.page_id == page.id,
        room_repo.model.status != new_status
    ).all()
    
    action = AuditAction.APPROVED if new_status == ReviewStatus.APPROVED else AuditAction.REJECTED

    for r in rooms:
        previous_status = r.status
        room_repo.update(r, status=new_status)
        AuditService(db).log(
            project_id=project_id,
            user_id=user.id,
            entity_type="Room",
            entity_id=r.id,
            action=action,
            previous_value={"status": previous_status.value},
            new_value={"status": new_status.value},
        )

    # 2. Update walls on this page that aren't already in the target status
    wall_repo = WallRepository(db)
    walls = db.query(wall_repo.model).filter(
        wall_repo.model.page_id == page.id,
        wall_repo.model.status != new_status
    ).all()

    for w in walls:
        previous_status = w.status
        wall_repo.update(w, status=new_status)
        AuditService(db).log(
            project_id=project_id,
            user_id=user.id,
            entity_type="Wall",
            entity_id=w.id,
            action=action,
            previous_value={"status": previous_status.value},
            new_value={"status": new_status.value},
        )

    # 3. Update YOLO detections/symbols on this page that aren't already in the target status
    det_repo = DetectionRepository(db)
    detections = db.query(det_repo.model).filter(
        det_repo.model.page_id == page.id,
        det_repo.model.status != new_status
    ).all()

    for d in detections:
        previous_status = d.status
        det_repo.update(d, status=new_status, reviewed_by_id=user.id, reviewed_at=datetime.now(timezone.utc))
        AuditService(db).log_field_change(
            project_id=project_id,
            user_id=user.id,
            entity_type="Detection",
            entity_id=d.id,
            field_name="status",
            previous_value=previous_status.value,
            new_value=new_status.value,
            action=action,
            reason=payload.reason,
        )

    return {
        "rooms_updated": len(rooms),
        "walls_updated": len(walls),
        "detections_updated": len(detections),
    }


@router.post("/pages/{page_id}/batch-apply-walls", response_model=BatchApplyWallsResponse)
def batch_apply_walls(
    page: OwnedPage,
    payload: BatchApplyWallsRequest,
    db: DbSession,
    user: CurrentUser,
) -> BatchApplyWallsResponse:
    blueprint = BlueprintRepository(db).get_or_404(page.blueprint_id)
    project_id = blueprint.project_id

    arch_walls = db.query(ArchitecturalWall).filter(ArchitecturalWall.page_id == page.id).all()
    arch_map = {w.id: w for w in arch_walls}

    updated_count = 0
    total_lf = 0.0
    total_gross = 0.0
    total_net = 0.0

    for rid in payload.wall_ids:
        target_aw = arch_map.get(rid) or arch_map.get(f"drywall-wall-{rid}")
        if not target_aw:
            target_aw = next((aw for aw in arch_walls if rid in aw.id), None)

        if target_aw:
            target_aw.wall_tag = payload.wall_tag
            target_aw.height_ft = payload.height_ft
            target_aw.height_provenance = "VERIFIED"
            target_aw.sides_to_hang = payload.sides_to_hang
            target_aw.assembly_tag = payload.wall_tag
            target_aw.assembly_description = payload.assembly_description
            target_aw.assembly_verified = True
            target_aw.status = "approved"
            target_aw.qto_eligible = True
            target_aw.qto_block_reason = None

            gross = target_aw.length_ft * payload.height_ft * payload.sides_to_hang
            net = max(0.0, gross - (target_aw.opening_deduction_sf or 0.0))
            target_aw.gross_sf = gross
            target_aw.net_sf = net

            updated_count += 1
            total_lf += target_aw.length_ft
            total_gross += gross
            total_net += net

    db.commit()

    # Recalculate trade takeoff
    try:
        trade_svc = TradeTakeoffService(db)
        if trade_svc.is_supported(TradeKey.DRYWALL):
            trade_svc.compute_and_persist(TradeKey.DRYWALL, blueprint, project_id, user.id)
    except Exception as exc:
        logger.warning("Trade takeoff recalculation notice: %s", exc)

    return BatchApplyWallsResponse(
        page_id=page.id,
        updated_count=updated_count,
        total_linear_ft=round(total_lf, 2),
        total_gross_sf=round(total_gross, 2),
        total_net_sf=round(total_net, 2),
        assembly_applied=f"{payload.wall_tag} ({payload.assembly_description})" if payload.assembly_description else payload.wall_tag,
        status="success",
    )



