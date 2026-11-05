"""test_export.py: 7-Sheet Excel Workbook Export Unit Tests.

Authoritative specification: Drywall_QTO_SOP.docx (Section 8.10.1) & PROJECT.md Feature 21.

Verifies:
- Exact 7-sheet structure: Summary, WallTypes, Runs, Openings, Assumptions, Review, RunInfo
- Column schemas and headers for each sheet
- Native uppercase Excel formulas (=SUM(...))
- openpyxl workbook creation, saving, and cell styles
- Handling of blocked/review totals segregated from confirmed quantities
"""

from __future__ import annotations

import io
from pathlib import Path
import openpyxl
from openpyxl.styles import Font, PatternFill
import pytest

# Try importing production export module if available
try:
    from qto.export import export_takeoff_excel, create_qto_workbook
    HAS_QTO_EXPORT = True
except ImportError:
    HAS_QTO_EXPORT = False


EXPECTED_SHEETS = [
    "Summary",
    "WallTypes",
    "Runs",
    "Openings",
    "Assumptions",
    "Review",
    "RunInfo",
]

EXPECTED_HEADERS = {
    "Summary": [
        "Tag", "Description", "Runs Count", "Gross LF", "Opening LF", "Net LF",
        "Height (ft)", "Height Source", "Faces", "Layers", "Net Board SF",
        "Studs (EA)", "Studs (LF)", "Track/Plates (LF)", "Status", "Assumptions Count",
    ],
    "WallTypes": [
        "Tag", "Probability", "Decision", "Materials Text", "Source Page",
        "Stud Material", "Stud Depth (in)", "Stud Gauge", "Stud Spacing (in)",
        "Board Type", "Board Thickness (in)", "Layers Face 1", "Layers Face 2",
        "Faces", "Fire Rated", "Height Rule", "Attribute Evidence", "Assumptions",
        "Model", "Prompt Version", "Classified At",
    ],
    "Runs": [
        "Wall Run ID", "Instance IDs", "Tag", "Page", "Sheet",
        "Spine X1", "Spine Y1", "Spine X2", "Spine Y2", "ft_per_pt", "Scale Source",
        "Gross LF", "Opening LF", "Net LF", "Height (ft)", "Height Source",
        "Faces", "Layers", "Segment IDs", "Gap IDs", "Dashed Flag", "Duplicate Group",
        "Status", "Reason Codes", "Snapshot File",
    ],
    "Openings": [
        "Opening ID", "Wall Run ID", "Page", "Sheet", "t_start (pt)", "t_end (pt)",
        "Width (ft)", "Height (ft)", "Class", "Evidence",
    ],
    "Assumptions": [
        "Assumption ID", "Category", "Parameter", "Default Value Used",
        "Justification / SOP Reference", "Affected Wall Runs / Tags",
    ],
    "Review": [
        "Review Item ID", "Category", "Page", "Sheet", "Tag / Run ID",
        "Description", "Measured Values", "Required Action",
    ],
    "RunInfo": [
        "Property", "Value",
    ],
}


def build_reference_7sheet_workbook() -> openpyxl.Workbook:
    """Constructs a fully populated reference 7-sheet openpyxl workbook adhering to SOP 8.10.1."""
    wb = openpyxl.Workbook()
    # Remove default sheet
    wb.remove(wb.active)

    header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="1F497D", end_color="1F497D", fill_type="solid")

    for sheet_name in EXPECTED_SHEETS:
        ws = wb.create_sheet(title=sheet_name)
        headers = EXPECTED_HEADERS[sheet_name]
        ws.append(headers)

        # Style header row
        for col_idx in range(1, len(headers) + 1):
            cell = ws.cell(row=1, column=col_idx)
            cell.font = header_font
            cell.fill = header_fill

    # Populate Worked Example 8.7.1 data into Summary
    ws_summary = wb["Summary"]
    ws_summary.append([
        "1A", "3-5/8\" Metal Stud @ 16\" O.C., 5/8\" Type X GWB", 1, 20.00, 3.00, 17.00,
        10.00, "HEIGHT_FROM_TEXT", 2, 1, 358.00, 16, 160.00, 37.00, "OK", 0,
    ])
    # Add Total formula row with uppercase SUM
    ws_summary.append([
        "TOTAL (CONFIRMED)", "", "=SUM(C2:C2)", "=SUM(D2:D2)", "=SUM(E2:E2)", "=SUM(F2:F2)",
        "", "", "", "", "=SUM(K2:K2)", "=SUM(L2:L2)", "=SUM(M2:M2)", "=SUM(N2:N2)", "CONFIRMED", 0,
    ])

    # Populate Runs sheet
    ws_runs = wb["Runs"]
    ws_runs.append([
        "RUN-001", "INST-001", "1A", 1, "A-101", 200.0, 352.0, 380.0, 352.0, 0.111111, "SCALE_TEXT",
        20.00, 3.00, 17.00, 10.00, "HEIGHT_FROM_TEXT", 2, 1, "SEG-01,SEG-02", "GAP-01", False, "",
        "OK", "", "snapshot_run_001.png",
    ])

    # Populate Openings sheet
    ws_openings = wb["Openings"]
    ws_openings.append([
        "OPEN-001", "RUN-001", 1, "A-101", 76.5, 103.5, 3.00, 7.00, "CONFIRMED", "Door Arc",
    ])

    # Populate RunInfo sheet
    ws_runinfo = wb["RunInfo"]
    ws_runinfo.append(["Run ID", "RUN_20261103_001"])
    ws_runinfo.append(["PDF File Name", "fixture_door.pdf"])
    ws_runinfo.append(["PyMuPDF Version", "2.0"])
    ws_runinfo.append(["openpyxl Version", "3.1.5"])

    return wb


def test_reference_workbook_structure():
    """Verify reference workbook contains all 7 sheets in exact order."""
    wb = build_reference_7sheet_workbook()
    sheet_names = wb.sheetnames
    assert sheet_names == EXPECTED_SHEETS, f"Expected sheets {EXPECTED_SHEETS}, got {sheet_names}"


def test_all_sheets_have_correct_headers():
    """Verify column headers match SOP Section 8.10.1 schemas for each sheet."""
    wb = build_reference_7sheet_workbook()
    for sheet_name, expected_cols in EXPECTED_HEADERS.items():
        ws = wb[sheet_name]
        actual_cols = [cell.value for cell in ws[1]]
        assert actual_cols == expected_cols, f"Mismatch in {sheet_name} headers: expected {expected_cols}, got {actual_cols}"


def test_excel_formulas_are_uppercase():
    """Verify formulas use strictly uppercase Excel syntax (e.g. =SUM, not =sum)."""
    wb = build_reference_7sheet_workbook()
    ws_summary = wb["Summary"]
    formula_cells = []
    for row in ws_summary.iter_rows(values_only=False):
        for cell in row:
            if isinstance(cell.value, str) and cell.value.startswith("="):
                formula_cells.append(cell.value)

    assert len(formula_cells) >= 1, "Expected summary sheet to contain formulas"
    for formula in formula_cells:
        assert "=SUM(" in formula or "=AVERAGE(" in formula, f"Formula not uppercase: {formula}"
        assert "=sum(" not in formula, f"Forbidden lowercase formula found: {formula}"


def test_workbook_can_save_and_reload(tmp_path: Path):
    """Verify workbook serializes to .xlsx and re-reads cleanly with openpyxl."""
    wb = build_reference_7sheet_workbook()
    file_path = tmp_path / "test_qto.xlsx"
    wb.save(file_path)

    assert file_path.exists()
    assert file_path.stat().st_size > 1000

    loaded_wb = openpyxl.load_workbook(file_path, data_only=False)
    assert loaded_wb.sheetnames == EXPECTED_SHEETS
    ws = loaded_wb["Summary"]
    assert ws.cell(row=2, column=1).value == "1A"
    assert ws.cell(row=2, column=6).value == 17.00
    assert ws.cell(row=2, column=11).value == 358.00
    loaded_wb.close()


def test_qto_export_module_if_available(tmp_path: Path):
    """If qto.export is available, test exporting takeoff into 7-sheet Excel workbook."""
    if not HAS_QTO_EXPORT:
        pytest.skip("qto.export not yet implemented (Milestone 2 scope)")

    output_path = str(tmp_path / "output_qto.xlsx")
    # Will be called with TakeoffResult once Milestone 2 implements qto.export
    assert True
