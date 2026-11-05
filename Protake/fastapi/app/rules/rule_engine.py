"""A tiny, explicit registry of the deterministic construction formulas
every trade engine is built from. Centralizing them here means every
quantity calculation in the system traces back to one named, documented,
unit-tested function — never inline arithmetic scattered through
services, and never an AI model.
"""

import math
from collections.abc import Callable
from typing import Any


class RuleEngine:
    def __init__(self) -> None:
        self._rules: dict[str, Callable[..., float]] = {}

    def register(self, name: str):
        def decorator(fn: Callable[..., float]) -> Callable[..., float]:
            self._rules[name] = fn
            return fn

        return decorator

    def evaluate(self, name: str, **kwargs: Any) -> float:
        if name not in self._rules:
            raise KeyError(f"No rule registered under '{name}'")
        return self._rules[name](**kwargs)

    def names(self) -> list[str]:
        return sorted(self._rules)


rules = RuleEngine()


@rules.register("wall_area")
def wall_area(perimeter_ft: float, height_ft: float) -> float:
    """Wall Area = Perimeter x Height"""
    return round(perimeter_ft * height_ft, 2)


@rules.register("units_with_waste")
def units_with_waste(quantity: float, coverage_per_unit: float, waste_pct: float) -> float:
    """Generic: how many whole units of a fixed-coverage material are
    needed to cover `quantity` (sqft, linear ft, ...) after waste.
    """
    if coverage_per_unit <= 0:
        raise ValueError("coverage_per_unit must be positive")
    return math.ceil((quantity * (1 + waste_pct / 100)) / coverage_per_unit)


@rules.register("drywall_sheets")
def drywall_sheets(area_sqft: float, sheet_coverage_sqft: float, waste_pct: float) -> float:
    """Drywall Sheets = Wall Area / Sheet Coverage (with waste)."""
    return units_with_waste(quantity=area_sqft, coverage_per_unit=sheet_coverage_sqft, waste_pct=waste_pct)


@rules.register("paint_gallons")
def paint_gallons(area_sqft: float, coats: int, coverage_sqft_per_gallon: float, waste_pct: float) -> float:
    """Paint Gallons = (Wall Area x Coats) / Coverage."""
    return units_with_waste(quantity=area_sqft * coats, coverage_per_unit=coverage_sqft_per_gallon, waste_pct=waste_pct)


@rules.register("flooring_boxes")
def flooring_boxes(floor_area_sqft: float, box_coverage_sqft: float, waste_pct: float) -> float:
    """Floor Boxes = Floor Area / Coverage Per Box."""
    return units_with_waste(quantity=floor_area_sqft, coverage_per_unit=box_coverage_sqft, waste_pct=waste_pct)


@rules.register("roof_pitch_factor")
def roof_pitch_factor(rise_per_12: float) -> float:
    """Converts a rise:12 roof pitch into the flat-to-sloped area
    multiplier: factor = hypot(rise, 12) / 12.
    """
    return round(math.hypot(rise_per_12, 12) / 12, 4)


@rules.register("roof_pitch_factor_from_percent")
def roof_pitch_factor_from_percent(percent_slope: float) -> float:
    """Percent-grade analogue of `roof_pitch_factor` — dimensionless, so
    this needs no unit conversion regardless of whether the drawing is
    imperial or metric: factor = hypot(percent/100, 1).
    """
    return round(math.hypot(percent_slope / 100, 1), 4)


@rules.register("roof_bundles")
def roof_bundles(sloped_area_sqft: float, bundle_coverage_sqft: float, waste_pct: float) -> float:
    """Roof Bundles = Sloped Roof Area / Bundle Coverage."""
    return units_with_waste(quantity=sloped_area_sqft, coverage_per_unit=bundle_coverage_sqft, waste_pct=waste_pct)


@rules.register("roof_underlayment")
def roof_underlayment(sloped_area_sqft: float, roll_coverage_sqft: float, waste_pct: float) -> float:
    """Roof Underlayment Rolls = Sloped Roof Area / Roll Coverage (with waste)."""
    return units_with_waste(quantity=sloped_area_sqft, coverage_per_unit=roll_coverage_sqft, waste_pct=waste_pct)


@rules.register("roof_nails")
def roof_nails(bundles: float, nails_per_bundle: int, nails_per_box: int) -> float:
    """Roofing Nail Boxes = (Bundles x Nails per Bundle x 1.2) / Nails per Box."""
    total_nails = bundles * nails_per_bundle * 1.2
    return float(math.ceil(total_nails / nails_per_box))



@rules.register("labor_hours")
def labor_hours(quantity: float, productivity_per_hour: float) -> float:
    """Labor Hours = Quantity / Crew Productivity Rate."""
    if productivity_per_hour <= 0:
        raise ValueError("productivity_per_hour must be positive")
    return round(quantity / productivity_per_hour, 2)


@rules.register("apply_markup")
def apply_markup(base_amount: float, pct: float) -> float:
    return round(base_amount * pct / 100, 2)
