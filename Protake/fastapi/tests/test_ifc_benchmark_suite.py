"""IFC Ground Truth Benchmark Test Suite:
Tests diverse IFC model scenarios, schema variants, unit scales, edge cases,
and QTO Eligibility Gates against expected ground truth quantities.
"""
import os
import sys
import tempfile
import pytest
import ifcopenshell
import ifcopenshell.api

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.bim.models import (
    CanonicalBIMModel,
    DataProvenanceStatus,
    QTOEligibilityStatus,
    QTOReadiness,
)
from app.bim.normalizer import BIMNormalizer
from app.ifc.reader import IFCReader
from app.ifc.validator import IFCValidator
from app.trades.drywall_bim import BIMDrywallEngine


# ==============================================================================
# BENCHMARK 1: Multi-Storey Commercial Model (IFC4, Millimeters)
# ==============================================================================
def test_benchmark_multi_storey_commercial():
    with tempfile.TemporaryDirectory() as tmpdir:
        ifc_path = os.path.join(tmpdir, "multi_storey.ifc")
        ifc = ifcopenshell.file(schema="IFC4")

        project = ifcopenshell.api.run("root.create_entity", ifc, ifc_class="IfcProject", name="Commercial Tower")
        ifcopenshell.api.run("unit.assign_unit", ifc, length={"is_metric": True, "raw": "MILLIMETERS"})
        site = ifcopenshell.api.run("root.create_entity", ifc, ifc_class="IfcSite", name="Commercial Site")
        building = ifcopenshell.api.run("root.create_entity", ifc, ifc_class="IfcBuilding", name="Tower A")
        
        # 2 Storeys
        storey1 = ifcopenshell.api.run("root.create_entity", ifc, ifc_class="IfcBuildingStorey", name="Level 01")
        storey1.Elevation = 0.0
        storey2 = ifcopenshell.api.run("root.create_entity", ifc, ifc_class="IfcBuildingStorey", name="Level 02")
        storey2.Elevation = 3500.0  # 3.5m

        ifcopenshell.api.run("aggregate.assign_object", ifc, relating_object=project, products=[site])
        ifcopenshell.api.run("aggregate.assign_object", ifc, relating_object=site, products=[building])
        ifcopenshell.api.run("aggregate.assign_object", ifc, relating_object=building, products=[storey1, storey2])

        # Wall on Level 1 (Length 10m = 32.81ft, Height 3.5m = 11.48ft)
        w_l1 = ifcopenshell.api.run("root.create_entity", ifc, ifc_class="IfcWall", name="Corridor Partition L1")
        ifcopenshell.api.run("spatial.assign_container", ifc, relating_structure=storey1, products=[w_l1])
        qto_l1 = ifcopenshell.api.run("pset.add_qto", ifc, product=w_l1, name="Qto_WallBaseQuantities")
        ifcopenshell.api.run("pset.edit_qto", ifc, qto=qto_l1, properties={"Length": 10000.0, "Width": 150.0, "Height": 3500.0})

        # Wall on Level 2 (Length 8m = 26.25ft, Height 3.5m = 11.48ft)
        w_l2 = ifcopenshell.api.run("root.create_entity", ifc, ifc_class="IfcWall", name="Office Partition L2")
        ifcopenshell.api.run("spatial.assign_container", ifc, relating_structure=storey2, products=[w_l2])
        qto_l2 = ifcopenshell.api.run("pset.add_qto", ifc, product=w_l2, name="Qto_WallBaseQuantities")
        ifcopenshell.api.run("pset.edit_qto", ifc, qto=qto_l2, properties={"Length": 8000.0, "Width": 150.0, "Height": 3500.0})

        ifc.write(ifc_path)

        # Parse & Validate
        reader = IFCReader(ifc_path)
        data = reader.parse()
        model = BIMNormalizer().normalize(data)

        assert len(model.storeys) == 2
        assert len(model.walls) == 2

        # Verify Storey separation
        w1 = next(w for w in model.walls if "L1" in w.name)
        w2 = next(w for w in model.walls if "L2" in w.name)
        assert w1.storey_name == "Level 01"
        assert w2.storey_name == "Level 02"

        # Calculate QTO
        qto = BIMDrywallEngine().calculate(model)
        assert qto.eligible_walls_count == 2
        assert qto.total_net_drywall_area_sqft > 1000.0  # Both storeys calculated


# ==============================================================================
# BENCHMARK 2: Mixed Concrete Core & Drywall Partitions (Scope Gating)
# ==============================================================================
def test_benchmark_mixed_concrete_and_drywall_gate():
    with tempfile.TemporaryDirectory() as tmpdir:
        ifc_path = os.path.join(tmpdir, "mixed_structural.ifc")
        ifc = ifcopenshell.file(schema="IFC4")

        project = ifcopenshell.api.run("root.create_entity", ifc, ifc_class="IfcProject", name="Core & Shell")
        ifcopenshell.api.run("unit.assign_unit", ifc, length={"is_metric": True, "raw": "MILLIMETERS"})
        site = ifcopenshell.api.run("root.create_entity", ifc, ifc_class="IfcSite", name="Site")
        building = ifcopenshell.api.run("root.create_entity", ifc, ifc_class="IfcBuilding", name="Building")
        storey = ifcopenshell.api.run("root.create_entity", ifc, ifc_class="IfcBuildingStorey", name="Level 01")

        ifcopenshell.api.run("aggregate.assign_object", ifc, relating_object=project, products=[site])
        ifcopenshell.api.run("aggregate.assign_object", ifc, relating_object=site, products=[building])
        ifcopenshell.api.run("aggregate.assign_object", ifc, relating_object=building, products=[storey])

        # 1. Structural Concrete Core (Should be Gated OUT)
        w_conc = ifcopenshell.api.run("root.create_entity", ifc, ifc_class="IfcWall", name="Concrete Elevator Core Wall")
        ifcopenshell.api.run("spatial.assign_container", ifc, relating_structure=storey, products=[w_conc])
        pset_conc = ifcopenshell.api.run("pset.add_pset", ifc, product=w_conc, name="Pset_WallCommon")
        ifcopenshell.api.run("pset.edit_pset", ifc, pset=pset_conc, properties={"LoadBearing": True})
        qto_conc = ifcopenshell.api.run("pset.add_qto", ifc, product=w_conc, name="Qto_WallBaseQuantities")
        ifcopenshell.api.run("pset.edit_qto", ifc, qto=qto_conc, properties={"Length": 8000.0, "Width": 350.0, "Height": 4000.0})

        # 2. Curtain Wall / Storefront (Should be Gated OUT)
        w_curtain = ifcopenshell.api.run("root.create_entity", ifc, ifc_class="IfcWall", name="Storefront Glazing System")
        ifcopenshell.api.run("spatial.assign_container", ifc, relating_structure=storey, products=[w_curtain])
        qto_curtain = ifcopenshell.api.run("pset.add_qto", ifc, product=w_curtain, name="Qto_WallBaseQuantities")
        ifcopenshell.api.run("pset.edit_qto", ifc, qto=qto_curtain, properties={"Length": 12000.0, "Width": 100.0, "Height": 3500.0})

        # 3. Drywall Partition (Should be ELIGIBLE)
        w_drywall = ifcopenshell.api.run("root.create_entity", ifc, ifc_class="IfcWall", name="Interior Drywall Partition")
        ifcopenshell.api.run("spatial.assign_container", ifc, relating_structure=storey, products=[w_drywall])
        qto_drywall = ifcopenshell.api.run("pset.add_qto", ifc, product=w_drywall, name="Qto_WallBaseQuantities")
        ifcopenshell.api.run("pset.edit_qto", ifc, qto=qto_drywall, properties={"Length": 6000.0, "Width": 120.0, "Height": 3000.0})

        ifc.write(ifc_path)

        data = IFCReader(ifc_path).parse()
        model = BIMNormalizer().normalize(data)

        # Verify Gate Classifications
        wall_map = {w.name: w for w in model.walls}
        assert wall_map["Concrete Elevator Core Wall"].qto_eligibility == QTOEligibilityStatus.INELIGIBLE_NON_DRYWALL
        assert wall_map["Storefront Glazing System"].qto_eligibility == QTOEligibilityStatus.INELIGIBLE_NON_DRYWALL
        assert wall_map["Interior Drywall Partition"].qto_eligibility == QTOEligibilityStatus.ELIGIBLE

        # QTO should strictly calculate only the eligible drywall wall
        qto = BIMDrywallEngine().calculate(model)
        assert qto.total_walls_evaluated == 3
        assert qto.eligible_walls_count == 1
        assert qto.excluded_walls_count == 2


# ==============================================================================
# BENCHMARK 3: Missing Material Data Triggers Model Health Review
# ==============================================================================
def test_benchmark_missing_materials_model_health():
    with tempfile.TemporaryDirectory() as tmpdir:
        ifc_path = os.path.join(tmpdir, "incomplete_model.ifc")
        ifc = ifcopenshell.file(schema="IFC4")

        project = ifcopenshell.api.run("root.create_entity", ifc, ifc_class="IfcProject", name="Bare IFC Model")
        ifcopenshell.api.run("unit.assign_unit", ifc, length={"is_metric": True, "raw": "MILLIMETERS"})
        building = ifcopenshell.api.run("root.create_entity", ifc, ifc_class="IfcBuilding", name="Building")
        storey = ifcopenshell.api.run("root.create_entity", ifc, ifc_class="IfcBuildingStorey", name="Level 01")

        ifcopenshell.api.run("aggregate.assign_object", ifc, relating_object=project, products=[building])
        ifcopenshell.api.run("aggregate.assign_object", ifc, relating_object=building, products=[storey])

        # Wall with zero Psets, zero materials, bare geometry
        w_bare = ifcopenshell.api.run("root.create_entity", ifc, ifc_class="IfcWall", name="Generic Bare Wall")
        ifcopenshell.api.run("spatial.assign_container", ifc, relating_structure=storey, products=[w_bare])

        ifc.write(ifc_path)

        data = IFCReader(ifc_path).parse()
        model = BIMNormalizer().normalize(data)

        # Health Card verification
        assert model.health_card is not None
        assert model.health_card.material_coverage_score == 0.0
        assert model.health_card.readiness == QTOReadiness.REVIEW_REQUIRED
        assert len(model.health_card.readiness_notes) > 0


# ==============================================================================
# BENCHMARK 4: Multiple Hosted Openings (Doors + Windows + Voids)
# ==============================================================================
def test_benchmark_multiple_openings_deductions():
    with tempfile.TemporaryDirectory() as tmpdir:
        ifc_path = os.path.join(tmpdir, "openings_benchmark.ifc")
        ifc = ifcopenshell.file(schema="IFC4")

        project = ifcopenshell.api.run("root.create_entity", ifc, ifc_class="IfcProject", name="Openings Project")
        ifcopenshell.api.run("unit.assign_unit", ifc, length={"is_metric": True, "raw": "MILLIMETERS"})
        building = ifcopenshell.api.run("root.create_entity", ifc, ifc_class="IfcBuilding", name="Building")
        storey = ifcopenshell.api.run("root.create_entity", ifc, ifc_class="IfcBuildingStorey", name="Level 01")

        ifcopenshell.api.run("aggregate.assign_object", ifc, relating_object=project, products=[building])
        ifcopenshell.api.run("aggregate.assign_object", ifc, relating_object=building, products=[storey])

        # Wall: Length 10m (32.808ft), Height 3m (9.843ft) => Single side gross = ~322.92 sqft
        wall = ifcopenshell.api.run("root.create_entity", ifc, ifc_class="IfcWall", name="Long Partition with Openings")
        ifcopenshell.api.run("spatial.assign_container", ifc, relating_structure=storey, products=[wall])
        qto_w = ifcopenshell.api.run("pset.add_qto", ifc, product=wall, name="Qto_WallBaseQuantities")
        ifcopenshell.api.run("pset.edit_qto", ifc, qto=qto_w, properties={"Length": 10000.0, "Width": 150.0, "Height": 3000.0})

        # Opening 1: Door (1000mm x 2100mm = 1.0m x 2.1m = 2.1 sqm = ~22.60 sqft)
        op1 = ifcopenshell.api.run("root.create_entity", ifc, ifc_class="IfcOpeningElement", name="Door Void 1")
        door1 = ifcopenshell.api.run("root.create_entity", ifc, ifc_class="IfcDoor", name="Door 1")
        door1.OverallWidth = 1000.0
        door1.OverallHeight = 2100.0

        ifc.create_entity("IfcRelVoidsElement", GlobalId=ifcopenshell.guid.new(), RelatingBuildingElement=wall, RelatedOpeningElement=op1)
        ifc.create_entity("IfcRelFillsElement", GlobalId=ifcopenshell.guid.new(), RelatingOpeningElement=op1, RelatedBuildingElement=door1)

        # Opening 2: Window (1500mm x 1200mm = 1.5m x 1.2m = 1.8 sqm = ~19.38 sqft)
        op2 = ifcopenshell.api.run("root.create_entity", ifc, ifc_class="IfcOpeningElement", name="Window Void 2")
        win2 = ifcopenshell.api.run("root.create_entity", ifc, ifc_class="IfcWindow", name="Window 2")
        win2.OverallWidth = 1500.0
        win2.OverallHeight = 1200.0

        ifc.create_entity("IfcRelVoidsElement", GlobalId=ifcopenshell.guid.new(), RelatingBuildingElement=wall, RelatedOpeningElement=op2)
        ifc.create_entity("IfcRelFillsElement", GlobalId=ifcopenshell.guid.new(), RelatingOpeningElement=op2, RelatedBuildingElement=win2)

        ifc.write(ifc_path)

        data = IFCReader(ifc_path).parse()
        model = BIMNormalizer().normalize(data)
        qto = BIMDrywallEngine().calculate(model)

        assert len(model.walls[0].openings) == 2
        # Deductions should equal Door + Window area on both sides
        expected_single_side_deduction = (1.0 * 2.1 + 1.5 * 1.2) * 10.76391  # ~41.98 sqft
        assert abs(qto.total_opening_deduction_sqft - (expected_single_side_deduction * 2)) < 2.0
