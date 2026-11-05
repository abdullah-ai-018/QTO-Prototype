from app.models.detection import Detection
from app.models.enums import TradeKey
from app.models.room import Room
from app.models.trade import TradeConfig
from app.models.wall import Wall
from app.rules.rule_engine import rules
from app.trades.base import LineItem, TradeEngine, TradeResult, build_source_proof


def _wall_paint_area(w: Wall, classifications: dict[int, object] | None) -> float:
    """Wall.area_sqft, unless a PaintingClassification override marks this
    wall not paintable (app.models.painting) — untyped here on purpose,
    same rationale as trades/drywall.py's `_wall_hang_area`. No override
    present (the default) reproduces today's behavior exactly.
    """
    override = classifications.get(w.id) if classifications else None
    if override is not None and not getattr(override, "paintable", True):
        return 0.0
    return w.area_sqft


def _get_opening_sqft(d: Detection, default_deduct: float) -> float:
    """Compute exact sqft deduction from detection dimensions when available."""
    w_ft = getattr(d, "width_ft", None)
    h_ft = getattr(d, "height_ft", None)
    if w_ft and h_ft:
        return float(w_ft * h_ft)
    area_sqft = getattr(d, "area_sqft", None)
    if area_sqft and area_sqft > 0:
        return float(area_sqft)
    return default_deduct


class PaintingEngine(TradeEngine):
    trade = TradeKey.PAINTING

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
        from app.models.enums import RoomType
        rooms = [r for r in rooms if r.room_type != RoomType.EXTERIOR_COVERED.value]
        cov = config.coverage_rates
        cost = config.material_unit_costs
        waste = config.waste_factor_pct
        coats = int(cov.get("coats", 2))
        proof = build_source_proof(rooms, walls)

        detections = detections or []
        door_deduct = cov.get("door_deduction_sqft", 21.0)
        window_deduct = cov.get("window_deduction_sqft", 15.0)

        has_linked_openings = any(d.linked_wall_id is not None and d.kind.value in ("door", "window") for d in detections)
        if has_linked_openings:
            # Real per-wall linking available — subtract actual opening dimensions
            wall_area_sqft = 0.0
            for w in walls:
                linked_openings = [d for d in detections if d.linked_wall_id == w.id and d.kind.value in ("door", "window")]
                deduction = sum(
                    _get_opening_sqft(d, door_deduct if d.kind.value == "door" else window_deduct)
                    for d in linked_openings
                )
                wall_area_sqft += max(0.0, _wall_paint_area(w, classifications) - deduction)
            wall_area_sqft = round(wall_area_sqft, 2)
        else:
            # Fallback deduction based on counts
            raw_wall_area_sqft = round(sum(_wall_paint_area(w, classifications) for w in walls), 2)
            opening_deduction_sqft = round(door_count * door_deduct + window_count * window_deduct, 2)
            wall_area_sqft = max(0.0, raw_wall_area_sqft - opening_deduction_sqft)

        ceiling_area_sqft = round(sum(r.area_sqft for r in rooms), 2)
        trim_linear_ft = round(sum(r.perimeter_ft for r in rooms), 2)
        total_paintable_sqft = wall_area_sqft + ceiling_area_sqft

        # Separate component gallon calculations
        wall_gallons = rules.evaluate(
            "paint_gallons",
            area_sqft=wall_area_sqft,
            coats=coats,
            coverage_sqft_per_gallon=cov["coverage_sqft_per_gallon"],
            waste_pct=waste,
        )
        ceiling_gallons = rules.evaluate(
            "paint_gallons",
            area_sqft=ceiling_area_sqft,
            coats=1,
            coverage_sqft_per_gallon=cov.get("ceiling_coverage_sqft_per_gallon", 400),
            waste_pct=waste,
        )
        total_finish_gallons = wall_gallons + ceiling_gallons

        primer_gallons = rules.evaluate(
            "units_with_waste",
            quantity=total_paintable_sqft,
            coverage_per_unit=cov["primer_coverage_sqft_per_gallon"],
            waste_pct=0,
        )

        trim_gallons = max(1.0, round(trim_linear_ft / cov.get("trim_coverage_ft_per_gallon", 500), 1)) if trim_linear_ft > 0 else 0.0

        labor_hours = rules.evaluate(
            "labor_hours",
            quantity=total_paintable_sqft * coats,
            productivity_per_hour=config.productivity_rates["paint_sqft_per_hour"],
        )

        line_items = [
            LineItem(
                label=f"Wall Finish Paint ({coats} coats)", quantity=wall_gallons, unit="gal", unit_cost=cost["paint_gallon"], source_proof=proof,
                formula_breakdown=f"ceil({wall_area_sqft} wall sqft × {coats} coats × 1.{int(waste):02d} waste / {cov['coverage_sqft_per_gallon']} sqft/gal) = {wall_gallons} gal",
            ),
            LineItem(
                label="Ceiling Paint (1 coat)", quantity=ceiling_gallons, unit="gal", unit_cost=cost.get("ceiling_paint_gallon", cost["paint_gallon"]), source_proof=proof,
                formula_breakdown=f"ceil({ceiling_area_sqft} ceiling sqft / {cov.get('ceiling_coverage_sqft_per_gallon', 400)} sqft/gal) = {ceiling_gallons} gal",
            ),
            LineItem(
                label="Primer", quantity=primer_gallons, unit="gal", unit_cost=cost["primer_gallon"], source_proof=proof,
                formula_breakdown=f"ceil({total_paintable_sqft} sqft / {cov['primer_coverage_sqft_per_gallon']} sqft/gal) = {primer_gallons} gal",
            ),
        ]
        if trim_gallons > 0:
            line_items.append(
                LineItem(
                    label="Baseboard / Trim Enamel", quantity=trim_gallons, unit="gal", unit_cost=cost.get("trim_paint_gallon", 55.0), source_proof=proof,
                    formula_breakdown=f"{trim_linear_ft} LF / 500 ft/gal = {trim_gallons} gal",
                )
            )

        line_items.append(
            LineItem(
                label="Labor", quantity=labor_hours, unit="hrs", unit_cost=config.labor_rate_per_hour, source_proof=proof,
                formula_breakdown=f"({total_paintable_sqft} sqft × {coats} coats) / {config.productivity_rates['paint_sqft_per_hour']} sqft/hr = {labor_hours} hrs",
            )
        )

        return TradeResult(
            trade=self.trade,
            material_quantity=total_finish_gallons,
            material_unit="gal",
            labor_hours=labor_hours,
            line_items=line_items,
            evidence={
                "wall_area_sqft": wall_area_sqft,
                "ceiling_area_sqft": ceiling_area_sqft,
                "trim_linear_ft": trim_linear_ft,
                "total_paintable_sqft": total_paintable_sqft,
            },
        )

