"""Professional Roofing Calculation Rules
Industry-standard formulas for accurate material takeoff
"""

import math
from typing import Dict, Any
from app.rules.base import RuleEngine


class RoofingRules(RuleEngine):
    """Professional roofing calculation rules following industry standards"""
    
    def register_rules(self):
        """Register all roofing calculation rules"""
        
        # Pitch factor calculations
        self.register("roof_pitch_factor", self._pitch_factor_from_rise)
        self.register("roof_pitch_factor_from_percent", self._pitch_factor_from_percent)
        self.register("roof_pitch_angle", self._pitch_angle_degrees)
        
        # Area and square calculations
        self.register("roof_bundles", self._calculate_shingle_bundles)
        self.register("roof_squares", self._calculate_roofing_squares)
        self.register("roof_underlayment", self._calculate_underlayment)
        
        # Linear material calculations
        self.register("roof_ridge_cap", self._calculate_ridge_cap)
        self.register("roof_starter_strip", self._calculate_starter_strip)
        self.register("roof_drip_edge", self._calculate_drip_edge)
        self.register("roof_valley_flashing", self._calculate_valley_flashing)
        
        # Fastener calculations
        self.register("roof_nails", self._calculate_roofing_nails)
        
        # Waste calculations
        self.register("units_with_waste", self._apply_waste_factor)
        
        # Labor calculations
        self.register("roof_labor_hours", self._calculate_labor_hours)
        
        # Special calculations
        self.register("ice_and_water_shield", self._calculate_ice_shield)
        self.register("pipe_flashing_count", self._estimate_pipe_flashings)
    
    def _pitch_factor_from_rise(self, rise_per_12: float) -> float:
        """Calculate roof area multiplier from rise per 12" run
        
        Formula: pitch_factor = sqrt(rise² + 12²) / 12
        
        Examples:
        - 4/12 pitch: sqrt(16 + 144) / 12 = 1.054
        - 6/12 pitch: sqrt(36 + 144) / 12 = 1.118  
        - 8/12 pitch: sqrt(64 + 144) / 12 = 1.202
        - 12/12 pitch: sqrt(144 + 144) / 12 = 1.414
        """
        return math.sqrt(rise_per_12**2 + 144) / 12
    
    def _pitch_factor_from_percent(self, percent_slope: float) -> float:
        """Calculate roof area multiplier from percentage slope
        
        Formula: pitch_factor = sqrt(1 + (percent_slope/100)²)
        
        Examples:
        - 25% slope: sqrt(1 + 0.25²) = 1.031
        - 50% slope: sqrt(1 + 0.5²) = 1.118
        - 100% slope: sqrt(1 + 1²) = 1.414
        """
        slope_decimal = percent_slope / 100
        return math.sqrt(1 + slope_decimal**2)
    
    def _pitch_angle_degrees(self, rise_per_12: float) -> float:
        """Calculate pitch angle in degrees from rise per 12" run"""
        return math.degrees(math.atan(rise_per_12 / 12))
    
    def _calculate_shingle_bundles(self, sloped_area_sqft: float, 
                                   bundle_coverage_sqft: float, 
                                   waste_pct: float) -> float:
        """Calculate shingle bundles needed
        
        Standard coverage:
        - 3-tab shingles: 33.3 sqft per bundle (3 bundles per square)
        - Architectural: 32.8 sqft per bundle  
        - Premium: varies, check manufacturer specs
        """
        gross_area = sloped_area_sqft * (1 + waste_pct / 100)
        bundles = math.ceil(gross_area / bundle_coverage_sqft)
        return float(bundles)
    
    def _calculate_roofing_squares(self, sloped_area_sqft: float) -> float:
        """Convert area to roofing squares (100 sqft = 1 square)"""
        return sloped_area_sqft / 100
    
    def _calculate_underlayment(self, sloped_area_sqft: float,
                               roll_coverage_sqft: float,
                               waste_pct: float) -> float:
        """Calculate underlayment rolls needed
        
        Standard roll coverage:
        - Synthetic underlayment: 400-1000 sqft per roll
        - Felt (15#): 400 sqft per roll
        - Felt (30#): 200 sqft per roll
        """
        gross_area = sloped_area_sqft * (1 + waste_pct / 100)
        rolls = math.ceil(gross_area / roll_coverage_sqft)
        return float(rolls)
    
    def _calculate_ridge_cap(self, ridge_length_ft: float, 
                            hip_length_ft: float,
                            ft_per_bundle: float,
                            waste_pct: float) -> float:
        """Calculate ridge cap bundles needed
        
        Standard coverage: 33 linear feet per bundle
        Includes both ridge and hip lines
        """
        total_length = ridge_length_ft + hip_length_ft
        gross_length = total_length * (1 + waste_pct / 100)
        bundles = math.ceil(gross_length / ft_per_bundle)
        return float(bundles)
    
    def _calculate_starter_strip(self, eave_length_ft: float,
                                ft_per_bundle: float,
                                waste_pct: float) -> float:
        """Calculate starter strip bundles needed
        
        Standard coverage: 105 linear feet per bundle
        Applied along all eave edges
        """
        gross_length = eave_length_ft * (1 + waste_pct / 100)
        bundles = math.ceil(gross_length / ft_per_bundle)
        return float(bundles)
    
    def _calculate_drip_edge(self, eave_length_ft: float,
                            rake_length_ft: float,
                            ft_per_piece: float,
                            waste_pct: float) -> float:
        """Calculate drip edge pieces needed
        
        Standard length: 10 feet per piece
        Required on all eave and rake edges
        """
        total_length = eave_length_ft + rake_length_ft
        gross_length = total_length * (1 + waste_pct / 100)
        pieces = math.ceil(gross_length / ft_per_piece)
        return float(pieces)
    
    def _calculate_valley_flashing(self, valley_length_ft: float,
                                  ft_per_piece: float,
                                  waste_pct: float) -> float:
        """Calculate valley flashing pieces needed
        
        Standard length: 10 feet per piece
        Valley flashing is critical for waterproofing
        """
        gross_length = valley_length_ft * (1 + waste_pct / 100)
        pieces = math.ceil(gross_length / ft_per_piece)
        return float(pieces)
    
    def _calculate_roofing_nails(self, bundles: float,
                                nails_per_bundle: int,
                                nails_per_box: int) -> float:
        """Calculate roofing nail boxes needed
        
        Standard usage:
        - 3-tab shingles: 320 nails per bundle
        - Architectural: 400 nails per bundle
        - Standard box: 7200 nails (50 lbs)
        """
        total_nails = bundles * nails_per_bundle
        # Add 20% extra for ridge cap, starter, repairs
        total_nails *= 1.2
        boxes = math.ceil(total_nails / nails_per_box)
        return float(boxes)
    
    def _apply_waste_factor(self, quantity: float,
                           coverage_per_unit: float,
                           waste_pct: float) -> float:
        """Apply waste factor and calculate units needed"""
        gross_quantity = quantity * (1 + waste_pct / 100)
        units = math.ceil(gross_quantity / coverage_per_unit)
        return float(units)
    
    def _calculate_labor_hours(self, squares: float,
                              complexity_factor: float,
                              crew_size: int = 3) -> float:
        """Calculate labor hours for roofing installation
        
        Base productivity rates (squares per day per crew):
        - Simple roof: 25 squares/day
        - Medium complexity: 20 squares/day  
        - Complex roof: 15 squares/day
        - Very complex: 10 squares/day
        
        Factors that reduce productivity:
        - Steep pitch (>8/12): -25%
        - Multiple stories: -15% per story above 1
        - Poor access: -20%
        - Weather conditions: -30%
        """
        base_productivity = 20  # squares per day
        adjusted_productivity = base_productivity * complexity_factor
        
        work_days = squares / adjusted_productivity
        labor_hours = work_days * 8 * crew_size  # 8 hours * crew size
        
        return round(labor_hours, 1)
    
    def _calculate_ice_shield(self, eave_length_ft: float,
                             valley_length_ft: float,
                             roll_coverage_ft: float,
                             waste_pct: float) -> float:
        """Calculate ice and water shield rolls needed
        
        Required locations:
        - All eave edges (minimum 2 feet up from wall)
        - All valley areas (both sides)
        - Around penetrations
        
        Standard roll: 75 linear feet
        """
        # Eaves need minimum 3 feet width coverage
        eave_area_ft = eave_length_ft * 3
        
        # Valleys need coverage on both sides (3 feet each side)
        valley_area_ft = valley_length_ft * 6
        
        total_linear_ft = (eave_area_ft + valley_area_ft) / 3  # Convert back to linear feet
        gross_length = total_linear_ft * (1 + waste_pct / 100)
        
        rolls = math.ceil(gross_length / roll_coverage_ft)
        return float(rolls)
    
    def _estimate_pipe_flashings(self, roof_area_squares: float) -> int:
        """Estimate number of pipe flashings/boots needed
        
        Rule of thumb: 1 penetration per 200-300 sqft
        Minimum 2 for any residential roof (plumbing vents)
        """
        estimated_count = max(2, int(roof_area_squares * 100 / 250))
        return estimated_count


# Global instance for use in trade engines
roofing_rules = RoofingRules()

# Register with main rule engine
from app.rules.rule_engine import rules
rules.update(roofing_rules.rules)