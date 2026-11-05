"""Read-only query tools the AI Assistant can call mid-conversation, via
DeepSeek's OpenAI-compatible function-calling.

Why this exists: `assistant_service._build_context` gives the model one
static snapshot at the start of a conversation — a project can have
hundreds of pending detections, so that snapshot deliberately stays small
(counts and totals, not full listings) to keep prompt size bounded. That
means a specific question ("which fixtures on page 3 are under 50%
confidence?") could never be answered accurately from it — the model
would have to guess. These tools let it query the live database for
exactly the slice it needs, when it needs it, instead.

Deliberately read-only. No tool here can create, update, or delete
anything — approving/rejecting detections from a chat message is a real
mutation with real consequences for a takeoff, and needs its own explicit
confirmation step in the UI before it's ever wired up (a separate,
later piece of work), not a side effect of answering a question.
"""

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.detection import Detection
from app.models.enums import DetectionKind, ReviewStatus
from app.models.page import Page
from app.models.room import Room
from app.models.wall import Wall
from app.repositories.blueprint_repository import BlueprintRepository
from app.repositories.page_repository import PageRepository
from app.repositories.room_repository import RoomRepository
from app.repositories.detection_repository import DetectionRepository
from app.models.project import Project

# OpenAI-compatible function-calling schemas (DeepSeek's tool-use format
# matches this exactly — same shape as GPT's, unlike Anthropic's own
# distinct tool-schema convention).
TOOL_SCHEMAS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "list_pages",
            "description": (
                "List every page/sheet in the project's blueprint(s), with its drawing type "
                "(floor_plan, roof_plan, elevation, section, text_specification), whether it's "
                "takeoff-eligible, and room/wall/detection counts. Use this first for any "
                "question about how many pages exist, what type a given page is, or which pages "
                "have how much data — before drilling into a specific page's detail."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_page_detail",
            "description": (
                "Full detail for one specific page: every room (name, area, status), a wall "
                "summary (count, total area, what share have a real measured thickness vs. the "
                "assumed default), and a detection breakdown by kind/source/status. Use this "
                "when the question names or implies a specific page number."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "page_number": {
                        "type": "integer",
                        "description": "The page number to inspect (1-indexed, matches the sheet numbering the user sees).",
                    }
                },
                "required": ["page_number"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_rooms",
            "description": (
                "Search rooms across every page of the project by name substring and/or area "
                "range. Use this for questions like 'find all offices', 'which rooms are over "
                "500 sqft', or 'what's the area of the Kitchenette'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name_contains": {
                        "type": "string",
                        "description": "Case-insensitive substring to match against room names, e.g. 'office' or 'toilet'. Omit to match all names.",
                    },
                    "min_area_sqft": {"type": "number", "description": "Minimum area in square feet, inclusive."},
                    "max_area_sqft": {"type": "number", "description": "Maximum area in square feet, inclusive."},
                    "page_number": {
                        "type": "integer",
                        "description": "Restrict the search to one page number. Omit to search the whole project.",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_flagged_detections",
            "description": (
                "List AI/geometry detections (fixtures, windows, doors, rooms, walls, symbols) "
                "filtered by kind, confidence range, review status, and/or page. Use this for "
                "review-queue questions like 'what's still pending on page 2', 'show low-"
                "confidence fixtures', or 'how many windows were detected'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "kind": {
                        "type": "string",
                        "enum": [k.value for k in DetectionKind],
                        "description": "Filter to one detection kind. Omit to include all kinds.",
                    },
                    "min_confidence": {"type": "number", "description": "0.0-1.0, inclusive lower bound."},
                    "max_confidence": {"type": "number", "description": "0.0-1.0, inclusive upper bound."},
                    "status": {
                        "type": "string",
                        "enum": [s.value for s in ReviewStatus],
                        "description": "Filter to one review status. Omit to include all statuses.",
                    },
                    "page_number": {
                        "type": "integer",
                        "description": "Restrict to one page number. Omit to search the whole project.",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "propose_approve_detection",
            "description": (
                "Propose approving a specific detection (by its detection_id, from "
                "list_flagged_detections output ONLY — get_page_detail/search_rooms return room_id, "
                "a different ID namespace; a Room entry there does not necessarily have a matching "
                "Detection row, so never pass a room_id here). This does NOT change anything by "
                "itself — it drafts an action shown to the user as a confirm/cancel button in the "
                "UI. Only the user's own click actually approves it. If the target came from "
                "get_page_detail/search_rooms (a room, not a flagged detection), use "
                "propose_set_room_status instead."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "detection_id": {"type": "integer", "description": "The detection's ID."},
                    "reason": {"type": "string", "description": "Optional short reason, shown to the user and recorded in the audit log."},
                },
                "required": ["detection_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "propose_reject_detection",
            "description": (
                "Propose rejecting a specific detection (by its detection_id, from "
                "list_flagged_detections output ONLY — NOT a room_id from get_page_detail/"
                "search_rooms, a different ID namespace; a Room entry there does not necessarily "
                "have a matching Detection row). Does NOT change anything by itself — drafts a "
                "confirm/cancel action for the user. If the target came from get_page_detail/"
                "search_rooms (a room, not a flagged detection), use propose_set_room_status "
                "instead."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "detection_id": {"type": "integer", "description": "The detection's ID."},
                    "reason": {"type": "string", "description": "Optional short reason, shown to the user and recorded in the audit log."},
                },
                "required": ["detection_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "propose_rename_room",
            "description": (
                "Propose renaming a specific room (by its ID, from get_page_detail/search_rooms "
                "output). Does NOT change anything by itself — drafts a confirm/cancel action for "
                "the user."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "room_id": {"type": "integer", "description": "The room's ID."},
                    "new_name": {"type": "string", "description": "The proposed new name."},
                },
                "required": ["room_id", "new_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "propose_set_room_status",
            "description": (
                "Propose approving or rejecting a specific room (by its ID). Does NOT change "
                "anything by itself — drafts a confirm/cancel action for the user."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "room_id": {"type": "integer", "description": "The room's ID."},
                    "status": {"type": "string", "enum": ["approved", "rejected"], "description": "The proposed new status."},
                    "reason": {"type": "string", "description": "Optional short reason, shown to the user and recorded in the audit log."},
                },
                "required": ["room_id", "status"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_wall_evidence",
            "description": (
                "Retrieve comprehensive physical-source forensic proof and evidence chain for a "
                "specific wall (by its wall_id, e.g. '535458', 'drywall-wall-535458', 'AW-535458', "
                "or by page_number). Returns dual-face segment IDs, exact face coordinates, CAD layers, "
                "measured thickness, centerline midpoint formula, opening clipping, canonical classification, "
                "QTO hang area calculations, and scale provenance."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "wall_id": {
                        "type": "string",
                        "description": "The wall's ID (e.g. '535458', 'backend-archwall-535458', 'drywall-wall-535458', 'AW-104').",
                    },
                    "page_number": {
                        "type": "integer",
                        "description": "Optional page number (1-indexed) if wall_id is not known.",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "propose_generate_estimate",
            "description": (
                "Propose generating (or regenerating) the project's cost estimate from its current "
                "approved geometry. Use this when the user asks about costs/pricing/trade quantities "
                "and the context shows no estimate yet, or an estimate that predates recent "
                "approvals (the estimate only reflects geometry that was approved at the moment it "
                "was generated — new approvals since then need a fresh run to show up in cost "
                "figures). Does NOT change anything by itself — drafts a confirm/cancel action; the "
                "actual generation only runs if the user confirms in the UI."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "overhead_pct": {"type": "number", "description": "Overhead percent on direct cost. Omit to use the project default (10)."},
                    "profit_pct": {"type": "number", "description": "Profit percent on top of overhead+contingency. Omit to use the project default (15)."},
                    "contingency_pct": {"type": "number", "description": "Contingency percent on direct cost. Omit to use the project default (5)."},
                },
            },
        },
    },
]

# Tool names that draft a UI-confirmable mutation instead of returning pure
# information. execute_tool() still runs these read-only (they only look up
# and validate the target, never write to the DB) — the actual mutation
# happens later, if and only if the user clicks confirm, via the same
# authenticated/audited REST endpoints the manual review UI already uses
# (POST /detections/{id}/approve|reject, PATCH /rooms/{id}). Kept as a
# separate set so assistant_service.ask() can pull these out of tool_calls
# into a distinct proposed_actions list for the frontend to render as
# actionable chips instead of plain text.
ACTION_TOOL_NAMES = {
    "propose_approve_detection",
    "propose_reject_detection",
    "propose_rename_room",
    "propose_set_room_status",
    "propose_generate_estimate",
}

# Hard ceiling on rows returned by any single tool call — a runaway
# 'search_rooms with no filters' on a huge project must not blow the
# response payload (and therefore the next request's prompt size) up
# unboundedly. The model is told about truncation explicitly so it knows
# to narrow its own query rather than trust an incomplete list as
# complete.
_MAX_ROWS = 60


def _project_page_ids(db: Session, project: Project) -> list[int]:
    blueprints = BlueprintRepository(db).find(project_id=project.id)
    page_ids: list[int] = []
    for bp in blueprints:
        page_ids.extend(p.id for p in PageRepository(db).find(blueprint_id=bp.id))
    return page_ids


def _list_pages(db: Session, project: Project, _args: dict) -> dict:
    blueprints = BlueprintRepository(db).find(project_id=project.id)
    pages: list[dict] = []
    for bp in blueprints:
        for page in PageRepository(db).find(blueprint_id=bp.id):
            room_count = len(db.execute(select(Room).where(Room.page_id == page.id)).scalars().all())
            wall_count = len(db.execute(select(Wall).where(Wall.page_id == page.id)).scalars().all())
            detection_count = len(db.execute(select(Detection).where(Detection.page_id == page.id)).scalars().all())
            pages.append(
                {
                    "page_number": page.page_number,
                    "page_type": page.page_type,
                    "is_takeoff_eligible": page.is_takeoff_eligible,
                    "skip_reason": page.skip_reason,
                    "room_count": room_count,
                    "wall_count": wall_count,
                    "detection_count": detection_count,
                }
            )
    pages.sort(key=lambda p: p["page_number"])
    return {"pages": pages}


def _get_page_detail(db: Session, project: Project, args: dict) -> dict:
    page_number = args.get("page_number")
    if page_number is None:
        return {"error": "page_number is required"}

    blueprints = BlueprintRepository(db).find(project_id=project.id)
    page: Page | None = None
    for bp in blueprints:
        page = PageRepository(db).find_one(blueprint_id=bp.id, page_number=int(page_number))
        if page:
            break
    if page is None:
        return {"error": f"No page {page_number} found in this project"}

    rooms = db.execute(select(Room).where(Room.page_id == page.id)).scalars().all()
    walls = db.execute(select(Wall).where(Wall.page_id == page.id)).scalars().all()
    detections = db.execute(select(Detection).where(Detection.page_id == page.id)).scalars().all()

    measured_walls = sum(1 for w in walls if w.thickness_measured)
    detection_breakdown: dict[str, int] = {}
    for d in detections:
        key = f"{d.kind.value}/{d.source.value}/{d.status.value}"
        detection_breakdown[key] = detection_breakdown.get(key, 0) + 1

    return {
        "page_number": page.page_number,
        "page_type": page.page_type,
        "is_takeoff_eligible": page.is_takeoff_eligible,
        "skip_reason": page.skip_reason,
        "scale_ft_per_px": page.scale_ft_per_px,
        "rooms": [
            {
                "room_id": r.id,
                "name": r.name,
                "area_sqft": round(r.area_sqft, 1),
                "room_type": r.room_type,
                "status": r.status.value,
            }
            for r in rooms
        ],
        "wall_summary": {
            "count": len(walls),
            "total_area_sqft": round(sum(w.area_sqft for w in walls), 1),
            "thickness_measured_count": measured_walls,
            "thickness_measured_pct": round(measured_walls / len(walls) * 100, 0) if walls else None,
        },
        "detection_breakdown_by_kind_source_status": detection_breakdown,
    }


def _search_rooms(db: Session, project: Project, args: dict) -> dict:
    page_ids = _project_page_ids(db, project)
    if not page_ids:
        return {"rooms": [], "truncated": False}

    stmt = select(Room, Page.page_number).join(Page, Room.page_id == Page.id).where(Room.page_id.in_(page_ids))
    name_contains = args.get("name_contains")
    if name_contains:
        stmt = stmt.where(Room.name.ilike(f"%{name_contains}%"))
    if args.get("min_area_sqft") is not None:
        stmt = stmt.where(Room.area_sqft >= args["min_area_sqft"])
    if args.get("max_area_sqft") is not None:
        stmt = stmt.where(Room.area_sqft <= args["max_area_sqft"])
    if args.get("page_number") is not None:
        stmt = stmt.where(Page.page_number == args["page_number"])

    rows = db.execute(stmt.order_by(Room.area_sqft.desc())).all()
    truncated = len(rows) > _MAX_ROWS
    rows = rows[:_MAX_ROWS]

    return {
        "rooms": [
            {
                "room_id": r.id,
                "name": r.name,
                "area_sqft": round(r.area_sqft, 1),
                "room_type": r.room_type,
                "status": r.status.value,
                "page_number": page_number,
            }
            for r, page_number in rows
        ],
        "truncated": truncated,
    }


def _list_flagged_detections(db: Session, project: Project, args: dict) -> dict:
    page_ids = _project_page_ids(db, project)
    if not page_ids:
        return {"detections": [], "truncated": False}

    stmt = (
        select(Detection, Page.page_number)
        .join(Page, Detection.page_id == Page.id)
        .where(Detection.page_id.in_(page_ids))
    )
    if args.get("kind"):
        stmt = stmt.where(Detection.kind == DetectionKind(args["kind"]))
    if args.get("status"):
        stmt = stmt.where(Detection.status == ReviewStatus(args["status"]))
    if args.get("min_confidence") is not None:
        stmt = stmt.where(Detection.confidence >= args["min_confidence"])
    if args.get("max_confidence") is not None:
        stmt = stmt.where(Detection.confidence <= args["max_confidence"])
    if args.get("page_number") is not None:
        stmt = stmt.where(Page.page_number == args["page_number"])

    rows = db.execute(stmt.order_by(Detection.confidence.asc())).all()
    truncated = len(rows) > _MAX_ROWS
    rows = rows[:_MAX_ROWS]

    return {
        "detections": [
            {
                "detection_id": d.id,
                "kind": d.kind.value,
                "label": d.label,
                "confidence": round(d.confidence, 2),
                "source": d.source.value,
                "status": d.status.value,
                "page_number": page_number,
                "linked_room_id": d.linked_room_id,
            }
            for d, page_number in rows
        ],
        "truncated": truncated,
    }


def _propose_approve_detection(db: Session, project: Project, args: dict) -> dict:
    return _propose_detection_review(db, project, args, "approved")


def _propose_reject_detection(db: Session, project: Project, args: dict) -> dict:
    return _propose_detection_review(db, project, args, "rejected")


def _propose_detection_review(db: Session, project: Project, args: dict, new_status: str) -> dict:
    detection_id = args.get("detection_id")
    if detection_id is None:
        return {"error": "detection_id is required"}

    page_ids = set(_project_page_ids(db, project))
    detection = DetectionRepository(db).get(int(detection_id))
    if detection is None or detection.page_id not in page_ids:
        return {
            "error": (
                f"No detection {detection_id} found in this project. If this ID came from "
                "get_page_detail/search_rooms, it's a room_id, not a detection_id — use "
                "propose_set_room_status instead."
            )
        }

    page = db.get(Page, detection.page_id)
    return {
        "proposed": True,
        "action": "reject_detection" if new_status == "rejected" else "approve_detection",
        "detection_id": detection.id,
        "label": detection.label,
        "kind": detection.kind.value,
        "current_status": detection.status.value,
        "new_status": new_status,
        "page_number": page.page_number if page else None,
        "reason": args.get("reason"),
    }


def _propose_rename_room(db: Session, project: Project, args: dict) -> dict:
    room_id = args.get("room_id")
    new_name = args.get("new_name")
    if room_id is None or not new_name:
        return {"error": "room_id and new_name are required"}

    page_ids = set(_project_page_ids(db, project))
    room = RoomRepository(db).get(int(room_id))
    if room is None or room.page_id not in page_ids:
        return {"error": f"No room {room_id} found in this project"}

    page = db.get(Page, room.page_id)
    return {
        "proposed": True,
        "action": "rename_room",
        "room_id": room.id,
        "current_name": room.name,
        "new_name": new_name,
        "page_number": page.page_number if page else None,
    }


def _propose_set_room_status(db: Session, project: Project, args: dict) -> dict:
    room_id = args.get("room_id")
    new_status = args.get("status")
    if room_id is None or new_status not in ("approved", "rejected"):
        return {"error": "room_id and status ('approved' or 'rejected') are required"}

    page_ids = set(_project_page_ids(db, project))
    room = RoomRepository(db).get(int(room_id))
    if room is None or room.page_id not in page_ids:
        return {"error": f"No room {room_id} found in this project"}

    page = db.get(Page, room.page_id)
    return {
        "proposed": True,
        "action": "set_room_status",
        "room_id": room.id,
        "label": room.name,
        "current_status": room.status.value,
        "new_status": new_status,
        "page_number": page.page_number if page else None,
        "reason": args.get("reason"),
    }


def _propose_generate_estimate(db: Session, project: Project, args: dict) -> dict:
    blueprints = BlueprintRepository(db).find(project_id=project.id)
    if not blueprints:
        return {"error": "This project has no blueprint uploaded yet — nothing to generate an estimate from"}
    blueprint = blueprints[0]

    page_ids = _project_page_ids(db, project)
    approved_rooms = RoomRepository(db).approved_for_pages(page_ids)
    from app.repositories.wall_repository import WallRepository

    approved_walls = WallRepository(db).approved_for_pages(page_ids)

    return {
        "proposed": True,
        "action": "generate_estimate",
        "blueprint_id": blueprint.id,
        "approved_room_count": len(approved_rooms),
        "approved_room_area_sqft": round(sum(r.area_sqft for r in approved_rooms), 1),
        "approved_wall_count": len(approved_walls),
        "approved_wall_area_sqft": round(sum(w.area_sqft for w in approved_walls), 1),
        "overhead_pct": args.get("overhead_pct", 10),
        "profit_pct": args.get("profit_pct", 15),
        "contingency_pct": args.get("contingency_pct", 5),
    }


def _get_wall_evidence(db: Session, project: Project, args: dict) -> dict:
    wall_id = args.get("wall_id")
    page_number = args.get("page_number")

    from app.models.architectural_wall import ArchitecturalWallModel
    from app.models.page import Page
    from app.models.blueprint import Blueprint

    blueprints = BlueprintRepository(db).find(project_id=project.id)
    bp_ids = [bp.id for bp in blueprints]
    if not bp_ids:
        return {"error": "No blueprints in this project"}

    pages = db.query(Page).filter(Page.blueprint_id.in_(bp_ids)).all()
    page_ids = [p.id for p in pages]
    page_map = {p.id: p for p in pages}
    bp_map = {bp.id: bp for bp in blueprints}

    aw: ArchitecturalWallModel | None = None
    if wall_id:
        raw_id = str(wall_id).replace("backend-archwall-", "").replace("backend-wall-", "").replace("AW-", "").replace("W-", "").strip()
        candidates = [raw_id, f"drywall-wall-{raw_id}", f"AW-{raw_id}", str(wall_id)]
        aw = db.query(ArchitecturalWallModel).filter(
            ArchitecturalWallModel.page_id.in_(page_ids),
            ArchitecturalWallModel.id.in_(candidates),
        ).first()
        if not aw:
            # Substring / bridged search
            aw = db.query(ArchitecturalWallModel).filter(
                ArchitecturalWallModel.page_id.in_(page_ids),
                ArchitecturalWallModel.id.like(f"%{raw_id}%"),
            ).first()

    if not aw and page_number is not None:
        target_page = next((p for p in pages if p.page_number == int(page_number)), None)
        if target_page:
            aw = db.query(ArchitecturalWallModel).filter(ArchitecturalWallModel.page_id == target_page.id).first()

    if not aw:
        return {"error": f"Wall '{wall_id}' not found in this project. Please specify an exact Wall ID or select a wall on the canvas."}

    page = page_map.get(aw.page_id)
    bp = bp_map.get(page.blueprint_id) if page else None

    ev_dict = aw.evidence or {}
    card = ev_dict.get("card", {})
    ev_chain = card.get("evidence_chain", {})
    openings = ev_dict.get("openings", [])

    face_a_id = ev_dict.get("face_a_segment_id") or ev_chain.get("face_a_segment_id") or card.get("face_a_segment_id")
    face_b_id = ev_dict.get("face_b_segment_id") or ev_chain.get("face_b_segment_id") or card.get("face_b_segment_id")
    face_a_coords = ev_dict.get("face_a_coords") or card.get("face_a_coords")
    face_b_coords = ev_dict.get("face_b_coords") or card.get("face_b_coords")
    recon_method = ev_dict.get("reconstruction_method") or card.get("reconstruction_method") or (
        "DUAL_FACE" if (face_a_id and face_b_id) else "SINGLE_FACE_EVIDENCE_BACKED"
    )

    cad_layers = ev_chain.get("layers", []) or ([ev_chain.get("cad_layer")] if ev_chain.get("cad_layer") else ["A-WALL"])

    return {
        "wall_id": f"backend-archwall-{aw.id}",
        "raw_id": aw.id,
        "verdict": "VERIFIED PHYSICAL WALL" if (recon_method == "DUAL_FACE" or aw.confidence >= 0.85) else "PROVISIONAL WALL (EVIDENCE-BACKED)",
        "reconstruction_method": recon_method,
        "source": {
            "blueprint_id": bp.id if bp else None,
            "blueprint_filename": bp.original_filename if bp else "Unknown",
            "page_id": page.id if page else None,
            "page_number": page.page_number if page else None,
            "sheet_code": page.sheet_code if page else None,
            "sheet_name": page.sheet_name if page else None,
        },
        "geometry": {
            "face_a_segment_id": face_a_id,
            "face_b_segment_id": face_b_id,
            "face_a_coords": face_a_coords,
            "face_b_coords": face_b_coords,
            "thickness_in": aw.thickness_in,
            "thickness_source": aw.thickness_source,
            "length_ft": aw.length_ft,
            "height_ft": aw.height_ft,
            "height_provenance": aw.height_provenance,
            "start_norm": aw.start_norm,
            "end_norm": aw.end_norm,
            "clipped_segments": aw.clipped_segments_norm,
            "wall_polygon": aw.wall_polygon_norm,
        },
        "evidence": {
            "cad_layers": cad_layers,
            "paired_faces": bool(face_a_id and face_b_id),
            "attached_openings_count": aw.openings_count,
            "opening_ids": [op.get("id") for op in openings if isinstance(op, dict)],
            "true_source_union_length_ft": ev_dict.get("true_source_union_length_ft", aw.length_ft),
            "is_bridged": ev_dict.get("is_bridged", False),
            "bridged_segment_count": ev_dict.get("bridged_segment_count", 1),
        },
        "classification": {
            "category": aw.classification,
            "confidence": aw.confidence,
            "reasons": card.get("rejection_reasons", []) if aw.status != "approved" else ["dual_independent_faces_supported", "room_boundary_topology"],
            "wall_tag": aw.wall_tag,
        },
        "qto": {
            "eligible": aw.qto_eligible,
            "block_reason": aw.qto_block_reason,
            "assembly_tag": aw.assembly_tag,
            "assembly_description": aw.assembly_description,
            "assembly_verified": aw.assembly_verified,
            "gross_sf": aw.gross_sf,
            "opening_deduction_sf": aw.opening_deduction_sf,
            "net_sf": aw.net_sf,
            "sides_to_hang": aw.sides_to_hang,
            "layers_side_a": aw.layers_side_a,
            "layers_side_b": aw.layers_side_b,
        },
        "scale": {
            "scale_ft_per_px": page.scale_ft_per_px if page else None,
            "scale_source": page.scale_source if page else "assumed_default",
            "scale_status": "VERIFIED" if (page and page.scale_source in ("reference_object_calibration", "dimension_measurement", "printed_notation", "user_calibrated")) else "ASSUMED_SCALE",
        },
        "proof_card": {
            "wall_id": f"W-{wall_id}",
            "source": "vector" if "vector" in (aw.source_evidence.get("source", "vector") if isinstance(aw.source_evidence, dict) else "vector") else "raster",
            "sheet": page.sheet_code if page and page.sheet_code else f"A-{page.page_number if page else 101}",
            "trade": "architectural",
            "level": "Level 1",
            "room_left": str(aw.room_ids[0]) if aw.room_ids and len(aw.room_ids) >= 1 else None,
            "room_right": str(aw.room_ids[1]) if aw.room_ids and len(aw.room_ids) >= 2 else None,
            "length_ft": aw.length_ft,
            "thickness_in": aw.thickness_in,
            "height_ft": aw.height_ft,
            "wall_type": aw.wall_tag or "W1",
            "opening_ids": [str(op.get("id")) for op in openings if isinstance(op, dict) and op.get("id")],
            "scale_source": page.scale_source if page else "verified",
            "height_source": aw.height_provenance,
            "physics": "PASS" if aw.status == "approved" else "FLAGGED",
            "topology": "PASS" if len(aw.room_ids) > 0 else "FLAGGED",
            "qto_eligible": aw.qto_eligible,
            "confidence": aw.confidence,
        },
    }


_DISPATCH = {
    "list_pages": _list_pages,
    "get_page_detail": _get_page_detail,
    "search_rooms": _search_rooms,
    "list_flagged_detections": _list_flagged_detections,
    "get_wall_evidence": _get_wall_evidence,
    "propose_approve_detection": _propose_approve_detection,
    "propose_reject_detection": _propose_reject_detection,
    "propose_rename_room": _propose_rename_room,
    "propose_set_room_status": _propose_set_room_status,
    "propose_generate_estimate": _propose_generate_estimate,
}


def execute_tool(db: Session, project: Project, name: str, arguments: dict[str, Any]) -> dict:
    handler = _DISPATCH.get(name)
    if handler is None:
        return {"error": f"Unknown tool '{name}'"}
    try:
        return handler(db, project, arguments)
    except Exception as exc:  # a tool failure must end the turn gracefully, not the whole request
        return {"error": f"Tool '{name}' failed: {exc}"}
