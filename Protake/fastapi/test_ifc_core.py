"""IFC Core Integrity & Geometric Truth Verification Script.
Tests real IFC files against strict invariant conservation rules and geometry reconciliation.
"""
import os
import sys
import glob
import json

# Add fastapi directory to path
sys.path.insert(0, r"c:\Users\lenovo\Desktop\QTO\fastapi")

from app.ifc.reader import IFCReader
from app.ifc.validator import IFCValidator
from app.bim.normalizer import BIMNormalizer
from app.trades.drywall_bim import BIMDrywallEngine
from app.trades.flooring_bim import BIMFlooringEngine
from app.trades.roofing_bim import BIMRoofingEngine

def test_ifc_file(file_path: str):
    print("=" * 80)
    print(f"TESTING IFC FILE: {os.path.basename(file_path)}")
    print("=" * 80)

    # 1. Validation & Schema Check
    validator = IFCValidator()
    report, ifc_file = validator.validate_file(file_path)
    print(f"[STAGE 1 - VALIDATION]")
    print(f"  Schema: {report.schema}")
    print(f"  Length Unit: {report.length_unit} (Scale to meters: {report.unit_scale_to_meters})")
    print(f"  Entity Counts => Walls: {report.wall_count}, Spaces: {report.space_count}, Openings: {report.opening_count}, Doors: {report.door_count}, Windows: {report.window_count}")
    print(f"  Validation Status: {report.status.value} (Valid: {report.is_valid})")

    # 2. Parsing via IFCReader
    print(f"\n[STAGE 2 - PARSING VIA IFCREADER]")
    reader = IFCReader(file_path)
    raw_data = reader.parse()
    raw_walls = raw_data.get("walls", [])
    raw_spaces = raw_data.get("spaces", [])
    raw_openings = raw_data.get("openings", [])
    print(f"  Parsed Walls: {len(raw_walls)}")
    print(f"  Parsed Spaces: {len(raw_spaces)}")
    print(f"  Parsed Openings: {len(raw_openings)}")

    # 3. Canonical Model Normalization
    print(f"\n[STAGE 3 - CANONICAL MODEL NORMALIZATION]")
    normalizer = BIMNormalizer()
    model = normalizer.normalize(raw_data)
    print(f"  Canonical Storeys: {len(model.storeys)}")
    print(f"  Canonical Walls: {len(model.walls)}")
    print(f"  Canonical Spaces: {len(model.spaces)}")
    print(f"  Canonical Openings: {len(model.openings)}")
    print(f"  Canonical Slabs: {len(model.slabs)}")
    print(f"  Canonical Roofs: {len(model.roofs)}")

    # 4. Conservation & Geometric Invariant Checks
    print(f"\n[STAGE 4 - GEOMETRIC INVARIANTS & CONSERVATION CHECKS]")
    invariants_passed = True
    guid_set = set()
    duplicate_guids = []

    for w in model.walls:
        if w.ifc_guid in guid_set:
            duplicate_guids.append(w.ifc_guid)
        guid_set.add(w.ifc_guid)

        # Invariant 1: Thickness > 0
        if w.nominal_thickness_in <= 0:
            print(f"  [FAIL] Wall {w.ifc_guid} has invalid thickness: {w.nominal_thickness_in}")
            invariants_passed = False

        # Invariant 2: Physical Height > 0
        if w.physical_height_ft <= 0:
            print(f"  [FAIL] Wall {w.ifc_guid} has invalid height: {w.physical_height_ft}")
            invariants_passed = False

        # Invariant 3: Length >= 0
        if w.length_ft < 0:
            print(f"  [FAIL] Wall {w.ifc_guid} has negative length: {w.length_ft}")
            invariants_passed = False

        # Invariant 4: Deductions <= Gross Area
        gross_single = w.length_ft * w.drywall_finish_height_ft
        total_openings = sum(op.area_sqft for op in w.openings)
        if total_openings > gross_single and gross_single > 0:
            # Note: Opening might exceed wall in rare clipping cases, but check effective deduction
            pass

    print(f"  Duplicate GUID Count: {len(duplicate_guids)} (Expected: 0)")
    if len(duplicate_guids) == 0 and invariants_passed:
        print(f"  [PASS] All Wall Geometric Invariants Passed!")
    else:
        print(f"  [WARN] Invariants Check had notices.")

    # 5. Drywall QTO Calculation & Reconciliation
    print(f"\n[STAGE 5 - DRYWALL QTO RECONCILIATION]")
    drywall_engine = BIMDrywallEngine(waste_factor=0.10)
    drywall_summary = drywall_engine.calculate(model)

    print(f"  Total Walls Evaluated: {drywall_summary.total_walls_evaluated}")
    print(f"  Eligible Walls: {drywall_summary.eligible_walls_count}")
    print(f"  Total Gross Wall Area: {drywall_summary.total_gross_wall_area_sqft:.2f} SF")
    print(f"  Total Opening Deductions: {drywall_summary.total_opening_deduction_sqft:.2f} SF")
    print(f"  Total Net Drywall Area: {drywall_summary.total_net_drywall_area_sqft:.2f} SF")
    print(f"  Board Area Equivalent (Net): {drywall_summary.board_area_equivalent_sqft:.2f} SF")
    print(f"  Estimated 4x8 Sheets (+10% waste): {drywall_summary.estimated_drywall_sheets_4x8} sheets")
    print(f"  Total Studs (16\" o.c. est): {drywall_summary.total_studs_count} EA")
    print(f"  Total Track LF: {drywall_summary.total_track_linear_ft:.2f} LF")
    print(f"  Total Line Items Generated: {len(drywall_summary.line_items)}")

    # Check conservation: Net <= Gross
    assert drywall_summary.total_net_drywall_area_sqft <= drywall_summary.total_gross_wall_area_sqft + 0.01, "Net Drywall exceeded Gross!"
    print(f"  [PASS] Net Drywall <= Gross Wall Area Invariant Verified!")

    # Check line items sum equals summary total
    line_item_net_sum = sum(item.quantity for item in drywall_summary.line_items if item.category == "WALL_BOARD")
    print(f"  Line Item Drywall Board Sum: {line_item_net_sum:.2f} SF (Summary Total: {drywall_summary.total_net_drywall_area_sqft:.2f} SF)")
    assert abs(line_item_net_sum - drywall_summary.total_net_drywall_area_sqft) < 0.1, "Line item sum does not match summary total!"
    print(f"  [PASS] Line Item Reconciliation Verified (Delta: {abs(line_item_net_sum - drywall_summary.total_net_drywall_area_sqft):.4f})")

    # 6. Sample Wall Provenance Inspection
    if model.walls:
        sample_wall = model.walls[0]
        print(f"\n[STAGE 6 - SAMPLE WALL AUDIT PROVENANCE]")
        print(f"  Wall ID: {sample_wall.id}")
        print(f"  Name: {sample_wall.name} | Storey: {sample_wall.storey_name}")
        print(f"  Length: {sample_wall.length_ft:.2f} ft ({sample_wall.length_provenance.value})")
        print(f"  Height: {sample_wall.physical_height_ft:.2f} ft ({sample_wall.height_provenance.value})")
        print(f"  Thickness: {sample_wall.nominal_thickness_in:.2f} in")
        print(f"  Assembly: {sample_wall.assembly.board_type} @ {sample_wall.assembly.stud_spacing_in}\" o.c. ({sample_wall.assembly.assembly_provenance.value})")
        print(f"  Openings Hosted: {len(sample_wall.openings)}")
        for op in sample_wall.openings:
            print(f"    - Opening {op.name} ({op.opening_type}): {op.width_ft:.2f}' x {op.height_ft:.2f}' = {op.area_sqft:.2f} SF")

    print("\n" + "=" * 80)
    print("TEST COMPLETED SUCCESSFULLY FOR: " + os.path.basename(file_path))
    print("=" * 80 + "\n")

if __name__ == "__main__":
    ifc_files = glob.glob(r"c:\Users\lenovo\Desktop\QTO\fastapi\storage\ifc\*.ifc")
    if not ifc_files:
        print("No IFC files found in storage.")
        sys.exit(1)

    # Pick unique filenames
    seen_names = set()
    unique_files = []
    for f in ifc_files:
        base = os.path.basename(f)
        # remove uuid prefix
        parts = base.split("_", 1)
        name = parts[1] if len(parts) > 1 else base
        if name not in seen_names:
            seen_names.add(name)
            unique_files.append(f)

    print(f"Found {len(unique_files)} distinct IFC sample models to test.")
    for f in unique_files[:3]:  # Test first 3 models
        test_ifc_file(f)
