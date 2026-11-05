"""National-average default pricing/coverage tables, seeded once at
startup as `is_default=True` TradeConfig rows (project_id=None). Any
project can override any subset of these via the trade-config API —
this is the "commercial pricing" starting point the spec asks for.
"""

from app.models.enums import TradeKey

DEFAULT_TRADE_CONFIGS: dict[TradeKey, dict] = {
    TradeKey.DRYWALL: {
        "labor_rate_per_hour": 42.0,
        "waste_factor_pct": 10.0,
        "coverage_rates": {
            "sheet_sizes_sqft": {"4x8": 32, "4x10": 40, "4x12": 48},
            "primary_sheet_size": "4x8",
            "compound_coverage_sqft_per_bucket": 370,
            "tape_ft_per_sheet": 12,
            "screws_per_sheet": 32,
            "corners_per_room_estimate": 4,
            "corner_bead_ft_per_corner": 8,
            # Standard opening sizes deducted from raw wall area, since actual
            # door/window dimensions aren't reliably measurable yet — overridable per project.
            "door_deduction_sqft": 21.0,  # 3ft x 7ft standard door
            "window_deduction_sqft": 15.0,  # 3ft x 5ft standard window
        },
        "material_unit_costs": {
            "sheet_4x8": 14.5,
            "sheet_4x10": 17.75,
            "sheet_4x12": 21.0,
            "compound_bucket": 22.0,
            "tape_per_ft": 0.06,
            "screws_per_100": 3.2,
            "corner_bead_per_ft": 0.55,
        },
        "productivity_rates": {"hang_sqft_per_hour": 55, "finish_sqft_per_hour": 90},
    },
    TradeKey.PAINTING: {
        "labor_rate_per_hour": 38.0,
        "waste_factor_pct": 5.0,
        "coverage_rates": {
            "coverage_sqft_per_gallon": 350,
            "primer_coverage_sqft_per_gallon": 400,
            "coats": 2,
            "door_deduction_sqft": 21.0,  # 3ft x 7ft standard door
            "window_deduction_sqft": 15.0,  # 3ft x 5ft standard window
        },
        "material_unit_costs": {"paint_gallon": 38.0, "primer_gallon": 29.0},
        "productivity_rates": {"paint_sqft_per_hour": 150},
    },
    TradeKey.FLOORING: {
        "labor_rate_per_hour": 40.0,
        "waste_factor_pct": 8.0,
        "coverage_rates": {
            "box_coverage_sqft": 22,
            "underlayment_coverage_sqft_per_roll": 100,
            "adhesive_coverage_sqft_per_gallon": 150,
            "trim_deduction_pct": 5.0,
        },
        "material_unit_costs": {
            "box": 46.0,
            "underlayment_roll": 65.0,
            "adhesive_gallon": 34.0,
            "transition_strip": 18.0,
            "trim_per_ft": 1.75,
        },
        "productivity_rates": {"install_sqft_per_hour": 28},
    },
    TradeKey.ROOFING: {
        "labor_rate_per_hour": 45.0,
        "waste_factor_pct": 12.0,
        "coverage_rates": {
            "assumed_pitch_rise_per_12": 6.0,
            "bundle_coverage_sqft": 33.3,
            "bundles_per_square": 3,
            "ridge_hip_ft_per_square": 0.4,
            "hip_ridge_cap_ft_per_bundle": 35,
            "ice_barrier_ft_per_roll": 66.7,
            "underlayment_coverage_sqft_per_roll": 400,
            "flashing_ft_per_square": 0.6,
            "fasteners_per_square": 320,
            "fasteners_per_box": 3000,
            "starter_ft_per_bundle": 100,
        },
        "material_unit_costs": {
            "bundle": 42.0,
            "starter_roll": 55.0,
            "ridge_cap_bundle": 48.0,
            "drip_edge_per_ft": 1.15,
            "flashing_per_ft": 3.4,
            "ice_barrier_roll": 95.0,
            "underlayment_roll": 68.0,
            "fastener_box": 12.0,
        },
        "productivity_rates": {"install_squares_per_hour": 0.6},
    },
}
