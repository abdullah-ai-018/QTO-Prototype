"""Automated tests for IFC Ingestion, Validation, Reader, Normalizer, and Auditable QTO."""
import os
import sys
import tempfile
import pytest

# Ensure app package is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import ifcopenshell
import ifcopenshell.api

from app.bim.models import (
    CanonicalBIMModel,
    CanonicalOpening,
    CanonicalProject,
    CanonicalStorey,
    CanonicalWall,
    WallAssembly,
)
from app.bim.normalizer import BIMNormalizer
from app.ifc.reader import IFCReader
from app.ifc.validator import IFCValidator, ModelStatus
from app.trades.drywall_bim import BIMDrywallEngine


def create_sample_test_ifc(filepath: str) -> None:
    """Creates a synthetic standard IFC file for end-to-end testing."""
    ifc = ifcopenshell.file(schema="IFC4")

    # 1. Project & Units (Millimeters)
    project = ifcopenshell.api.run("root.create_entity", ifc, ifc_class="IfcProject", name="Sample Test Project")
    ifcopenshell.api.run("unit.assign_unit", ifc, length={"is_metric": True, "raw": "MILLIMETERS"})

    # 2. Site, Building, Storey
    site = ifcopenshell.api.run("root.create_entity", ifc, ifc_class="IfcSite", name="Test Site")
    building = ifcopenshell.api.run("root.create_entity", ifc, ifc_class="IfcBuilding", name="Test Building")
    storey = ifcopenshell.api.run("root.create_entity", ifc, ifc_class="IfcBuildingStorey", name="Level 01")

    ifcopenshell.api.run("aggregate.assign_object", ifc, relating_object=project, products=[site])
    ifcopenshell.api.run("aggregate.assign_object", ifc, relating_object=site, products=[building])
    ifcopenshell.api.run("aggregate.assign_object", ifc, relating_object=building, products=[storey])

    # 3. Walls
    # Wall 1: Interior Partition (Length 6000mm = ~19.685ft, Height 3000mm = ~9.84ft)
    wall1 = ifcopenshell.api.run(
        "root.create_entity",
        ifc,
        ifc_class="IfcWall",
        name="Interior Partition W-101",
    )
    ifcopenshell.api.run("spatial.assign_container", ifc, relating_structure=storey, products=[wall1])

    # Pset_WallCommon
    pset_wall1 = ifcopenshell.api.run("pset.add_pset", ifc, product=wall1, name="Pset_WallCommon")
    ifcopenshell.api.run(
        "pset.edit_pset",
        ifc,
        pset=pset_wall1,
        properties={"IsExternal": False, "LoadBearing": False, "FireRating": "1hr"},
    )

    # Qto_WallBaseQuantities
    qto_wall1 = ifcopenshell.api.run("pset.add_qto", ifc, product=wall1, name="Qto_WallBaseQuantities")
    ifcopenshell.api.run(
        "pset.edit_qto",
        ifc,
        qto=qto_wall1,
        properties={"Length": 6000.0, "Width": 150.0, "Height": 3000.0, "GrossSideArea": 18.0, "NetSideArea": 16.0},
    )

    # Wall 2: Structural Concrete (Excluded from Drywall)
    wall2 = ifcopenshell.api.run(
        "root.create_entity",
        ifc,
        ifc_class="IfcWall",
        name="Concrete Shear Wall W-102",
    )
    ifcopenshell.api.run("spatial.assign_container", ifc, relating_structure=storey, products=[wall2])

    pset_wall2 = ifcopenshell.api.run("pset.add_pset", ifc, product=wall2, name="Pset_WallCommon")
    ifcopenshell.api.run(
        "pset.edit_pset",
        ifc,
        pset=pset_wall2,
        properties={"IsExternal": False, "LoadBearing": True},
    )

    qto_wall2 = ifcopenshell.api.run("pset.add_qto", ifc, product=wall2, name="Qto_WallBaseQuantities")
    ifcopenshell.api.run(
        "pset.edit_qto",
        ifc,
        qto=qto_wall2,
        properties={"Length": 4000.0, "Width": 300.0, "Height": 3000.0, "GrossSideArea": 12.0},
    )

    # 4. Opening & Door in Wall 1 (Door 900mm x 2100mm)
    opening = ifcopenshell.api.run("root.create_entity", ifc, ifc_class="IfcOpeningElement", name="Door Opening O-101")
    door = ifcopenshell.api.run("root.create_entity", ifc, ifc_class="IfcDoor", name="Single Flush Door D-101")

    # Set door dimensions
    door.OverallWidth = 900.0
    door.OverallHeight = 2100.0

    # Voids relationship (Wall1 -> Opening)
    ifc.create_entity(
        "IfcRelVoidsElement",
        GlobalId=ifcopenshell.guid.new(),
        RelatingBuildingElement=wall1,
        RelatedOpeningElement=opening,
    )
    # Fills relationship (Opening -> Door)
    ifc.create_entity(
        "IfcRelFillsElement",
        GlobalId=ifcopenshell.guid.new(),
        RelatingOpeningElement=opening,
        RelatedBuildingElement=door,
    )

    # 5. Space / Room
    space = ifcopenshell.api.run("root.create_entity", ifc, ifc_class="IfcSpace", name="Office 101")
    ifcopenshell.api.run("aggregate.assign_object", ifc, relating_object=storey, products=[space])
    qto_space = ifcopenshell.api.run("pset.add_qto", ifc, product=space, name="Qto_SpaceBaseQuantities")
    ifcopenshell.api.run(
        "pset.edit_qto",
        ifc,
        qto=qto_space,
        properties={"NetFloorArea": 25.0, "GrossFloorArea": 27.0, "Height": 3000.0},
    )

    ifc.write(filepath)


def test_ifc_validator_and_reader():
    """Verifies that IFCValidator and IFCReader extract the structural hierarchy and dimensions accurately."""
    tmpdir = os.path.join(os.path.dirname(__file__), "scratch_tmp")
    os.makedirs(tmpdir, exist_ok=True)
    ifc_path = os.path.join(tmpdir, "test_model.ifc")
    try:
        create_sample_test_ifc(ifc_path)

        # 1. Validation
        validator = IFCValidator()
        report, ifc_file = validator.validate_file(ifc_path)
        assert report.is_valid is True
        assert report.schema == "IFC4"
        assert report.wall_count == 2
        assert report.door_count == 1
        assert report.opening_count == 1
        assert report.space_count == 1
        assert report.unit_scale_to_meters == 0.001

        # 2. Reader Parse
        reader = IFCReader(ifc_path)
        data = reader.parse()

        assert len(data["walls"]) == 2
        assert len(data["openings"]) >= 1
        assert len(data["spaces"]) == 1
        assert len(data["storeys"]) == 1

        # 3. Normalizer
        normalizer = BIMNormalizer()
        model = normalizer.normalize(data)

        assert len(model.walls) == 2
        assert model.total_drywall_eligible_walls == 1  # Concrete wall excluded

        w1 = next(w for w in model.walls if "W-101" in w.name)
        assert w1.drywall_scope_eligible is True
        assert abs(w1.length_ft - 19.685) < 0.05
        assert abs(w1.physical_height_ft - 9.84) < 0.05

        del ifc_file, reader
        import gc
        gc.collect()
        assert len(w1.openings) == 1

        w2 = next(w for w in model.walls if "W-102" in w.name)
        assert w2.drywall_scope_eligible is False
        assert w2.wall_classification == "STRUCTURAL_CONCRETE"
    finally:
        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_drywall_qto_calculation_precision():
    """Verifies that BIMDrywallEngine computes gross, opening deductions, and net quantities with 100% provenance."""
    # Construct a synthetic canonical wall
    opening = CanonicalOpening(
        id="OP-001",
        ifc_guid="GUID-OP-001",
        name="Door Opening",
        opening_type="DOOR",
        width_ft=3.0,
        height_ft=7.0,
        area_sqft=21.0,
    )

    wall = CanonicalWall(
        id="WALL-001",
        ifc_guid="3kL7Q4p018kF4bYx2v",
        name="Office Partition Wall",
        storey_id="STOREY-01",
        storey_name="Level 01",
        length_ft=20.0,
        nominal_thickness_in=4.75,
        physical_height_ft=10.0,
        start_point=(0.0, 0.0, 0.0),
        end_point=(20.0, 0.0, 0.0),
        openings=[opening],
        assembly=WallAssembly(
            stud_type="LIGHT_GAUGE_STEEL",
            stud_size='3-5/8"',
            stud_gauge="25ga",
            stud_spacing_in=16,
            board_type='5/8" Type X',
            side_a_layers=1,
            side_b_layers=1,
        ),
        wall_classification="INTERIOR_PARTITION",
        drywall_scope_eligible=True,
        drywall_finish_height_ft=10.0,
        drywall_side_a_scope=True,
        drywall_side_b_scope=True,
    )

    model = CanonicalBIMModel(
        project=CanonicalProject(
            id="PRJ-1",
            ifc_guid="GUID-PRJ-1",
            name="Test",
            schema_version="IFC4",
            length_unit="METRE",
        ),
        storeys=[CanonicalStorey(id="STOREY-01", ifc_guid="G-S1", name="Level 01", elevation_ft=0.0)],
        walls=[wall],
        openings=[opening],
    )

    engine = BIMDrywallEngine(waste_factor=0.10)
    qto = engine.calculate(model)

    # Gross single side = 20ft * 10ft = 200 sqft
    # Opening deduction = 21 sqft
    # Net single side = 200 - 21 = 179 sqft
    # Total net (Side A + Side B) = 179 * 2 = 358 sqft
    assert qto.total_gross_wall_area_sqft == 400.0  # Both sides gross
    assert qto.total_opening_deduction_sqft == 42.0  # Both sides deduction (21 * 2)
    assert qto.total_net_drywall_area_sqft == 358.0

    # With 10% waste: 358 * 1.10 = 393.8 sqft => ceil(393.8 / 32) = 13 sheets of 4x8
    assert qto.total_drywall_sheets_4x8 == 13

    # Studs: 20ft / (16/12) = 15 + 2 = 17 studs
    assert qto.total_studs_count == 17
    # Track linear feet: 20 * 2 = 40 LF
    assert qto.total_track_linear_ft == 40.0

    # Provenance audit verification
    assert len(qto.line_items) >= 3
    board_item = next(i for i in qto.line_items if i.category == "WALL_BOARD")
    assert board_item.source_guid == "3kL7Q4p018kF4bYx2v"
    assert board_item.provenance.ifc_guid == "3kL7Q4p018kF4bYx2v"
    assert board_item.provenance.net_drywall_sqft == 358.0
    assert board_item.provenance.status == "CONFIRMED"
