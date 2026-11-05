"""Enhanced Professional Roofing Engine with AI-driven Analysis and Markup System
Comprehensive roofing takeoff following industry best practices with configurable markup calculations
"""

from typing import List, Dict, Optional, Union
import math
from dataclasses import dataclass, field

from app.models.detection import Detection
from app.models.enums import TradeKey, RoofType, RoofComplexity, RoofMaterialType
from app.models.room import Room
from app.models.trade import TradeConfig
from app.models.wall import Wall
from app.rules.rule_engine import rules
from app.trades.base import LineItem, TradeEngine, TradeResult, build_source_proof
from app.ai.roof_analyzer import ProfessionalRoofAnalyzer, RoofAnalysisResult


def _wall_roof_feature(w: Wall, classifications: Optional[Dict[int, object]]) -> Optional[str]:
    """Wall.roof_feature's value, unless a RoofingClassification override
    exists for this wall (app.models.roofing_takeoff) — untyped here on
    purpose, same rationale as trades/drywall.py's `_wall_hang_area`. Two
    -level fallback: override table -> Wall.roof_feature column -> the
    ridge_cap_ft square-footage estimate below (unchanged either way when
    `classifications` is None, the default).
    """
    override = classifications.get(w.id) if classifications else None
    if override is not None:
        raw = getattr(override, "roof_feature", None)
        return getattr(raw, "value", raw)
    raw = getattr(w, "roof_feature", None)
    return getattr(raw, "value", raw)


@dataclass
class MarkupConfig:
    """Configuration for markup/profit calculations"""
    # Default markup percentages
    material_markup_pct: float = 25.0  # 25% markup on materials
    labor_markup_pct: float = 35.0     # 35% markup on labor
    overhead_pct: float = 10.0         # 10% overhead
    profit_pct: float = 15.0           # 15% profit margin
    
    # Room-specific markups (can override defaults)
    room_specific_markups: Dict[str, Dict[str, float]] = field(default_factory=dict)
    
    # Area type markups (like Office: 95%, Pool Office: 95%, etc.)
    area_type_markups: Dict[str, float] = field(default_factory=lambda: {
        "Office": 95.0,
        "Pool Office": 95.0,
        "Corridor": 95.0,
        "Warehouse": 75.0,
        "Residential": 85.0,
        "Commercial": 90.0,
        "Industrial": 80.0
    })
    
    def get_markup_for_room(self, room_name: str, area_type: str = None) -> Dict[str, float]:
        """Get markup percentages for a specific room or area type"""
        # Check room-specific first
        if room_name in self.room_specific_markups:
            return self.room_specific_markups[room_name]
        
        # Check area type
        if area_type and area_type in self.area_type_markups:
            base_markup = self.area_type_markups[area_type]
            return {
                "material_markup_pct": base_markup,
                "labor_markup_pct": base_markup,
                "overhead_pct": self.overhead_pct,
                "profit_pct": self.profit_pct
            }
        
        # Return defaults
        return {
            "material_markup_pct": self.material_markup_pct,
            "labor_markup_pct": self.labor_markup_pct,
            "overhead_pct": self.overhead_pct,
            "profit_pct": self.profit_pct
        }


@dataclass
class EnhancedLineItem(LineItem):
    """Enhanced line item with markup calculations"""
    base_cost: float = 0.0
    markup_pct: float = 0.0
    overhead_cost: float = 0.0
    profit_cost: float = 0.0
    final_price: float = 0.0
    
    @property
    def total_cost(self) -> float:
        # Override to return final price if calculated, otherwise fallback to base cost
        return round(self.final_price if self.final_price > 0.0 else super().total_cost, 2)
    
    def calculate_markup(self, markup_pct: float, overhead_pct: float = 0.0, profit_pct: float = 0.0):
        """Calculate markup, overhead, and profit"""
        self.base_cost = self.quantity * self.unit_cost
        self.markup_pct = markup_pct
        
        # Apply markup
        marked_up_cost = self.base_cost * (1 + markup_pct / 100)
        
        # Apply overhead
        self.overhead_cost = marked_up_cost * (overhead_pct / 100)
        
        # Apply profit
        cost_with_overhead = marked_up_cost + self.overhead_cost
        self.profit_cost = cost_with_overhead * (profit_pct / 100)
        
        # Final price
        self.final_price = cost_with_overhead + self.profit_cost



class EnhancedRoofingEngine(TradeEngine):

    """Professional roofing takeoff engine with comprehensive material calculations and markup system
    
    Features:
    - AI-driven roof type classification
    - Pitch factor calculations 
    - Complete material breakdown (shingles, underlayment, flashing, fasteners)
    - Ridge/hip/valley detection and calculations
    - Opening deductions with flashing requirements
    - Waste factor based on roof complexity
    - Labor hour estimates with productivity rates
    - Configurable markup/profit system per room or area type
    - Professional pricing with overhead and profit calculations
    """

    trade = TradeKey.ROOFING

    def __init__(self, markup_config: Optional[MarkupConfig] = None):
        super().__init__()
        self.roof_analyzer: Optional[ProfessionalRoofAnalyzer] = None
        self.markup_config = markup_config or MarkupConfig()

    def set_markup_config(self, markup_config: MarkupConfig):
        """Update markup configuration"""
        self.markup_config = markup_config

    def add_room_markup(self, room_name: str, material_markup: float, labor_markup: float, overhead: float = None, profit: float = None):
        """Add specific markup for a room"""
        markup_dict = {
            "material_markup_pct": material_markup,
            "labor_markup_pct": labor_markup,
        }
        if overhead is not None:
            markup_dict["overhead_pct"] = overhead
        if profit is not None:
            markup_dict["profit_pct"] = profit
            
        self.markup_config.room_specific_markups[room_name] = markup_dict

    def add_area_type_markup(self, area_type: str, markup_pct: float):
        """Add markup for an area type (like Office: 95%)"""
        self.markup_config.area_type_markups[area_type] = markup_pct

    def calculate(
        self, 
        rooms: List[Room], 
        walls: List[Wall], 
        config: TradeConfig, 
        door_count: int = 0, 
        window_count: int = 0, 
        detections: List[Detection] | None = None,
        roof_analysis: Optional[RoofAnalysisResult] = None,
        room_area_types: Optional[Dict[str, str]] = None,  # Map room names to area types
        classifications: Optional[Dict[int, object]] = None,
    ) -> TradeResult:
        """Calculate comprehensive roofing takeoff with professional accuracy and markup calculations"""
        
        cov = config.coverage_rates
        cost = config.material_unit_costs
        waste = config.waste_factor_pct
        proof = build_source_proof(rooms, walls)

        # Basic measurements
        flat_area_sqft = round(sum(r.area_sqft for r in rooms), 2)
        eave_perimeter_ft = round(sum(r.perimeter_ft for r in rooms), 2)

        # Get pitch factor & roof geometry source
        fallback_warning = None
        if roof_analysis:
            pitch_factor = roof_analysis.slope_factor
            sloped_area_sqft = roof_analysis.total_area_sqft
            waste = roof_analysis.recommended_waste_pct
            roof_complexity = roof_analysis.complexity
            roof_geometry_source = "dedicated_roof_planes"
        else:
            # Fallback to ceiling area calculations
            roof_geometry_source = "ceiling_area_fallback"
            fallback_warning = "no_approved_roof_geometry; ceiling_area_fallback_used"
            if "assumed_pitch_percent" in cov:
                pitch_factor = rules.evaluate("roof_pitch_factor_from_percent", percent_slope=cov["assumed_pitch_percent"])
            else:
                pitch_factor = rules.evaluate("roof_pitch_factor", rise_per_12=cov["assumed_pitch_rise_per_12"])
            sloped_area_sqft = round(flat_area_sqft * pitch_factor, 2)
            roof_complexity = RoofComplexity.MEDIUM

        # Calculate roofing squares (industry standard)
        squares = round(sloped_area_sqft / 100, 2)

        # MATERIAL CALCULATIONS WITH MARKUP
        line_items = []
        
        # Determine markup for the primary room (or use default if multiple rooms)
        primary_room = rooms[0] if rooms else None
        room_name = primary_room.name if primary_room else "Default"
        area_type = room_area_types.get(room_name) if room_area_types else None
        
        markup_rates = self.markup_config.get_markup_for_room(room_name, area_type)

        # 1. ASPHALT SHINGLES
        bundles = rules.evaluate(
            "roof_bundles", 
            sloped_area_sqft=sloped_area_sqft, 
            bundle_coverage_sqft=cov["bundle_coverage_sqft"], 
            waste_pct=waste
        )
        shingle_item = EnhancedLineItem(
            label="Asphalt Shingles (3-tab or architectural)",
            unit="bundles",
            quantity=bundles,
            unit_cost=cost.get("shingle_bundle", 45.0),
            source_proof=proof
        )
        shingle_item.calculate_markup(
            markup_rates["material_markup_pct"],
            markup_rates["overhead_pct"],
            markup_rates["profit_pct"]
        )
        line_items.append(shingle_item)

        # 2. STARTER STRIPS
        starter_bundles = rules.evaluate(
            "units_with_waste", 
            quantity=eave_perimeter_ft, 
            coverage_per_unit=cov["starter_ft_per_bundle"], 
            waste_pct=5  # Lower waste for linear materials
        )
        starter_item = EnhancedLineItem(
            label="Starter Strip Shingles",
            unit="bundles", 
            quantity=starter_bundles,
            unit_cost=cost.get("starter_bundle", 35.0),
            source_proof=proof
        )
        starter_item.calculate_markup(
            markup_rates["material_markup_pct"],
            markup_rates["overhead_pct"],
            markup_rates["profit_pct"]
        )
        line_items.append(starter_item)

        # 3. UNDERLAYMENT
        underlayment_rolls = rules.evaluate(
            "roof_underlayment",
            sloped_area_sqft=sloped_area_sqft,
            roll_coverage_sqft=cov.get("underlayment_roll_coverage_sqft", 400),
            waste_pct=waste
        )
        underlayment_item = EnhancedLineItem(
            label="Synthetic Underlayment",
            unit="rolls",
            quantity=underlayment_rolls,
            unit_cost=cost.get("underlayment_roll", 85.0),
            source_proof=proof
        )
        underlayment_item.calculate_markup(
            markup_rates["material_markup_pct"],
            markup_rates["overhead_pct"],
            markup_rates["profit_pct"]
        )
        line_items.append(underlayment_item)

        # 4. ICE & WATER SHIELD (for eaves and valleys)
        if roof_analysis:
            ice_shield_ft = eave_perimeter_ft + (roof_analysis.valley_length_ft * 2)  # Valleys need both sides
        else:
            ice_shield_ft = eave_perimeter_ft + (squares * 2)  # Estimate 2 ft per square for valleys
        
        ice_shield_rolls = rules.evaluate(
            "units_with_waste",
            quantity=ice_shield_ft,
            coverage_per_unit=cov.get("ice_shield_ft_per_roll", 75),
            waste_pct=10
        )
        ice_shield_item = EnhancedLineItem(
            label="Ice & Water Shield",
            unit="rolls",
            quantity=ice_shield_rolls,
            unit_cost=cost.get("ice_shield_roll", 125.0),
            source_proof=proof
        )
        ice_shield_item.calculate_markup(
            markup_rates["material_markup_pct"],
            markup_rates["overhead_pct"],
            markup_rates["profit_pct"]
        )
        line_items.append(ice_shield_item)

        # 5. RIDGE CAP SHINGLES
        if roof_analysis:
            ridge_cap_ft = roof_analysis.ridge_length_ft + roof_analysis.hip_length_ft
        else:
            # Use detected walls with roof features (or their
            # classification override, if one exists) or estimate
            ridge_ft = sum(w.length_ft for w in walls if _wall_roof_feature(w, classifications) == "ridge")
            hip_ft = sum(w.length_ft for w in walls if _wall_roof_feature(w, classifications) == "hip")
            if ridge_ft == 0 and hip_ft == 0:
                ridge_cap_ft = squares * 12  # Estimate 12 ft per square
            else:
                ridge_cap_ft = ridge_ft + hip_ft

        ridge_cap_bundles = rules.evaluate(
            "units_with_waste",
            quantity=ridge_cap_ft,
            coverage_per_unit=cov.get("ridge_cap_ft_per_bundle", 33),
            waste_pct=10
        )
        ridge_cap_item = EnhancedLineItem(
            label="Ridge Cap Shingles",
            unit="bundles",
            quantity=ridge_cap_bundles,  
            unit_cost=cost.get("ridge_cap_bundle", 55.0),
            source_proof=proof
        )
        ridge_cap_item.calculate_markup(
            markup_rates["material_markup_pct"],
            markup_rates["overhead_pct"],
            markup_rates["profit_pct"]
        )
        line_items.append(ridge_cap_item)

        # 6. DRIP EDGE
        drip_edge_ft = eave_perimeter_ft
        if roof_analysis:
            drip_edge_ft += roof_analysis.rake_length_ft
        else:
            drip_edge_ft += eave_perimeter_ft * 0.3  # Estimate rake as 30% of eave

        drip_edge_pieces = rules.evaluate(
            "units_with_waste",
            quantity=drip_edge_ft,
            coverage_per_unit=cov.get("drip_edge_ft_per_piece", 10),
            waste_pct=5
        )
        drip_edge_item = EnhancedLineItem(
            label="Aluminum Drip Edge",
            unit="pieces",
            quantity=drip_edge_pieces,
            unit_cost=cost.get("drip_edge_piece", 12.0),
            source_proof=proof
        )
        drip_edge_item.calculate_markup(
            markup_rates["material_markup_pct"],
            markup_rates["overhead_pct"],
            markup_rates["profit_pct"]
        )
        line_items.append(drip_edge_item)

        # 7. VALLEY FLASHING (if valleys detected)
        if roof_analysis and roof_analysis.valley_length_ft > 0:
            valley_flashing_ft = roof_analysis.valley_length_ft
            valley_flashing_pieces = rules.evaluate(
                "units_with_waste",
                quantity=valley_flashing_ft,
                coverage_per_unit=cov.get("valley_flashing_ft_per_piece", 10),
                waste_pct=10
            )
            valley_item = EnhancedLineItem(
                label="Valley Flashing (W-style)",
                unit="pieces",
                quantity=valley_flashing_pieces,
                unit_cost=cost.get("valley_flashing_piece", 18.0),
                source_proof=proof
            )
            valley_item.calculate_markup(
                markup_rates["material_markup_pct"],
                markup_rates["overhead_pct"],
                markup_rates["profit_pct"]
            )
            line_items.append(valley_item)

        # 8. STEP FLASHING (for walls and chimneys)
        step_flashing_count = 0
        if roof_analysis:
            # Count openings that need step flashing (chimneys, walls)
            step_flashing_count = len([o for o in roof_analysis.openings if o['type'] in ['chimney', 'wall_intersection']])
        
        if step_flashing_count > 0:
            step_flashing_pieces = step_flashing_count * 20  # ~20 pieces per chimney/wall
            step_item = EnhancedLineItem(
                label="Step Flashing",
                unit="pieces",
                quantity=step_flashing_pieces,
                unit_cost=cost.get("step_flashing_piece", 2.5),
                source_proof=proof
            )
            step_item.calculate_markup(
                markup_rates["material_markup_pct"],
                markup_rates["overhead_pct"],
                markup_rates["profit_pct"]
            )
            line_items.append(step_item)

        # 9. PIPE BOOTS/FLASHING
        if roof_analysis:
            pipe_boot_count = len(roof_analysis.penetrations)
        else:
            pipe_boot_count = max(1, int(squares / 5))  # Estimate 1 per 5 squares
        
        if pipe_boot_count > 0:
            pipe_boot_item = EnhancedLineItem(
                label="Pipe Boots/Flashing",
                unit="pieces",
                quantity=pipe_boot_count,
                unit_cost=cost.get("pipe_boot", 15.0),
                source_proof=proof
            )
            pipe_boot_item.calculate_markup(
                markup_rates["material_markup_pct"],
                markup_rates["overhead_pct"],
                markup_rates["profit_pct"]
            )
            line_items.append(pipe_boot_item)

        # 10. ROOFING NAILS
        nail_boxes = rules.evaluate(
            "roof_nails",
            bundles=bundles,
            nails_per_bundle=cov.get("nails_per_shingle_bundle", 320),
            nails_per_box=cov.get("nails_per_box", 7200)
        )
        nail_item = EnhancedLineItem(
            label="1.25\" Galvanized Roofing Nails",
            unit="boxes",
            quantity=nail_boxes,
            unit_cost=cost.get("nail_box", 85.0),
            source_proof=proof
        )
        nail_item.calculate_markup(
            markup_rates["material_markup_pct"],
            markup_rates["overhead_pct"],
            markup_rates["profit_pct"]
        )
        line_items.append(nail_item)

        # 11. ROOFING CEMENT/SEALANT
        cement_tubes = max(2, int(squares / 3))  # At least 2 tubes, ~1 per 3 squares
        cement_item = EnhancedLineItem(
            label="Roofing Cement/Sealant",
            unit="tubes",
            quantity=cement_tubes,
            unit_cost=cost.get("roofing_cement_tube", 8.0),
            source_proof=proof
        )
        cement_item.calculate_markup(
            markup_rates["material_markup_pct"],
            markup_rates["overhead_pct"],
            markup_rates["profit_pct"]
        )
        line_items.append(cement_item)

        # LABOR CALCULATIONS WITH MARKUP
        labor_hours = self._calculate_labor_hours(squares, roof_complexity, pitch_factor, config.productivity_rates)
        
        # Add labor line item with separate labor markup
        labor_item = EnhancedLineItem(
            label="Roofing Labor",
            unit="hrs",
            quantity=labor_hours,
            unit_cost=cost.get("roofing_labor_hour", 65.0),
            source_proof=proof
        )
        labor_item.calculate_markup(
            markup_rates["labor_markup_pct"],
            markup_rates["overhead_pct"],
            markup_rates["profit_pct"]
        )
        line_items.append(labor_item)

        # Calculate totals with markup
        material_total = sum(item.total_cost for item in line_items if item.unit != "hrs")
        labor_total = sum(item.total_cost for item in line_items if item.unit == "hrs")
        grand_total = material_total + labor_total

        evidence_data = {
            "roof_geometry_source": roof_geometry_source,
            "flat_area_sqft": flat_area_sqft,
            "sloped_area_sqft": sloped_area_sqft,
            "pitch_factor": pitch_factor,
        }
        if fallback_warning:
            evidence_data["fallback_warning"] = fallback_warning

        return TradeResult(
            trade=self.trade,
            material_quantity=squares,
            material_unit="sq",
            labor_hours=labor_hours,
            line_items=line_items,
            evidence=evidence_data,
        )
    
    def _calculate_labor_hours(
        self, squares: float, complexity: RoofComplexity, pitch_factor: float, productivity_rates: dict | None = None
    ) -> float:
        """Calculate labor hours based on roof characteristics. Every
        assumption here is overridable per-project via TradeConfig.
        productivity_rates; the literals below are only the defaults
        (unchanged from this engine's original hardcoded values).
        """
        productivity_rates = productivity_rates or {}

        # Base productivity: squares per day for typical crew
        default_squares_per_day = {
            RoofComplexity.SIMPLE: 25,
            RoofComplexity.MEDIUM: 20,
            RoofComplexity.COMPLEX: 15,
            RoofComplexity.VERY_COMPLEX: 10,
        }
        productivity = productivity_rates.get(
            f"roof_squares_per_day_{complexity.value}", default_squares_per_day.get(complexity, 20)
        )

        # Adjust for steep pitch (reduces productivity)
        steep_pitch_threshold = productivity_rates.get("roof_steep_pitch_threshold", 1.2)  # > 8/12
        steep_pitch_factor = productivity_rates.get("roof_steep_pitch_productivity_factor", 0.75)  # 25% slower
        if pitch_factor > steep_pitch_threshold:
            productivity *= steep_pitch_factor

        crew_size = productivity_rates.get("roof_crew_size", 3)
        hours_per_day = productivity_rates.get("roof_hours_per_workday", 8)

        work_days = squares / productivity
        labor_hours = work_days * hours_per_day * crew_size

        return round(labor_hours, 1)


RoofingEngine = EnhancedRoofingEngine

