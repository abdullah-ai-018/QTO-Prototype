"""Generic per-trade persistence + validation orchestrator.

Wraps an already-isolated TradeEngine.calculate() call from the outside:
resolve approved geometry -> call the engine (unchanged) -> validate the
result -> persist a versioned snapshot into that trade's own tables. No
engine file needs to change to gain persistence, evidence, or a
validated/needs_review/error status — this mirrors (and will eventually
replace the inline duplicate of) EstimateService.compute_trade_results.

Adding a new trade to this orchestrator is just one TRADE_MODELS entry —
the compute/persist/read logic itself is trade-agnostic.
"""

import dataclasses
import hashlib
import logging
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.geometry.page_classifier import PageType  # noqa: F401  (re-exported for callers)
from app.models.blueprint import Blueprint
from app.models.enums import DetectionKind, TradeKey, TradeTakeoffStatus
from app.repositories.base import BaseRepository
from app.repositories.detection_repository import DetectionRepository
from app.repositories.drywall_repository import (
    DrywallClassificationRepository,
    DrywallItemRepository,
    DrywallTakeoffRepository,
)
from app.repositories.flooring_repository import (
    FlooringClassificationRepository,
    FlooringItemRepository,
    FlooringTakeoffRepository,
)
from app.repositories.page_repository import PageRepository
from app.repositories.painting_repository import (
    PaintingClassificationRepository,
    PaintingItemRepository,
    PaintingTakeoffRepository,
)
from app.repositories.roofing_takeoff_repository import (
    RoofingClassificationRepository,
    RoofingItemRepository,
    RoofingTakeoffRepository,
)
from app.repositories.room_repository import RoomRepository
from app.repositories.schedule_item_repository import ScheduleItemRepository
from app.repositories.wall_repository import WallRepository
from app.services.estimate_service import TRADE_PAGE_TYPES, _normalized_page_type
from app.services.ground_truth_service import GroundTruthService
from app.trades.base import TradeResult
from app.trades.pricing_service import PricingService
from app.trades.registry import TRADE_ENGINES
from app.trades.validation import crashed_validation, validate_trade_result

logger = logging.getLogger("protake")


def _fingerprint(parts: list[tuple]) -> str:
    """Short deterministic fingerprint of a sorted (kind, id, state) tuple
    list — changes whenever any contributing row is added, removed, or
    edited, so it can be compared later to detect a stale takeoff.
    """
    raw = "|".join(f"{kind}:{id_}:{state}" for kind, id_, state in sorted(parts, key=lambda p: (p[0], p[1])))
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _geometry_version(rooms: list, walls: list) -> str:
    parts = [("room", r.id, r.updated_at.isoformat()) for r in rooms]
    parts += [("wall", w.id, w.updated_at.isoformat()) for w in walls]
    return _fingerprint(parts)


def _scale_version(pages: list) -> str:
    parts = [("page", p.id, f"{p.scale_source}:{p.scale_ft_per_px}:{p.updated_at.isoformat()}") for p in pages]
    return _fingerprint(parts)


@dataclass
class TradeModelSet:
    takeoff_repo: type[BaseRepository]
    item_repo: type[BaseRepository]
    classification_repo: type[BaseRepository] | None = None
    # "wall" (drywall/painting key their override by Wall.id) or "room"
    # (flooring keys by Room.id, since its engine sums room area, not
    # wall area) — decides which id list + repo method the orchestrator
    # uses to build the `classifications` kwarg below.
    classification_scope: str = "wall"


TRADE_MODELS: dict[TradeKey, TradeModelSet] = {
    TradeKey.DRYWALL: TradeModelSet(
        takeoff_repo=DrywallTakeoffRepository,
        item_repo=DrywallItemRepository,
        classification_repo=DrywallClassificationRepository,
        classification_scope="wall",
    ),
    TradeKey.PAINTING: TradeModelSet(
        takeoff_repo=PaintingTakeoffRepository,
        item_repo=PaintingItemRepository,
        classification_repo=PaintingClassificationRepository,
        classification_scope="wall",
    ),
    TradeKey.FLOORING: TradeModelSet(
        takeoff_repo=FlooringTakeoffRepository,
        item_repo=FlooringItemRepository,
        classification_repo=FlooringClassificationRepository,
        classification_scope="room",
    ),
    TradeKey.ROOFING: TradeModelSet(
        takeoff_repo=RoofingTakeoffRepository,
        item_repo=RoofingItemRepository,
        classification_repo=RoofingClassificationRepository,
        classification_scope="wall",
    ),
}


class TradeTakeoffService:
    def __init__(self, db: Session):
        self.db = db
        self.pages = PageRepository(db)
        self.rooms = RoomRepository(db)
        self.walls = WallRepository(db)
        self.detections = DetectionRepository(db)
        self.schedule_items = ScheduleItemRepository(db)
        self.pricing = PricingService(db)

    def is_supported(self, trade: TradeKey) -> bool:
        return trade in TRADE_MODELS

    def _resolve_opening_count(self, all_page_ids: list[int], kind: DetectionKind) -> int:
        if self.schedule_items.any_for_pages(all_page_ids):
            return self.schedule_items.approved_quantity_for_pages(all_page_ids, kind)
        return self.detections.candidate_count_by_kind(all_page_ids, kind)

    @staticmethod
    def _extract_page_text(blueprint: Blueprint, pages: list) -> dict[int, dict]:
        """Read every page's words once, as {page_id: {"full": str, "items": [...]}}.

        GAP-F FIX: Added "_extraction_failed" sentinel key to the return dict when the
        PDF file is missing or unreadable. Callers check for this key and surface an
        explicit pipeline failure rather than silently returning a zero-quantity result
        that is indistinguishable from an actual verified-zero scope.
        """
        out: dict[int, dict] = {}
        path = getattr(blueprint, "file_path", None)
        if not path:
            out["_extraction_failed"] = {"reason": "blueprint_file_path_missing", "path": None}
            return out
        try:
            import fitz

            with fitz.open(path) as doc:
                for p in pages:
                    idx = (p.page_number or 0) - 1
                    if idx < 0 or idx >= doc.page_count:
                        continue
                    page = doc.load_page(idx)
                    pw, ph = page.rect.width, page.rect.height
                    if pw <= 0 or ph <= 0:
                        continue
                    words = [w for w in page.get_text("words") if w[4].strip()]
                    out[p.id] = {
                        "full": page.get_text("text"),
                        "items": [
                            (w[0] / pw, w[1] / ph, w[2] / pw, w[3] / ph, w[4].strip())
                            for w in words
                        ],
                    }
        except FileNotFoundError:
            out["_extraction_failed"] = {"reason": "file_not_found", "path": path}
            logger.error("Page text extraction failed — file not found: %s (blueprint %s)", path, blueprint.id)
        except Exception as e:
            out["_extraction_failed"] = {"reason": str(e), "path": path}
            logger.warning(f"Page text extraction failed for blueprint {blueprint.id}: {e}")
        return out

    def compute(
        self, trade: TradeKey, blueprint: Blueprint, project_id: int | None, page_id: int | None = None
    ) -> TradeResult:
        """Resolve approved geometry, call the engine, validate — no
        persistence. Shared by compute_and_persist() below *and* by
        EstimateService.compute_trade_results(), which must NOT persist a
        new trade-owned row on every call: it also powers the "live",
        non-persisted breakdown endpoint, which would otherwise spam a
        new takeoff snapshot on every UI refresh.

        `page_id`, when given, additionally scopes the rooms/walls/
        detections/opening-counts fed into the engine to that single page
        — the engine itself, its formulas, and (when page_id is None) the
        existing project-level behavior are completely unchanged. Sheet
        classification and schedule-intelligence parsing still run across
        every page in the blueprint regardless of `page_id`, since a wall's
        assembly/tag can be defined on a different sheet (e.g. a partition
        schedule) than the one its geometry lives on.
        """
        engine = TRADE_ENGINES[trade]
        models = TRADE_MODELS.get(trade)

        pages = self.pages.find(blueprint_id=blueprint.id)
        all_page_ids = [p.id for p in pages]
        relevant_types = TRADE_PAGE_TYPES[trade]
        relevant_pages = [p for p in pages if _normalized_page_type(p.page_type) in relevant_types]
        if page_id is not None:
            relevant_pages = [p for p in relevant_pages if p.id == page_id]
        page_ids = [p.id for p in relevant_pages]

        rooms = self.rooms.candidate_for_pages(page_ids)
        walls = self.walls.candidate_for_pages(page_ids)
        detections = self.detections.candidate_for_pages(page_ids)

        self.pricing.seed_defaults_if_missing()
        config = self.pricing.resolve(trade, project_id)

        opening_count_page_ids = [page_id] if page_id is not None else all_page_ids
        door_count = self._resolve_opening_count(opening_count_page_ids, DetectionKind.DOOR)
        window_count = self._resolve_opening_count(opening_count_page_ids, DetectionKind.WINDOW)

        # A trade only receives `classifications` if it both owns a
        # classification repo (TRADE_MODELS) *and* its engine's calculate()
        # accepts the kwarg — true for all 4 trades today; keep them added
        # in lockstep for any future trade (see trades/drywall.py's
        # `_wall_hang_area` / trades/flooring.py's `_floor_eligible`).
        engine_kwargs = {}
        if models is not None and models.classification_repo is not None:
            if models.classification_scope == "room":
                engine_kwargs["classifications"] = models.classification_repo(self.db).for_rooms([r.id for r in rooms])
            else:
                engine_kwargs["classifications"] = models.classification_repo(self.db).for_walls([w.id for w in walls])

        # Multi-Page Blueprint Set Intelligence Index
        from app.intelligence.sheet_classifier import BlueprintSheetClassifier
        from app.intelligence.schedule_parser import MultiSheetScheduleParser
        from app.models.project_knowledge_graph import ProjectBlueprintIndex, DetailSheetEntry
        from app.geometry.detail_callouts import normalize_sheet_ref

        classifier = BlueprintSheetClassifier()
        sched_parser = MultiSheetScheduleParser()
        project_index = ProjectBlueprintIndex(blueprint_id=blueprint.id)

        # Sheet text is the input to *all* schedule intelligence, so it is read
        # once here and shared. Previously this passed `p.sheet_number`, which
        # Page does not define (the column is `sheet_code`) — getattr's default
        # made every sheet classify from an empty string, so sheet_type was
        # always UNKNOWN and no partition/door schedule was ever indexed. That
        # single wrong attribute name is what left assembly resolution starved.
        page_text = self._extract_page_text(blueprint, pages)

        # GAP-F: Build a pipeline_failure_reason string if PDF was unreadable.
        # Only DRYWALL requires PDF text for schedule/assembly resolution.
        # Other trades (flooring, painting, roofing) compute from DB geometry only
        # and do not need the PDF — scoping this failure to DRYWALL preserves the
        # per-trade isolation guarantee (one trade failure must not affect others).
        _pdf_failure: str | None = None
        if "_extraction_failed" in page_text and trade == TradeKey.DRYWALL:
            failure = page_text["_extraction_failed"]
            _pdf_failure = (
                f"PIPELINE_FAILURE_PDF_UNREADABLE: "
                f"reason={failure.get('reason', 'unknown')}, "
                f"path={failure.get('path', 'unknown')}, "
                f"blueprint_id={blueprint.id}. "
                f"Schedule intelligence, tag resolution and assembly lookup cannot proceed."
            )
            logger.error(_pdf_failure)

        for p in pages:
            meta = classifier.classify_sheet(
                p.id,
                p.page_number,
                page_text.get(p.id, {}).get("full", "") or (p.sheet_code or ""),
                getattr(blueprint, "name", None),
            )
            project_index.sheets[p.id] = meta
            # Parse from the full sheet text, not text_content_sample — the
            # sample is truncated to 300 chars, which is shorter than any real
            # schedule table's header row.
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

        if trade == TradeKey.DRYWALL:
            engine_kwargs["project_index"] = project_index
            # Positioned word boxes for wall-tag association. Without these the
            # resolver has no tags to match against and every wall resolves to
            # assembly_resolved=False, which the QTO gate then filters out.
            engine_kwargs["text_items"] = {
                page_id: t["items"]
                for page_id, t in page_text.items()
                if page_id != "_extraction_failed"  # GAP-F: exclude sentinel key
            }
            # Real schedule-table evidence (ScheduleTableParser: PDF's own vector
            # tables first, spatial-text fallback second). Without this,
            # DrywallSemanticWallPipeline's WallTagResolver.specs stays empty, so
            # every resolved tag maps to assembly=None regardless of what the
            # sheet's own partition schedule actually says — the single blocker
            # identified across every prior audit of this pipeline. Computed once
            # per compute() call (not per wall) since it scans the whole document.
            from app.intelligence.schedule_table_parser import ScheduleTableParser
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
            engine_kwargs["schedule_evidence"] = schedule_evidence

            # GAP-4 FIX: Merge ScheduleTableParser results into
            # ProjectBlueprintIndex.partition_schedules so CrossSheetReconciler
            # also sees the table-parsed assemblies.  Previously the reconciler
            # only queried project_index.partition_schedules which was built
            # exclusively by MultiSheetScheduleParser (regex line-match) — any
            # tag found by the table parser but missed by the regex parser was
            # invisible to reconciliation.  The two paths are now unified here,
            # with table-parser results taking precedence (verified=True wins).
            from app.models.project_knowledge_graph import PartitionScheduleEntry
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

            # Phase 2: page scale info so opening bbox_norm can be converted to
            # real feet. Passed separately from project_index because SheetMetadata
            # doesn't carry pixel dimensions — Page ORM rows do.
            engine_kwargs["page_scale_info"] = {
                p.id: {
                    "scale_ft_per_px": p.scale_ft_per_px or 0.0,
                    "width_px": p.width_px or 0,
                    "height_px": p.height_px or 0,
                }
                for p in pages
            }

        try:
            # GAP-F: Surface PDF-unreadable as a caught pipeline failure with
            # distinct messaging — not a silent zero, not an unhandled exception.
            if _pdf_failure:
                raise RuntimeError(_pdf_failure)
            result = engine.calculate(rooms, walls, config, door_count, window_count, detections, **engine_kwargs)
            validation = validate_trade_result(trade, result, rooms, walls, relevant_pages)

            # ── D-007 FIX: Scale Gate ─────────────────────────────────────────
            # A page with assumed scale (confidence=0.0) feeds QTO with
            # potentially wrong physical measurements (area error = scale² factor).
            # Assumed scale does NOT block computation (the geometry is still
            # useful for markup/review) but MUST downgrade validation to
            # NEEDS_REVIEW so the result is never presented as a confirmed QTO.
            from app.geometry.metrics import SCALE_SOURCE_ASSUMED
            assumed_scale_pages = [
                p for p in relevant_pages
                if getattr(p, "scale_source", None) == SCALE_SOURCE_ASSUMED
            ]
            if assumed_scale_pages:
                assumed_page_nums = [p.page_number for p in assumed_scale_pages]
                validation.status = TradeTakeoffStatus.NEEDS_REVIEW
                validation.confidence = min(getattr(validation, "confidence", 0.5), 0.40)
                existing_reasons = list(getattr(validation, "reasons", []) or [])
                validation.reasons = existing_reasons + [
                    f"assumed_scale_on_pages:{assumed_page_nums}:quantities_unverified"
                ]

            # ── D-009 FIX: Provisional height propagation ─────────────────────
            # When drywall engine flagged qto_is_provisional=True (assumed height),
            # ensure the validation status reflects that — not just the proof dict.
            qto_flags = (result.evidence or {}).get("qto_confidence_flags", {})
            if qto_flags.get("qto_is_provisional") and validation.status == TradeTakeoffStatus.VALIDATED:
                validation.status = TradeTakeoffStatus.NEEDS_REVIEW
                existing_reasons = list(getattr(validation, "reasons", []) or [])
                validation.reasons = existing_reasons + ["height_assumed:qto_provisional"]

        except Exception as e:
            logger.error(f"Error calculating trade {trade}: {e}", exc_info=True)
            result = TradeResult(
                trade=trade,
                material_quantity=0.0,
                material_unit="sqft" if trade != TradeKey.ROOFING else "sq",
                labor_hours=0.0,
                line_items=[],
            )
            validation = crashed_validation(e)

        # Real independent verification: compare against human-verified
        # reference quantities when any exist for this blueprint/trade
        # (app.models.ground_truth.GroundTruthReference, seeded via
        # POST .../ground-truth). GroundTruthService is honest when none
        # exist — has_ground_truth=False, not a fabricated pass — so this
        # never claims an accuracy this blueprint was never actually
        # checked against. When reference rows DO exist and disagree beyond
        # tolerance, that's real evidence the computed quantity is wrong and
        # must not be silently reported as "validated".
        GROUND_TRUTH_VARIANCE_TOLERANCE_PCT = 10.0
        ground_truth_evidence: dict | None = None
        try:
            gt_report = GroundTruthService(self.db).compare(
                trade, blueprint.id, result.material_quantity, result.material_unit
            )
            ground_truth_evidence = {
                "has_ground_truth": gt_report.has_ground_truth,
                "comparisons": [
                    {
                        "item_label": c.item_label,
                        "reference_quantity": c.reference_quantity,
                        "unit": c.unit,
                        "source": c.source,
                        "verified_by": c.verified_by,
                        "variance_pct": c.variance_pct,
                    }
                    for c in gt_report.comparisons
                ],
            }
            if gt_report.has_ground_truth:
                worst_variance = max(
                    (abs(c.variance_pct) for c in gt_report.comparisons if c.variance_pct is not None),
                    default=None,
                )
                if worst_variance is not None and worst_variance > GROUND_TRUTH_VARIANCE_TOLERANCE_PCT:
                    validation.status = TradeTakeoffStatus.NEEDS_REVIEW
                    validation.confidence = min(validation.confidence, 0.6)
                    validation.reasons = list(validation.reasons) + [
                        f"ground_truth_variance_exceeds_tolerance:{worst_variance:.1f}pct"
                    ]
        except Exception as gt_exc:
            # Ground truth is a real check when present, but its own failure
            # (DB error, etc.) must never take down a takeoff that would
            # otherwise have computed fine — same isolation principle as the
            # rest of this method.
            logger.warning("Ground truth comparison failed for blueprint %s trade %s: %s", blueprint.id, trade, gt_exc)

        # Merge, don't overwrite: engines that populate their own
        # result.evidence (e.g. roofing's roof_geometry_source/
        # fallback_warning/pitch_factor) must keep it — this generic
        # provenance is additive on top, not a replacement. Engine keys
        # win on collision since they're the more specific claim.
        evidence = {
            "room_ids": [r.id for r in rooms],
            "wall_ids": [w.id for w in walls],
            "page_ids": page_ids,
            "door_count": door_count,
            "window_count": window_count,
            # Snapshot versioning: lets a persisted takeoff be checked for
            # staleness later — if the current geometry/scale fingerprint
            # for these same rooms/walls/pages no longer matches what's
            # stored here, the room/wall geometry or scale calibration
            # changed since this takeoff was computed.
            "geometry_version": _geometry_version(rooms, walls),
            "scale_version": _scale_version(relevant_pages),
            "engine_version": getattr(engine, "version", "unknown"),
            **(result.evidence or {}),
        }
        if ground_truth_evidence is not None:
            evidence["ground_truth"] = ground_truth_evidence
        return dataclasses.replace(result, evidence=evidence, validation=validation)

    def compute_and_persist(self, trade: TradeKey, blueprint: Blueprint, project_id: int, created_by_id: int | None):
        if trade not in TRADE_MODELS:
            raise ValueError(f"No persisted takeoff model wired for trade {trade.value!r} yet")

        result = self.compute(trade, blueprint, project_id)
        validation = result.validation

        models = TRADE_MODELS[trade]
        takeoff_repo = models.takeoff_repo(self.db)
        item_repo = models.item_repo(self.db)

        # Idempotent: delete any existing takeoffs for this blueprint+trade before
        # inserting the fresh result, so repeated POST calls don't accumulate rows.
        model_cls = models.takeoff_repo.model
        existing = self.db.execute(
            select(model_cls).where(model_cls.blueprint_id == blueprint.id)
        ).scalars().all()
        for old in existing:
            takeoff_repo.delete(old)
        self.db.flush()

        takeoff = takeoff_repo.create(
            project_id=project_id,
            blueprint_id=blueprint.id,
            created_by_id=created_by_id,
            material_quantity=result.material_quantity,
            material_unit=result.material_unit,
            labor_hours=result.labor_hours,
            material_cost=result.material_cost,
            labor_cost=result.labor_cost,
            direct_cost=result.direct_cost,
            status=validation.status,
            confidence=validation.confidence,
            evidence=result.evidence,
            validation_reasons=validation.reasons,
            geometry_version=result.evidence.get("geometry_version") if result.evidence else None,
            scale_version=result.evidence.get("scale_version") if result.evidence else None,
            engine_version=result.evidence.get("engine_version") if result.evidence else None,
        )
        for li in result.line_items:
            item_repo.create(
                takeoff_id=takeoff.id,
                label=li.label,
                quantity=li.quantity,
                unit=li.unit,
                unit_cost=li.unit_cost,
                total_cost=li.total_cost,
                source_proof=li.source_proof,
                formula_breakdown=li.formula_breakdown,
            )
        return takeoff

    def latest(self, trade: TradeKey, blueprint_id: int):
        if trade not in TRADE_MODELS:
            return None
        model_cls = TRADE_MODELS[trade].takeoff_repo.model
        stmt = select(model_cls).where(model_cls.blueprint_id == blueprint_id).order_by(model_cls.created_at.desc()).limit(1)
        return self.db.execute(stmt).scalars().first()
