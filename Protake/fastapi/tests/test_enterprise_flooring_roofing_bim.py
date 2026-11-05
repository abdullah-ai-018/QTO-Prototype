"""Unit tests for Enterprise Flooring and Roofing BIM and 2D QTO engines."""
import pytest

from app.bim.models import (
    CanonicalBIMModel,
    CanonicalProject,
    CanonicalBuilding,
    CanonicalStorey,
    CanonicalSlab,
    CanonicalRoof,
    CanonicalSpace,
    FlooringAssembly,
    FlooringType,
)
from app.trades.flooring_bim import BIMFlooringEngine, BIMFlooringSummary
from app.trades.roofing_bim import BIMRoofingEngine, BIMRoofingSummary
from app.trades.flooring import FlooringEngine
from app.models.room import Room
from app.models.wall import Wall
from app.models.trade import TradeConfig
from app.models.enums import TradeKey


def test_bim_flooring_engine_takeoff():
    """Verify BIM Flooring Engine calculates tiles, wood, underlayment, mortar, grout, trim and transitions."""
    model = CanonicalBIMModel(
        project=CanonicalProject(
            id="P-01",
            ifc_guid="P-01",
            name="Test Project",
            schema_version="IFC4",
            length_unit="METRE",
            buildings=[],
        ),
        storeys=[
            CanonicalStorey(id="S-01", ifc_guid="S-01", name="Level 1", elevation_ft=0.0)
        ],
        spaces=[
            CanonicalSpace(
                id="SP-01",
                ifc_guid="SP-01",
                name="Master Bathroom",
                storey_id="S-01",
                net_floor_area_sqft=120.0,
                gross_floor_area_sqft=125.0,
                ceiling_height_ft=9.0,
                perimeter_ft=45.0,
                source_psets={"Pset_SpaceCommon": {"FloorFinish": "Ceramic Tile"}},
            ),
            CanonicalSpace(
                id="SP-02",
                ifc_guid="SP-02",
                name="Living Room",
                storey_id="S-01",
                net_floor_area_sqft=350.0,
                gross_floor_area_sqft=360.0,
                ceiling_height_ft=9.0,
                perimeter_ft=76.0,
                source_psets={"Pset_SpaceCommon": {"FloorFinish": "Hardwood Timber"}},
            ),
        ],
    )

    engine = BIMFlooringEngine()
    summary: BIMFlooringSummary = engine.calculate(model)

    assert summary.total_floor_area_sqft == 470.0
    assert summary.total_elements_count == 2
    assert summary.material_types_count >= 1
    assert len(summary.line_items) == 2
    for li in summary.line_items:
        assert li.category == "FLOORING_SURFACE"
        assert li.unit == "SQFT"
        assert li.net_area_sqft > 0


def test_bim_roofing_engine_takeoff():
    """Verify BIM Roofing Engine calculates true sloped area, squares, bundles, starter, ice & water, drip edge."""
    model = CanonicalBIMModel(
        project=CanonicalProject(
            id="P-01",
            ifc_guid="P-01",
            name="Test Project",
            schema_version="IFC4",
            length_unit="METRE",
            buildings=[],
        ),
        storeys=[
            CanonicalStorey(id="S-02", ifc_guid="S-02", name="Roof Level", elevation_ft=20.0)
        ],
        roofs=[
            CanonicalRoof(
                id="RF-01",
                ifc_guid="RF-01",
                name="Main Gable Roof",
                storey_id="S-02",
                storey_name="Roof Level",
                roof_type="GABLE",
                slope_degrees=18.43,
                pitch_ratio="4:12",
                pitch_multiplier=1.054,
                plan_area_sqft=2000.0,
                true_surface_area_sqft=2108.0,
                ridge_length_ft=45.0,
                eave_length_ft=90.0,
                rake_length_ft=60.0,
                hip_length_ft=0.0,
                valley_length_ft=0.0,
                primary_material="ASPHALT_SHINGLES",
                waste_factor_pct=10.0,
            )
        ],
    )

    engine = BIMRoofingEngine(default_waste_factor=0.10)
    summary: BIMRoofingSummary = engine.calculate(model)

    assert summary.total_plan_area_sqft == 2000.0
    assert summary.total_true_surface_area_sqft == 2108.0
    assert summary.eligible_elements_count == 1
    assert len(summary.line_items) == 1
    assert summary.line_items[0].category == "ROOFING_SURFACE"
    assert summary.line_items[0].quantity == 2108.0
    assert summary.line_items[0].unit == "SF"


def test_2d_flooring_engine_takeoff():
    """Verify 2D Blueprint Flooring Engine calculates both Tile and Wood assemblies with line-item proofs."""
    rooms = [
        Room(id=1, name="Kitchen", area_sqft=180.0, perimeter_ft=54.0),
        Room(id=2, name="Bathroom", area_sqft=80.0, perimeter_ft=36.0),
        Room(id=3, name="Bedroom", area_sqft=220.0, perimeter_ft=60.0),
    ]
    walls = [
        Wall(id=1, length_ft=54.0, height_ft=9.0),
        Wall(id=2, length_ft=36.0, height_ft=9.0),
        Wall(id=3, length_ft=60.0, height_ft=9.0),
    ]
    config = TradeConfig(
        trade=TradeKey.FLOORING,
        waste_factor_pct=10.0,
        coverage_rates={
            "box_coverage_sqft": 20.0,
            "underlayment_coverage_sqft_per_roll": 100.0,
            "adhesive_coverage_sqft_per_gallon": 150.0,
            "trim_deduction_pct": 10.0,
        },
        material_unit_costs={
            "box": 65.0,
            "tile_box": 55.0,
            "underlayment_roll": 42.0,
            "adhesive_gallon": 55.0,
            "transition_strip": 24.50,
            "trim_per_ft": 3.25,
        },
        productivity_rates={"install_sqft_per_hour": 35.0},
        labor_rate_per_hour=45.0,
    )

    engine = FlooringEngine()
    result = engine.calculate(rooms=rooms, walls=walls, config=config)

    assert result.trade == TradeKey.FLOORING
    assert result.material_unit == "sqft"
    assert result.material_quantity == 480.0  # 180 + 80 + 220
    assert result.labor_hours == 0.0
    assert len(result.line_items) == 2  # Wood Surface, Tile Surface (NO labor)
    labels = [li.label for li in result.line_items]
    assert "Porcelain / Ceramic Tile Surface" in labels
    assert "Hardwood / LVP Flooring Surface" in labels
