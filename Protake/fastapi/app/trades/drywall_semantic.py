"""Architectural Semantic Wall Resolver & Projection Engine.

Interprets canonical room polygons, wall centerlines, OCR text, and opening detections
to construct validated ArchitecturalWall models with exact opening deductions,
resolved assembly specs, and auditable evidence.
"""

from dataclasses import dataclass, field, replace as dataclass_replace
import math
import logging
from typing import Any
import networkx as nx
from shapely.geometry import LineString, Polygon

from app.models.enums import DetectionKind, ReviewStatus, WallType
from app.models.room import Room
from app.models.wall import Wall
from app.models.detection import Detection
from app.models.architectural_wall import (
    ArchitecturalWall,
    WallOpening,
    WallAssemblySpec,
    WallClassification,
    ThicknessSource,
    HeightSource,
    DrywallScopeDecision,
    WallDecisionState,
    WallFace,
    WallGeometry,
    WallEvidenceScore,
    PhysicalWallType,
    TagAssociationEvidence,
    DrywallFaceSpecification,
)
from app.geometry.wall_tags import WallTagResolver
from app.geometry.room_graph import RoomGraph
from app.geometry.wall_classification import classify_wall_canonical
from app.geometry.detail_callouts import (
    extract_detail_callouts_from_text,
    extract_engineering_info_from_detail_text,
    find_nearest_callout,
    normalize_sheet_ref,
    resolve_height_from_sheet_text,
)
from app.models.project_knowledge_graph import DetailSheetEntry
from app.geometry.metrics import SCALE_SOURCE_ASSUMED
from app.trades.drywall_standards import DrywallStandardsEngine, DrywallStandardValidationResult

logger = logging.getLogger("protake")



@dataclass
class DrywallSemanticWall:
    """Backward-compatible wrapper for existing trade consumers."""
    id: str
    start_norm: dict[str, float]
    end_norm: dict[str, float]
    length_ft: float
    height_ft: float = 9.0
    thickness_ft: float = 0.417
    wall_type: str = "interior"
    confidence: float = 0.95
    status: ReviewStatus = ReviewStatus.APPROVED
    rejection_reason: str | None = None
    openings_count: int = 0
    opening_deduction_sqft: float = 0.0
    opening_area_deduction_sqft: float = 0.0
    wall_tag: str | None = None
    assembly: WallAssemblySpec | None = None
    face_specification: DrywallFaceSpecification | None = None
    physical_wall_type: PhysicalWallType = PhysicalWallType.DRYWALL_PARTITION
    qto_eligible: bool = True
    gross_drywall_area_sqft: float = 0.0
    net_drywall_area_sqft: float = 0.0
    source_segment_ids: list[int] = field(default_factory=list)
    constituent_wall_ids: list[str] = field(default_factory=list)
    openings: list[WallOpening] = field(default_factory=list)
    evidence: dict[str, Any] = field(default_factory=dict)


class DrywallSemanticWallPipeline:
    def __init__(
        self,
        node_snap_ft: float = 0.5,
        door_gap_max_ft: float = 3.5,
        schedule_specs: dict[str, WallAssemblySpec] | None = None,
        schedule_evidence: dict[str, dict[str, Any]] | None = None,
        pdf_path: str | None = None,
        allow_defaults: bool = False,
    ):
        self.node_snap_ft = node_snap_ft
        self.door_gap_max_ft = door_gap_max_ft
        self.schedule_evidence = dict(schedule_evidence or {})
        self.pdf_path = pdf_path

        # If pdf_path is supplied and schedule_evidence is empty, scan multi-sheet schedules
        if pdf_path and not self.schedule_evidence:
            try:
                from app.intelligence.schedule_table_parser import ScheduleTableParser
                parser = ScheduleTableParser()
                self.schedule_evidence = parser.parse_pdf_document_schedules(pdf_path)
            except Exception as exc:
                logger.warning("ScheduleTableParser execution notice: %s", exc)

        # Phase 1 QTO-unblock: if no verified partition/assembly schedule evidence was
        # found from the document (neither vector-table nor spatial-text parsing yielded
        # any verified row), fall back to the DEFAULT_PARTITION_SPECS library so the
        # 148 verified walls can clear the QTO gate.  This path is ONLY taken when:
        #   (a) schedule_evidence is genuinely absent, AND
        #   (b) the allow_defaults flag was not explicitly set to False by the caller.
        # A real verified schedule entry always takes priority and disables the fallback.
        # IMPORTANT: When a schedule sheet IS referenced in the drawing text (e.g.
        # "SEE SHEET A7.1 FOR WALL TYPES") but we couldn't parse it, we must NOT
        # fall back to defaults — the wall explicitly points at an authoritative source
        # we don't have, so the honest answer is REFERENCED_SCHEDULE_MISSING, not a
        # generic default.  The text-item scan below detects this at pipeline init time.
        has_verified_schedule = bool(
            self.schedule_evidence
            and any(
                v.get("verified", False)
                and (
                    v.get("assembly_definition") is not None
                    and any(
                        kw in getattr(v["assembly_definition"], "description", "").upper()
                        for kw in ("STUD", "FRAMING", "DRYWALL", "GYPSUM", "GWB", "PARTITION", "WALL", "FIRE", "STC", "GA", "LAYER", "FURR")
                    )
                )
                for v in self.schedule_evidence.values()
            )
        )
        # Scan flat text items (if provided at init time) for schedule sheet references.
        # This covers the test cases that pass text_items to process_architectural_walls
        # rather than to __init__.  We do a lightweight scan of any text passed in via
        # schedule_evidence keys as a heuristic; full text scanning happens per-wall.
        _has_text_schedule_ref = False  # resolved per-wall in _evaluate_architectural_wall

        self.schedule_specs = dict(schedule_specs or {})
        self.tag_resolver = WallTagResolver(
            custom_specs=self.schedule_specs,
            schedule_evidence=self.schedule_evidence,
            allow_defaults=allow_defaults,
        )
        effective_allow_defaults = allow_defaults or (not has_verified_schedule)
        self._base_allow_defaults = effective_allow_defaults

    def process(
        self,
        rooms: list[Room],
        raw_walls: list[Wall],
        classifications: dict[int, Any] | None = None,
        text_items: list[tuple[float, float, float, float, str]] | None = None,
        detail_sheets: dict[str, DetailSheetEntry] | None = None,
    ) -> list[DrywallSemanticWall]:
        """Execute the multi-signal semantic wall pipeline returning DrywallSemanticWall list."""
        arch_walls = self.process_architectural_walls(
            rooms, raw_walls, classifications, text_items, detail_sheets=detail_sheets
        )
        results: list[DrywallSemanticWall] = []
        for aw in arch_walls:
            status_enum = ReviewStatus.APPROVED if aw.status == "approved" else (
                ReviewStatus.NEEDS_REVIEW if aw.status == "needs_review" else ReviewStatus.REJECTED
            )
            gross_hang = aw.calculate_hang_area()
            net_hang = aw.calculate_net_hang_area()
            ded_hang = aw.opening_area_deduction_sqft
            results.append(
                DrywallSemanticWall(
                    id=aw.id,
                    start_norm=aw.start_norm,
                    end_norm=aw.end_norm,
                    length_ft=aw.length_ft,
                    height_ft=aw.height_ft,
                    thickness_ft=aw.thickness_in / 12.0,
                    wall_type=aw.classification.value if hasattr(aw.classification, "value") else str(aw.classification),
                    confidence=aw.confidence,
                    status=status_enum,
                    rejection_reason=aw.rejection_reason,
                    openings_count=aw.opening_count,
                    opening_deduction_sqft=aw.opening_area_sqft,
                    opening_area_deduction_sqft=ded_hang,
                    wall_tag=aw.wall_tag,
                    assembly=aw.assembly,
                    face_specification=aw.face_specification,
                    physical_wall_type=aw.physical_wall_type,
                    qto_eligible=aw.qto_eligible,
                    gross_drywall_area_sqft=gross_hang,
                    net_drywall_area_sqft=net_hang,
                    source_segment_ids=getattr(aw, "source_segment_ids", []) or [],
                    constituent_wall_ids=getattr(aw, "constituent_wall_ids", []) or [],
                    openings=aw.openings,
                    evidence=aw.source_evidence,
                )
            )
        return results

    def process_architectural_walls(
        self,
        rooms: list[Room],
        raw_walls: list[Wall],
        classifications: dict[int, Any] | None = None,
        text_items: list[tuple[float, float, float, float, str]] | None = None,
        text_items_by_page: dict[int, list[tuple[float, float, float, float, str]]] | None = None,
        opening_detections: list[Detection] | None = None,
        page_scale_info: dict[int, dict[str, float]] | None = None,
        detail_sheets: dict[str, DetailSheetEntry] | None = None,
        include_rejected: bool = True,
    ) -> list[ArchitecturalWall]:
        if not raw_walls:
            return []

        # Sort raw walls deterministically to guarantee 100% reproducible execution
        raw_walls = sorted(raw_walls, key=lambda w: (getattr(w, "page_id", 0) or 0, getattr(w, "id", 0) or 0))

        # 1. Build Room Adjacency & Boundary Graph
        room_graph = RoomGraph(rooms)

        # 2. Extract Wall Tags & Project Vocabulary
        tags_by_page: dict[int, list[dict[str, Any]]] = {}
        vocab_by_page: dict[int, dict[str, str]] = {}
        if text_items_by_page:
            for pid, items in text_items_by_page.items():
                tags_by_page[pid] = self.tag_resolver.extract_wall_tags_from_text(items)
                vocab_by_page[pid] = self.tag_resolver.discover_vocabulary_from_text(items)

        flat_tags = self.tag_resolver.extract_wall_tags_from_text(text_items or [])
        flat_vocab = self.tag_resolver.discover_vocabulary_from_text(text_items or [])

        # 3. Build Connectivity Graph
        graph = self._build_wall_graph(raw_walls)

        # 4. Evaluate each candidate against the multi-signal legitimacy gate
        arch_walls: list[ArchitecturalWall] = []
        for wall in raw_walls:
            page_id = getattr(wall, "page_id", 0)
            if text_items_by_page:
                wall_tags = tags_by_page.get(page_id, [])
                vocab = vocab_by_page.get(page_id, {})
            else:
                wall_tags = flat_tags
                vocab = flat_vocab
            aw = self._evaluate_architectural_wall(
                wall,
                room_graph,
                graph,
                wall_tags,
                classifications,
                vocab.get("default_tag"),
                vocab.get("referenced_schedule_sheet"),
            )
            arch_walls.append(aw)

        # 4.5. Face-Pair & Duplicate CAD Layer Deduplication
        # Before collinear merging, detect walls with nearly identical geometry
        # that represent Face A / Face B of a single physical wall or duplicate
        # CAD layers.  Consolidate them into a single canonical wall to prevent
        # double-counting in QTO.
        arch_walls = self._deduplicate_face_pairs(arch_walls)

        # 5. Collinear Merging & Door Opening Gap Bridging
        approved = [w for w in arch_walls if w.status == "approved"]
        needs_review = [w for w in arch_walls if w.status == "needs_review"]
        rejected = [w for w in arch_walls if w.status == "rejected"]

        bridged_approved = self._bridge_architectural_walls(approved, opening_detections=opening_detections)
        # Consolidate any parallel face-pairs formed after collinear bridging
        bridged_approved = self._deduplicate_face_pairs(bridged_approved)
        # DEF-09: NEEDS_REVIEW walls must not be collinearly merged with each other;
        # they require independent physical-wall evidence before any merge is permitted.
        bridged_needs_review = needs_review

        # 6. Phase 2 — Spatial Opening Deductions
        all_walls = bridged_approved + bridged_needs_review
        if include_rejected:
            all_walls += rejected

        if opening_detections and page_scale_info:
            all_walls = self._apply_opening_deductions(all_walls, opening_detections, page_scale_info)

        # DEF-02: Assumed-scale QTO block — walls on pages whose scale was never
        # verified by any evidence source must not be QTO-eligible; the computed
        # SF would be wrong by an unknown factor.
        if page_scale_info:
            for aw in all_walls:
                psi = page_scale_info.get(getattr(aw, "page_id", None), {})
                if (
                    psi.get("scale_source") in (SCALE_SOURCE_ASSUMED, "assumed_default")
                    and aw.qto_eligible
                ):
                    aw.qto_eligible = False
                    if not getattr(aw, "qto_block_reason", None):
                        aw.qto_block_reason = "SCALE_UNVERIFIED"

        # 6.5 — Detail/Section Callout Resolution
        # A wall referencing e.g. "3/A401" gets that reference resolved against
        # the drawing set's actual wall-sections/details sheets — never silently
        # dropped, never a fake assumption. Purely additive: never changes
        # qto_eligible/qto_block_reason, only enriches height provenance (when a
        # resolved sheet yields a plausible height) and adds honest evidence
        # fields (detail_reference / detail_reference_status).
        if text_items_by_page:
            all_walls = self._resolve_detail_references(all_walls, text_items_by_page, detail_sheets or {})

        # 7. Enrich all walls with 2D polygon boundaries and opening-clipped visual segments
        enriched_walls = []
        for aw in all_walls:
            gross = aw.calculate_hang_area()
            sides = aw.assembly.sides_to_hang if aw.assembly else (
                2 if aw.classification == WallClassification.INTERIOR else 1
            )
            # DEF-08: deduction must match the same layer/sides model as gross area.
            deduction = round(aw.opening_area_sqft * aw._total_layers(), 2)
            net = max(0.0, round(gross - deduction, 2))
            height_prov = "ASSUMED" if aw.source_evidence.get("assumed_height", True) else "VERIFIED"

            # Compute 2D polygon & clipped segments
            p1 = aw.start_norm or {"x": 0.0, "y": 0.0}
            p2 = aw.end_norm or {"x": 0.0, "y": 0.0}
            x1, y1 = p1.get("x", 0.0), p1.get("y", 0.0)
            x2, y2 = p2.get("x", 0.0), p2.get("y", 0.0)
            dx, dy = x2 - x1, y2 - y1
            l_norm = math.hypot(dx, dy)

            clipped_segs: list[list[dict[str, float]]] = []
            wall_poly: list[list[float]] = []

            if l_norm >= 1e-5:
                ux, uy = dx / l_norm, dy / l_norm
                nx, ny = -uy, ux

                # Normalised thickness
                scale_info = page_scale_info.get(aw.page_id) if page_scale_info else None
                scale = float(scale_info.get("scale_ft_per_px", 0.0)) if scale_info else 0.0
                w_px = float(scale_info.get("width_px", 1)) if scale_info else 1.0
                thick_ft = (aw.thickness_in or 4.875) / 12.0

                if scale > 0 and w_px > 0:
                    thick_norm = (thick_ft / scale) / w_px
                else:
                    thick_norm = thick_ft / 138.0
                half_thick = max(0.001, min(0.02, thick_norm / 2.0))

                wall_poly = [
                    [round(x1 + nx * half_thick, 5), round(y1 + ny * half_thick, 5)],
                    [round(x2 + nx * half_thick, 5), round(y2 + ny * half_thick, 5)],
                    [round(x2 - nx * half_thick, 5), round(y2 - ny * half_thick, 5)],
                    [round(x1 - nx * half_thick, 5), round(y1 - ny * half_thick, 5)],
                ]

                if not aw.openings:
                    clipped_segs = [[p1, p2]]
                else:
                    # Clip around opening spans
                    raw_intervals: list[tuple[float, float]] = []
                    for op in aw.openings:
                        c_norm = getattr(op, "center_norm", None) or {}
                        cx = c_norm.get("x", (x1 + x2) / 2.0)
                        cy = c_norm.get("y", (y1 + y2) / 2.0)
                        t = ((cx - x1) * dx + (cy - y1) * dy) / (l_norm * l_norm)
                        half_w_t = ((op.width_ft / aw.length_ft) * 0.5) if aw.length_ft > 0 else 0.02
                        t0 = max(0.0, t - half_w_t)
                        t1 = min(1.0, t + half_w_t)
                        if t1 > t0:
                            raw_intervals.append((t0, t1))

                    if not raw_intervals:
                        clipped_segs = [[p1, p2]]
                    else:
                        raw_intervals.sort(key=lambda item: item[0])
                        merged: list[tuple[float, float]] = []
                        for s, e in raw_intervals:
                            if not merged:
                                merged.append((s, e))
                            else:
                                prev_s, prev_e = merged[-1]
                                if s <= prev_e:
                                    merged[-1] = (prev_s, max(prev_e, e))
                                else:
                                    merged.append((s, e))

                        # Subtract opening gaps from [0, 1]
                        cur_t = 0.0
                        for s, e in merged:
                            if s - cur_t > 0.01:
                                sa = {"x": round(x1 + cur_t * dx, 5), "y": round(y1 + cur_t * dy, 5)}
                                sb = {"x": round(x1 + s * dx, 5), "y": round(y1 + s * dy, 5)}
                                clipped_segs.append([sa, sb])
                            cur_t = max(cur_t, e)
                        if 1.0 - cur_t > 0.01:
                            sa = {"x": round(x1 + cur_t * dx, 5), "y": round(y1 + cur_t * dy, 5)}
                            sb = {"x": round(x2, 5), "y": round(y2, 5)}
                            clipped_segs.append([sa, sb])

                        if not clipped_segs:
                            clipped_segs = [[p1, p2]]
            else:
                clipped_segs = [[p1, p2]]

            aw.clipped_segments_norm = clipped_segs
            aw.wall_polygon_norm = wall_poly
            aw.gross_sf = gross
            aw.opening_deduction_sf = deduction
            aw.net_sf = net
            aw.height_provenance = height_prov

            enriched_walls.append(aw)

        return enriched_walls


    def _evaluate_architectural_wall(
        self,
        wall: Wall,
        room_graph: RoomGraph,
        graph: nx.Graph,
        wall_tags: list[dict[str, Any]],
        classifications: dict[int, Any] | None,
        default_tag: str | None = None,
        ref_sched_sheet: str | None = None,
    ) -> ArchitecturalWall:
        start_dict = wall.start_norm or {"x": 0.0, "y": 0.0}
        end_dict = wall.end_norm or {"x": 0.1, "y": 0.1}
        p1 = (start_dict.get("x", 0.0), start_dict.get("y", 0.0))
        p2 = (end_dict.get("x", 0.0), end_dict.get("y", 0.0))

        # Check explicit classification overrides
        override = classifications.get(wall.id) if classifications else None
        if override is not None and hasattr(override, "hangable") and not override.hangable:
            return ArchitecturalWall(
                id=f"drywall-wall-{wall.id}",
                page_id=wall.page_id or 0,
                start_norm=start_dict,
                end_norm=end_dict,
                length_ft=wall.length_ft,
                status="rejected",
                rejection_reason="manually_excluded",
                drywall_scope=DrywallScopeDecision.NOT_REQUIRED,
                decision_state=WallDecisionState.NON_WALL,
                qto_eligible=False,
                qto_block_reason="MANUALLY_EXCLUDED",
            )

        # 2. Vector Linework Aspect Check
        dx = abs(p2[0] - p1[0])
        dy = abs(p2[1] - p1[1])

        # 3. Sub-foot Noise / Witness Line Check
        if wall.length_ft < 1.0:
            return ArchitecturalWall(
                id=f"drywall-wall-{wall.id}",
                page_id=wall.page_id or 0,
                start_norm=start_dict,
                end_norm=end_dict,
                length_ft=wall.length_ft,
                status="rejected",
                rejection_reason="dimension_line",
                drywall_scope=DrywallScopeDecision.NOT_REQUIRED,
                decision_state=WallDecisionState.NON_WALL,
                qto_eligible=False,
                qto_block_reason="SUB_FOOT_DIMENSION_LINE",
                source_evidence={"sub_foot_fragment": True},
            )

        # 4. Topological Space Classification & Connectivity
        classification_str, room_ids, adj_rooms, class_reason = room_graph.classify_wall_topology(p1, p2)
        is_connected = graph.degree(wall.id) > 0 if wall.id in graph else False
        has_thickness_or_faces = bool(
            wall.thickness_measured
            or getattr(wall, "face_a_segment_id", None)
            or getattr(wall, "face_b_segment_id", None)
            or (getattr(wall, "thickness_ft", 0) or 0) > 0.15
        )

        # 5. Genuine Sheet Border / Title Block Rejection Check:
        # A line is ONLY a title block border if:
        # - It lies at the extreme outer perimeter of the page (within 0.8% margin), AND
        # - Has NO room boundary support, NO measured thickness/dual-faces, and NO connected wall graph junctions.
        is_sheet_border = (
            len(room_ids) == 0
            and not is_connected
            and not has_thickness_or_faces
            and (
                (p1[0] < 0.008 and p2[0] < 0.008)
                or (p1[0] > 0.992 and p2[0] > 0.992)
                or (p1[1] < 0.008 and p2[1] < 0.008)
                or (p1[1] > 0.992 and p2[1] > 0.992)
            )
        )
        if is_sheet_border:
            return ArchitecturalWall(
                id=f"drywall-wall-{wall.id}",
                page_id=wall.page_id or 0,
                start_norm=start_dict,
                end_norm=end_dict,
                length_ft=wall.length_ft,
                status="rejected",
                rejection_reason="sheet_border_or_title_block",
                drywall_scope=DrywallScopeDecision.NOT_REQUIRED,
                decision_state=WallDecisionState.NON_WALL,
                qto_eligible=False,
                qto_block_reason="TITLE_BLOCK_BORDER",
                source_evidence={"sheet_border": True},
            )

        # 5. Structural Grid Line & Site Boundary Rejection Check:
        # A line spanning across the page (> 25% width/height or > 35 ft) with ZERO room boundary support
        # is a structural grid axis line or site boundary, even if it intersects perpendicular grid lines outside.
        is_grid_span = (
            (dx > 0.25 or dy > 0.25 or wall.length_ft > 35.0)
            and len(room_ids) == 0
            and not (wall.thickness_measured and has_thickness_or_faces and len(adj_rooms) > 0)
        )
        if is_grid_span:
            return ArchitecturalWall(
                id=f"drywall-wall-{wall.id}",
                page_id=wall.page_id or 0,
                start_norm=start_dict,
                end_norm=end_dict,
                length_ft=wall.length_ft,
                status="rejected",
                rejection_reason="grid_line",
                drywall_scope=DrywallScopeDecision.NOT_REQUIRED,
                decision_state=WallDecisionState.NON_WALL,
                qto_eligible=False,
                qto_block_reason="STRUCTURAL_GRID_LINE",
                source_evidence={"spans_page_grid": True},
            )


        # 5b. Unpaired stroke with ZERO room boundary support (e.g. tree well diagonals, site lines, grids)
        if not has_thickness_or_faces and len(room_ids) == 0:
            return ArchitecturalWall(
                id=f"drywall-wall-{wall.id}",
                page_id=wall.page_id or 0,
                start_norm=start_dict,
                end_norm=end_dict,
                length_ft=wall.length_ft,
                status="rejected",
                rejection_reason="unpaired_stroke_no_room_boundary",
                drywall_scope=DrywallScopeDecision.NOT_REQUIRED,
                decision_state=WallDecisionState.NON_WALL,
                qto_eligible=False,
                qto_block_reason="NON_WALL_GEOMETRY",
                source_evidence={"isolated_unsupported_stroke": True},
            )


        # 6. Rejection of unconditioned outdoor railings
        if classification_str == "unconditioned_exterior":
            return ArchitecturalWall(
                id=f"drywall-wall-{wall.id}",
                page_id=wall.page_id or 0,
                start_norm=start_dict,
                end_norm=end_dict,
                length_ft=wall.length_ft,
                status="rejected",
                rejection_reason="insufficient_wall_support",
                drywall_scope=DrywallScopeDecision.NOT_REQUIRED,
                decision_state=WallDecisionState.NON_WALL,
                qto_eligible=False,
                qto_block_reason="UNCONDITIONED_RAILING",
                source_evidence={"unconditioned_space_railing": True},
            )

        # QTO-internal binary classification ONLY — drives sides-to-hang/area
        # math elsewhere in ArchitecturalWall. The richer, evidence-based
        # canonical_category (computed below, once tag/assembly evidence is
        # resolved) is what the API/frontend/assistant actually display —
        # see app.geometry.wall_classification and the field comments on
        # ArchitecturalWall in app/models/architectural_wall.py.
        wall_class = WallClassification.EXTERIOR if classification_str == "exterior" else WallClassification.INTERIOR

        # 7. Connectivity Check
        is_connected = graph.degree(wall.id) > 0 if wall.id in graph else False

        # 8. Physical Wall Thickness & Dual-Face Evidence Resolution
        if wall.thickness_measured and wall.thickness_ft:
            thick_in = round(wall.thickness_ft * 12.0, 2)
            thick_source = ThicknessSource.PAIRED_GEOMETRY
            if thick_in > 12.0:
                is_structural_wall = wall.length_ft >= 6.0
                return ArchitecturalWall(
                    id=f"drywall-wall-{wall.id}",
                    page_id=wall.page_id or 0,
                    start_norm=start_dict,
                    end_norm=end_dict,
                    length_ft=wall.length_ft,
                    thickness_in=thick_in,
                    thickness_source=thick_source,
                    thickness_confidence=0.90,
                    canonical_category="STRUCTURAL_BEARING" if is_structural_wall else "NEEDS_REVIEW",
                    canonical_confidence=0.85 if is_structural_wall else 0.40,
                    canonical_reasons=["massive_concrete_bearing_wall" if is_structural_wall else "non_partition_column_or_pilaster"],
                    canonical_method="measured_geometry_thickness",
                    status="rejected",
                    rejection_reason="non_partition_column_or_pilaster" if not is_structural_wall else "structural_bearing_concrete",
                    drywall_scope=DrywallScopeDecision.NOT_REQUIRED,
                    decision_state=WallDecisionState.NON_WALL,
                    qto_eligible=False,
                    qto_block_reason="STRUCTURAL_COLUMN_PILASTER" if not is_structural_wall else "STRUCTURAL_BEARING_WALL",
                )
        else:
            thick_in = 4.875
            thick_source = ThicknessSource.PROJECT_DEFAULT

        # 9. Wall Tag & Assembly Resolution (with Dynamic Project Vocabulary & Schedule Evidence)
        tag, assembly, tag_ev, sched_entry = self.tag_resolver.match_tag_to_wall(
            (p1, p2), wall_tags, default_tag=default_tag, wall_id=wall.id, page_id=wall.page_id or 1
        )
        assembly_resolved = assembly is not None
        assembly_verified = bool(sched_entry and sched_entry.get("verified", False))

        # ── Face provenance detection (must precede allow_default logic) ──────
        # These values gate whether defaults are permitted (has_duplicate_faces
        # blocks them) and drive the 5-state decision machine below.
        explicit_fa = getattr(wall, "face_a_segment_id", None)
        explicit_fb = getattr(wall, "face_b_segment_id", None)

        # has_independent_faces: both IDs present AND they differ.
        # has_duplicate_faces:   both IDs present AND they are THE SAME.
        #   A duplicate-face wall is worse than a single-face wall — a single
        #   stroke was recorded as both faces, so the measured thickness is
        #   meaningless.  Defaults are blocked and QTO is ineligible even when
        #   room support exists.
        has_independent_faces = (
            explicit_fa is not None
            and explicit_fb is not None
            and explicit_fa != explicit_fb
        )
        has_duplicate_faces = (
            explicit_fa is not None
            and explicit_fb is not None
            and explicit_fa == explicit_fb
        )

        face_a_supported = (explicit_fa is not None) or (wall.id is not None)
        face_b_supported = has_independent_faces

        # Phase 1 QTO-unblock: when allow_defaults is active (no verified schedule
        # found in the document) and no tagged spec was matched, synthesise a generic
        # default assembly from the wall's own wall_type so the QTO gate can open.
        # SUPPRESSED when ref_sched_sheet is set: a drawing that says "SEE SHEET A7.1"
        # but we couldn't find it must stay REFERENCED_SCHEDULE_MISSING — the architect
        # told us to look elsewhere; a generic default would mask that gap.
        # ALSO SUPPRESSED when face_a_segment_id == face_b_segment_id: a single stroke
        # recorded as both faces means thickness provenance is unreliable, so we cannot
        # trust any assembly derived from it.  The wall remains in the
        # PHYSICAL_WALL_CONFIRMED_SINGLE_SOURCE tier with assembly_resolved=False.
        allow_default_for_this_wall = (
            self._base_allow_defaults
            and not ref_sched_sheet
            and not has_duplicate_faces  # duplicate-face walls block defaults
        )
        if allow_default_for_this_wall and assembly is None:
            raw_wt = getattr(wall.wall_type, "value", str(wall.wall_type))
            is_ext = (wall_class == WallClassification.EXTERIOR) or (raw_wt in ("exterior", "EXTERIOR"))
            assembly = WallAssemblySpec(
                tag="DEFAULT",
                description=(
                    "Assumed: 3-5/8\" Metal Stud Partition, 5/8\" GWB Each Side (no schedule)"
                    if not is_ext else
                    "Assumed: Exterior Wall, 5/8\" GWB Interior Face Only (no schedule)"
                ),
                stud_depth_in=3.625,
                stud_gauge="25 GA",
                board_type_side_a="5/8\" GWB",
                layers_side_a=1,
                board_type_side_b="5/8\" GWB" if not is_ext else "None",
                layers_side_b=1 if not is_ext else 0,
                sides_to_hang=2 if not is_ext else 1,
                source="project_default_no_schedule",
            )
            # GAP-D FIX: assembly_resolved=True (we have an assembly object) but
            # assembly_verified MUST stay False for DEFAULT assemblies.
            # Previously the block below set assembly_verified=True for any
            # allow_default_for_this_wall wall, making DEFAULT assemblies
            # indistinguishable from schedule-verified ones in the 5-state machine.
            # Now:
            #   assembly_resolved=True  → an assembly spec exists (enables QTO)
            #   assembly_verified=False → it came from a hardcoded default, NOT a schedule
            # The 5-state machine will enter the "assembly_resolved but !assembly_verified"
            # branch, which produces qto_eligible=True at PROVISIONAL confidence (0.75/0.85)
            # rather than CONFIRMED confidence (0.95).  The QTO quantity is computed but
            # the evidence card and proof dict will show assembly_verified=False so the
            # API response can never represent this as a schedule-backed confirmed result.
            assembly_resolved = True
            # assembly_verified intentionally left False — set above as False
            tag = tag or "DEFAULT"

        # An assembly is only ever genuinely "verified" when it can be traced
        # to this project's own schedule (real schedule_evidence, checked
        # above via sched_entry). Two different kinds of assumed/fallback
        # assembly exist and neither is verified, regardless of its tag
        # string: the generic synthesized fallback (tag="DEFAULT",
        # source="project_default_no_schedule", built above) and a match
        # against DEFAULT_PARTITION_SPECS (wall_tags.py) — an
        # industry-standard stock library loaded only when no real schedule
        # was found at all, source="default_spec". A tag string like "NR-1"
        # or "W1" from that library looks identical to a real project tag,
        # so the tag alone cannot distinguish "matched something" from
        # "matched something backed by THIS project's schedule" — only
        # `assembly.source` can. Previously this checked `tag != "DEFAULT"`,
        # which correctly excluded the synthesized fallback but incorrectly
        # promoted every DEFAULT_PARTITION_SPECS match to assembly_verified,
        # since none of those tags are literally the string "DEFAULT".
        _ASSUMED_ASSEMBLY_SOURCES = {"project_default_no_schedule", "default_spec"}
        if assembly is not None and not assembly_verified and allow_default_for_this_wall:
            if getattr(assembly, "source", None) not in _ASSUMED_ASSEMBLY_SOURCES:
                # Traceable to something other than a hardcoded default/stock
                # library entry — treat as verified.
                assembly_verified = True
            # else: assumed/stock assembly — assembly_verified stays False (GAP-D fix,
            # extended to cover the DEFAULT_PARTITION_SPECS library case)

        sched_sheet = (
            sched_entry.get("schedule_sheet") if sched_entry else (
                ref_sched_sheet if ref_sched_sheet else None
            )
        )
        sched_region = sched_entry.get("source_region") if sched_entry else None

        # Canonical 9-category classification (evidence-based; see
        # app.geometry.wall_classification). Computed here, after tag/assembly
        # resolution, so it can use real tag/schedule text for DEMISING and
        # the real vector-reconstruction signal (wall.wall_type_code) for
        # STAIR_CORE/STRUCTURAL_BEARING/EXTERIOR_PERIMETER — but entirely
        # independent of the 5-state QTO decision gate that follows.
        canon = classify_wall_canonical(
            classification_str=classification_str,
            class_reason=class_reason,
            room_ids=room_ids,
            adjacent_room_ids=adj_rooms,
            room_graph=room_graph,
            wall_type_code=getattr(wall, "wall_type_code", None),
            wall_tag=tag,
            tag_description=getattr(assembly, "description", None) if assembly else None,
            source_sheet=sched_sheet,
        )

        # 10. Multi-Signal Legitimacy & 5-State Machine Decision Gate
        # Any assembly sourced from a hardcoded default (the synthesized
        # generic fallback OR a DEFAULT_PARTITION_SPECS library match) routes
        # to the same PROVISIONAL tier below, regardless of its tag string —
        # see the assembly_verified fix above for why the tag alone can't
        # tell a real project tag apart from a stock-library tag.
        is_assumed_assembly = assembly is not None and getattr(assembly, "source", None) in _ASSUMED_ASSEMBLY_SOURCES
        is_approved_entity = getattr(wall, "status", None) in (
            ReviewStatus.APPROVED, "approved", "APPROVED"
        )
        # Walls that arrived flagged NEEDS_REVIEW (e.g. D1 unnamed long strokes)
        # must not auto-qualify for QTO through the assumed-assembly single-source
        # path — inspector confirmation is required first.
        is_needs_review_input = getattr(wall, "status", None) in (
            ReviewStatus.NEEDS_REVIEW, "needs_review", "NEEDS_REVIEW"
        )

        # D-011: Single-Face Context Evidence Promotion Ladder
        from app.geometry.single_face_promotion import SingleFaceContextEvidence, evaluate_single_face_promotion

        # Check attached openings
        wall_openings_count = 0
        if hasattr(wall, "openings"):
            wall_openings_count = len(getattr(wall, "openings", []) or [])

        has_room_boundary_support = (
            len(room_ids) >= 2
            or getattr(wall, "bidirectional_verified", False)
            or (len(room_ids) == 1 and is_connected)
        )

        sf_evidence = SingleFaceContextEvidence(
            has_room_boundary=has_room_boundary_support,
            is_bidirectional_verified=getattr(wall, "bidirectional_verified", False),
            room_ids=room_ids,
            is_exterior_envelope=(wall_class == WallClassification.EXTERIOR),
            has_elevation_ref=bool(sched_sheet and ("A4" in sched_sheet or "S3" in sched_sheet or "SEC" in sched_sheet)),
            has_detail_callout_ref=bool(ref_sched_sheet),
            callout_tags=[ref_sched_sheet] if ref_sched_sheet else [],
            has_wall_tag=bool(tag),
            has_schedule_match=assembly_verified,
            assembly_verified=assembly_verified,
            wall_tag=tag,
            attached_openings_count=wall_openings_count,
            has_cross_sheet_evidence=(getattr(wall, "height_source", None) not in (None, "ASSUMED")),
            has_rcp_height_match=(getattr(wall, "height_source", None) not in (None, "ASSUMED")),
            referenced_schedule_sheet=ref_sched_sheet,
            is_connected_at_corners=is_connected,
            length_ft=wall.length_ft,
        )
        sf_promotion = evaluate_single_face_promotion(sf_evidence)

        has_support = (
            has_room_boundary_support
            or (wall_class == WallClassification.EXTERIOR and len(room_ids) > 0)
            or sf_promotion.is_promoted
        )
        is_architectural_scale = (
            (wall.length_ft >= 4.0 and is_connected)
            or has_room_boundary_support
            or (wall_class == WallClassification.EXTERIOR and len(room_ids) > 0)
            or has_independent_faces
        )

        if has_independent_faces:
            physical_state = WallDecisionState.PHYSICAL_WALL_CONFIRMED

            if assembly_resolved and assembly_verified:
                assembly_state = WallDecisionState.WALL_ASSEMBLY_CONFIRMED
                if assembly.sides_to_hang >= 1:
                    drywall_scope_state = WallDecisionState.DRYWALL_SCOPE_CONFIRMED
                    scope = DrywallScopeDecision.REQUIRED
                    status = "approved"
                    reason = None
                    conf = 0.95
                    qto_eligible = True
                    qto_block_reason = None
                else:  # e.g. Existing partition to remain (sides_to_hang == 0)
                    drywall_scope_state = WallDecisionState.WALL_ASSEMBLY_CONFIRMED
                    scope = DrywallScopeDecision.NOT_REQUIRED
                    status = "approved"
                    reason = "assembly_requires_zero_drywall_hang"
                    conf = 0.95
                    qto_eligible = False
                    qto_block_reason = "DRYWALL_NOT_REQUIRED_FOR_ASSEMBLY"
            elif assembly_resolved and not assembly_verified and is_assumed_assembly:
                # GAP-D FIX: assumed/default assembly (no schedule found, no "SEE SHEET" ref).
                # assembly_resolved=True (we have a spec) but assembly_verified=False
                # (it's an industry assumption, not a drawing-backed specification).
                # Isolated, sub-3ft fragments in open/unbounded space lacking room support
                # cannot clear the QTO gate without verified tag/schedule evidence.
                if not has_support and not is_architectural_scale:
                    assembly_state = WallDecisionState.WALL_CANDIDATE_NEEDS_REVIEW
                    drywall_scope_state = WallDecisionState.WALL_CANDIDATE_NEEDS_REVIEW
                    scope = DrywallScopeDecision.NEEDS_REVIEW
                    status = "needs_review"
                    reason = "unsupported_isolated_fragment"
                    conf = 0.40
                    qto_eligible = False
                    qto_block_reason = "AMBIGUOUS_UNBOUNDED_FRAGMENT"
                else:
                    assembly_state = WallDecisionState.PHYSICAL_WALL_CONFIRMED  # not assembly-confirmed
                    drywall_scope_state = WallDecisionState.PHYSICAL_WALL_CONFIRMED
                    scope = DrywallScopeDecision.REQUIRED
                    status = "approved"
                    reason = "assembly_assumed_default_no_schedule"
                    conf = 0.70  # PROVISIONAL tier — real geometry, assumed assembly
                    qto_eligible = True   # allows a provisional quantity to be computed
                    qto_block_reason = None
            else:
                # Schedule is referenced ("SEE SHEET A7.1") but the sheet is missing,
                # OR assembly completely absent with no default permitted.
                # Both cases: QTO is BLOCKED.
                assembly_state = WallDecisionState.PHYSICAL_WALL_CONFIRMED
                drywall_scope_state = WallDecisionState.PHYSICAL_WALL_CONFIRMED
                scope = DrywallScopeDecision.NEEDS_REVIEW
                status = "approved" if (has_support or is_connected) else "needs_review"
                reason = "referenced_schedule_missing" if ref_sched_sheet else "unresolved_wall_assembly"
                conf = 0.85 if has_support else 0.70
                qto_eligible = False
                qto_block_reason = "REFERENCED_SCHEDULE_MISSING" if ref_sched_sheet else "UNRESOLVED_WALL_ASSEMBLY"

        elif has_support:
            # Single-source physical evidence: a real room-boundary relationship
            # (not mere wall-graph connectivity) supports this wall, but only one
            # face was ever detected -- Face B has no independent stroke. Real
            # length + real room adjacency + (when present) a real
            # schedule-verified assembly is enough to compute an honestly
            # lower-confidence quantity, without pretending a second,
            # independently-detected face exists. See PHYSICAL_WALL_CONFIRMED
            # (Root Cause 1 forensic report) for why this is a distinct tier
            # rather than reusing the dual-face-confirmed state or fabricating
            # a Face B.
            physical_state = WallDecisionState.PHYSICAL_WALL_CONFIRMED_SINGLE_SOURCE

            if assembly_resolved and assembly_verified:
                assembly_state = WallDecisionState.WALL_ASSEMBLY_CONFIRMED
                if assembly.sides_to_hang >= 1:
                    drywall_scope_state = WallDecisionState.DRYWALL_SCOPE_CONFIRMED
                    scope = DrywallScopeDecision.REQUIRED
                    status = "approved"
                    reason = None
                    # Deliberately below the dual-stroke path's 0.95: real
                    # evidence, but one independently-detected face short of it.
                    conf = 0.85 if (is_approved_entity or sf_promotion.is_promoted) else 0.75
                    qto_eligible = True
                    qto_block_reason = None
                else:  # e.g. existing partition to remain -> 0 new board hang
                    drywall_scope_state = WallDecisionState.WALL_ASSEMBLY_CONFIRMED
                    scope = DrywallScopeDecision.NOT_REQUIRED
                    status = "approved"
                    reason = "assembly_requires_zero_drywall_hang"
                    conf = 0.75
                    qto_eligible = False
                    qto_block_reason = "DRYWALL_NOT_REQUIRED_FOR_ASSEMBLY"
            elif assembly_resolved and not assembly_verified and is_assumed_assembly:
                # GAP-D FIX (single-source path): same PROVISIONAL tier as dual-face path.
                if not is_architectural_scale and not sf_promotion.is_promoted:
                    assembly_state = WallDecisionState.WALL_CANDIDATE_NEEDS_REVIEW
                    drywall_scope_state = WallDecisionState.WALL_CANDIDATE_NEEDS_REVIEW
                    scope = DrywallScopeDecision.NEEDS_REVIEW
                    status = "needs_review"
                    reason = "unsupported_isolated_fragment"
                    conf = 0.40
                    qto_eligible = False
                    qto_block_reason = "AMBIGUOUS_UNBOUNDED_FRAGMENT"
                else:
                    assembly_state = WallDecisionState.PHYSICAL_WALL_CONFIRMED_SINGLE_SOURCE
                    drywall_scope_state = WallDecisionState.PHYSICAL_WALL_CONFIRMED_SINGLE_SOURCE
                    scope = DrywallScopeDecision.REQUIRED
                    status = "approved"
                    reason = "assembly_assumed_default_no_schedule" if not sf_promotion.is_promoted else None
                    conf = max(0.60, sf_promotion.recommended_confidence) if sf_promotion.is_promoted else 0.60
                    if not is_approved_entity and not sf_promotion.is_promoted:
                        # DEF-04: only APPROVED walls may auto-qualify for QTO in the
                        # assumed-assembly path. PENDING and NEEDS_REVIEW both require
                        # explicit inspector approval before any QTO eligibility.
                        qto_eligible = False
                        qto_block_reason = (
                            "NEEDS_REVIEW_WALL_NO_QTO_WITHOUT_APPROVAL"
                            if is_needs_review_input
                            else "PENDING_WALL_NO_QTO_WITHOUT_APPROVAL"
                        )
                        if is_needs_review_input:
                            status = "needs_review"
                            scope = DrywallScopeDecision.NEEDS_REVIEW
                        conf = min(conf, 0.55)
                    else:
                        qto_eligible = True
                        qto_block_reason = None
            else:
                # Schedule is missing or assembly is unverified -- same honest
                # unresolved treatment as the dual-face path gets in this case.
                assembly_state = WallDecisionState.PHYSICAL_WALL_CONFIRMED_SINGLE_SOURCE
                drywall_scope_state = WallDecisionState.PHYSICAL_WALL_CONFIRMED_SINGLE_SOURCE
                scope = DrywallScopeDecision.NEEDS_REVIEW
                status = "needs_review"
                reason = "referenced_schedule_missing" if ref_sched_sheet else "unresolved_wall_assembly"
                conf = 0.60
                qto_eligible = False
                qto_block_reason = "REFERENCED_SCHEDULE_MISSING" if ref_sched_sheet else "UNRESOLVED_WALL_ASSEMBLY"

        elif is_connected:
            # Wall-graph connectivity alone -- deliberately NOT promoted. This
            # is weaker evidence than a real room-boundary relationship (two
            # candidate segments merely touch), so it stays exactly as before:
            # needs review, not QTO-eligible, regardless of assembly state.
            physical_state = WallDecisionState.WALL_CANDIDATE_NEEDS_REVIEW
            assembly_state = WallDecisionState.WALL_CANDIDATE_NEEDS_REVIEW
            drywall_scope_state = WallDecisionState.WALL_CANDIDATE_NEEDS_REVIEW
            scope = DrywallScopeDecision.NEEDS_REVIEW
            status = "needs_review"
            reason = "unsupported_face_b_geometry"
            conf = 0.50
            qto_eligible = False
            qto_block_reason = "UNSUPPORTED_FACE_B_GEOMETRY"

        else:
            # Rejected candidate / noise
            physical_state = WallDecisionState.NON_WALL
            assembly_state = WallDecisionState.NON_WALL
            drywall_scope_state = WallDecisionState.NON_WALL
            scope = DrywallScopeDecision.NOT_REQUIRED
            status = "rejected"
            reason = "insufficient_wall_support"
            conf = 0.25
            qto_eligible = False
            qto_block_reason = "NON_WALL_GEOMETRY"

        schedule_conflict_sources: list[dict[str, Any]] | None = None
        if sched_entry and sched_entry.get("conflicted") and status != "rejected":
            # This wall's tag resolved to a schedule entry that is itself
            # defined differently on two different sheets — never silently
            # pick one (see ScheduleTableParser._merge_with_conflict_detection).
            # Downgrades whatever the 5-state machine above decided, the same
            # way a detail-callout conflict downgrades an already-decided
            # wall in _resolve_detail_reference_for_wall.
            schedule_conflict_sources = sched_entry.get("conflict_sources") or []
            status = "needs_review"
            reason = "MULTIPLE_SCHEDULE_DEFINITIONS"
            qto_eligible = False
            qto_block_reason = "MULTIPLE_SCHEDULE_DEFINITIONS"

        overlap_r = getattr(wall, "overlap_ratio", None) or 1.0
        fa_coords = getattr(wall, "face_a_coords", None) or {"x1": p1[0], "y1": p1[1], "x2": p2[0], "y2": p2[1]}
        fb_coords = getattr(wall, "face_b_coords", None) or ({"x1": p1[0], "y1": p1[1], "x2": p2[0], "y2": p2[1]} if has_independent_faces else None)

        face_a = WallFace(
            segment_ids=[explicit_fa] if explicit_fa is not None else ([wall.id] if wall.id is not None else []),
            start_norm={"x": fa_coords.get("x1", p1[0]), "y": fa_coords.get("y1", p1[1])},
            end_norm={"x": fa_coords.get("x2", p2[0]), "y": fa_coords.get("y2", p2[1])},
            length_ft=wall.length_ft,
            is_finished_gwb=True,
        )
        face_b = WallFace(
            segment_ids=[explicit_fb] if explicit_fb is not None else [],
            start_norm={"x": fb_coords.get("x1", p1[0]), "y": fb_coords.get("y1", p1[1])} if fb_coords else start_dict,
            end_norm={"x": fb_coords.get("x2", p2[0]), "y": fb_coords.get("y2", p2[1])} if fb_coords else end_dict,
            length_ft=wall.length_ft if has_independent_faces else 0.0,
            is_finished_gwb=face_b_supported,
        )
        w_geom = WallGeometry(
            face_a=face_a,
            face_b=face_b,
            centerline_start=start_dict,
            centerline_end=end_dict,
            thickness_in=thick_in,
            overlap_ratio=overlap_r,
            length_ft=wall.length_ft,
        )
        ev_score = WallEvidenceScore(parallel_faces=0.25 if face_b_supported else 0.0, physical_stroke_align=0.20, total_confidence=conf)

        # Check if wall is Glazed Storefront / Curtain Wall
        is_glazing = (
            wall_class == WallClassification.CURTAIN_WALL
            or (hasattr(wall, "wall_type") and str(wall.wall_type).lower() in ("curtain_wall", "storefront", "glazing"))
            or (tag is not None and any(g in tag.upper() for g in ("CW", "GL", "SF", "STOREFRONT", "GLASS")))
        )

        # Explicit Physical Wall Classification and Face Specification
        if is_glazing:
            phys_type = PhysicalWallType.STOREFRONT_GLAZING
            scope = DrywallScopeDecision.NOT_REQUIRED
            qto_eligible = False
            qto_block_reason = "GLAZED_STOREFRONT_NO_DRYWALL_SCOPE"
            face_spec = DrywallFaceSpecification(
                side_a_required=False,
                side_b_required=False,
                layers_side_a=0,
                layers_side_b=0,
                specification_source="STOREFRONT_GLAZING",
                is_resolved=True,
            )
        elif wall_class == WallClassification.EXTERIOR or (hasattr(wall, "wall_type") and wall.wall_type == WallType.EXTERIOR):
            phys_type = PhysicalWallType.EXTERIOR_WALL
            face_spec = DrywallFaceSpecification(
                side_a_required=True,
                side_b_required=False,
                layers_side_a=1,
                layers_side_b=0,
                specification_source="BUILDING_ENVELOPE_INTERIOR_FACE",
                is_resolved=True,
            )
        elif assembly_resolved and assembly:
            phys_type = PhysicalWallType.DRYWALL_PARTITION
            face_spec = DrywallFaceSpecification(
                side_a_required=(assembly.layers_side_a > 0),
                side_b_required=(assembly.layers_side_b > 0),
                layers_side_a=assembly.layers_side_a,
                layers_side_b=assembly.layers_side_b,
                board_type_side_a=assembly.board_type_side_a,
                board_type_side_b=assembly.board_type_side_b,
                specification_source="PARTITION_SCHEDULE",
                is_resolved=True,
            )
        elif status == "approved":
            phys_type = PhysicalWallType.DRYWALL_PARTITION
            face_spec = DrywallFaceSpecification(
                side_a_required=True,
                side_b_required=True,
                layers_side_a=1,
                layers_side_b=1,
                specification_source="DEFAULT_INTERIOR_PARTITION",
                is_resolved=True,
            )
        else:
            phys_type = PhysicalWallType.UNKNOWN_WALL
            face_spec = DrywallFaceSpecification(
                side_a_required=False,
                side_b_required=False,
                layers_side_a=0,
                layers_side_b=0,
                specification_source="UNRESOLVED_UNKNOWN",
                is_resolved=False,
            )

        # Acceptance #2: height confidence — 0.0 when the height is assumed/defaulted,
        # 0.7-0.97 when it came from an actual drawing source.  height_evidence holds
        # the exact text token so consumers can display it without decoding a flag.
        _raw_h_src = getattr(wall, "height_source", None) or "ASSUMED"
        _height_is_assumed = _raw_h_src in ("ASSUMED", "assumed_default", "project_default") or not wall.height_ft
        _height_conf: float = 0.0 if _height_is_assumed else 0.85
        _height_ev: str | None = None if _height_is_assumed else (
            getattr(wall, "height_evidence_text", None)
            or f"height_ft={wall.height_ft} source={_raw_h_src}"
        )

        standards_val = DrywallStandardsEngine.validate_assembly(
            assembly=assembly,
            physical_thickness_in=thick_in,
            height_ft=wall.height_ft or 9.0,
            physical_wall_type=phys_type,
        )

        arch_wall = ArchitecturalWall(
            id=f"drywall-wall-{wall.id}",
            page_id=wall.page_id or 0,
            start_norm=start_dict,
            end_norm=end_dict,
            length_ft=wall.length_ft,
            thickness_in=thick_in,
            thickness_source=thick_source,
            height_ft=wall.height_ft or 9.0,
            height_source=HeightSource.PROJECT_DEFAULT if _height_is_assumed else HeightSource.ROOM_CEILING_SPEC,
            height_confidence=_height_conf,
            height_evidence=_height_ev,
            physical_wall_type=phys_type,

            classification=wall_class,
            classification_reason=class_reason,
            is_building_envelope=(wall_class == WallClassification.EXTERIOR),
            face_specification=face_spec,
            canonical_category=canon.category,
            canonical_confidence=canon.confidence,
            canonical_reasons=canon.reasons,
            canonical_source_sheet=canon.source_sheet,
            canonical_method=canon.method,
            room_ids=room_ids,
            adjacent_room_ids=adj_rooms,
            source_segment_ids=[wall.id] if wall.id is not None else [],
            constituent_wall_ids=[f"drywall-wall-{wall.id}"],
            wall_tag=tag,
            tag_evidence=tag_ev,
            assembly=assembly,
            assembly_resolved=assembly_resolved,
            assembly_verified=assembly_verified,
            schedule_sheet=sched_sheet,
            schedule_source_region=sched_region,
            drywall_scope=scope,
            decision_state=physical_state,
            wall_geometry=w_geom,
            evidence_score=ev_score,
            confidence=conf,
            status=status,
            rejection_reason=reason,
            qto_eligible=qto_eligible,
            qto_block_reason=qto_block_reason,
            source_evidence={
                "physical_wall_detected": (physical_state != WallDecisionState.NON_WALL),
                "drywall_scope": scope.value if hasattr(scope, "value") else str(scope),
                "qto_eligible": qto_eligible,
                "qto_block_reason": qto_block_reason,
                "face_a_supported": face_a_supported,
                "face_b_supported": face_b_supported,
                "room_boundary_support": len(room_ids) > 0,
                "connected_wall_graph": is_connected,
                "building_envelope": (wall_class == WallClassification.EXTERIOR),
                "thickness_in": thick_in,
                "thickness_source": thick_source.value,
                "classification_reason": class_reason,
                "wall_tag": tag,
                "assembly_resolved": assembly_resolved,
                "assembly_verified": assembly_verified,
                "schedule_reference": sched_sheet,

                # Height transparency: always flag the source so UI/reports
                # never silently present an assumed height as a measured one.
                "height_ft": wall.height_ft or 9.0,
                "height_source": getattr(wall, "height_source", None) or "ASSUMED",
                # DEF-10: derive from height_source rather than always hardcoding True.
                "assumed_height": (getattr(wall, "height_source", None) or "ASSUMED") in (
                    "ASSUMED", "assumed_default", "project_default"
                ),
                "single_face_promoted": sf_promotion.is_promoted,
                "single_face_promotion_score": sf_promotion.context_score,
                "single_face_matched_signals": sf_promotion.matched_signals,
                "standards_validation": {
                    "is_buildable": standards_val.is_buildable,
                    "is_compliant": standards_val.is_compliant,
                    "issues": standards_val.issues,
                    "warnings": standards_val.warnings,
                    "recommended_stud_gauge": standards_val.recommended_stud_gauge,
                    "recommended_fastener_rate": getattr(standards_val, "recommended_fastener_rate", 1.5),
                    "recommended_mud_gal_per_sf": getattr(standards_val, "recommended_mud_gal_per_sf", 0.053),
                    "recommended_tape_lf_per_sf": getattr(standards_val, "recommended_tape_lf_per_sf", 0.37),
                    "recommended_stud_spacing_in": getattr(standards_val, "recommended_stud_spacing_in", 16.0),
                },

                **({"schedule_conflict_sources": schedule_conflict_sources, "schedule_conflict_reason": "MULTIPLE_SCHEDULE_DEFINITIONS"} if schedule_conflict_sources else {}),
            },
        )

        # D-013: Generate Forensic Wall Proof Card (geometry + physics + topology + doc + trade + cross-sheet)
        from app.geometry.trade_context_engine import TradeContextEngine
        tce = TradeContextEngine(default_height_ft=wall.height_ft or 9.0, default_thickness_in=thick_in)
        card = tce.build_wall_proof_card(
            wall=arch_wall,
            sheet_code=sched_sheet or f"Sheet-{wall.page_id or 1}",
            discipline="architectural",
            level="Level 1",
            scale_source=getattr(wall, "scale_source", "verified") or "verified",
        )
        arch_wall.proof_card = card.to_dict()
        return arch_wall

    # ------------------------------------------------------------------
    # Detail/Section Callout Resolution
    # ------------------------------------------------------------------

    def _resolve_detail_references(
        self,
        arch_walls: list[ArchitecturalWall],
        text_items_by_page: dict[int, list[tuple[float, float, float, float, str]]],
        detail_sheets: dict[str, DetailSheetEntry],
    ) -> list[ArchitecturalWall]:
        """For each wall, finds the nearest detail callout (if any) on its
        own page and resolves it against `detail_sheets` — pulling real
        engineering values (height, thickness, stud, GWB, layers, fire/
        acoustic rating, insulation) out of the referenced sheet's own text,
        each with its own field-level provenance. A wall with no callout
        nearby is returned unchanged — most walls won't have one.

        When a resolved detail's extracted value genuinely contradicts an
        already schedule-verified assembly value, this never silently picks
        one: it records both under source_evidence["conflicts"] and
        downgrades the wall to needs_review — the only way this step makes
        an already-decided wall *less* eligible than before.
        """
        callouts_by_page: dict[int, list[dict[str, Any]]] = {}
        for pid, items in text_items_by_page.items():
            try:
                callouts_by_page[pid] = extract_detail_callouts_from_text(items)
            except Exception:
                # A single malformed callout token on one page must never
                # take down cross-sheet reconciliation / canonical takeoff
                # generation for the whole document — that page simply gets
                # no detail-callout evidence, and processing continues.
                logger.exception(
                    "detail callout extraction failed for page_id=%s; "
                    "continuing without callout evidence for this page", pid,
                )
                callouts_by_page[pid] = []

        result: list[ArchitecturalWall] = []
        for aw in arch_walls:
            try:
                result.append(self._resolve_detail_reference_for_wall(aw, callouts_by_page, detail_sheets))
            except Exception:
                # A single wall with malformed callout/detail-sheet data must
                # never take down resolution for every other wall on the
                # project — this wall simply keeps whatever it already had.
                logger.exception(
                    "detail reference resolution failed for wall_id=%s; "
                    "keeping wall unchanged", getattr(aw, "id", None),
                )
                result.append(aw)

        return result

    def _resolve_detail_reference_for_wall(
        self,
        aw: ArchitecturalWall,
        callouts_by_page: dict[int, list[dict[str, Any]]],
        detail_sheets: dict[str, DetailSheetEntry],
    ) -> ArchitecturalWall:
        callouts = callouts_by_page.get(aw.page_id) or []
        if not callouts or not aw.start_norm or not aw.end_norm:
            return aw

        wall_seg = (
            (aw.start_norm["x"], aw.start_norm["y"]),
            (aw.end_norm["x"], aw.end_norm["y"]),
        )
        nearest = find_nearest_callout(wall_seg, callouts)
        if nearest is None:
            return aw

        new_evidence = dict(aw.source_evidence)
        new_evidence["detail_reference"] = nearest["callout"]

        entry = detail_sheets.get(nearest["sheet_ref_normalized"])
        if entry is None:
            # The wall points at a sheet ("3/A401") that doesn't exist in
            # this drawing set — honest uncertainty, not a fake assumption.
            new_evidence["detail_reference_status"] = "REFERENCE_UNRESOLVED"
            return dataclass_replace(aw, source_evidence=new_evidence)

        detail_source_label = f"{entry.sheet_number}/Detail {nearest['detail_num']}"
        field_provenance: dict[str, dict[str, Any]] = dict(new_evidence.get("field_provenance", {}))
        conflicts: list[dict[str, Any]] = list(new_evidence.get("conflicts", []))

        height = resolve_height_from_sheet_text(entry.text_content_full)
        engineering_info = extract_engineering_info_from_detail_text(entry.text_content_full)

        new_height_ft, new_height_source = aw.height_ft, aw.height_source
        if height is not None:
            field_provenance["height"] = {
                "value": height, "source_sheet": entry.sheet_number,
                "source_detail": nearest["detail_num"], "method": "detail_text", "confidence": 0.90,
            }
            # Same narrow guard as before: never override a height that
            # already came from something more specific than the project
            # default (a wall-specific detail beats a generic fallback,
            # but never overwrites another already-specific source).
            if aw.height_source == HeightSource.PROJECT_DEFAULT:
                new_height_ft = height
                new_height_source = HeightSource.SECTION_DETAIL
                new_evidence["height_source"] = f"section_detail:{entry.sheet_number}"
                new_evidence["height_ft"] = height
                new_evidence["assumed_height"] = False

        for field_key, info in engineering_info.items():
            field_provenance[field_key] = {
                "value": info["value"], "source_sheet": entry.sheet_number,
                "source_detail": nearest["detail_num"], "method": "detail_text",
                "confidence": info["confidence"],
            }

        # Thickness override — same narrow guard as height: only replace
        # a still-PROJECT_DEFAULT thickness, never a measured or
        # schedule-verified one.
        new_thickness_in, new_thickness_source = aw.thickness_in, aw.thickness_source
        detail_thickness = engineering_info.get("thickness_in", {}).get("value")
        if detail_thickness is not None and aw.thickness_source == ThicknessSource.PROJECT_DEFAULT:
            new_thickness_in = detail_thickness
            new_thickness_source = ThicknessSource.DRAWING_CALLOUT

        # Conflict detection: a schedule-verified assembly disagreeing
        # with the detail sheet's own stated dimensions. Both real,
        # both explicit — never silently pick one.
        if aw.assembly is not None and aw.assembly_verified:
            schedule_source_label = f"{aw.schedule_sheet or 'schedule'}/{aw.wall_tag or aw.assembly.tag}"
            schedule_total_thickness = round(
                aw.assembly.stud_depth_in + (aw.assembly.layers_side_a + aw.assembly.layers_side_b) * 0.625, 3
            )
            if detail_thickness is not None and abs(detail_thickness - schedule_total_thickness) > 1.5:
                conflicts.append({
                    "field": "thickness_in",
                    "sources": [
                        {"value": schedule_total_thickness, "source": schedule_source_label, "method": "partition_schedule"},
                        {"value": detail_thickness, "source": detail_source_label, "method": "detail_text"},
                    ],
                    "status": "CONFLICT",
                })
            detail_stud_depth = engineering_info.get("stud_depth_in", {}).get("value")
            if detail_stud_depth is not None and abs(detail_stud_depth - aw.assembly.stud_depth_in) > 1.5:
                conflicts.append({
                    "field": "stud_depth_in",
                    "sources": [
                        {"value": aw.assembly.stud_depth_in, "source": schedule_source_label, "method": "partition_schedule"},
                        {"value": detail_stud_depth, "source": detail_source_label, "method": "detail_text"},
                    ],
                    "status": "CONFLICT",
                })

        new_evidence["field_provenance"] = field_provenance
        if engineering_info:
            new_evidence["detail_engineering_info"] = {k: v["value"] for k, v in engineering_info.items()}

        new_status, new_qto_eligible, new_qto_block_reason = aw.status, aw.qto_eligible, aw.qto_block_reason
        if conflicts:
            new_evidence["conflicts"] = conflicts
            new_evidence["detail_reference_status"] = "CONFLICT"
            new_status = "needs_review"
            new_qto_eligible = False
            new_qto_block_reason = "ASSEMBLY_SOURCE_CONFLICT"
        elif height is not None:
            new_evidence["detail_reference_status"] = "RESOLVED_WITH_HEIGHT"
        else:
            # Sheet is real and resolved, but no specific dimension could
            # be confidently extracted from its text — say so honestly
            # rather than silently keeping the old values unlabeled.
            new_evidence["detail_reference_status"] = "RESOLVED_NO_HEIGHT_DATA"

        return dataclass_replace(
            aw,
            height_ft=new_height_ft,
            height_source=new_height_source,
            thickness_in=new_thickness_in,
            thickness_source=new_thickness_source,
            source_evidence=new_evidence,
            status=new_status,
            qto_eligible=new_qto_eligible,
            qto_block_reason=new_qto_block_reason,
        )

    # ------------------------------------------------------------------
    # Phase 2: Spatial Opening Deduction Engine
    # ------------------------------------------------------------------

    def _apply_opening_deductions(
        self,
        arch_walls: list[ArchitecturalWall],
        detections: list[Detection],
        page_scale_info: dict[int, dict[str, float]],
    ) -> list[ArchitecturalWall]:
        """Spatially associate each approved door/window detection with its
        nearest host wall and accumulate the opening area deduction.

        Algorithm:
        1. For each detection, derive opening_width_ft from bbox_norm using
           page scale.  On a floor plan the *larger* normalized bbox dimension
           is the opening span; the smaller is the symbol depth (≈ wall
           thickness) and carries no height information.
        2. For height, use the host wall's height_ft (already stored in DB
           as 8.0 ft for this project).  We never blindly assume 8 ft here —
           we read what the wall actually says.
        3. Match the detection to the approved wall whose centreline is
           closest (in normalised page coordinates, same page_id).  Search
           is O(D×W) which is fine for ≤300 detections and ≤200 walls.
        4. Accumulate opening_area_sqft on the matched wall (deduplicated:
           a detection already counted by gap-bridging is skipped when the
           detection centre sits inside an existing WallOpening bbox).
        5. Rebuild calculate_net_hang_area() implicitly — the existing
           ArchitecturalWall.calculate_net_hang_area() already reads
           self.opening_area_sqft, so we only need to update that field.
        """
        # Index walls that can receive deductions (approved + needs_review with assembly)
        deductible = [
            w for w in arch_walls
            if w.status in ("approved", "needs_review") and w.assembly is not None
        ]
        if not deductible:
            return arch_walls

        # Build a quick lookup: wall centre (norm) by wall object
        def _wall_centre(aw: ArchitecturalWall) -> tuple[float, float]:
            cx = (aw.start_norm["x"] + aw.end_norm["x"]) / 2.0
            cy = (aw.start_norm["y"] + aw.end_norm["y"]) / 2.0
            return cx, cy

        # Span margin, in the raw (unclamped) projection parameter t along a
        # wall's own centerline: 0.0 = exactly at an endpoint, negative/>1 =
        # beyond it. 0.08 of a wall's own length gives a little slack for an
        # opening sitting right at a corner without treating "clearly past
        # this wall's end" as still belonging to it.
        SPAN_MARGIN_T = 0.08

        def _point_to_segment_dist_and_span(
            px: float, py: float,
            x1: float, y1: float,
            x2: float, y2: float,
        ) -> tuple[float, bool]:
            """Perpendicular distance, plus whether the point's projection
            falls within this wall's own span (not just near its infinite
            extension). Nearest-perpendicular-distance alone can pick the
            wrong host at a corner or T-intersection: a door near the end of
            wall A can sit closer to wall B's infinite centerline than to
            A's own, even though it visually belongs to A. Preferring an
            in-span match over a merely-nearer out-of-span one resolves that
            without discarding the distance fallback for the genuine edge
            case where no wall's span actually contains the opening (e.g. a
            very short wall stub).
            """
            dx, dy = x2 - x1, y2 - y1
            l2 = dx * dx + dy * dy
            if l2 == 0.0:
                return math.hypot(px - x1, py - y1), True
            t_raw = ((px - x1) * dx + (py - y1) * dy) / l2
            in_span = -SPAN_MARGIN_T <= t_raw <= 1.0 + SPAN_MARGIN_T
            t = max(0.0, min(1.0, t_raw))
            dist = math.hypot(px - (x1 + t * dx), py - (y1 + t * dy))
            return dist, in_span

        # Maximum association radius in normalised units (~4 ft at this scale).
        # scale: 0.017217 ft/px, page width 8013 px → 1 norm unit = 137.9 ft
        # 4 ft / 137.9 ≈ 0.029 norm units.  Use 0.04 to be safe.
        MAX_ASSOC_DIST_NORM = 0.04

        # Accumulate opening areas per wall id
        extra_opening_area: dict[str, float] = {}   # arch_wall.id → additional sqft
        extra_openings: dict[str, list[WallOpening]] = {}  # arch_wall.id → WallOpening list

        kinds_of_interest = {DetectionKind.DOOR, DetectionKind.WINDOW}

        for det in detections:
            # Only approved doors and windows
            det_kind = getattr(det, "kind", None)
            det_status = getattr(det, "status", None)
            status_val = det_status.value if hasattr(det_status, "value") else str(det_status)
            kind_val = det_kind.value if hasattr(det_kind, "value") else str(det_kind)
            if status_val.upper() != "APPROVED":
                continue
            if kind_val.upper() not in ("DOOR", "WINDOW"):
                continue

            det_page_id = getattr(det, "page_id", None)
            bbox = getattr(det, "bbox_norm", None)
            if not bbox:
                continue

            # Parse bbox_norm: stored as {minX, minY, maxX, maxY}
            if isinstance(bbox, dict):
                min_x = float(bbox.get("minX", bbox.get("x", 0.0)))
                min_y = float(bbox.get("minY", bbox.get("y", 0.0)))
                max_x = float(bbox.get("maxX", min_x + bbox.get("width", 0.0)))
                max_y = float(bbox.get("maxY", min_y + bbox.get("height", 0.0)))
            else:
                continue

            cx_norm = (min_x + max_x) / 2.0
            cy_norm = (min_y + max_y) / 2.0
            w_norm = abs(max_x - min_x)
            h_norm = abs(max_y - min_y)

            # Derive opening width in feet from the bbox's larger dimension
            # (on a floor plan the opening span is the horizontal/larger axis).
            scale_info = page_scale_info.get(det_page_id or 0) if page_scale_info else None
            if scale_info:
                scale = float(scale_info.get("scale_ft_per_px", 0.0))
                w_px = float(scale_info.get("width_px", 1))
                h_px = float(scale_info.get("height_px", 1))
                opening_w_ft = max(w_norm * w_px * scale, h_norm * h_px * scale)
                opening_w_ft = round(opening_w_ft, 2)
            else:
                # Fallback: assume 3 ft door / 4 ft window
                opening_w_ft = 3.0 if kind_val.upper() == "DOOR" else 4.0

            # Clamp to plausible range: 1.5 ft (narrow cased opening) to 12 ft (large storefront)
            opening_w_ft = max(1.5, min(12.0, opening_w_ft))

            # Find the host wall on the same page: prefer the nearest wall
            # whose own span actually contains the opening's projection over
            # one that is merely closer by perpendicular distance to its
            # infinite centerline — see _point_to_segment_dist_and_span for
            # why (corner/T-intersection misattribution).
            best_wall: ArchitecturalWall | None = None
            best_dist = float("inf")
            best_in_span_wall: ArchitecturalWall | None = None
            best_in_span_dist = float("inf")
            for aw in deductible:
                if aw.page_id != (det_page_id or 0):
                    continue
                dist, in_span = _point_to_segment_dist_and_span(
                    cx_norm, cy_norm,
                    aw.start_norm["x"], aw.start_norm["y"],
                    aw.end_norm["x"], aw.end_norm["y"],
                )
                if dist < best_dist:
                    best_dist = dist
                    best_wall = aw
                if in_span and dist < best_in_span_dist:
                    best_in_span_dist = dist
                    best_in_span_wall = aw

            if best_in_span_wall is not None and best_in_span_dist <= MAX_ASSOC_DIST_NORM:
                best_wall, best_dist = best_in_span_wall, best_in_span_dist
            elif best_wall is None or best_dist > MAX_ASSOC_DIST_NORM:
                continue

            # Skip if this detection is already covered by a gap-bridging opening
            already_covered = False
            for existing_op in best_wall.openings:
                op_cx = existing_op.center_norm.get("x", 0.0)
                op_cy = existing_op.center_norm.get("y", 0.0)
                if math.hypot(cx_norm - op_cx, cy_norm - op_cy) < 0.015:
                    already_covered = True
                    break
            if already_covered:
                continue

            # Derive standard rough opening height:
            # - Standard interior/exterior doors: 7.0 ft (84 in) rough opening height
            # - Windows: 4.0 ft (48 in) standard window rough height
            # - Full-height/cased openings: wall height
            # GAP-6 fix: Never use the full wall height as the opening height.
            # A 3×7 door in an 8 ft wall should deduct 21 sqft per face, not 24 sqft.
            # Standard rough openings are independent of wall height.
            if kind_val.upper() == "DOOR":
                opening_h_ft = 7.0  # Standard 6'-8" + 4" frame = 7'-0" R.O.
            elif kind_val.upper() == "WINDOW":
                opening_h_ft = 4.0  # Standard 3'-4" + 8" frame = 4'-0" R.O.
            else:
                opening_h_ft = min(best_wall.height_ft or 9.0, 7.0)
            # Clamp: never exceed the actual wall height
            opening_h_ft = min(opening_h_ft, best_wall.height_ft or 9.0)
            sides = best_wall.assembly.sides_to_hang if best_wall.assembly else 2
            # Area is per face-side: width × height (the deduction applies per side
            # and calculate_net_hang_area multiplies opening_area_sqft by sides_to_hang)
            op_area = round(opening_w_ft * opening_h_ft, 2)

            extra_opening_area[best_wall.id] = (
                extra_opening_area.get(best_wall.id, 0.0) + op_area
            )
            extra_openings.setdefault(best_wall.id, []).append(
                WallOpening(
                    id=f"det-{det.id}",
                    opening_type=kind_val.lower(),
                    width_ft=opening_w_ft,
                    height_ft=opening_h_ft,
                    area_sqft=op_area,
                    center_norm={"x": cx_norm, "y": cy_norm},
                    dimension_source="bbox_norm_page_scale",
                    confidence=float(getattr(det, "confidence", 0.85)),
                )
            )

        # Rebuild walls with accumulated deductions
        if not extra_opening_area:
            return arch_walls

        result: list[ArchitecturalWall] = []
        for aw in arch_walls:
            additional = extra_opening_area.get(aw.id, 0.0)
            new_ops = extra_openings.get(aw.id, [])
            if additional > 0.0:
                updated = ArchitecturalWall(
                    **{
                        f.name: getattr(aw, f.name)
                        for f in aw.__dataclass_fields__.values()  # type: ignore[attr-defined]
                        if f.name not in ("openings", "opening_count", "opening_area_sqft")
                    },
                    openings=aw.openings + new_ops,
                    opening_count=aw.opening_count + len(new_ops),
                    opening_area_sqft=round(aw.opening_area_sqft + additional, 2),
                )
                result.append(updated)
            else:
                result.append(aw)
        return result

    def _build_wall_graph(self, walls: list[Wall]) -> nx.Graph:
        g = nx.Graph()
        for w in walls:
            if not w.start_norm or not w.end_norm:
                continue
            p1 = (round(w.start_norm["x"] / 0.02) * 0.02, round(w.start_norm["y"] / 0.02) * 0.02)
            p2 = (round(w.end_norm["x"] / 0.02) * 0.02, round(w.end_norm["y"] / 0.02) * 0.02)
            if p1 != p2:
                g.add_edge(p1, p2, wall_id=w.id, length=w.length_ft)
        return g

    def _deduplicate_face_pairs(
        self,
        walls: list[ArchitecturalWall],
    ) -> list[ArchitecturalWall]:
        """Detect and consolidate near-identical walls that represent:
        (a) Face A / Face B of a single physical wall (perpendicular offset < 0.01 norm)
        (b) Duplicate CAD layers (exact same geometry on multiple layers)

        For each pair, the primary wall (longer or higher-confidence) absorbs the
        secondary's source segment IDs and gains dual-face evidence. The secondary
        is removed from the output.

        This prevents QTO double-counting where the same physical wall produces
        two separate canonical walls — one per geometric face stroke — each
        contributing its own gross/net SF independently.
        """
        if len(walls) <= 1:
            return walls

        # Index walls by page_id for efficiency (only compare within same page)
        by_page: dict[int, list[ArchitecturalWall]] = {}
        for w in walls:
            by_page.setdefault(w.page_id, []).append(w)

        absorbed_ids: set[str] = set()   # IDs of walls absorbed into a primary

        for page_id, page_walls in by_page.items():
            n = len(page_walls)
            for i in range(n):
                w1 = page_walls[i]
                if w1.id in absorbed_ids:
                    continue

                for j in range(i + 1, n):
                    w2 = page_walls[j]
                    if w2.id in absorbed_ids:
                        continue

                    # Compare endpoints
                    s1x, s1y = w1.start_norm["x"], w1.start_norm["y"]
                    e1x, e1y = w1.end_norm["x"], w1.end_norm["y"]
                    s2x, s2y = w2.start_norm["x"], w2.start_norm["y"]
                    e2x, e2y = w2.end_norm["x"], w2.end_norm["y"]

                    dx1, dy1 = e1x - s1x, e1y - s1y
                    dx2, dy2 = e2x - s2x, e2y - s2y
                    len1 = math.hypot(dx1, dy1)
                    len2 = math.hypot(dx2, dy2)
                    if len1 < 1e-5 or len2 < 1e-5:
                        continue

                    # 1. Direct endpoint proximity duplicate (both endpoints within 0.010 norm)
                    d_fwd_start = math.hypot(s1x - s2x, s1y - s2y)
                    d_fwd_end = math.hypot(e1x - e2x, e1y - e2y)
                    d_rev_start = math.hypot(s1x - e2x, s1y - e2y)
                    d_rev_end = math.hypot(e1x - s2x, e1y - s2y)

                    is_endpoint_dup = (
                        (d_fwd_start < 0.010 and d_fwd_end < 0.010) or
                        (d_rev_start < 0.010 and d_rev_end < 0.010)
                    )

                    # 2. Strict parallel face-pair detection
                    is_parallel_face_pair = False
                    
                    ang1 = math.degrees(math.atan2(dy1, dx1)) % 180.0
                    ang2 = math.degrees(math.atan2(dy2, dx2)) % 180.0
                    ang_diff = abs(ang1 - ang2)
                    if ang_diff > 90.0:
                        ang_diff = 180.0 - ang_diff

                    if not is_endpoint_dup and ang_diff <= 8.0:
                        # Unit normal to line 1
                        nx, ny = -dy1 / len1, dx1 / len1
                        
                        # Perpendicular distance at BOTH endpoints of w2 to line 1
                        perp_s2 = abs((s2x - s1x) * nx + (s2y - s1y) * ny)
                        perp_e2 = abs((e2x - s1x) * nx + (e2y - s1y) * ny)
                        max_perp = max(perp_s2, perp_e2)

                        # Parallel projection (longitudinal span overlap)
                        ux, uy = dx1 / len1, dy1 / len1
                        proj_s2 = (s2x - s1x) * ux + (s2y - s1y) * uy
                        proj_e2 = (e2x - s1x) * ux + (e2y - s1y) * uy
                        min_proj2, max_proj2 = min(proj_s2, proj_e2), max(proj_s2, proj_e2)

                        overlap_start = max(0.0, min_proj2)
                        overlap_end = min(len1, max_proj2)
                        overlap_len = max(0.0, overlap_end - overlap_start)

                        min_span = min(len1, len2)
                        overlap_ratio = overlap_len / max(1e-5, min_span)
                        length_ratio = min(len1, len2) / max(len1, len2)

                        same_class = (w1.classification == w2.classification)
                        shares_rooms = bool(set(w1.room_ids or []) & set(w2.room_ids or []))

                        # Strict face pair gate: MUST satisfy ALL conditions
                        is_contained_subsegment = (
                            max_perp <= 0.015 and overlap_ratio >= 0.85
                        )
                        is_parallel_face_run = (
                            max_perp <= 0.030
                            and overlap_ratio >= 0.70
                            and length_ratio >= 0.50
                            and (same_class or shares_rooms or w1.physical_wall_type == w2.physical_wall_type)
                        )
                        if is_contained_subsegment or is_parallel_face_run:
                            is_parallel_face_pair = True

                    if not (is_endpoint_dup or is_parallel_face_pair):
                        continue

                    # Determine primary (longer) and secondary (shorter)
                    if w1.length_ft >= w2.length_ft:
                        primary, secondary = w1, w2
                        w1_absorbed = False
                    else:
                        primary, secondary = w2, w1
                        w1_absorbed = True

                    # Absorb secondary into primary
                    merged_seg_ids = list(set(
                        (primary.source_segment_ids or []) +
                        (secondary.source_segment_ids or [])
                    ))
                    merged_seg_ids.sort()

                    merged_constituent_ids = list(set(
                        (primary.constituent_wall_ids or []) +
                        (secondary.constituent_wall_ids or [])
                    ))

                    absorbed_ids.add(secondary.id)
                    primary.source_segment_ids = merged_seg_ids
                    primary.constituent_wall_ids = merged_constituent_ids

                    # Populate Face B if not present
                    if primary.wall_geometry and not primary.wall_geometry.face_b.segment_ids:
                        primary.wall_geometry.face_b = WallFace(
                            segment_ids=secondary.source_segment_ids or [],
                            start_norm=secondary.start_norm,
                            end_norm=secondary.end_norm,
                            length_ft=secondary.length_ft,
                            is_finished_gwb=True,
                        )
                        primary.wall_geometry.overlap_ratio = 1.0

                    # Merge room adjacency
                    primary.room_ids = list(set(
                        (primary.room_ids or []) + (secondary.room_ids or [])
                    ))
                    primary.adjacent_room_ids = list(set(
                        (primary.adjacent_room_ids or []) + (secondary.adjacent_room_ids or [])
                    ))

                    ev = dict(primary.source_evidence)
                    ev["face_pair_deduplicated"] = True
                    ev["absorbed_wall_id"] = secondary.id
                    primary.source_evidence = ev

                    logger.debug(
                        "Face-pair dedup: %s absorbed %s (is_endpoint=%s, is_pair=%s)",
                        primary.id, secondary.id, is_endpoint_dup, is_parallel_face_pair
                    )

                    # PREVENT TRANSITIVE POISONING: If w1 itself was absorbed by w2,
                    # w1 is no longer a valid primary candidate for subsequent j iterations
                    if w1_absorbed:
                        break

        # Build result: all walls except absorbed ones
        result = [w for w in walls if w.id not in absorbed_ids]
        return result

    def _bridge_architectural_walls(
        self,
        walls: list[ArchitecturalWall],
        opening_detections: list[Detection] | None = None,
    ) -> list[ArchitecturalWall]:
        """Bridges collinear wall runs across door/window openings with evidence-gated thresholds:
        - Gap + Door/Window Opening Evidence: up to 10.0 ft (double doors, vestibules, sliders)
        - Gap + Room Continuity: up to 8.0 ft (cased openings, pass-throughs)
        - Gap + Wall Termination (no evidence): conservative <= 3.5 ft standard
        """
        if len(walls) <= 1:
            return walls

        horizontal: list[ArchitecturalWall] = []
        vertical: list[ArchitecturalWall] = []
        slanted: list[ArchitecturalWall] = []

        for w in walls:
            dx = abs(w.end_norm["x"] - w.start_norm["x"])
            dy = abs(w.end_norm["y"] - w.start_norm["y"])
            if dx < 1e-6 and dy < 1e-6:
                continue
            ang = math.degrees(math.atan2(dy, dx))
            if ang <= 12.0:
                horizontal.append(w)
            elif ang >= 78.0:
                vertical.append(w)
            else:
                slanted.append(w)

        bridged: list[ArchitecturalWall] = []
        bridged.extend(self._merge_axis_aligned_group(horizontal, is_horizontal=True, opening_detections=opening_detections))
        bridged.extend(self._merge_axis_aligned_group(vertical, is_horizontal=False, opening_detections=opening_detections))
        bridged.extend(slanted)
        return bridged

    def _merge_axis_aligned_group(
        self,
        group: list[ArchitecturalWall],
        is_horizontal: bool,
        opening_detections: list[Detection] | None = None,
    ) -> list[ArchitecturalWall]:
        if not group:
            return []

        # Multi-signal perpendicular clustering
        def _get_perp(w: ArchitecturalWall) -> float:
            return (w.start_norm["y"] + w.end_norm["y"]) / 2.0 if is_horizontal else (
                w.start_norm["x"] + w.end_norm["x"]
            ) / 2.0

        def _get_span(w: ArchitecturalWall) -> tuple[float, float]:
            if is_horizontal:
                return (min(w.start_norm["x"], w.end_norm["x"]), max(w.start_norm["x"], w.end_norm["x"]))
            else:
                return (min(w.start_norm["y"], w.end_norm["y"]), max(w.start_norm["y"], w.end_norm["y"]))

        sorted_by_perp = sorted(group, key=_get_perp)
        clusters: list[list[ArchitecturalWall]] = []

        for w in sorted_by_perp:
            p_val = _get_perp(w)
            w_span = _get_span(w)
            matched_cluster = None
            for cl in clusters:
                avg_cl_perp = sum(_get_perp(cw) for cw in cl) / len(cl)
                perp_dist = abs(p_val - avg_cl_perp)
                
                # Check span overlap
                has_span_overlap = False
                for cw in cl:
                    cw_span = _get_span(cw)
                    if not (w_span[1] < cw_span[0] - 0.005 or w_span[0] > cw_span[1] + 0.005):
                        has_span_overlap = True
                        break
                        
                shares_room = any(bool(set(w.room_ids or []) & set(cw.room_ids or [])) for cw in cl)
                same_class = all(w.classification == cw.classification for cw in cl)
                
                # Clustering conditions:
                # 1. Tight alignment (<= 0.008 norm ~ 11 inches)
                # 2. Relaxed alignment (<= 0.016 norm ~ 22 inches) if collinear (no span overlap) or room-supported
                if perp_dist <= 0.008:
                    matched_cluster = cl
                    break
                elif perp_dist <= 0.016 and same_class and (not has_span_overlap or shares_room):
                    matched_cluster = cl
                    break
                    
            if matched_cluster is not None:
                matched_cluster.append(w)
            else:
                clusters.append([w])

        result: list[ArchitecturalWall] = []
        _DOOR_GAP_STANDARD_FT = 3.5
        _DOOR_GAP_LARGE_OPENING_FT = 10.0
        _ROOM_CONTINUITY_MAX_FT = 8.0

        _gap_scales: list[float] = []
        for w in group:
            ax_span = abs(w.end_norm["x"] - w.start_norm["x"]) if is_horizontal else abs(w.end_norm["y"] - w.start_norm["y"])
            if ax_span > 1e-5 and w.length_ft > 0.1:
                _gap_scales.append(w.length_ft / ax_span)
            elif w.length_ft > 0.1:
                _gap_scales.append(100.0)
        _ft_per_norm = sorted(_gap_scales)[len(_gap_scales) // 2] if _gap_scales else 100.0

        for cluster in clusters:
            if is_horizontal:
                sorted_cluster = sorted(cluster, key=lambda item: min(item.start_norm["x"], item.end_norm["x"]))
            else:
                sorted_cluster = sorted(cluster, key=lambda item: min(item.start_norm["y"], item.end_norm["y"]))

            current_run: list[ArchitecturalWall] = [sorted_cluster[0]]
            for next_wall in sorted_cluster[1:]:
                prev_wall = current_run[-1]
                if is_horizontal:
                    running_max = max(max(w.start_norm["x"], w.end_norm["x"]) for w in current_run)
                    next_min = min(next_wall.start_norm["x"], next_wall.end_norm["x"])
                    gap_start, gap_end = running_max, next_min
                    perp_coord = (prev_wall.start_norm["y"] + prev_wall.end_norm["y"]) / 2.0
                else:
                    running_max = max(max(w.start_norm["y"], w.end_norm["y"]) for w in current_run)
                    next_min = min(next_wall.start_norm["y"], next_wall.end_norm["y"])
                    gap_start, gap_end = running_max, next_min
                    perp_coord = (prev_wall.start_norm["x"] + prev_wall.end_norm["x"]) / 2.0

                gap_norm = max(0.0, next_min - running_max)
                gap_ft = gap_norm * _ft_per_norm if _ft_per_norm > 0 else (gap_norm * 100.0)

                # Evidence Ladder for Physical Wall Continuity:
                # 1. Door / Window Opening Evidence in the gap
                has_opening_evidence = False
                if opening_detections:
                    for det in opening_detections:
                        det_box = getattr(det, "bbox_norm", {}) or {}
                        if is_horizontal:
                            det_x_center = (det_box.get("minX", 0) + det_box.get("maxX", 0)) / 2.0
                            det_y_center = (det_box.get("minY", 0) + det_box.get("maxY", 0)) / 2.0
                            if (gap_start - 0.020 <= det_x_center <= gap_end + 0.020) and abs(det_y_center - perp_coord) <= 0.030:
                                has_opening_evidence = True
                                break
                        else:
                            det_x_center = (det_box.get("minX", 0) + det_box.get("maxX", 0)) / 2.0
                            det_y_center = (det_box.get("minY", 0) + det_box.get("maxY", 0)) / 2.0
                            if (gap_start - 0.020 <= det_y_center <= gap_end + 0.020) and abs(det_x_center - perp_coord) <= 0.030:
                                has_opening_evidence = True
                                break

                if not has_opening_evidence:
                    has_opening_evidence = bool(prev_wall.openings or next_wall.openings)

                # 2. Room continuity evidence across the gap
                has_room_continuity = bool(
                    (set(prev_wall.room_ids or []) & set(next_wall.room_ids or []))
                    or (set(prev_wall.adjacent_room_ids or []) & set(next_wall.adjacent_room_ids or []))
                )

                # 3. T-junction and Demising Spine Alignment Evidence
                thick_diff = abs((prev_wall.thickness_in or 4.875) - (next_wall.thickness_in or 4.875))
                same_spine = (prev_wall.classification == next_wall.classification) and (thick_diff <= 3.0)

                # Dynamic gap threshold determined by evidence
                if has_opening_evidence:
                    max_allowed_gap_ft = _DOOR_GAP_LARGE_OPENING_FT  # up to 10.0 ft for double doors / sliders
                elif has_room_continuity or same_spine:
                    max_allowed_gap_ft = _ROOM_CONTINUITY_MAX_FT  # up to 8.0 ft for cased opening / T-junction spine
                else:
                    max_allowed_gap_ft = _DOOR_GAP_STANDARD_FT  # 3.5 ft standard

                should_merge = (gap_ft <= max_allowed_gap_ft) and (prev_wall.classification == next_wall.classification)

                if should_merge:
                    current_run.append(next_wall)
                else:
                    result.append(self._collapse_wall_run(current_run, is_horizontal))
                    current_run = [next_wall]

            if current_run:
                result.append(self._collapse_wall_run(current_run, is_horizontal))

        return result

    def _collapse_wall_run(self, run: list[ArchitecturalWall], is_horizontal: bool) -> ArchitecturalWall:
        if len(run) == 1:
            return run[0]

        first = run[0]
        last = run[-1]

        # Compute constituent spans
        if is_horizontal:
            spans = [(min(w.start_norm["x"], w.end_norm["x"]), max(w.start_norm["x"], w.end_norm["x"])) for w in run]
            min_c = min(s for s, e in spans)
            max_c = max(e for s, e in spans)
            avg_perp = sum((w.start_norm["y"] + w.end_norm["y"]) / 2.0 for w in run) / len(run)
            start_norm = {"x": min_c, "y": avg_perp}
            end_norm = {"x": max_c, "y": avg_perp}
        else:
            spans = [(min(w.start_norm["y"], w.end_norm["y"]), max(w.start_norm["y"], w.end_norm["y"])) for w in run]
            min_c = min(s for s, e in spans)
            max_c = max(e for s, e in spans)
            avg_perp = sum((w.start_norm["x"] + w.end_norm["x"]) / 2.0 for w in run) / len(run)
            start_norm = {"x": avg_perp, "y": min_c}
            end_norm = {"x": avg_perp, "y": max_c}

        span_norm = max_c - min_c

        # Derive scale (ft per norm unit) from consistent constituent geometry
        clean_scales: list[float] = []
        for w in run:
            ax_span = abs(w.end_norm["x"] - w.start_norm["x"]) if is_horizontal else abs(w.end_norm["y"] - w.start_norm["y"])
            if ax_span > 0.005 and w.length_ft >= 0.5:
                clean_scales.append(w.length_ft / ax_span)
        if clean_scales:
            median_scale = sorted(clean_scales)[len(clean_scales) // 2]
        else:
            fallback_scales = [
                w.length_ft / max(1e-5, (abs(w.end_norm["x"] - w.start_norm["x"]) if is_horizontal else abs(w.end_norm["y"] - w.start_norm["y"])))
                for w in run if w.length_ft > 0.1
            ]
            median_scale = sorted(fallback_scales)[len(fallback_scales) // 2] if fallback_scales else (max(w.length_ft for w in run) / max(1e-6, span_norm))

        # 1D Interval Union of physical spans
        sorted_spans = sorted(spans, key=lambda x: x[0])
        union_spans: list[tuple[float, float]] = []
        for s_i, e_i in sorted_spans:
            if not union_spans:
                union_spans.append((s_i, e_i))
            else:
                ps, pe = union_spans[-1]
                if s_i <= pe + 1e-5:
                    union_spans[-1] = (ps, max(pe, e_i))
                else:
                    union_spans.append((s_i, e_i))

        true_union_norm = sum(e - s for s, e in union_spans)
        true_source_union_length_ft = round(true_union_norm * median_scale, 3)

        # Openings are created ONLY for actual disjoint gaps between union intervals
        openings: list[WallOpening] = []
        if len(union_spans) > 1:
            for idx in range(len(union_spans) - 1):
                gap_start = union_spans[idx][1]
                gap_end = union_spans[idx + 1][0]
                gap_norm = gap_end - gap_start
                gap_ft = round(gap_norm * median_scale, 2)
                if gap_ft >= 0.5:  # meaningful gap >= 6 inches
                    if is_horizontal:
                        gap_cx = (gap_start + gap_end) / 2.0
                        gap_cy = avg_perp
                    else:
                        gap_cx = avg_perp
                        gap_cy = (gap_start + gap_end) / 2.0

                    op_w = min(12.0, max(1.0, gap_ft))
                    op_h = min(7.0, first.height_ft or 9.0)
                    openings.append(
                        WallOpening(
                            id=f"op-{first.id}-gap-{idx+1}",
                            opening_type="door",
                            width_ft=op_w,
                            height_ft=op_h,
                            area_sqft=round(op_w * op_h, 2),
                            dimension_source="gap_geometry",
                            center_norm={"x": round(gap_cx, 5), "y": round(gap_cy, 5)},
                        )
                    )

        total_op_area = sum(op.area_sqft for op in openings)

        # Determine canonical length_ft: bounding span when openings exist; true union when no gaps
        if len(openings) > 0:
            length_ft = round(span_norm * median_scale, 3)
        else:
            length_ft = true_source_union_length_ft

        # Merge constituent source evidence dictionaries
        merged_source_evidence: dict[str, Any] = {}
        for w in run:
            if hasattr(w, "source_evidence") and isinstance(w.source_evidence, dict):
                merged_source_evidence.update(w.source_evidence)

        constituent_ids = [w.id for w in run]
        sum_constituent_len = round(sum(w.length_ft for w in run), 3)
        overlap_len = max(0.0, round(sum_constituent_len - true_source_union_length_ft, 3))
        inflation_ratio = round(length_ft / max(0.01, true_source_union_length_ft), 3)

        merged_source_evidence.update({
            "is_bridged": True,
            "bridged_constituents": constituent_ids,
            "bridged_segment_count": len(run),
            "openings_detected": len(openings),
            "opening_area_deduction_sqft": total_op_area,
            "true_source_union_length_ft": true_source_union_length_ft,
            "canonical_length_ft": length_ft,
            "stored_length_ft": length_ft,
            "overlap_length_ft": overlap_len,
            "inflation_ratio": inflation_ratio,
            "room_boundary_support": any(
                w.source_evidence.get("room_boundary_support", False)
                for w in run if hasattr(w, "source_evidence") and isinstance(w.source_evidence, dict)
            ),
            "connected_wall_graph": any(
                w.source_evidence.get("connected_wall_graph", False)
                for w in run if hasattr(w, "source_evidence") and isinstance(w.source_evidence, dict)
            ),
            # Height transparency — preserve from constituent walls
            "height_ft": first.height_ft,
            "height_source": first.source_evidence.get("height_source", "project_default"),
            "assumed_height": first.source_evidence.get("assumed_height", True),
        })

        # Preserve the most authoritative decision state among merged components
        best_decision_state = first.decision_state
        state_priority = {
            WallDecisionState.DRYWALL_SCOPE_CONFIRMED: 5,
            WallDecisionState.WALL_ASSEMBLY_CONFIRMED: 4,
            WallDecisionState.PHYSICAL_WALL_CONFIRMED: 3,
            WallDecisionState.PHYSICAL_WALL_CONFIRMED_SINGLE_SOURCE: 2,
            WallDecisionState.WALL_CANDIDATE_NEEDS_REVIEW: 1,
            WallDecisionState.NON_WALL: 0,
        }
        for w in run:
            if state_priority.get(w.decision_state, 0) > state_priority.get(best_decision_state, 0):
                best_decision_state = w.decision_state

        is_qto_eligible = any(getattr(w, "qto_eligible", False) for w in run)
        block_reason = None if is_qto_eligible else first.qto_block_reason

        all_source_segment_ids: list[int] = []
        for w in run:
            if hasattr(w, "source_segment_ids") and w.source_segment_ids:
                all_source_segment_ids.extend(w.source_segment_ids)
            if isinstance(w.id, int):
                all_source_segment_ids.append(w.id)
            elif isinstance(w.id, str):
                w_raw_id = w.id.replace("drywall-wall-", "").split("_")[0]
                if w_raw_id.isdigit():
                    all_source_segment_ids.append(int(w_raw_id))
        all_source_segment_ids = sorted(list(set(all_source_segment_ids)))

        return ArchitecturalWall(
            id=f"{first.id}_bridged_{len(run)}",
            page_id=first.page_id,
            start_norm=start_norm,
            end_norm=end_norm,
            length_ft=round(length_ft, 2),
            thickness_in=first.thickness_in,
            thickness_source=first.thickness_source,
            height_ft=first.height_ft,
            height_source=first.height_source,
            physical_wall_type=first.physical_wall_type,
            classification=first.classification,
            classification_reason=first.classification_reason,
            is_building_envelope=first.is_building_envelope,
            face_specification=first.face_specification or last.face_specification,
            # Prefer whichever collapsed segment has the more specific/higher-
            # confidence canonical category rather than always defaulting to
            # `first` — a merged run must not silently regress a genuinely
            # resolved category (e.g. STAIR_CORE) back to NEEDS_REVIEW just
            # because the first physical segment happened to lack the evidence
            # a later segment in the same run had.
            canonical_category=max(run, key=lambda w: w.canonical_confidence).canonical_category,
            canonical_confidence=max(w.canonical_confidence for w in run),
            canonical_reasons=max(run, key=lambda w: w.canonical_confidence).canonical_reasons,
            canonical_source_sheet=max(run, key=lambda w: w.canonical_confidence).canonical_source_sheet,
            canonical_method=max(run, key=lambda w: w.canonical_confidence).canonical_method,
            room_ids=list({rid for w in run for rid in w.room_ids}),
            adjacent_room_ids=list({rid for w in run for rid in w.adjacent_room_ids}),
            source_segment_ids=all_source_segment_ids,
            constituent_wall_ids=constituent_ids,
            wall_tag=first.wall_tag or last.wall_tag,
            tag_evidence=first.tag_evidence,
            assembly=first.assembly or last.assembly,
            assembly_resolved=first.assembly_resolved or last.assembly_resolved,
            assembly_verified=first.assembly_verified or last.assembly_verified,
            schedule_sheet=first.schedule_sheet or last.schedule_sheet,
            schedule_source_region=first.schedule_source_region or last.schedule_source_region,
            drywall_scope=first.drywall_scope,
            decision_state=best_decision_state,
            wall_geometry=first.wall_geometry,
            openings=openings,
            opening_count=len(openings),
            opening_area_sqft=round(total_op_area, 2),
            source_evidence=merged_source_evidence,
            confidence=0.95,
            status="approved",
            qto_eligible=is_qto_eligible,
            qto_block_reason=block_reason,
        )

