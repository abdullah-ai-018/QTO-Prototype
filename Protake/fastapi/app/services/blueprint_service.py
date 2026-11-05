"""Blueprint ingestion + processing orchestration:

  upload PDF -> rasterize pages (PyMuPDF) -> persist Page rows
      -> run geometry engine per page -> persist Room/Wall rows
      -> run OCR pipeline -> apply room-name overrides / flags
      -> run AI validation -> persist Detection rows (doors/windows/symbols)
"""

import logging

from fastapi import HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import SessionLocal
from app.geometry.document_context import build_document_context
from app.geometry.engine import GeometryResult, analyze_page
from app.geometry.metrics import (
    DEFAULT_WALL_THICKNESS_FT,
    SCALE_SOURCE_ASSUMED,
    SCALE_SOURCE_MEASURED,
    SCALE_SOURCE_PRINTED,
    SCALE_SOURCE_REFERENCE_OBJECT,
    SCALE_SOURCE_USER,
    ScaleContext,
    calibrate_scale_from_reference_objects,
    calibrate_scale_ft_per_px,
    default_scale_ft_per_px,
    scale_ft_per_px_from_ratio,
)
from app.models.blueprint import Blueprint
from app.models.enums import BlueprintStatus, DetectionKind, DetectionSource, ReviewStatus, WallType
from app.models.page import Page
from app.models.room import Room
from app.repositories.architectural_wall_repository import ArchitecturalWallRepository
from app.repositories.blueprint_repository import BlueprintRepository
from app.repositories.detection_repository import DetectionRepository
from app.repositories.page_repository import PageRepository
from app.repositories.project_knowledge_graph_repository import ProjectKnowledgeGraphRepository
from app.repositories.room_repository import RoomRepository
from app.repositories.schedule_item_repository import ScheduleItemRepository
from app.repositories.wall_repository import WallRepository
from app.services.pdf_engine import get_page_count, rasterize_page
from app.utils.files import page_image_path, page_thumbnail_path, save_upload

logger = logging.getLogger("protake")


def _extract_height_from_rcp_pages(
    pdf_path: str, rcp_page_numbers: list[int]
) -> tuple[float, str, str]:
    """Read RCP page text and return the first plausible ceiling height annotation.

    Returns (height_ft, source_tag, evidence_type). Falls back to (9.0, "DEFAULT", "ASSUMED")
    when no annotation is found. Evidence type mirrors HeightSource enum values:
    "RCP_MATCH", "PARTITION_SCHEDULE", or "ASSUMED".
    """
    import re
    HT = re.compile(
        r"(\d{1,2})['\-](\d{0,2})\s*\"?\s*"
        r"(?:AFF|A\.F\.F\.|CLG|CEILING|T\.O\.\s*WALL|T\.O\.\s*PLATE|DECK|CLR)",
        re.IGNORECASE,
    )
    try:
        import fitz
        doc = fitz.open(pdf_path)
        for pn in rcp_page_numbers:
            if 0 < pn <= len(doc):
                text = doc[pn - 1].get_text()
                for m in HT.finditer(text):
                    feet = int(m.group(1))
                    inches_str = (m.group(2) or "").strip()
                    inches = int(inches_str) / 12.0 if inches_str else 0.0
                    height = feet + inches
                    if 6.0 <= height <= 20.0:
                        doc.close()
                        return height, f"RCP-page-{pn}", "RCP_MATCH"
        doc.close()
    except Exception:
        pass
    return 9.0, "DEFAULT", "ASSUMED"


ALLOWED_CONTENT_TYPES = {
    "application/pdf",
    "image/png",
    "image/jpeg",
    "image/jpg",
    "image/webp",
    "image/tiff",
    "application/acad",
    "application/x-acad",
    "application/autocad_dwg",
    "image/vnd.dwg",
    "image/x-dwg",
    "application/dwg",
    "application/x-dwg",
    "image/vnd.dxf",
    "image/x-dxf",
    "application/dxf",
    "application/x-dxf",
    "application/octet-stream",
}
ALLOWED_EXTENSIONS = (".pdf", ".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff", ".dwg", ".dxf")
MAX_UPLOAD_SIZE_BYTES_DEFAULT = 100 * 1024 * 1024


# How many pages of one blueprint process concurrently. Pages used to run
# strictly one at a time (OCR + geometry + 4-model AI validation each,
# measured at ~2-3 minutes/page on a real CAD set) regardless of how many
# CPU cores or pool workers were actually available — a 14-page set paid
# for that fully sequentially. This pool is reused across all of a
# blueprint's pages (not recreated per page), so every model each worker
# loads stays warm for every page after its first, rather than reloading
# per page.
#
# Kept deliberately conservative: each worker loads a FULL model stack —
# PaddleOCR's ~5 sub-models (doc-orientation, UVDoc, textline-orientation,
# detection, recognition), all 4 YOLO models, and SAM2 (~150MB alone).
# That's 10+ models resident per worker simultaneously; 3 concurrent
# workers is enough to risk a genuine OOM kill on a memory-constrained
# machine (a killed worker surfaces as concurrent.futures.BrokenProcessPool
# — see process_all_pages). 2 is the safer default. Raise it only after
# confirming your machine has the headroom (watch actual RAM use during a
# real multi-page run, not just core count).
PAGE_PARALLELISM = 2


class BlueprintService:
    def __init__(self, db: Session):
        self.db = db
        self.blueprints = BlueprintRepository(db)
        self.pages = PageRepository(db)
        self.rooms = RoomRepository(db)
        self.walls = WallRepository(db)
        self.architectural_walls = ArchitecturalWallRepository(db)
        self.project_knowledge_graphs = ProjectKnowledgeGraphRepository(db)
        self.detections = DetectionRepository(db)
        self.schedule_items = ScheduleItemRepository(db)


    async def upload(self, project_id: int, uploaded_by_id: int, file: UploadFile) -> Blueprint:
        filename_lower = (file.filename or "").lower()
        is_allowed = (
            file.content_type in ALLOWED_CONTENT_TYPES
            or any(filename_lower.endswith(ext) for ext in ALLOWED_EXTENSIONS)
        )
        if not is_allowed:
            raise HTTPException(
                status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                "Only PDF blueprints, images (PNG, JPG, WEBP), and DWG/DXF CAD files are supported",
            )

        stored_filename, file_path, size_bytes = await save_upload(file)

        # On-the-fly DWG / DXF to PDF conversion using Aspose.CAD
        if file_path.lower().endswith((".dwg", ".dxf")):
            pdf_path = file_path.rsplit(".", 1)[0] + ".pdf"
            try:
                import aspose.cad as cad
                from aspose.cad.imageoptions import CadRasterizationOptions, PdfOptions

                image = cad.Image.load(file_path)
                
                rasterization_options = CadRasterizationOptions()
                rasterization_options.page_width = 3000.0
                rasterization_options.page_height = 2000.0
                rasterization_options.layouts = ["Model"]
                
                pdf_options = PdfOptions()
                pdf_options.vector_rasterization_options = rasterization_options
                
                image.save(pdf_path, pdf_options)
                
                import os
                file_path = pdf_path
                stored_filename = os.path.basename(pdf_path)
                size_bytes = os.path.getsize(pdf_path)
            except Exception as exc:
                logger.warning("DWG/DXF CAD vector conversion notice: %s", exc)
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    "DWG CAD files must be exported as Vector PDF. In AutoCAD, click Plot -> 'DWG To PDF.pc3' to generate a full-precision vector plan with all wall layers and partition schedules."
                ) from exc



        try:
            num_pages = get_page_count(file_path)
        except Exception as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Could not read blueprint file: {exc}") from exc

        blueprint = self.blueprints.create(
            project_id=project_id,
            uploaded_by_id=uploaded_by_id,
            original_filename=file.filename or stored_filename,
            stored_filename=stored_filename,
            file_path=file_path,
            file_size_bytes=size_bytes,
            num_pages=num_pages,
            status=BlueprintStatus.UPLOADED,
        )
        return blueprint

    def _run_page_ocr(self, page: Page) -> list:
        """Run OCR exactly once per page. Both scale auto-detection and
        the room-name/dimension pipeline need OCR tokens, but OCR is the
        slowest step in the pipeline (full-page CPU inference) — running
        it twice per page doubles that cost for no benefit, so callers
        share this single result instead of each calling run_ocr().
        """
        try:
            from app.ocr.paddle_engine import run_ocr

            return run_ocr(page.image_path, pdf_path=page.blueprint.file_path, page_number=page.page_number)
        except Exception as exc:
            print(f"[Protake] OCR notice: {exc}")
            return []

    def _detect_scale_from_tokens(self, page: Page, tokens: list) -> tuple[float, str] | None:
        """Best-effort auto scale detection for a page that has never been
        calibrated; a page the user has manually calibrated is never
        overridden by this.

        Two sources, in order of trustworthiness. The sheet's printed scale
        note ("1/8\"=1'-0\"", "SC 1:100") states what the drawing was
        *authored* at, which is not always what the PDF in hand is
        *plotted* at. The sheet's own gridline dimensions are a direct
        measurement of the file itself, so when they can be read they win —
        see geometry.dimension_scale for the real sheet where the printed
        note was 2.00x off and inflated every area by ~4x.
        """
        # Collect tokens from both OCR and native PDF text blocks (multiline safe)
        all_tokens = list(tokens)
        ratio_scale: float | None = None
        try:
            import fitz
            doc = fitz.open(page.blueprint.file_path)
            if 0 <= page.page_number - 1 < len(doc):
                pdf_page = doc[page.page_number - 1]
                pw, ph = pdf_page.rect.width, pdf_page.rect.height
                scale_x = (page.width_px or pw) / pw if pw > 0 else 1.0
                scale_y = (page.height_px or ph) / ph if ph > 0 else 1.0
                blocks = pdf_page.get_text("blocks")
                from app.ocr.parsers import _parse_scale_ratio
                for b in blocks:
                    block_text = b[4].strip()
                    if block_text and ratio_scale is None:
                        direct_ratio = _parse_scale_ratio(block_text)
                        if direct_ratio is not None:
                            ratio_scale = scale_ft_per_px_from_ratio(direct_ratio, page.dpi)

                    lines = block_text.split("\n")
                    bx0, by0, bx1, by1 = b[0] * scale_x, b[1] * scale_y, b[2] * scale_x, b[3] * scale_y
                    for line in lines:
                        l_clean = line.strip()
                        if l_clean:
                            all_tokens.append(
                                OcrToken(
                                    text=l_clean,
                                    bbox_px=[(bx0, by0), (bx1, by0), (bx1, by1), (bx0, by1)],
                                    confidence=1.0,
                                )
                            )
        except Exception as exc:
            logger.debug("Native text scale extraction fallback: %s", exc)

        if ratio_scale is None:
            try:
                from app.ocr.parsers import classify_tokens

                classified = classify_tokens(all_tokens)
                best_scale = max(classified["scales"], key=lambda s: s.confidence, default=None)
                if best_scale is not None and best_scale.ratio is not None and best_scale.confidence >= 0.8:
                    ratio_scale = scale_ft_per_px_from_ratio(best_scale.ratio, page.dpi)
            except Exception as exc:
                print(f"[Protake] Scale auto-detection notice: {exc}")

        try:
            from app.geometry.dimension_scale import (
                disagrees_with_prior,
                measure_scale_from_dimensions,
            )

            measured = measure_scale_from_dimensions(
                all_tokens, page.width_px or 0, page.height_px or 0, ratio_scale
            )
            if measured is not None and (
                ratio_scale is None or disagrees_with_prior(measured.ft_per_px, ratio_scale)
            ):
                logger.info(
                    "Blueprint %s page %s: scale measured from %d gridline bays "
                    "(%s, spread %.1f%%) = %.6f ft/px, overriding printed-note scale %s",
                    page.blueprint_id,
                    page.page_number,
                    measured.samples,
                    measured.unit,
                    measured.relative_spread * 100,
                    measured.ft_per_px,
                    f"{ratio_scale:.6f}" if ratio_scale else "none",
                )
                return (measured.ft_per_px, SCALE_SOURCE_MEASURED)
        except Exception as exc:
            print(f"[Protake] Dimension-scale measurement notice: {exc}")

        # The printed note, when the sheet's own dimensions could not be read.
        return (ratio_scale, SCALE_SOURCE_PRINTED) if ratio_scale else None

    def _persist_schedule_items(self, page: Page) -> None:
        """Schedule sheets (door/window schedules) are marked non-eligible
        for room/wall takeoff, but their table data is exactly what a
        real quantity — not a visual guess — for door/window counts looks
        like. Self-gating: does nothing if no door/window schedule table
        is actually present on the page.
        """
        from app.ocr.schedule_parser import parse_schedule_pdf_page

        try:
            items = parse_schedule_pdf_page(page.blueprint.file_path, page.page_number)
        except Exception as exc:
            print(f"[Protake] Schedule parser notice: {exc}")
            return

        for item in items:
            self.schedule_items.create(
                page_id=page.id,
                schedule_type=DetectionKind.DOOR if item.schedule_type == "door" else DetectionKind.WINDOW,
                item_code=item.item_code,
                quantity=item.quantity,
                attributes=item.attributes,
                confidence=0.85,
                status=ReviewStatus.PENDING,
            )

    def run_geometry_analysis(self, page: Page, doc_ctx_dict: dict | None = None) -> GeometryResult:
        # A page that already carries a scale was calibrated by a user; a
        # scale read off the sheet by OCR counts as known too. Anything else
        # is the 1/8"=1'-0" assumption, which the geometry engine must not
        # treat as authoritative when sizing filters.
        scale = page.scale_ft_per_px or default_scale_ft_per_px(page.dpi)
        scale_is_calibrated = page.scale_ft_per_px is not None

        # OCR always runs once here now, not only when uncalibrated. This
        # isn't new cost: Step 4 below already ran OCR fresh whenever
        # `page_ocr_tokens` came in as None (i.e. every already-calibrated
        # page paid for it anyway, just later and for a different reason).
        # Running it up front means its result can also be used to erase
        # text from the wall-band mask before wall/room geometry is derived
        # from it (see analyze_page's `ocr_text_boxes_px`) — printed room
        # labels are bold/underlined thick enough to otherwise survive
        # stroke-thickness selection as spurious "walls".
        self._set_stage(page.blueprint, f"Reading labels & scale via OCR (page {page.page_number})…")
        page_ocr_tokens = self._run_page_ocr(page)
        ocr_text_boxes_px = [
            (
                min(p[0] for p in tok.bbox_px),
                min(p[1] for p in tok.bbox_px),
                max(p[0] for p in tok.bbox_px),
                max(p[1] for p in tok.bbox_px),
            )
            for tok in page_ocr_tokens
        ]

        # Room-name labels, classified from text pattern alone (no
        # dependency on room polygons — see ocr.parsers.classify_tokens) so
        # they're available before geometry runs. Passed into analyze_page
        # purely as a last-resort split hint for a region wall data alone
        # can't separate; every existing room gate still applies to what it
        # produces, this never invents area/shape by itself.
        from app.ocr.parsers import classify_tokens

        ocr_room_label_centroids_px = [
            label.centroid_px for label in classify_tokens(page_ocr_tokens)["rooms"]
        ]

        # Resolve the page's scale BEFORE geometry runs, and keep WHERE it
        # came from  geometry needs to tell a measured scale from an
        # assumed one to know whether real-world size gates may be applied
        # at all (see metrics.ScaleContext).
        scale_source = page.scale_source or (SCALE_SOURCE_USER if page.scale_ft_per_px is not None else SCALE_SOURCE_ASSUMED)
        if page.scale_ft_per_px is None:
            detected = self._detect_scale_from_tokens(page, page_ocr_tokens)
            if detected is not None:
                scale, scale_source = detected
                scale_is_calibrated = True
                self.pages.update(page, scale_ft_per_px=scale, scale_source=scale_source)

        # Persist provenance even when scale stayed unresolved (assumed
        # default) — a page silently running on the fallback scale must be
        # explicitly queryable as such, not indistinguishable from one no
        # one has looked at yet. Measured on a real raster-only sheet: an
        # assumed scale swung detected room count from 17 to 4 with no
        # error raised and nothing to flag it for review (see room-recall
        # diagnostic). A no-op when the branch above already wrote the same
        # value, since `page.scale_source` is updated in place by then.
        if page.scale_source != scale_source:
            self.pages.update(page, scale_source=scale_source)

        scale_context = (
            ScaleContext.from_ft_per_px(scale, scale_source, dpi=page.dpi)
            if scale_is_calibrated
            else ScaleContext.assumed(page.dpi)
        )

        # Step 1: Quick sanity check BEFORE heavy geometry (saves time on unreadable pages)
        import cv2  # noqa: E401
        img_gray = cv2.imread(page.image_path, cv2.IMREAD_GRAYSCALE)
        if img_gray is None:
            # Can't read image — mark as skip
            self.pages.update(
                page,
                page_type="empty_blank",
                is_takeoff_eligible=False,
                skip_reason="Could not read rasterized page image",
                geometry_processed=True,
            )
            return GeometryResult(rooms=[], walls=[], wall_segment_count_raw=0, wall_segment_count_merged=0)

        # Step 2: Run geometry engine — classification (with real title-block
        # text from the original PDF) happens inside, and its result rides
        # along on GeometryResult so we don't classify twice.
        # Only set when a project has an explicit, persisted trade
        # selection (app.models.trade.TradeConfig) — None for every other
        # project, never defaulted/guessed. See PageContext.selected_trade.
        project = page.blueprint.project
        selected_trade = (
            project.trade_configs[0].trade.value if project and project.trade_configs else None
        )

        # D-005: Extract per-page context entry from the whole-document pre-pass.
        # This tells analyze_page the sheet's authoritative type (floor_plan, rcp,
        # partition_schedule) so wall/room processing can use it, and provides the
        # list of RCP pages needed for height resolution at geometry time.
        doc_ctx_entry: dict | None = None
        if doc_ctx_dict:
            doc_ctx_entry = (doc_ctx_dict.get("pages") or {}).get(str(page.page_number))

        # D-005: Resolve ceiling height from RCP sheets before geometry runs.
        # Walls stored in DB get height_ft/height_source from the verified annotation
        # rather than the 9.0 ft project default. Falls back to ASSUMED if no RCP found.
        rcp_page_numbers: list[int] = (
            (doc_ctx_dict or {}).get("authoritative_sheets", {}).get("reflected_ceiling_plan", [])
        )
        if rcp_page_numbers:
            _rcp_height, _rcp_source, _rcp_ev_type = _extract_height_from_rcp_pages(
                page.blueprint.file_path, rcp_page_numbers
            )
        else:
            _rcp_height, _rcp_source, _rcp_ev_type = 9.0, "DEFAULT", "ASSUMED"
        height_is_verified = _rcp_ev_type != "ASSUMED"

        self._set_stage(page.blueprint, f"Detecting rooms & walls (page {page.page_number})…")
        result = analyze_page(
            page.image_path,
            scale_ft_per_px=scale,
            pdf_path=page.blueprint.file_path,
            page_number=page.page_number,
            scale_is_calibrated=scale_is_calibrated,
            ocr_text_boxes_px=ocr_text_boxes_px,
            ocr_room_label_centroids_px=ocr_room_label_centroids_px,
            scale_context=scale_context,
            selected_trade=selected_trade,
            doc_ctx_entry=doc_ctx_entry,
        )

        # D-005: Apply verified height to all detected walls so the DB row carries
        # the correct height_ft instead of the GeometryWall default of 9.0 ft.
        if height_is_verified:
            for _gw in result.walls:
                _gw.height_ft = _rcp_height
                _gw.height_source = _rcp_ev_type
            logger.info(
                "Blueprint %s page %s: height resolved from %s = %.1f ft (evidence: %s)",
                page.blueprint_id, page.page_number, _rcp_source, _rcp_height, _rcp_ev_type,
            )

        # Step 3: Persist classifier decision into the DB page row
        self.pages.update(
            page,
            page_type=result.page_type,
            is_takeoff_eligible=result.is_takeoff_eligible,
            skip_reason=result.skip_reason,
            discipline=result.discipline,
            primary_title=result.primary_title,
            classification_confidence=result.classification_confidence,
            geometry_authority=result.geometry_authority,
        )

        # Step 4: Scan and persist any schedule table items if present on the page
        self._persist_schedule_items(page)

        # Step 5: Only save rooms/walls for takeoff-eligible pages
        if not result.is_takeoff_eligible:
            self.pages.update(page, geometry_processed=True)
            return result  # rooms=[], walls=[] for non-eligible pages

        # Step 4: Run OCR pipeline to label rooms with real text from blueprint (Master Bedroom, Kitchen, etc.)
        # Reuse tokens from the scale-detection OCR pass above if we already
        # ran one for this page, instead of paying for OCR inference twice.
        room_names: dict[int, str] = {}
        try:
            from app.ocr.pipeline import run_ocr_pipeline
            ocr_res = run_ocr_pipeline(
                image_path=page.image_path,
                geometry=result,
                scale_ft_per_px=scale,
                image_w=page.width_px or 3000,
                image_h=page.height_px or 2000,
                tokens=page_ocr_tokens,
            )
            room_names = ocr_res.room_name_overrides
        except Exception as ocr_exc:
            print(f"[Protake] OCR notice: {ocr_exc}")

        # Run AI validation first so its symbol detections (doors, furniture)
        # can inform candidate taxonomy typing.
        if get_settings().ai_validation_enabled:
            self._set_stage(page.blueprint, f"Detecting doors & windows (page {page.page_number})…")
            try:
                from app.services.analysis_service import AnalysisService

                yolo_exclude = []
                if result.windows:
                    yolo_exclude.extend(["windows", "window"])
                if getattr(result, "doors", None):
                    yolo_exclude.extend(["doors", "door"])
                if getattr(result, "stairs", None):
                    yolo_exclude.extend(["stairs", "stair"])

                ai_detections = AnalysisService(self.db).run_ai_validation(
                    page,
                    geometry=result,
                    ocr_text_boxes_px=ocr_text_boxes_px,
                    # The vector layer already found every window/door/stair on this
                    # page — every YOLO model's own guesses would only ever
                    # be redundant duplicates.
                    exclude_yolo_classes=yolo_exclude if yolo_exclude else None,
                )
            except Exception as ai_exc:
                # Absent or unloadable weights, or an inference failure, must
                # never cost the page the rooms and walls it already has.
                logger.warning(
                    "Blueprint %s page %s: AI symbol detection skipped: %s",
                    page.blueprint_id,
                    page.page_number,
                    ai_exc,
                )

        # Step 4b: Reference-Object Scale Calibration (Door/Window Calibration)
        # Priority order:
        # 1. User Calibration (SCALE_SOURCE_USER)
        # 2. Printed Scale (SCALE_SOURCE_PRINTED)
        # 3. Dimension Gridlines (SCALE_SOURCE_MEASURED)
        # 4. Reference-Object Calibration (SCALE_SOURCE_REFERENCE_OBJECT) — Triggered HERE if 1-3 were uncalibrated/assumed
        # 5. Assumed Default (SCALE_SOURCE_ASSUMED)
        if page.scale_source in (SCALE_SOURCE_ASSUMED, None):
            all_ref_candidates = list(locals().get("ai_detections", []))
            if getattr(result, "doors", None):
                all_ref_candidates.extend(result.doors)

            if all_ref_candidates:
                ref_ctx, ref_diag = calibrate_scale_from_reference_objects(
                    detections=all_ref_candidates,
                    dpi=page.dpi or 150.0,
                    sheet_width_px=float(page.width_px or 3300.0),
                )

                if ref_ctx is not None and ref_ctx.is_calibrated and ref_ctx.ft_per_px > 0:
                    new_scale = ref_ctx.ft_per_px
                    logger.info(
                        "Blueprint %s page %s: Calibrated scale from reference objects (%s tier, %d doors/windows) = %.6f ft/px (overriding assumed scale %s) — re-running geometry at correct scale",
                        page.blueprint_id,
                        page.page_number,
                        ref_diag.get("tier_used"),
                        ref_diag.get("door_candidates_inliers", 0),
                        new_scale,
                        f"{scale:.6f}" if scale else "none",
                    )

                    # D-002: Re-derive geometry at the calibrated scale instead of
                    # multiplying in-place. Post-hoc multiplication corrupts geometry
                    # because filters (minimum wall length, room area thresholds) that
                    # fired at the WRONG scale during the first pass can't be un-fired —
                    # walls that should have passed but were too short at the assumed
                    # scale are already gone; walls that shouldn't have passed because
                    # they were long enough only at the assumed scale are already in.
                    # Re-running from scratch at the correct scale gives geometry that
                    # was produced with the right physical constraints from the start.
                    scale = new_scale
                    scale_is_calibrated = True
                    self.pages.update(page, scale_ft_per_px=new_scale, scale_source=SCALE_SOURCE_REFERENCE_OBJECT)
                    new_scale_context = ScaleContext.from_ft_per_px(new_scale, SCALE_SOURCE_REFERENCE_OBJECT, dpi=page.dpi)
                    result = analyze_page(
                        page.image_path,
                        pdf_path=page.blueprint.file_path,
                        page_number=page.page_number,
                        scale_is_calibrated=True,
                        ocr_text_boxes_px=ocr_text_boxes_px,
                        ocr_room_label_centroids_px=ocr_room_label_centroids_px,
                        scale_context=new_scale_context,
                        selected_trade=selected_trade,
                        doc_ctx_entry=doc_ctx_entry,
                    )
                    if height_is_verified:
                        for _gw in result.walls:
                            _gw.height_ft = _rcp_height
                            _gw.height_source = _rcp_ev_type


        from app.models.enums import RoomType, DetectionKind
        from shapely.geometry import Polygon, box
        
        # Build symbol boxes for density / adjacency checks
        door_boxes = []
        furn_boxes = []
        
        # AI detections
        ai_detections = locals().get("ai_detections", [])
        for det in ai_detections:
            if getattr(det, 'bbox_norm', None):
                b = det.bbox_norm
                rect = box(b['minX'], b['minY'], b['maxX'], b['maxY'])
                if det.kind == DetectionKind.DOOR:
                    door_boxes.append(rect)
                elif det.kind in (DetectionKind.OBJECT, DetectionKind.FIXTURE):
                    furn_boxes.append(rect)
                    
        # Vector doors
        for door in getattr(result, "doors", []):
            if getattr(door, 'bbox_norm', None):
                b = door.bbox_norm
                door_boxes.append(box(b['minX'], b['minY'], b['maxX'], b['maxY']))
                
        # First pass: assign types by OCR / Door adjacency
        candidate_info = []
        for idx, room in enumerate(result.rooms):
            confirmed_name = room_names.get(idx) or room.name
            poly = Polygon(room.polygon_norm)
            
            name_lower = confirmed_name.lower()
            if any(word in name_lower for word in ['deck', 'porch', 'patio', 'covered', 'trellis', 'outdoor', 'terrace', 'balcony', 'canopy', 'veranda', 'gazebo', 'breezeway']):
                taxonomy_type = RoomType.EXTERIOR_COVERED.value
            else:
                taxonomy_type = room.room_type
                if not taxonomy_type:
                    door_touch = any(poly.intersects(d) or poly.distance(d) < 0.01 for d in door_boxes)
                    if any(word in name_lower for word in ['corridor', 'hall', 'passage', 'walkway']):
                        taxonomy_type = RoomType.CORRIDOR.value
                    elif any(word in name_lower for word in ['room', 'bath', 'bed', 'kitchen', 'office', 'closet', 'living', 'dining', 'lounge']) or door_touch:
                        taxonomy_type = RoomType.INTERIOR_ROOM.value
                    else:
                        taxonomy_type = RoomType.UNKNOWN.value
                        
            candidate_info.append({
                "idx": idx,
                "room": room,
                "name": confirmed_name,
                "type": taxonomy_type,
                "poly": poly
            })
            
        # Second pass: Nesting check (SUB_PARTITION)
        for c in candidate_info:
            if c["type"] == RoomType.EXTERIOR_COVERED.value:
                continue
            poly_inner = c["poly"].buffer(-1e-6)
            enclosing = [o for o in candidate_info if o["idx"] != c["idx"] and o["poly"].contains(poly_inner)]
            
            if enclosing:
                # To prevent cascading misclassification, only type as SUB_PARTITION if nested
                # inside an already-established valid envelope (INTERIOR_ROOM, CORRIDOR, etc)
                valid_outers = [o for o in enclosing if o["type"] in (
                    RoomType.INTERIOR_ROOM.value,
                    RoomType.CORRIDOR.value,
                )]
                if valid_outers:
                    c["type"] = RoomType.SUB_PARTITION.value
                    
        # Clean existing page entities before persisting newly analyzed ones
        self.rooms.clear_for_page(page.id)
        self.walls.clear_for_page(page.id)
        self.detections.clear_for_page(page.id)

        room_id_by_index: dict[int, int] = {}
        created_rooms: list[Room] = []
        room_rejected_count = 0
        for c in candidate_info:
            # status/rejection_reasons come from room_validation's
            # context-aware gate (drawing zone + low wall-contact — see
            # engine.py's room-creation loop). A REJECTED room is still
            # persisted, not dropped — distinguishable from an ordinary
            # reviewable room in the same review queue, mirroring how
            # Wall rows already work (see wall_validation.py).
            if c["room"].status == ReviewStatus.REJECTED:
                room_rejected_count += 1
            db_room = self.rooms.create(
                page_id=page.id,
                name=c["name"],
                room_type=c["type"],
                polygon_norm=c["room"].polygon_norm,
                bbox_norm=c["room"].bbox_norm,
                centroid_norm=c["room"].centroid_norm,
                area_sqft=c["room"].area_sqft,
                perimeter_ft=c["room"].perimeter_ft,
                confidence=c["room"].confidence,
                source=DetectionSource.GEOMETRY,
                status=c["room"].status,
            )
            room_id_by_index[c["idx"]] = db_room.id
            created_rooms.append(db_room)
        if candidate_info:
            logger.info(
                "Blueprint %s page %s: %d room candidates, %d rejected (outside drawing zone / "
                "low wall contact), %d accepted for review",
                page.blueprint_id, page.page_number, len(candidate_info), room_rejected_count,
                len(candidate_info) - room_rejected_count,
            )

        # D-012: Canonical Room Merging Engine
        # When candidate room polygons represent the same physical room (IoU >= 0.70 or
        # sub-region coverage >= 0.80), merge them into a canonical room:
        # 1. Synthesizes union geometry with exact recalculation of area and perimeter.
        # 2. Preserves evidence from all contributing sources (names, finishes, provenance).
        # 3. Boosts confidence to reward independent multi-source verification.
        # 4. Remaps all wall-room associations to canonical_room_id.
        from app.geometry.duplicate_service import merge_room_candidates

        merge_results = merge_room_candidates(created_rooms, scale_ft_per_px=scale or 0.0)
        for mr in merge_results:
            keeper = next((r for r in created_rooms if r.id == mr.canonical_room_id), None)
            if keeper is None:
                continue

            # Update keeper with synthesized canonical attributes
            self.rooms.update(
                keeper,
                name=mr.merged_name,
                room_type=mr.merged_room_type,
                floor_finish=mr.merged_floor_finish,
                wall_finish=mr.merged_wall_finish,
                ceiling_finish=mr.merged_ceiling_finish,
                polygon_norm=mr.merged_polygon_norm,
                bbox_norm=mr.merged_bbox_norm,
                centroid_norm=mr.merged_centroid_norm,
                area_sqft=mr.merged_area_sqft,
                perimeter_ft=mr.merged_perimeter_ft,
                confidence=mr.merged_confidence,
            )

            # Remap wall-room index mapping from absorbed rooms to canonical keeper
            for abs_id in mr.absorbed_room_ids:
                room_id_by_index = {
                    i: (keeper.id if rid == abs_id else rid)
                    for i, rid in room_id_by_index.items()
                }
                absorbed_r = next((r for r in created_rooms if r.id == abs_id), None)
                if absorbed_r:
                    self.rooms.delete(absorbed_r)

            logger.info(
                "Blueprint %s page %s: canonical room merge complete — '%s' (Canonical ID %d, %.0f sqft, conf %.2f, %d evidence sources preserved, %d absorbed)",
                page.blueprint_id, page.page_number,
                mr.merged_name, mr.canonical_room_id, mr.merged_area_sqft, mr.merged_confidence,
                len(mr.evidence_sources), len(mr.absorbed_room_ids),
            )

        wall_rejected_count = 0
        for wall in result.walls:
            # status/rejection_reasons come from wall_validation's
            # context-aware gate (drawing zone + isolated/unlinked/interior
            # evidence — see engine.py's wall loop). A REJECTED wall is
            # still persisted, not dropped, so nothing here is silently
            # deleted — it is just distinguishable from an ordinary
            # reviewable wall in the same review queue Detection rows
            # already use this status for (see FORENSIC_AUDIT_REPORT.md §9).
            if wall.status == ReviewStatus.REJECTED:
                wall_rejected_count += 1
            db_wall = self.walls.create(
                page_id=page.id,
                room_id=room_id_by_index.get(wall.room_index) if wall.room_index is not None else None,
                start_norm=wall.start_norm,
                end_norm=wall.end_norm,
                length_ft=wall.length_ft,
                height_ft=wall.height_ft,  # DEF-01: propagate from GeometryWall, not hardcoded 9.0
                # Measured from the drawing when the wall mask supported it,
                # otherwise the model's assumed stud-wall default.
                thickness_ft=(
                    wall.thickness_ft if wall.thickness_ft is not None else DEFAULT_WALL_THICKNESS_FT
                ),
                thickness_measured=wall.thickness_measured,
                wall_type=WallType.EXTERIOR if wall.wall_type == "exterior" else WallType.INTERIOR,
                wall_type_code=getattr(wall, "wall_type_code", None),
                confidence=wall.confidence,
                source=DetectionSource.GEOMETRY,
                status=wall.status,
            )
            db_wall.face_a_segment_id = wall.face_a_segment_id
            db_wall.face_b_segment_id = wall.face_b_segment_id
            db_wall.face_a_coords = wall.face_a_coords
            db_wall.face_b_coords = wall.face_b_coords
            db_wall.overlap_ratio = wall.overlap_ratio
            # DEF-01/DEF-10: persist height provenance from the geometry engine.
            db_wall.height_source = getattr(wall, "height_source", "ASSUMED")
            # DEF-03: persist fine-grained source tag from GeometryWall.source.
            db_wall.source_tag = getattr(wall, "source", None)
        if result.walls:
            logger.info(
                "Blueprint %s page %s: %d wall candidates, %d rejected (outside drawing zone / "
                "isolated-unlinked-interior), %d accepted for review",
                page.blueprint_id, page.page_number, len(result.walls), wall_rejected_count,
                len(result.walls) - wall_rejected_count,
            )

        # Windows the PDF's own WINDOW vector layer already found are a
        # real geometric measurement (see vector_windows.py), not a guess —
        # persisted with source=GEOMETRY like rooms/walls above, ahead of
        # the YOLO pass below rather than alongside it.
        for window in result.windows:
            self.detections.create(
                page_id=page.id,
                kind=DetectionKind.WINDOW,
                label="Window",
                trade=None,
                polygon_norm=window.polygon_norm,
                bbox_norm=window.bbox_norm,
                confidence=1.0,
                source=DetectionSource.GEOMETRY,
                status=ReviewStatus.PENDING,
            )

        # Doors from vector DOOR layer are also persisted directly
        for door in getattr(result, "doors", []):
            self.detections.create(
                page_id=page.id,
                kind=DetectionKind.DOOR,
                label="Door",
                trade=None,
                polygon_norm=door.polygon_norm,
                bbox_norm=door.bbox_norm,
                confidence=1.0,
                source=DetectionSource.GEOMETRY,
                status=ReviewStatus.PENDING,
            )

        # Stairs from vector stair layer are also persisted directly
        for stair in getattr(result, "stairs", []):
            self.detections.create(
                page_id=page.id,
                kind=DetectionKind.STAIRS,
                label="Stairs",
                trade=None,
                polygon_norm=stair.polygon_norm,
                bbox_norm=stair.bbox_norm,
                confidence=1.0,
                source=DetectionSource.GEOMETRY,
                status=ReviewStatus.PENDING,
            )

        # Doors, windows and fixtures are symbols, not quantities, so they
        # come from the trained YOLO segmentation model rather than the
        # geometry engine (`best.pt` carries door / windows / cav-sliders
        # classes; validation_engine maps them onto DetectionKind).
        #
        # This used to be reachable only via POST /pages/{id}/ai-validate,
        # which nothing ever called — so `detections` stayed empty and no
        # door ever reached the UI despite the model being trained and
        # configured. Running it here, on the geometry just computed, means
        # symbols land together with rooms and walls in the same pass.
        try:
            self.associate_ocr_codes_with_detections(page.id, page_ocr_tokens)
        except Exception as assoc_exc:
            logger.warning("Failed to associate OCR codes to detections: %s", assoc_exc)

        self.pages.update(page, geometry_processed=True)
        return result


    def _set_stage(self, blueprint: Blueprint, stage: str) -> None:
        """Record what the background worker is doing right now, and commit
        immediately so a client polling GET /blueprints/{id} sees it live.

        `pages_processed` alone is too coarse for user-facing progress: it
        only advances once an entire page finishes, and one page's
        rasterize+geometry+OCR can take 1-3 minutes — long enough that the
        percentage bar sits frozen the whole time and then jumps in one
        step. This gives the client something to show (and animate toward)
        during that gap instead of nothing.
        """
        self.blueprints.update(blueprint, current_stage=stage)
        self.db.commit()

    def process_single_page(self, blueprint: Blueprint, page_index: int, num_pages: int, doc_ctx_dict: dict | None = None) -> Page:
        """Rasterize + persist + geometry-analyze exactly one page. Any
        failure is isolated to this page and recorded on its own Page row
        instead of propagating — the caller is responsible for committing
        once this returns (see `process_all_pages`)."""
        page_number = page_index + 1

        self._set_stage(blueprint, f"Rasterizing page {page_number} of {num_pages}…")
        try:
            rp = rasterize_page(
                blueprint.file_path,
                page_index,
                page_image_path(blueprint.id, page_number),
                page_thumbnail_path(blueprint.id, page_number),
            )
        except Exception as exc:
            # Couldn't even rasterize this page (corrupt page data) — record
            # a stub so the sheet count stays honest and move on to the
            # next page; nothing else in the set is affected.
            logger.warning("Blueprint %s page %s failed to rasterize: %s", blueprint.id, page_number, exc)
            return self.pages.create(
                blueprint_id=blueprint.id,
                page_number=page_number,
                sheet_code=None,  # genuinely unreadable — never fabricate a page-index code
                sheet_name=f"Sheet {page_number}",
                width_px=1,
                height_px=1,
                image_path="",
                geometry_processed=True,
                is_takeoff_eligible=False,
                page_type="empty_blank",
                skip_reason=f"Could not rasterize page: {exc}",
            )

        page = self.pages.create(
            blueprint_id=blueprint.id,
            page_number=rp.page_number,
            sheet_code=rp.sheet_code,
            sheet_name=rp.sheet_name,
            width_px=rp.width_px,
            height_px=rp.height_px,
            dpi=rp.dpi,
            image_path=rp.image_path,
            thumbnail_path=rp.thumbnail_path,
        )

        # run_geometry_analysis sets its own stage messages (OCR first, then
        # geometry) in the right order — nothing to set here.
        try:
            self.run_geometry_analysis(page, doc_ctx_dict=doc_ctx_dict)
        except Exception as exc:
            # Geometry/OCR blew up on this one page — isolate the failure
            # so every other page in the document keeps processing. The
            # rasterized image is still there; the page is just marked
            # non-eligible instead of silently missing rooms/walls.
            logger.warning("Blueprint %s page %s failed geometry analysis: %s", blueprint.id, page_number, exc)
            self.pages.update(
                page,
                geometry_processed=True,
                is_takeoff_eligible=False,
                page_type="empty_blank",
                skip_reason=f"Geometry analysis failed: {exc}",
            )

        return page

    def process_all_pages(self, blueprint: Blueprint) -> list[Page]:
        """Processes every page, committing immediately as each finishes.
        This replaces the old all-or-nothing approach (rasterize every
        page, analyze every page, one giant transaction committed only at
        the very end) with two guarantees that matter for large,
        multi-page sheet sets:

          1. A crash or timeout partway through never rolls back pages
             already finished — they're committed as they land.
          2. One bad page (corrupt scan, OCR exception) is isolated by
             `process_single_page` and never takes the rest of the
             document down with it.

        Pages run up to PAGE_PARALLELISM at a time (see that constant) via
        a process pool local to this call, instead of one at a time in this
        single worker — measured at ~2-3 minutes/page on a real CAD set
        (OCR + geometry + 4-model AI validation each), a 14-page document
        previously paid for all of that fully sequentially no matter how
        many CPU cores were actually idle.
        """
        blueprint_id = blueprint.id
        self.blueprints.update(
            blueprint, status=BlueprintStatus.PROCESSING, pages_processed=0, current_stage="Opening blueprint…"
        )
        self.db.commit()

        try:
            num_pages = get_page_count(blueprint.file_path)
        except Exception as exc:
            self.blueprints.update(
                blueprint, status=BlueprintStatus.FAILED, processing_error=f"Could not read blueprint file: {exc}"
            )
            self.db.commit()
            return []

        # Whole-document understanding pass: reads every page's text and
        # classifies it (both the live takeoff-eligibility classifier and the
        # schedule-authority classifier) BEFORE any per-page geometry
        # detection starts. Observation-only for now — nothing below acts on
        # a divergence — but it makes the document set's shape (which sheets
        # are eligible, where the two classifiers disagree) visible ahead of
        # detection instead of only discoverable after the fact, and it is
        # the first read of the document that isn't scoped to one page.
        doc_ctx_dict: dict | None = None
        try:
            document_context = build_document_context(blueprint.file_path)
            logger.info("Blueprint %s: %s", blueprint_id, document_context.summary_line())
            for divergence in document_context.classification_divergences:
                logger.warning(
                    "Blueprint %s classification divergence: %s", blueprint_id, divergence.reason
                )
            # D-005: Serialize the document context for per-page workers. A plain dict
            # survives process-pool pickling; the full DocumentContext dataclass does not
            # cross the process boundary cleanly on all platforms.
            doc_ctx_dict = document_context.to_dict()
        except Exception as exc:
            # This pass is diagnostic-only in this phase — a failure here
            # must never block the per-page pipeline that already works.
            logger.warning("Blueprint %s: document understanding pass failed (non-fatal): %s", blueprint_id, exc)

        # Record existing page IDs for safe transactional replacement upon completion
        existing_pages = self.pages.find(blueprint_id=blueprint_id)
        old_page_ids = [p.id for p in existing_pages] if existing_pages else []

        # Safe worker strategy: serialize multi-page PDFs (num_pages > 2) to eliminate model duplication & OOM
        worker_count = 1 if num_pages > 2 else max(1, min(PAGE_PARALLELISM, num_pages))
        logger.info("Blueprint %s: processing %d pages with worker_count=%d", blueprint_id, num_pages, worker_count)

        import gc
        completed = 0

        if worker_count == 1:
            # Serialized execution with explicit memory garbage collection per page
            for page_index in range(num_pages):
                self._set_stage(blueprint, f"Processing page {page_index + 1} of {num_pages}…")
                _process_one_page_standalone(blueprint_id, page_index, num_pages, doc_ctx_dict=doc_ctx_dict)
                completed += 1
                self.blueprints.update(blueprint, pages_processed=completed)
                self.db.commit()
                gc.collect()
        else:
            from concurrent.futures import ProcessPoolExecutor, as_completed
            from concurrent.futures.process import BrokenProcessPool

            with ProcessPoolExecutor(max_workers=worker_count) as executor:
                futures = {
                    executor.submit(_process_one_page_standalone, blueprint_id, page_index, num_pages, doc_ctx_dict): page_index
                    for page_index in range(num_pages)
                }
                for future in as_completed(futures):
                    try:
                        future.result()
                    except BrokenProcessPool as exc:
                        raise RuntimeError(
                            f"Worker crashed on multi-page blueprint {blueprint_id}. Use serialized execution."
                        ) from exc
                    completed += 1
                    self.blueprints.update(blueprint, pages_processed=completed)
                    self.db.commit()
                    gc.collect()

        # Clean old staged records now that all new pages have successfully completed
        if old_page_ids:
            try:
                self.architectural_walls.clear_for_pages(old_page_ids)
                self.walls.clear_for_pages(old_page_ids)
                self.rooms.clear_for_pages(old_page_ids)
                self.detections.clear_for_pages(old_page_ids)
                self.db.query(Page).filter(Page.id.in_(old_page_ids)).delete(synchronize_session=False)
                self.db.commit()
            except Exception as clean_exc:
                logger.warning("Blueprint %s: non-fatal error cleaning old page records: %s", blueprint_id, clean_exc)

        pages = sorted(self.pages.find(blueprint_id=blueprint_id), key=lambda p: p.page_number)
        try:
            self.generate_and_persist_canonical_takeoff(blueprint)
        except Exception as canon_exc:
            logger.exception("Blueprint %s canonical takeoff pipeline failed (non-fatal): %s", blueprint_id, canon_exc)

        self.blueprints.update(blueprint, status=BlueprintStatus.PROCESSED, current_stage="Done")
        self.db.commit()
        return pages

    def generate_and_persist_canonical_takeoff(self, blueprint: Blueprint) -> None:
        """Whole-blueprint post-processing step:
        1. Classifies all sheets & parses schedules across multi-sheet set.
        2. Persists ProjectKnowledgeGraph for document-level authority.
        3. Executes canonical DrywallSemanticWallPipeline.
        4. Persists canonical ArchitecturalWallModel rows with 2D polygon & opening clipping.
        5. Computes and persists initial Drywall TradeTakeoff snapshot.
        """
        from app.intelligence.cross_sheet_reconciler import CrossSheetReconciler
        from app.intelligence.schedule_parser import MultiSheetScheduleParser
        from app.intelligence.schedule_table_parser import ScheduleTableParser
        from app.intelligence.sheet_classifier import BlueprintSheetClassifier
        from app.models.detection import Detection
        from app.models.enums import TradeKey
        from app.models.project_knowledge_graph import PartitionScheduleEntry, ProjectBlueprintIndex, DetailSheetEntry
        from app.models.room import Room
        from app.models.wall import Wall
        from app.services.trade_takeoff_service import TradeTakeoffService
        from app.trades.drywall_semantic import DrywallSemanticWallPipeline
        from app.geometry.detail_callouts import normalize_sheet_ref

        pages = sorted(self.pages.find(blueprint_id=blueprint.id), key=lambda p: p.page_number)
        if not pages:
            return

        all_page_ids = [p.id for p in pages]
        eligible_pages = [p for p in pages if p.is_takeoff_eligible]
        eligible_page_ids = [p.id for p in eligible_pages]

        # 1. Whole Document Intelligence
        classifier = BlueprintSheetClassifier()
        sched_parser = MultiSheetScheduleParser()
        project_index = ProjectBlueprintIndex(blueprint_id=blueprint.id)

        # Extract page text
        page_text = TradeTakeoffService._extract_page_text(blueprint, pages)

        for p in pages:
            full_text = page_text.get(p.id, {}).get("full", "") or (p.sheet_code or "")
            meta = classifier.classify_sheet(p.id, p.page_number, full_text, getattr(blueprint, "original_filename", None))

            # Reconcile: if the title-block extractor found nothing during rasterization,
            # try to promote the full-OCR result to Page.sheet_code so the UI-facing
            # value gets filled in rather than staying None.
            if p.sheet_code is None and meta.sheet_number is not None:
                self.pages.update(p, sheet_code=meta.sheet_number)

            project_index.sheets[p.id] = meta
            if meta.sheet_number is not None:
                if meta.sheet_type.value == "partition_schedule":
                    project_index.partition_schedules.update(
                        sched_parser.parse_partition_schedule(meta.text_content_full, meta.sheet_number, p.id)
                    )
                elif meta.sheet_type.value == "door_window_schedule":
                    project_index.door_schedules.update(
                        sched_parser.parse_door_schedule(meta.text_content_full, meta.sheet_number, p.id)
                    )
                elif meta.sheet_type.value in ("wall_sections", "details_elevations"):
                    # Indexes section/detail sheets so a "3/A401"-style callout
                    # found near a wall on another sheet can be resolved to real
                    # content — see app.geometry.detail_callouts.
                    key = normalize_sheet_ref(meta.sheet_number)
                    project_index.detail_sheets[key] = DetailSheetEntry(
                        sheet_number=key,
                        page_id=p.id,
                        sheet_type=meta.sheet_type.value,
                        text_content_full=meta.text_content_full,
                    )

        # Schedule Table Parser
        try:
            sched_page_nums = [
                meta.page_number
                for meta in project_index.sheets.values()
                if getattr(meta.sheet_type, "value", str(meta.sheet_type)) == "partition_schedule"
            ]
            schedule_evidence = (
                ScheduleTableParser().parse_pdf_document_schedules(
                    blueprint.file_path, target_pages=sched_page_nums
                )
                if sched_page_nums
                else {}
            )
            for tag_key, ev in schedule_evidence.items():
                if ev.get("verified") and "assembly_definition" in ev:
                    spec = ev["assembly_definition"]
                    if tag_key.upper() not in project_index.partition_schedules:
                        project_index.partition_schedules[tag_key.upper()] = PartitionScheduleEntry(
                            tag=tag_key.upper(),
                            description=getattr(spec, "description", ""),
                            stud_depth_in=getattr(spec, "stud_depth_in", 3.625),
                            stud_gauge=getattr(spec, "stud_gauge", "20 GA"),
                            board_type_side_a=getattr(spec, "board_type_side_a", "5/8\" GWB"),
                            layers_side_a=getattr(spec, "layers_side_a", 1),
                            board_type_side_b=getattr(spec, "board_type_side_b", "5/8\" GWB"),
                            layers_side_b=getattr(spec, "layers_side_b", 1),
                            sides_to_hang=getattr(spec, "sides_to_hang", 2),
                            fire_rating_hr=getattr(spec, "fire_rating_hr", None),
                            sound_rating_stc=getattr(spec, "sound_rating_stc", None),
                            source_sheet_number=ev.get("schedule_sheet", "UNKNOWN"),
                            source_sheet_page_id=ev.get("source_page"),
                            confidence=0.95,
                        )
        except Exception as sched_exc:
            logger.warning("ScheduleTableParser pass notice: %s", sched_exc)
            schedule_evidence = {}

        # 2. Persist Project Knowledge Graph
        try:
            existing_pkg = self.project_knowledge_graphs.for_blueprint(blueprint.id)
            if existing_pkg:
                self.db.delete(existing_pkg)
                self.db.commit()
            pkg_orm = project_index.to_orm()
            self.db.add(pkg_orm)
            self.db.commit()
        except Exception as pkg_exc:
            logger.warning("Could not persist ProjectKnowledgeGraph: %s", pkg_exc)

        from app.geometry.page_classifier import get_trade_relevance, TradeRelevance

        # 3. Load geometry ONLY from drywall-relevant pages (excludes roof_plan, site_plan, demo, etc.)
        drywall_eligible_pages = [
            p for p in pages
            if p.is_takeoff_eligible and get_trade_relevance(p.page_type, "drywall") != TradeRelevance.NOT_RELEVANT
        ]
        drywall_page_ids = [p.id for p in drywall_eligible_pages]

        all_rooms = self.db.query(Room).filter(Room.page_id.in_(drywall_page_ids)).all() if drywall_page_ids else []
        all_walls = self.db.query(Wall).filter(Wall.page_id.in_(drywall_page_ids)).all() if drywall_page_ids else []
        all_detections = self.db.query(Detection).filter(Detection.page_id.in_(drywall_page_ids)).all() if drywall_page_ids else []

        opening_dets = [d for d in all_detections if d.kind in (DetectionKind.DOOR, DetectionKind.WINDOW)]
        page_scale_info = {
            p.id: {
                "scale_ft_per_px": p.scale_ft_per_px or 0.0,
                "width_px": p.width_px or 0,
                "height_px": p.height_px or 0,
                # DEF-02: scale_source must be propagated so QTO gate can block assumed-scale pages.
                "scale_source": p.scale_source or SCALE_SOURCE_ASSUMED,
            }
            for p in pages
        }
        text_items = {
            page_id: t["items"]
            for page_id, t in page_text.items()
            if page_id != "_extraction_failed"
        }

        # 4. Run canonical DrywallSemanticWallPipeline
        pipeline = DrywallSemanticWallPipeline(schedule_evidence=schedule_evidence)
        arch_walls = pipeline.process_architectural_walls(
            all_rooms,
            all_walls,
            classifications=None,
            text_items_by_page=text_items,
            opening_detections=opening_dets if opening_dets else None,
            page_scale_info=page_scale_info,
            detail_sheets=project_index.detail_sheets,
            include_rejected=False,
        )

        # 5. Cross-sheet reconciliation
        reconciler = CrossSheetReconciler(project_index)
        reconciled_walls = []
        for aw in arch_walls:
            rec_wall, _ = reconciler.reconcile_wall(aw)
            reconciled_walls.append(rec_wall)
        arch_walls = reconciled_walls

        # 6. Clear and persist canonical ArchitecturalWallModel rows
        for pid in all_page_ids:
            self.architectural_walls.clear_for_page(pid)

        for aw in arch_walls:
            orm_wall = aw.to_orm()
            self.db.add(orm_wall)
        self.db.commit()

        # 7. Compute & persist initial Drywall takeoff
        try:
            trade_svc = TradeTakeoffService(self.db)
            if trade_svc.is_supported(TradeKey.DRYWALL):
                trade_svc.compute_and_persist(TradeKey.DRYWALL, blueprint, blueprint.project_id, blueprint.uploaded_by_id)
        except Exception as takeoff_exc:
            logger.warning("Initial drywall takeoff compute notice: %s", takeoff_exc)

    def calibrate_page(
        self,
        page: Page,
        point_a: tuple[float, float],
        point_b: tuple[float, float],
        real_world_value: float,
        unit: str = "ft",
        reprocess: bool = True,
    ) -> Page:
        """D-002: Deterministic Scale Calibration & Full Geometry Reprocessing.

        When scale is calibrated, full geometry analysis is re-run from scratch
        at the new scale (ScaleContext.from_ft_per_px) so all physical filters,
        minimum wall lengths, and room area thresholds are derived with the
        correct physical constraints from raw pixels, rather than corrupting
        geometry via post-hoc number multiplication.
        """
        scale = calibrate_scale_ft_per_px(point_a, point_b, real_world_value, unit=unit)
        updated_page = self.pages.update(page, scale_ft_per_px=scale, scale_source=SCALE_SOURCE_USER)

        if reprocess:
            logger.info(
                "Blueprint %s page %s: calibrated scale to %.6f ft/px — triggering full geometry re-run (D-002)",
                page.blueprint_id, page.page_number, scale
            )
            # Re-derive full geometry from scratch at the calibrated scale
            self.run_geometry_analysis(updated_page)

            # Re-run trade takeoff re-computation if blueprint is available
            try:
                if updated_page.blueprint:
                    from app.models.enums import TradeKey
                    from app.services.trade_takeoff_service import TradeTakeoffService
                    trade_svc = TradeTakeoffService(self.db)
                    if trade_svc.is_supported(TradeKey.DRYWALL):
                        trade_svc.compute_and_persist(
                            TradeKey.DRYWALL,
                            updated_page.blueprint,
                            updated_page.blueprint.project_id,
                            updated_page.blueprint.uploaded_by_id,
                        )
            except Exception as takeoff_exc:
                logger.warning("Takeoff re-computation notice post-calibration: %s", takeoff_exc)

        return updated_page

    def associate_ocr_codes_with_detections(self, page_id: int, tokens: list) -> None:
        if not tokens:
            return

        import re
        from app.repositories.detection_repository import DetectionRepository
        from app.models.enums import ReviewStatus

        _DOOR_WINDOW_CODE_RE = re.compile(r"^[DW]-?\d{1,2}[A-Z]?$|^WD-?\d{1,2}$", re.IGNORECASE)

        repo = DetectionRepository(self.db)
        detections = repo.find(page_id=page_id)

        target_detections = [d for d in detections if d.kind in ["door", "window"]]
        if not target_detections:
            return

        code_tokens = []
        for t in tokens:
            txt = t.text.strip()
            if _DOOR_WINDOW_CODE_RE.match(txt):
                xs = [p[0] for p in t.bbox_px]
                ys = [p[1] for p in t.bbox_px]
                cx = sum(xs) / len(xs)
                cy = sum(ys) / len(ys)
                code_tokens.append((txt, cx, cy))

        if not code_tokens:
            return

        from app.repositories.page_repository import PageRepository
        page = PageRepository(self.db).get(page_id)
        if not page or not page.width_px or not page.height_px:
            return
        w, h = page.width_px, page.height_px

        # Query all pages for the blueprint to resolve blueprint-wide schedule items
        from app.repositories.schedule_item_repository import ScheduleItemRepository
        schedule_repo = ScheduleItemRepository(self.db)
        pages_in_blueprint = PageRepository(self.db).find(blueprint_id=page.blueprint_id)
        all_blueprint_page_ids = [p.id for p in pages_in_blueprint]

        for det in target_detections:
            det_xs = [p[0] * w for p in det.polygon_norm]
            det_ys = [p[1] * h for p in det.polygon_norm]
            det_cx = sum(det_xs) / len(det_xs)
            det_cy = sum(det_ys) / len(det_ys)

            best_code = None
            best_dist = 150.0

            for text, cx, cy in code_tokens:
                dist = ((det_cx - cx) ** 2 + (det_cy - cy) ** 2) ** 0.5
                if dist < best_dist:
                    best_dist = dist
                    best_code = text

            if best_code:
                clean_code = best_code.upper().replace("-", "")
                is_door_code = clean_code.startswith("D") or clean_code.startswith("WD")
                is_window_code = clean_code.startswith("W") and not clean_code.startswith("WD")
                
                if (det.kind == "door" and is_door_code) or (det.kind == "window" and is_window_code):
                    kind_name = "Door" if det.kind == "door" else "Window"
                    # Brain Context Fusion: lookup properties inside parsed legend / schedule tables
                    schedule_item = schedule_repo.find_by_code_and_pages(all_blueprint_page_ids, clean_code)
                    if schedule_item:
                        size_str = schedule_item.attributes.get("size") or ""
                        glazing = schedule_item.attributes.get("glazing") or ""
                        detail = f"{size_str} {glazing}".strip()
                        if detail:
                            repo.update(det, label=f"{kind_name} {clean_code} ({detail})")
                            continue
                    repo.update(det, label=f"{kind_name} {clean_code}")


def _process_one_page_standalone(blueprint_id: int, page_index: int, num_pages: int, doc_ctx_dict: dict | None = None) -> int:
    """Runs inside one of `process_all_pages`'s pool workers — a
    SQLAlchemy Session can't cross a process boundary, so (exactly like
    `run_blueprint_processing` below) this opens and owns its own session
    for exactly one page, rather than sharing the caller's.

    `doc_ctx_dict` is the serialized DocumentContext from the whole-document
    pre-pass (D-005). It is a plain dict so it survives process-pool pickling.

    Returns the page number processed, purely so a caller inspecting
    completed futures has something readable to log if it wants it.
    """
    db = SessionLocal()
    try:
        blueprint = BlueprintRepository(db).get(blueprint_id)
        if blueprint is None:
            raise RuntimeError(f"Blueprint {blueprint_id} vanished before page {page_index + 1} could process")
        page = BlueprintService(db).process_single_page(blueprint, page_index, num_pages, doc_ctx_dict=doc_ctx_dict)
        db.commit()
        return page.page_number
    finally:
        db.close()


def run_blueprint_processing(blueprint_id: int) -> None:
    """Background-task entry point for `POST /blueprints/{id}/process`.

    Runs after the request has already returned 202 Accepted, so it can't
    reuse the request-scoped DB session (closed by then) — it owns its own
    session end-to-end, exactly like any other out-of-request worker would.
    """
    db = SessionLocal()
    try:
        blueprint = BlueprintRepository(db).get(blueprint_id)
        if blueprint is None:
            logger.warning("Blueprint %s vanished before background processing could start", blueprint_id)
            return
        BlueprintService(db).process_all_pages(blueprint)
    except Exception as exc:
        # process_all_pages already isolates per-page failures; this only
        # catches something catastrophic (e.g. a DB connection drop) that
        # broke out of that loop entirely.
        logger.exception("Blueprint %s background processing crashed", blueprint_id)
        db.rollback()
        blueprint = db.get(Blueprint, blueprint_id)
        if blueprint is not None:
            blueprint.status = BlueprintStatus.FAILED
            blueprint.processing_error = str(exc)
            db.commit()
    finally:
        db.close()

