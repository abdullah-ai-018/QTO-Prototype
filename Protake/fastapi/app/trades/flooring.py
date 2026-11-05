import math

from app.models.detection import Detection
from app.models.enums import TradeKey
from app.models.room import Room
from app.models.trade import TradeConfig
from app.models.wall import Wall
from app.rules.rule_engine import rules
from app.trades.base import LineItem, TradeEngine, TradeResult, build_source_proof


def _floor_eligible(r: Room, classifications: dict[int, object] | None) -> bool:
    """True unless a FlooringClassification override (app.models.flooring)
    marks this room ineligible — untyped here on purpose, same rationale
    as trades/drywall.py's `_wall_hang_area`. No override present (the
    default) reproduces today's behavior exactly.
    """
    override = classifications.get(r.id) if classifications else None
    if override is None:
        return True
    return getattr(override, "flooring_eligible", True)


class FlooringEngine(TradeEngine):
    trade = TradeKey.FLOORING

    def calculate(
        self,
        rooms: list[Room],
        walls: list[Wall],
        config: TradeConfig,
        door_count: int = 0,
        window_count: int = 0,
        detections: list[Detection] | None = None,
        classifications: dict[int, object] | None = None,
    ) -> TradeResult:
        rooms = [r for r in rooms if _floor_eligible(r, classifications)]
        cost = config.material_unit_costs
        proof = build_source_proof(rooms, walls)

        floor_area_sqft = round(sum(r.area_sqft for r in rooms), 2)

        # Distinguish Wet areas (Tile) vs Dry areas (Hardwood/LVP)
        tile_rooms = [r for r in rooms if any(k in (r.name or "").lower() for k in ["bath", "toilet", "wc", "wash", "powder", "restroom"])]
        wood_rooms = [r for r in rooms if r not in tile_rooms]

        tile_area_sqft = round(sum(r.area_sqft for r in tile_rooms), 2)
        wood_area_sqft = round(sum(r.area_sqft for r in wood_rooms), 2)

        line_items = []

        if wood_area_sqft > 0:
            line_items.append(
                LineItem(
                    label="Hardwood / LVP Flooring Surface",
                    quantity=wood_area_sqft,
                    unit="sqft",
                    unit_cost=cost.get("wood_sqft", cost.get("box", 65.0) / 20.0),
                    source_proof=proof,
                    formula_breakdown=f"Net floor area = {wood_area_sqft} sqft",
                )
            )

        if tile_area_sqft > 0:
            line_items.append(
                LineItem(
                    label="Porcelain / Ceramic Tile Surface",
                    quantity=tile_area_sqft,
                    unit="sqft",
                    unit_cost=cost.get("tile_sqft", cost.get("tile_box", 55.0) / 16.0),
                    source_proof=proof,
                    formula_breakdown=f"Net floor area = {tile_area_sqft} sqft",
                )
            )

        if not line_items and floor_area_sqft > 0:
            line_items.append(
                LineItem(
                    label="Flooring Surface",
                    quantity=floor_area_sqft,
                    unit="sqft",
                    unit_cost=cost.get("sqft", 3.25),
                    source_proof=proof,
                    formula_breakdown=f"Net floor area = {floor_area_sqft} sqft",
                )
            )

        return TradeResult(
            trade=self.trade,
            material_quantity=floor_area_sqft,
            material_unit="sqft",
            labor_hours=0.0,
            line_items=line_items,
        )
