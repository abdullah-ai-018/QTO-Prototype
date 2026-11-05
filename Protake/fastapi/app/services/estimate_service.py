"""Estimate engine: aggregates every trade engine's output for a
blueprint's approved geometry into a single versioned Estimate, with
markup applied on top of the deterministic direct cost.
"""

from sqlalchemy.orm import Session

from app.geometry.page_classifier import LEGACY_ARCHITECTURAL, PageType
from app.models.blueprint import Blueprint
from app.models.enums import EstimateItemCategory, EstimateStatus, TradeKey
from app.models.estimate import Estimate
from app.repositories.estimate_repository import EstimateRepository
from app.repositories.page_repository import PageRepository
from app.repositories.room_repository import RoomRepository
from app.repositories.wall_repository import WallRepository
from app.rules.rule_engine import rules
from app.schemas.estimate import RoomReviewWarningItem, ScaleWarningItem
from app.trades.base import TradeResult

from app.trades.pricing_service import PricingService
from app.trades.registry import TRADE_ENGINES

# Which drawing sub-types feed each trade — the whole point being that
# Roofing never sees floor-plan rooms and Flooring never sees roof-plan
# rooms, even though both live in the same `rooms`/`walls` tables.
TRADE_PAGE_TYPES: dict[TradeKey, set[str]] = {
    TradeKey.FLOORING: {PageType.FLOOR_PLAN.value, PageType.PARTITION_PLAN.value},
    TradeKey.PAINTING: {PageType.FLOOR_PLAN.value, PageType.PARTITION_PLAN.value, PageType.ELEVATION.value},
    TradeKey.DRYWALL: {PageType.FLOOR_PLAN.value, PageType.PARTITION_PLAN.value, PageType.RCP.value, PageType.ELEVATION.value, PageType.SECTION.value},
    TradeKey.ROOFING: {PageType.ROOF_PLAN.value},
}


def _normalized_page_type(page_type: str | None) -> str:
    if not page_type or page_type == LEGACY_ARCHITECTURAL:
        return PageType.FLOOR_PLAN.value
    return page_type


def _next_version(previous: str | None) -> str:
    if not previous:
        return "v1.00"
    major, minor = previous.replace("v", "").split(".")
    return f"v{major}.{int(minor) + 1:02d}"


class EstimateService:
    def __init__(self, db: Session):
        self.db = db
        self.pages = PageRepository(db)
        self.rooms = RoomRepository(db)
        self.walls = WallRepository(db)
        self.estimates = EstimateRepository(db)
        self.pricing = PricingService(db)

    def get_scale_warnings(self, blueprint_id: int | None):
        if not blueprint_id:
            return None
        from app.geometry.metrics import SCALE_SOURCE_ASSUMED, SCALE_SOURCE_REFERENCE_OBJECT
        from app.schemas.estimate import ScaleWarningItem

        pages = self.pages.find(blueprint_id=blueprint_id)
        assumed_pages = [p for p in pages if p.scale_source == SCALE_SOURCE_ASSUMED]
        low_conf_pages = [
            p for p in pages
            if p.scale_source == SCALE_SOURCE_REFERENCE_OBJECT and getattr(p, "scale_confidence", 1.0) <= 0.30
        ]

        warnings: list[ScaleWarningItem] = []

        if assumed_pages:
            page_ids = [p.id for p in assumed_pages]
            names = ", ".join(f"page {p.page_number} ({p.sheet_name or p.sheet_code or 'unnamed'})" for p in assumed_pages[:5])
            more = f" and {len(assumed_pages) - 5} more" if len(assumed_pages) > 5 else ""
            reason = (
                f"{len(assumed_pages)} page(s) rely on assumed default scale: {names}{more}. "
                "Room/wall counts and spatial quantities may be inaccurate until scale is calibrated."
            )
            warnings.append(ScaleWarningItem(page_ids=page_ids, reason=reason, scale_source=SCALE_SOURCE_ASSUMED))

        if low_conf_pages:
            page_ids = [p.id for p in low_conf_pages]
            names = ", ".join(f"page {p.page_number} ({p.sheet_name or p.sheet_code or 'unnamed'})" for p in low_conf_pages[:5])
            more = f" and {len(low_conf_pages) - 5} more" if len(low_conf_pages) > 5 else ""
            reason = (
                f"{len(low_conf_pages)} page(s) rely on low-confidence wall-thickness scale fallback (confidence 0.30): {names}{more}. "
                "Verify critical room dimensions before bid submission."
            )
            warnings.append(ScaleWarningItem(page_ids=page_ids, reason=reason, scale_source=SCALE_SOURCE_REFERENCE_OBJECT))

        return warnings if warnings else None

    def get_review_warnings(self, blueprint_id: int) -> list[RoomReviewWarningItem] | None:
        """Structured warning items for pages containing rooms that were routed to the
        Human Review Queue (ReviewStatus.NEEDS_REVIEW) due to raster wall contact.
        """
        pages = self.pages.find(blueprint_id=blueprint_id)
        if not pages:
            return None

        review_pages = []
        total_needs_review_count = 0
        for p in pages:
            rooms = self.rooms.find(page_id=p.id)
            needs_review_rooms = [r for r in rooms if r.status.value == "needs_review"]
            if needs_review_rooms:
                review_pages.append(p)
                total_needs_review_count += len(needs_review_rooms)

        if not review_pages:
            return None

        page_ids = [p.id for p in review_pages]
        names = ", ".join(f"page {p.page_number} ({p.sheet_name or p.sheet_code or 'unnamed'})" for p in review_pages[:5])
        more = f" and {len(review_pages) - 5} more" if len(review_pages) > 5 else ""
        reason = (
            f"{len(review_pages)} page(s) contain {total_needs_review_count} room(s) routed to the Human Review Queue: {names}{more}. "
            "Inspect room polygons in the UI review queue before approving takeoff estimates."
        )

        return [
            RoomReviewWarningItem(
                page_ids=page_ids,
                needs_review_count=total_needs_review_count,
                reason=reason,
                warning_type="needs_human_review",
            )
        ]

    def compute_trade_results(self, blueprint: Blueprint, project_id: int | None) -> dict[TradeKey, TradeResult]:
        """Delegates to TradeTakeoffService.compute() per trade — the same
        resolve-geometry -> call-engine -> validate path the isolated
        per-trade takeoff endpoints use, so evidence/validation is computed
        one way, not duplicated here. Deliberately calls `compute()`, not
        `compute_and_persist()`: this method also powers the "live",
        non-persisted breakdown endpoint, which must not write a new
        trade-owned row on every recompute.
        """
        from app.services.trade_takeoff_service import TradeTakeoffService

        takeoff_service = TradeTakeoffService(self.db)
        return {trade: takeoff_service.compute(trade, blueprint, project_id) for trade in TRADE_ENGINES}

    def generate_estimate(
        self,
        project_id: int,
        blueprint: Blueprint,
        created_by_id: int,
        overhead_pct: float,
        profit_pct: float,
        contingency_pct: float,
    ) -> Estimate:
        trade_results = self.compute_trade_results(blueprint, project_id)

        material_cost = round(sum(r.material_cost for r in trade_results.values()), 2)
        labor_cost = round(sum(r.labor_cost for r in trade_results.values()), 2)
        direct_cost = round(material_cost + labor_cost, 2)

        overhead_amount = rules.evaluate("apply_markup", base_amount=direct_cost, pct=overhead_pct)
        contingency_amount = rules.evaluate("apply_markup", base_amount=direct_cost, pct=contingency_pct)
        profit_base = direct_cost + overhead_amount + contingency_amount
        profit_amount = rules.evaluate("apply_markup", base_amount=profit_base, pct=profit_pct)
        final_bid_price = round(profit_base + profit_amount, 2)

        previous = self.estimates.latest_for_project(project_id)
        version = _next_version(previous.version if previous else None)

        estimate = self.estimates.create(
            project_id=project_id,
            blueprint_id=blueprint.id,
            created_by_id=created_by_id,
            version=version,
            status=EstimateStatus.DRAFT,
            material_cost=material_cost,
            labor_cost=labor_cost,
            direct_cost=direct_cost,
            overhead_pct=overhead_pct,
            overhead_amount=overhead_amount,
            profit_pct=profit_pct,
            profit_amount=profit_amount,
            contingency_pct=contingency_pct,
            contingency_amount=contingency_amount,
            final_bid_price=final_bid_price,
        )

        from app.models.estimate import EstimateItem

        for trade, result in trade_results.items():
            for line_item in result.line_items:
                category = EstimateItemCategory.LABOR if line_item.unit == "hrs" else EstimateItemCategory.MATERIAL
                item = EstimateItem(
                    estimate_id=estimate.id,
                    trade=trade,
                    category=category,
                    label=line_item.label,
                    quantity=line_item.quantity,
                    unit=line_item.unit,
                    unit_cost=line_item.unit_cost,
                    total_cost=line_item.total_cost,
                    source_proof=line_item.source_proof,
                    formula_breakdown=line_item.formula_breakdown,
                )
                self.db.add(item)
        self.db.flush()
        self.db.refresh(estimate)
        return estimate
