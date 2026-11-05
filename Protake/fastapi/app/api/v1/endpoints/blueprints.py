from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status

from app.api.deps import CurrentUser, DbSession, OwnedProject, get_owned_project
from app.models.blueprint import Blueprint
from app.models.enums import BlueprintStatus
from app.repositories.blueprint_repository import BlueprintRepository
from app.schemas.blueprint import BlueprintRead, BlueprintUploadResponse
from app.services.blueprint_service import BlueprintService, run_blueprint_processing
from app.utils.pagination import Page as Paginated
from app.utils.pagination import PageParams, page_params, paginate

router = APIRouter(tags=["Blueprints"])


def get_owned_blueprint(blueprint_id: int, db: DbSession, user: CurrentUser) -> Blueprint:
    blueprint = BlueprintRepository(db).get(blueprint_id)
    if blueprint is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Blueprint {blueprint_id} not found")
    get_owned_project(blueprint.project_id, db, user)  # raises 403/404 as needed
    return blueprint


OwnedBlueprint = Annotated[Blueprint, Depends(get_owned_blueprint)]


@router.post("/projects/{project_id}/blueprints", response_model=BlueprintUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_blueprint(
    project: OwnedProject,
    db: DbSession,
    user: CurrentUser,
    file: UploadFile = File(...),
) -> BlueprintUploadResponse:
    service = BlueprintService(db)
    blueprint = await service.upload(project.id, user.id, file)
    return BlueprintUploadResponse(blueprint=BlueprintRead.model_validate(blueprint), message="Upload received. Call /process to rasterize and analyze.")


@router.get("/projects/{project_id}/blueprints", response_model=Paginated[BlueprintRead])
def list_blueprints(
    project: OwnedProject,
    db: DbSession,
    params: Annotated[PageParams, Depends(page_params)],
) -> Paginated[BlueprintRead]:
    repo = BlueprintRepository(db)
    return paginate(db, repo.for_project(project.id), params, Blueprint, BlueprintRead)


@router.get("/blueprints/{blueprint_id}", response_model=BlueprintRead)
def get_blueprint(blueprint: OwnedBlueprint) -> BlueprintRead:
    return BlueprintRead.model_validate(blueprint)


STALE_PROCESSING_TIMEOUT = timedelta(minutes=5)


@router.post(
    "/blueprints/{blueprint_id}/process",
    response_model=BlueprintRead,
    status_code=status.HTTP_202_ACCEPTED,
)
def process_blueprint(
    blueprint: OwnedBlueprint,
    db: DbSession,
    request: Request,
    selected_trade: str | None = Query(None),
) -> BlueprintRead:
    """Kicks off rasterization + geometry analysis in a background worker
    *process* (see `app.state.process_pool`, created in main.py's lifespan)
    and returns immediately — large multi-page sheet sets can take minutes,
    far past what a synchronous HTTP request (or a browser's fetch
    timeout) should ever have to wait on, and a real OS process (not a
    thread) means the rest of the API keeps responding normally while it
    runs instead of stalling behind the GIL. Poll `GET /blueprints/{id}`
    for `status` and `pages_processed`/`num_pages`, then `GET
    /blueprints/{id}/pages` once `status` is `processed` or `failed`.
    """
    if selected_trade:
        from app.trades.pricing_service import PricingService
        try:
            pricing = PricingService(db)
            pricing.upsert_project_override(blueprint.project_id, {"trade": selected_trade})
            db.commit()
        except Exception:
            pass

    if blueprint.status == BlueprintStatus.PROCESSING:
        age = datetime.now(timezone.utc) - blueprint.updated_at
        if age < STALE_PROCESSING_TIMEOUT:
            return BlueprintRead.model_validate(blueprint)  # genuinely still running — don't start a second pass

    repo = BlueprintRepository(db)
    repo.update(blueprint, status=BlueprintStatus.PROCESSING, pages_processed=0)
    blueprint.processing_error = None  # BaseRepository.update() skips explicit None fields, so clear it directly
    db.commit()

    request.app.state.process_pool.submit(run_blueprint_processing, blueprint.id)
    return BlueprintRead.model_validate(blueprint)


@router.get("/blueprints/{blueprint_id}/audit-trace")
def audit_trace(blueprint_id: int, db: DbSession) -> dict:
    from app.models.architectural_wall import ArchitecturalWallModel
    from app.models.detection import Detection
    from app.models.page import Page
    from app.models.project_knowledge_graph import ProjectKnowledgeGraphModel

    bp = BlueprintRepository(db).get(blueprint_id)
    if not bp:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Blueprint {blueprint_id} not found")

    pages = db.query(Page).filter(Page.blueprint_id == blueprint_id).order_by(Page.page_number).all()
    pkg = db.query(ProjectKnowledgeGraphModel).filter(ProjectKnowledgeGraphModel.blueprint_id == blueprint_id).first()

    floor_plans = [p for p in pages if (p.page_type == "floor_plan" or (p.is_takeoff_eligible and p.page_number == 1))]
    active_page = floor_plans[0] if floor_plans else (pages[0] if pages else None)

    arch_walls = []
    detections = []
    if active_page:
        arch_walls = db.query(ArchitecturalWallModel).filter(ArchitecturalWallModel.page_id == active_page.id).all()
        detections = db.query(Detection).filter(Detection.page_id == active_page.id).all()

    # Pick 5 representative walls
    sample_walls = []
    if arch_walls:
        sorted_by_len = sorted(arch_walls, key=lambda w: w.length_ft, reverse=True)
        # Select across different lengths and classifications
        sample_walls = sorted_by_len[:min(5, len(sorted_by_len))]

    # Pick 3 representative openings
    door_window_dets = [d for d in detections if getattr(d.kind, "value", str(d.kind)).lower() in ("door", "window")]
    sample_openings = []
    for d in door_window_dets[:3]:
        sample_openings.append({
            "detection_id": d.id,
            "kind": getattr(d.kind, "value", str(d.kind)),
            "label": d.label,
            "bbox_norm": d.bbox_norm,
            "confidence": d.confidence,
        })

    # Total QTO metrics on authoritative sheet
    qto_walls = [w for w in arch_walls if w.qto_eligible]
    gross_sf = sum(w.gross_sf for w in qto_walls)
    ded_sf = sum(w.opening_deduction_sf for w in qto_walls)
    net_sf = sum(w.net_sf for w in qto_walls)
    gross_lf = sum(w.length_ft for w in qto_walls)

    return {
        "blueprint_id": bp.id,
        "filename": bp.original_filename,
        "status": getattr(bp.status, "value", str(bp.status)),
        "authoritative_drywall_sheet": {
            "page_id": active_page.id if active_page else None,
            "page_number": active_page.page_number if active_page else None,
            "sheet_code": active_page.sheet_code if active_page else None,
            "sheet_name": active_page.sheet_name if active_page else None,
            "width_px": active_page.width_px if active_page else None,
            "height_px": active_page.height_px if active_page else None,
            "scale_ft_per_px": active_page.scale_ft_per_px if active_page else None,
        },
        "knowledge_graph": {
            "sheets": pkg.sheets_data if pkg else {},
            "partition_schedules": pkg.partition_schedules_data if pkg else {},
            "door_schedules": pkg.door_schedules_data if pkg else {},
        },
        "qto_summary": {
            "total_arch_walls": len(arch_walls),
            "qto_eligible_walls": len(qto_walls),
            "gross_lf": round(gross_lf, 2),
            "gross_sf": round(gross_sf, 2),
            "deductions_sf": round(ded_sf, 2),
            "net_sf": round(net_sf, 2),
        },
        "five_representative_walls": [


            {
                "id": w.id,
                "wall_tag": w.wall_tag,
                "assembly_tag": w.assembly_tag,
                "assembly_description": w.assembly_description,
                "classification": w.classification,
                "length_ft": w.length_ft,
                "height_ft": w.height_ft,
                "height_provenance": w.height_provenance,
                "thickness_in": w.thickness_in,
                "start_norm": w.start_norm,
                "end_norm": w.end_norm,
                "clipped_segments_norm": w.clipped_segments_norm,
                "wall_polygon_norm": w.wall_polygon_norm,
                "gross_sf": w.gross_sf,
                "opening_deduction_sf": w.opening_deduction_sf,
                "net_sf": w.net_sf,
                "qto_eligible": w.qto_eligible,
                "status": w.status,
            }
            for w in sample_walls
        ],
        "three_representative_openings": sample_openings,
    }


@router.get("/debug/blueprints")
def debug_list_blueprints(db: DbSession) -> list[dict]:
    bps = db.query(Blueprint).order_by(Blueprint.id.desc()).limit(20).all()
    return [
        {
            "id": bp.id,
            "filename": bp.original_filename,
            "status": getattr(bp.status, "value", str(bp.status)),
            "pages_processed": bp.pages_processed,
            "num_pages": bp.num_pages,
            "file_path": bp.file_path,
        }
        for bp in bps
    ]


@router.get("/blueprints/{blueprint_id}/reprocess-canonical")

@router.post("/blueprints/{blueprint_id}/reprocess-canonical")
def reprocess_canonical(blueprint_id: int, db: DbSession) -> dict:
    bp = BlueprintRepository(db).get(blueprint_id)
    if not bp:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Blueprint {blueprint_id} not found")

    svc = BlueprintService(db)
    svc.generate_and_persist_canonical_takeoff(bp)
    return audit_trace(blueprint_id, db)




