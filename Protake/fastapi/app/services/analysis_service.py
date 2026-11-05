"""Orchestrates the OCR and AI-validation passes over an already
geometry-processed page, persisting their output as OCR-confirmed room
names and reviewable `Detection` rows respectively.
"""

import re

from PIL import Image
from shapely.geometry import Point, Polygon
from sqlalchemy.orm import Session

from app.ai.validation_engine import ValidationFinding, run_validation, to_normalized_polygon
from app.geometry.drawing_zone import in_drawing_zone
from app.geometry.engine import GeometryResult, analyze_page
from app.geometry.metrics import SCALE_SOURCE_USER, ScaleContext, default_scale_ft_per_px
from app.models.detection import Detection
from app.models.enums import DetectionKind, DetectionSource, ReviewStatus, TradeKey
from app.models.page import Page
from app.ocr.parsers import TradeTagLabel
from app.ocr.pipeline import OcrPipelineResult, run_ocr_pipeline
from app.repositories.detection_repository import DetectionRepository
from app.repositories.room_repository import RoomRepository

_TAG_TYPE_LABELS = {
    "floor_finish": "Floor Finish",
    "wall_type": "Wall Type",
    "paint_finish": "Paint Finish",
    "roof_note": "Roof Note",
}

# The exact default a room gets from the geometry engine (GeometryRoom
# name=f"Room {i+1}") when nothing has named it yet. Only rooms still
# carrying this are candidates for the AI-inferred fallback below — a room
# OCR already named for real is never overwritten by a model's guess.
_GENERIC_ROOM_NAME_RE = re.compile(r"^Room \d+$")

# How close an AI room-type prediction's centroid may sit outside a room's
# own polygon and still count as "this prediction is about that room" — a
# detect-only model's bounding box is looser than a segmentation mask, so a
# small normalized-space tolerance (2% of the page) covers that slack
# without reaching into a neighboring room.
_ROOM_MATCH_TOLERANCE_NORM = 0.02

# A room name containing any of these is plausibly a wet room a real
# Sink/Toilet/Bathtub/Shower/Vanity could actually be in.
_WET_ROOM_KEYWORDS = {
    "toilet", "bath", "wc", "washroom", "restroom", "kitchen", "kitchenette",
    "pwdr", "powder", "utility", "laundry", "shower", "janitor", "mudroom",
}

_FIXTURE_LABELS = {"sink", "toilet", "bathtub", "shower", "vanity"}


class AnalysisService:
    def __init__(self, db: Session):
        self.db = db
        self.rooms = RoomRepository(db)
        self.detections = DetectionRepository(db)

    def _recompute_geometry(self, page: Page) -> GeometryResult:
        # A page carrying a stored scale has been calibrated (by the user,
        # or by detection during ingest, which persists it); otherwise this
        # is explicitly an assumption and must be marked as one.
        scale_context = (
            ScaleContext.from_ft_per_px(page.scale_ft_per_px, SCALE_SOURCE_USER, dpi=page.dpi)
            if page.scale_ft_per_px is not None
            else ScaleContext.assumed(page.dpi)
        )
        project = page.blueprint.project
        selected_trade = (
            project.trade_configs[0].trade.value if project and project.trade_configs else None
        )
        return analyze_page(
            page.image_path,
            pdf_path=page.blueprint.file_path,
            page_number=page.page_number,
            scale_context=scale_context,
            selected_trade=selected_trade,
        )

    def run_ocr(self, page: Page) -> OcrPipelineResult:
        geometry = self._recompute_geometry(page)
        with Image.open(page.image_path) as img:
            w, h = img.size

        result = run_ocr_pipeline(
            page.image_path,
            geometry,
            page.scale_ft_per_px or default_scale_ft_per_px(page.dpi),
            w,
            h,
            pdf_path=page.blueprint.file_path,
            page_number=page.page_number,
        )

        db_rooms = self.rooms.find(page_id=page.id)
        db_rooms_sorted = sorted(db_rooms, key=lambda r: r.id)
        for idx, confirmed_name in result.room_name_overrides.items():
            if idx < len(db_rooms_sorted):
                self.rooms.update(db_rooms_sorted[idx], name=confirmed_name)

        self._persist_trade_tags(page, result.trade_tags, w, h)

        self.db.flush()
        from app.repositories.page_repository import PageRepository

        PageRepository(self.db).update(page, ocr_processed=True)
        return result

    def _persist_trade_tags(self, page: Page, trade_tags: list[TradeTagLabel], image_w: int, image_h: int) -> None:
        """Turn each OCR-recognized trade callout (material code, wall-type
        tag, paint finish, roof note) into a reviewable SYMBOL detection
        tagged with its trade, so it shows up in the normal review queue.
        """
        pad_x, pad_y = 25.0, 12.0
        for tag in trade_tags:
            cx, cy = tag.centroid_px
            x1, y1 = max(0.0, cx - pad_x), max(0.0, cy - pad_y)
            x2, y2 = min(float(image_w), cx + pad_x), min(float(image_h), cy + pad_y)
            polygon_norm = [
                [round(x1 / image_w, 5), round(y1 / image_h, 5)],
                [round(x2 / image_w, 5), round(y1 / image_h, 5)],
                [round(x2 / image_w, 5), round(y2 / image_h, 5)],
                [round(x1 / image_w, 5), round(y2 / image_h, 5)],
            ]
            bbox_norm = {
                "minX": polygon_norm[0][0],
                "minY": polygon_norm[0][1],
                "maxX": polygon_norm[2][0],
                "maxY": polygon_norm[2][1],
            }
            self.detections.create(
                page_id=page.id,
                kind=DetectionKind.SYMBOL,
                label=f"{_TAG_TYPE_LABELS.get(tag.tag_type, tag.tag_type)}: {tag.text}",
                trade=TradeKey(tag.trade),
                polygon_norm=polygon_norm,
                bbox_norm=bbox_norm,
                confidence=tag.confidence,
                source=DetectionSource.OCR,
                status=ReviewStatus.PENDING,
            )

    def run_ai_validation(
        self,
        page: Page,
        geometry: GeometryResult | None = None,
        ocr_text_boxes_px: list[tuple[float, float, float, float]] | None = None,
        exclude_yolo_classes: list[str] | None = None,
    ) -> list[Detection]:
        """Persist the AI pass's symbol findings (doors, windows, fixtures)
        as reviewable Detection rows.

        `geometry` lets a caller that has just computed it hand it over —
        the upload pipeline does, because recomputing here would run the
        whole geometry engine a second time for the same page (25s+ on a
        6000px sheet). The on-demand endpoint passes nothing and pays for
        the recompute, as before.

        `ocr_text_boxes_px`, when available, blanks those regions before the
        YOLO fixture/room-type passes run — verified on a real commercial
        floor plan that bold sheet text (title block, sheet titles, general
        notes) was otherwise read as "Sink"/"Toilet" at up to 80% confidence
        (see yolo_detector._mask_text_regions).

        `exclude_yolo_classes` drops specific YOLO class names entirely —
        used when the geometry engine already found the same thing from a
        more reliable source (a PDF's own WINDOW vector layer beats YOLO
        guessing on the raster every time it exists) and a second, lower-
        confidence guess at the same object would only be noise.
        """
        import json
        import logging
        from shapely.geometry import LineString, Point, Polygon
        from app.geometry.page_classifier import classify_page_content, PageType
        from app.geometry.engine import _extract_page_text_fast
        logger = logging.getLogger("protake")

        if geometry is None:
            geometry = self._recompute_geometry(page)
        with Image.open(page.image_path) as img:
            w, h = img.size

        # Only passed when genuinely calibrated (user-set, or OCR-detected
        # from the sheet) — an assumed/default scale must not be trusted to
        # reject a real cabinet-model finding as "implausibly large" (see
        # validation_engine._is_implausibly_large_cabinet_finding).
        scale_for_size_gate = page.scale_ft_per_px if page.scale_ft_per_px else None

        findings: list[ValidationFinding] = run_validation(
            geometry, page.image_path, w, h, ocr_text_boxes_px, scale_for_size_gate
        )
        if exclude_yolo_classes:
            excluded = {c.lower() for c in exclude_yolo_classes}
            findings = [f for f in findings if f.label.lower() not in excluded]
        findings = self._drop_redundant_roomtype_findings(page, findings, w, h)
        findings = self._drop_implausible_fixture_findings(page, findings, w, h)

        # 1. Page Classifier Reconstruction for Drawing Zone & Page Type Context
        raw_text_tokens = _extract_page_text_fast(page.blueprint.file_path, page.page_number) if page.blueprint.file_path and page.page_number else []
        num_walls = len(geometry.walls) if geometry and geometry.walls else 0
        classification = classify_page_content(page.image_path, raw_text_tokens, num_walls)
        drawing_zone = classification.drawing_zone_bbox

        # 2. Get Rooms for room support / link logic
        db_rooms = self.rooms.find(page_id=page.id)

        # allowed classes by page type
        allowed_kinds = {DetectionKind.DOOR, DetectionKind.WINDOW, DetectionKind.STAIRS, DetectionKind.FIXTURE, DetectionKind.OBJECT, DetectionKind.ROOM, DetectionKind.WALL}
        if page.page_type == PageType.ROOF_PLAN.value:
            allowed_kinds = {DetectionKind.ANNOTATION, DetectionKind.ROOM}

        created: list[Detection] = []
        
        # Validation stats counters
        accepted_cnt = 0
        rejected_by_page_type = 0
        rejected_outside_zone = 0
        rejected_no_geometry = 0
        rejected_invalid_size = 0
        rejected_context_conflict = 0

        model_only = 0
        geometry_supported = 0
        vector_supported = 0
        ocr_supported = 0
        multi_source_supported = 0

        for finding in findings:
            polygon_norm = to_normalized_polygon(finding, w, h)
            xs = [p[0] for p in polygon_norm]
            ys = [p[1] for p in polygon_norm]
            bbox_norm = {"minX": min(xs), "minY": min(ys), "maxX": max(xs), "maxY": max(ys)}
            
            centroid = Point((bbox_norm["minX"] + bbox_norm["maxX"]) / 2.0, (bbox_norm["minY"] + bbox_norm["maxY"]) / 2.0)

            # A. Inside Drawing Zone check — same shared implementation and
            # constant walls now use (see app.geometry.drawing_zone), so
            # "inside the drawing zone" means one thing across AI findings,
            # rooms, and walls instead of three independently-hardcoded 0.85s.
            inside_drawing_zone = in_drawing_zone(bbox_norm, drawing_zone)

            # B. Page Type validation
            page_type_valid = finding.kind in allowed_kinds
            if page.page_type == PageType.FLOOR_PLAN.value and finding.label.lower() in ("roof note", "roof note callout"):
                page_type_valid = False

            # C. Geometry Wall support distance calculation
            geometry_support_score = 0.0
            min_dist = 1.0
            if geometry and geometry.walls:
                for w_geom in geometry.walls:
                    line = LineString([
                        (w_geom.start_norm["x"], w_geom.start_norm["y"]),
                        (w_geom.end_norm["x"], w_geom.end_norm["y"])
                    ])
                    dist = line.distance(centroid)
                    if dist < min_dist:
                        min_dist = dist
                # Wall support score: 1.0 at touching/on-wall, degrading to 0.0 at 0.05 normalized distance away
                geometry_support_score = max(0.0, min(1.0, 1.0 - (min_dist / 0.05)))

            # D. Room overlap support check
            room_support_score = 0.0
            linked_room_id = None
            if db_rooms:
                finding_poly = Polygon(polygon_norm) if len(polygon_norm) >= 3 else Point(centroid).buffer(0.01)
                for db_r in db_rooms:
                    db_poly = Polygon(db_r.polygon_norm)
                    if not db_poly.is_valid:
                        db_poly = db_poly.buffer(0)
                    if not finding_poly.is_valid:
                        finding_poly = finding_poly.buffer(0)
                    
                    if db_poly.intersects(finding_poly):
                        intersection_area = db_poly.intersection(finding_poly).area
                        union_area = db_poly.union(finding_poly).area
                        iou = intersection_area / union_area if union_area > 0 else 0.0
                        if iou > room_support_score:
                            room_support_score = iou
                            linked_room_id = db_r.id

            # E. Vector support check
            vector_support = 0.0
            if finding.kind == DetectionKind.WINDOW and getattr(geometry, "windows", None):
                vector_support = 1.0
            elif finding.kind == DetectionKind.DOOR and getattr(geometry, "doors", None):
                vector_support = 1.0

            # F. OCR support check
            ocr_support = 0.0
            if ocr_text_boxes_px:
                for tx0, ty0, tx1, ty1 in ocr_text_boxes_px:
                    tox = max(0.0, min(bbox_norm["maxX"]*w, tx1) - max(bbox_norm["minX"]*w, tx0))
                    toy = max(0.0, min(bbox_norm["maxY"]*h, ty1) - max(bbox_norm["minY"]*h, ty0))
                    if tox > 0 and toy > 0:
                        ocr_support = 1.0
                        break

            # G. Confidence Fusion Logic
            final_conf = finding.confidence
            decision = "accepted"
            rejection_reason = None

            if not page_type_valid:
                final_conf = min(final_conf, 0.15)
                decision = "rejected"
                rejection_reason = "incompatible_page_type"
                rejected_by_page_type += 1
            elif not inside_drawing_zone:
                final_conf = min(final_conf, 0.15)
                decision = "rejected"
                rejection_reason = "outside_drawing_zone"
                rejected_outside_zone += 1
            elif finding.kind in (DetectionKind.WINDOW, DetectionKind.DOOR) and geometry_support_score < 0.2:
                final_conf = min(final_conf, 0.15)
                decision = "rejected"
                rejection_reason = "no_geometry_wall_support"
                rejected_no_geometry += 1
            elif finding.kind == DetectionKind.FIXTURE and finding.note and "disagrees" in finding.note:
                # Implausible fixture flagged during cross-check/size-gate
                final_conf = min(final_conf, 0.15)
                decision = "rejected"
                rejection_reason = "implausible_fixture"
                rejected_invalid_size += 1
            elif final_conf < 0.25:
                decision = "rejected"
                rejection_reason = "low_model_confidence"
                rejected_context_conflict += 1
            else:
                accepted_cnt += 1
                if geometry_support_score > 0.2 or room_support_score > 0.1:
                    geometry_supported += 1
                else:
                    model_only += 1

                if vector_support > 0:
                    vector_supported += 1
                if ocr_support > 0:
                    ocr_supported += 1
                if (vector_support > 0 or ocr_support > 0) and (geometry_support_score > 0.2 or room_support_score > 0.1):
                    multi_source_supported += 1

            final_conf = round(max(0.01, min(1.0, final_conf)), 2)

            # Preserve Provenance in label field via JSON structure (using abbreviated keys to fit within 255 chars)
            provenance = {
                "mc": float(finding.confidence),
                "ptv": bool(page_type_valid),
                "idz": bool(inside_drawing_zone),
                "gs": float(max(geometry_support_score, room_support_score)),
                "os": float(ocr_support),
                "vs": float(vector_support),
                "fc": float(final_conf),
                "d": decision,
                "rr": rejection_reason
            }

            label_str = f"{finding.label} | PROVENANCE: {json.dumps(provenance)}"

            detection = self.detections.create(
                page_id=page.id,
                kind=finding.kind,
                label=label_str,
                trade=None,
                polygon_norm=polygon_norm,
                bbox_norm=bbox_norm,
                confidence=final_conf,
                source=finding.source,
                status=ReviewStatus.PENDING if decision == "accepted" else ReviewStatus.REJECTED,
                linked_room_id=linked_room_id
            )
            created.append(detection)

        from app.geometry.page_classifier import get_trade_relevance
        selected_trade_val = page.blueprint.project.trade_configs[0].trade.value if page.blueprint.project and page.blueprint.project.trade_configs else None
        trade_relevance = get_trade_relevance(page.page_type, selected_trade_val)

        # Log Context Debug Report
        report = f"""
========================================
BLUEPRINT ID: {page.blueprint_id}
SELECTED TRADE: {selected_trade_val or "None"}
REQUESTED TAKEOFF TRADE: {selected_trade_val or "ALL"}
PAGE ID: {page.id}
SHEET NUMBER: {page.sheet_code or "Unknown"}
PAGE TYPE: {page.page_type}
TRADE RELEVANCE: {trade_relevance.value}
PIPELINE ENTERED: AI_VALIDATION
PIPELINE EXITED: {"ACCEPTED" if accepted_cnt > 0 else "NO_ACCEPTED_CANDIDATES"}
----------------------------------------
PAGE CONTEXT
page_type: {page.page_type}
takeoff_eligible: {page.is_takeoff_eligible}
scale: {"calibrated" if page.scale_ft_per_px else "assumed"}
drawing_zone: {drawing_zone}
selected_trade: {selected_trade_val or "None"}

AI CONTEXT
allowed_classes: {[k.value for k in allowed_kinds]}
candidate_count: {len(findings)}

VALIDATION
accepted: {accepted_cnt}
rejected_by_page_type: {rejected_by_page_type}
rejected_outside_zone: {rejected_outside_zone}
rejected_no_geometry: {rejected_no_geometry}
rejected_invalid_size: {rejected_invalid_size}
rejected_context_conflict: {rejected_context_conflict}

EVIDENCE
model_only: {model_only}
geometry_supported: {geometry_supported}
vector_supported: {vector_supported}
ocr_supported: {ocr_supported}
multi_source_supported: {multi_source_supported}
========================================
"""
        logger.info(report)
        print(report)

        self._apply_ai_room_name_fallback(page, findings, created)

        from app.repositories.page_repository import PageRepository

        PageRepository(self.db).update(page, ai_validated=True)
        return created

    def _drop_redundant_roomtype_findings(
        self, page: Page, findings: list[ValidationFinding], image_w: int, image_h: int
    ) -> list[ValidationFinding]:
        """Remove best_roomtype.pt's ROOM findings for a room OCR already
        named for real, before any of them become a reviewable Detection.

        best_roomtype.pt's own purpose (see its docstring in yolo_detector)
        is naming a room from its furniture when nothing else can — the
        model has no way to know that purpose has already been served by
        OCR elsewhere. Left unfiltered, its 12-class residential vocabulary
        (Kitchen/Bedroom/Washroom/Dressing Room/...) gets forced onto every
        room on the sheet regardless of what kind of space it actually is:
        verified on a real commercial office floor plan, it produced 24
        Kitchen/Bedroom/Dressing Room guesses on rooms already correctly
        named "Office"/"Corridor"/"Toilet" by OCR — pure noise a reviewer
        then has to reject one at a time.

        Building-type detection (residential vs. commercial) was tried as
        the filter and measurably failed — OCR-label vocabulary overlap
        with this model's own class list scored 0.44 on a residential sheet
        and 0.40 on the commercial one, indistinguishable. "Is this room
        already named" is a fact already sitting in the database, not a
        guess, which is why it's used instead: this never touches
        best_new.pt's broader (158-class, both-domains) findings, and never
        touches a room OCR has NOT already named — that case is exactly
        what `_apply_ai_room_name_fallback` below still needs this model
        for.
        """
        named_rooms = [r for r in self.rooms.find(page_id=page.id) if not _GENERIC_ROOM_NAME_RE.match(r.name)]
        if not named_rooms:
            return findings

        named_polygons = [Polygon(r.polygon_norm) for r in named_rooms]

        def _is_redundant(finding: ValidationFinding) -> bool:
            if finding.kind != DetectionKind.ROOM or finding.model_role != "roomtype":
                return False
            xs = [p[0] / image_w for p in finding.polygon_px]
            ys = [p[1] / image_h for p in finding.polygon_px]
            centroid = Point(sum(xs) / len(xs), sum(ys) / len(ys))
            return any(
                polygon.contains(centroid) or polygon.distance(centroid) < _ROOM_MATCH_TOLERANCE_NORM
                for polygon in named_polygons
            )

        return [f for f in findings if not _is_redundant(f)]

    def _drop_implausible_fixture_findings(
        self, page: Page, findings: list[ValidationFinding], image_w: int, image_h: int
    ) -> list[ValidationFinding]:
        """Drop a Sink/Toilet/Bathtub/Shower/Vanity guess that lands inside
        a room OCR has confidently named as something that is not a wet
        room.

        best.pt and best_furniture.pt both carry these classes, and both
        were measured guessing them onto plain office-cubicle desk/chair
        icons at 25-73% confidence on a real commercial floor plan — the
        model has no training data distinguishing an office furniture
        symbol from a bathroom fixture symbol at this resolution/style, so
        it guesses wrong across cubicle after cubicle rather than only
        inside actual restrooms. A room OCR has already named for real is
        strong, independent evidence of what kind of space it is; a
        fixture reported inside a room confidently named "Office"/
        "Corridor"/"Pool Office" is almost certainly this failure mode,
        not a real fixture.

        Deliberately lenient in the other direction: a fixture inside an
        UNNAMED room (still "Room N") is kept, since that could genuinely
        be an unlabeled small bathroom — only a room OCR has *positively*
        named as something else rules a fixture out.
        """
        named_rooms = [r for r in self.rooms.find(page_id=page.id) if not _GENERIC_ROOM_NAME_RE.match(r.name)]
        if not named_rooms:
            return findings

        non_wet_polygons = [
            Polygon(r.polygon_norm)
            for r in named_rooms
            if not any(kw in r.name.lower() for kw in _WET_ROOM_KEYWORDS)
        ]
        if not non_wet_polygons:
            return findings

        def _is_implausible(finding: ValidationFinding) -> bool:
            if finding.kind != DetectionKind.FIXTURE or finding.label.lower() not in _FIXTURE_LABELS:
                return False
            xs = [p[0] / image_w for p in finding.polygon_px]
            ys = [p[1] / image_h for p in finding.polygon_px]
            centroid = Point(sum(xs) / len(xs), sum(ys) / len(ys))
            return any(polygon.contains(centroid) for polygon in non_wet_polygons)

        return [f for f in findings if not _is_implausible(f)]

    def _apply_ai_room_name_fallback(
        self, page: Page, findings: list[ValidationFinding], created: list[Detection]
    ) -> None:
        """Name a room from what the AI room-type models (best_new.pt /
        best_roomtype.pt) classified it as, when OCR found no printed label
        for it at all — the scenario those models exist for: a drawing with
        fixture symbols (a bathtub, a bed) but no room names printed on the
        sheet, which OCR-only naming can never fill in.

        Restricted to YOLO-sourced ROOM findings specifically. `run_validation`
        also emits ROOM-kind findings from `cross_check_rooms` (SAM boundary
        agreement checks) tagged `source=FUSION` — those just echo a room's
        own existing name back for the IoU comparison and carry no new
        naming information, so using them here would be a no-op at best.

        Never touches a room OCR already named for real — only ones still
        carrying the geometry engine's generic "Room N" default — and marks
        the result as AI-inferred (in the name text and `source`) rather
        than pretending it has the certainty of a label the drafter
        actually printed, so the estimator knows to double-check it.
        """
        room_detections = [
            d for f, d in zip(findings, created) if f.kind == DetectionKind.ROOM and f.source == DetectionSource.YOLO
        ]
        if not room_detections:
            return

        unnamed_rooms = [r for r in self.rooms.find(page_id=page.id) if _GENERIC_ROOM_NAME_RE.match(r.name)]
        if not unnamed_rooms:
            return

        room_polygons: dict[int, Polygon] = {r.id: Polygon(r.polygon_norm) for r in unnamed_rooms}

        best_by_room: dict[int, tuple[float, str]] = {}
        for detection in room_detections:
            xs = [p[0] for p in detection.polygon_norm]
            ys = [p[1] for p in detection.polygon_norm]
            centroid = Point(sum(xs) / len(xs), sum(ys) / len(ys))
            for room_id, polygon in room_polygons.items():
                if not (polygon.contains(centroid) or polygon.distance(centroid) < _ROOM_MATCH_TOLERANCE_NORM):
                    continue
                current = best_by_room.get(room_id)
                if current is None or detection.confidence > current[0]:
                    best_by_room[room_id] = (detection.confidence, detection.label)
                break

        for room in unnamed_rooms:
            match = best_by_room.get(room.id)
            if match is None:
                continue
            _, label = match
            self.rooms.update(room, name=f"{label} (AI-detected — unverified)", source=DetectionSource.FUSION)
