"""Regression tests for partition schedule vs RCP/electrical/mechanical fixture isolation."""

import pytest
from app.intelligence.schedule_table_parser import ScheduleTableParser
from app.models.architectural_wall import WallAssemblySpec
from app.trades.drywall_semantic import DrywallSemanticWallPipeline


def test_a_space_heater_not_partition_assembly():
    """Test A: H-1 = Space Heater → NOT partition assembly."""
    parser = ScheduleTableParser()
    rows = [
        ["TAG", "DESCRIPTION"],
        ["H-1", "SPACE HEATER: BROMIC HEATING: TUNGSTEN SMART-HEAT ELECTRIC 4000W WALL MOUNT"],
    ]
    results = parser.parse_table_grid(rows, sheet_number="A7.2", page_number=4, table_bbox={"x0": 0, "y0": 0, "x1": 1, "y1": 1})
    assert "H-1" not in results, "Space heater fixture H-1 must not be classified as a partition assembly"


def test_b_recessed_led_downlight_not_partition_assembly():
    """Test B: L-1 = Recessed LED Downlight → NOT partition assembly."""
    parser = ScheduleTableParser()
    rows = [
        ["SYM", "DESCRIPTION", "REMARKS"],
        ["L-1", "RECESSED 6 INCH LED DOWNLIGHT, ROUND. KENALL ENVIROPRO EPDL SERIES", "TRIM FINISH: WHITE"],
    ]
    results = parser.parse_table_grid(rows, sheet_number="A7.2", page_number=4, table_bbox={"x0": 0, "y0": 0, "x1": 1, "y1": 1})
    assert "L-1" not in results, "Lighting fixture L-1 must not be classified as a partition assembly"


def test_c_valid_partition_table_accepted():
    """Test C: A valid table containing STUD / GWB / GYPSUM / FIRE RATING → accepted as partition schedule."""
    parser = ScheduleTableParser()
    rows = [
        ["TYPE", "FRAMING", "BOARD", "FIRE RATING"],
        ["P-1", "3-5/8\" METAL STUD 20 GA", "5/8\" TYPE X GWB EACH SIDE", "1 HR"],
        ["W-1", "6\" STEEL STUD 20 GA", "5/8\" GYPSUM BOARD 2 LAYERS", "2 HR"],
    ]
    results = parser.parse_table_grid(rows, sheet_number="A7.1", page_number=3, table_bbox={"x0": 0, "y0": 0, "x1": 1, "y1": 1})
    assert "P-1" in results, "Valid partition P-1 must be parsed"
    assert "W-1" in results, "Valid partition W-1 must be parsed"
    assert results["P-1"]["assembly_definition"].stud_depth_in == 3.625
    assert results["P-1"]["assembly_definition"].fire_rating_hr == 1.0
    assert results["W-1"]["assembly_definition"].stud_depth_in == 6.0
    assert results["W-1"]["assembly_definition"].fire_rating_hr == 2.0


def test_d_rcp_schedule_does_not_disable_defaults():
    """Test D: RCP schedule + no partition schedule → RCP tags do not set has_verified_schedule=True."""
    rcp_schedule_evidence = {
        "H-1": {
            "tag": "H-1",
            "schedule_sheet": "A7.2",
            "source_page": 4,
            "source_region": {"x0": 0, "y0": 0, "x1": 1, "y1": 1},
            "assembly_definition": WallAssemblySpec(
                tag="H-1",
                description="Space Heater Bromic Heating Electric",
                stud_depth_in=3.625,
            ),
            "verified": True,
        }
    }
    pipeline = DrywallSemanticWallPipeline(schedule_evidence=rcp_schedule_evidence)
    # has_verified_schedule must be False because H-1 has no wall/partition description
    assert pipeline._base_allow_defaults is True, "RCP fixture tags must not disable default partition fallback"


def test_e_valid_partition_schedule_behavior_intact():
    """Test E: Existing valid partition schedule behavior remains intact."""
    valid_schedule_evidence = {
        "NR-1": {
            "tag": "NR-1",
            "schedule_sheet": "A7.1",
            "source_page": 3,
            "source_region": {"x0": 0, "y0": 0, "x1": 1, "y1": 1},
            "assembly_definition": WallAssemblySpec(
                tag="NR-1",
                description="3-5/8\" Metal Stud, 5/8\" Type X GWB Each Side",
                stud_depth_in=3.625,
                stud_gauge="25 GA",
                board_type_side_a="5/8\" Type X GWB",
                layers_side_a=1,
                board_type_side_b="5/8\" Type X GWB",
                layers_side_b=1,
                sides_to_hang=2,
            ),
            "verified": True,
        }
    }
    pipeline = DrywallSemanticWallPipeline(schedule_evidence=valid_schedule_evidence)
    assert pipeline.schedule_evidence["NR-1"]["verified"] is True
    assert "NR-1" in pipeline.tag_resolver.specs
    assert pipeline.tag_resolver.specs["NR-1"].stud_depth_in == 3.625
