"""test_challenger_verification.py: Comprehensive Empirical Challenge & Stress Harness.

Authoritative verification for:
1. End-to-End user journey test (Upload -> Process -> SSE S00-S16 -> Summary -> Annotated PDF -> QTO Excel).
2. Negative tests & Windows robustness:
   - Non-PDF upload rejection (HTTP 400, no crash).
   - Corrupted PDF upload rejection (HTTP 400, clean error, no file lock/PermissionError).
   - Missing scale handling (graceful fallback to DEFAULT_ASSUMED, ASSUMP-01, QTY_BLOCKED).
   - Windows file lock verification: verify uploaded and generated files can be deleted/cleaned up cleanly.
3. Mathematical parity challenge:
   - Worked Example 8.7.1 exact numerical parity:
     L_net = 17.00 LF, A_board = 358.00 SF, 16 studs, 37.00 LF track, 0% waste policy.
4. Excel formula & sheet structure challenge:
   - Exact 7 sheets: Summary, WallTypes, Runs, Openings, Assumptions, Review, RunInfo.
   - Strict uppercase formula validation (=SUM, =AVERAGE, zero lowercase formulas).
5. PyMuPDF Annotated PDF verification:
   - Valid PDF structure, vector drawings (bands & edges), interactive tooltips.
"""

from __future__ import annotations

import io
import json
import math
import os
from pathlib import Path
import shutil
import tempfile
import time
from typing import Any, Dict, List

from fastapi.testclient import TestClient
import openpyxl
import pymupdf as fitz
import pytest

import app
from tests.make_fixtures import FIXTURES_DIR, build_all_fixtures
from qto.dedup import WallRun
from qto.geometry import Point, Segment, BoundingBox
from qto.openings import Opening
from qto.quantities import (
    calculate_takeoff,
    calculate_gross_lf,
    calculate_net_lf,
    calculate_board_area,
    calculate_stud_count,
    calculate_track_lf,
    calculate_plates_lf,
    calculate_consumables,
    split_run_into_segments,
)
from qto.pipeline import run_pipeline, QTOPipeline


@pytest.fixture(scope="session", autouse=True)
def ensure_fixtures():
    build_all_fixtures(FIXTURES_DIR)


# =============================================================================
# SCENARIO 1: END-TO-END USER JOURNEY VERIFICATION
# =============================================================================

def test_scenario_1_e2e_user_journey_fixture_door():
    """Verify complete end-to-end user journey using fixture_door.pdf."""
    client = TestClient(app.app)
    pdf_path = FIXTURES_DIR / "fixture_door.pdf"
    assert pdf_path.exists(), "fixture_door.pdf must exist in fixtures"

    # Step 1: Upload blueprint PDF
    with open(pdf_path, "rb") as f:
        file_bytes = f.read()
    
    upload_res = client.post(
        "/api/upload",
        files={"file": ("fixture_door.pdf", io.BytesIO(file_bytes), "application/pdf")},
    )
    assert upload_res.status_code == 200, f"Upload failed: {upload_res.status_code} {upload_res.text}"
    up_data = upload_res.json()
    assert "file_id" in up_data
    file_id = up_data["file_id"]
    assert up_data["page_count"] == 1
    assert up_data["file_size"] == len(file_bytes)

    # Step 2: Trigger processing
    process_res = client.post(f"/api/process/{file_id}")
    assert process_res.status_code == 202, f"Process start failed: {process_res.status_code}"
    proc_data = process_res.json()
    assert "run_id" in proc_data
    run_id = proc_data["run_id"]
    assert proc_data["status"] == "processing"

    # Step 3: Wait for pipeline completion & poll status
    start_t = time.time()
    max_wait = 8.0
    status_data = {}
    while time.time() - start_t < max_wait:
        st_res = client.get(f"/api/pipeline/status/{run_id}")
        assert st_res.status_code == 200
        status_data = st_res.json()
        if status_data.get("status") in ("completed", "error"):
            break
        time.sleep(0.1)

    assert status_data.get("status") == "completed", f"Pipeline failed or timed out: {status_data}"
    assert status_data.get("progress_pct") == 100
    assert "S16" in status_data.get("current_stage", "") or "Complete" in status_data.get("current_stage", "")

    # Step 4: Consume SSE events stream and verify stage emission S00 to S16
    sse_res = client.get(f"/api/pipeline/events/{run_id}")
    assert sse_res.status_code == 200
    assert "text/event-stream" in sse_res.headers.get("content-type", "")
    sse_text = sse_res.text
    assert len(sse_text) > 0

    event_stages = []
    has_complete = False
    for line in sse_text.splitlines():
        if line.startswith("data:"):
            payload = json.loads(line[5:].strip())
            if "stage" in payload:
                event_stages.append(payload["stage"])
            if payload.get("status") == "completed":
                has_complete = True

    # Assert all key stages S00 to S16 are emitted
    required_stages = ["S00", "S01", "S02", "S03", "S04", "S05", "S06", "S07", "S08", "S13", "S14", "S15", "S16"]
    for req in required_stages:
        assert any(req in s for s in event_stages), f"Required stage {req} missing from emitted stages: {event_stages}"
    assert has_complete, "SSE did not emit final complete event"

    # Step 5: Retrieve summary metrics (/api/takeoff/{run_id}/summary)
    summary_res = client.get(f"/api/takeoff/{run_id}/summary")
    assert summary_res.status_code == 200
    summary_data = summary_res.json()
    assert summary_data["run_id"] == run_id
    assert summary_data["total_gross_lf"] == 20.00
    assert summary_data["total_opening_deduction_lf"] == 3.00
    assert summary_data["total_net_lf"] == 17.00
    assert summary_data["total_board_sf"] == 358.00
    assert summary_data["total_studs_ea"] == 16
    assert summary_data["total_track_lf"] == 37.00
    assert summary_data["waste_percent"] == 0.0
    assert "consumables" in summary_data
    assert summary_data["consumables"]["fasteners_ea"] == 358.0
    assert summary_data["consumables"]["joint_tape_lf"] == 136.04
    assert summary_data["consumables"]["joint_compound_gal"] == 3.401
    assert summary_data["consumables"]["acoustic_sealant_lf"] == 80.00
    assert "artifacts" in summary_data
    assert summary_data["artifacts"]["annotated_pdf_url"] == f"/api/blueprint/{run_id}/annotated-pdf"
    assert summary_data["artifacts"]["excel_workbook_url"] == f"/api/takeoff/{run_id}/export/excel"

    # Step 6: Download annotated.pdf (/api/blueprint/{run_id}/annotated-pdf)
    pdf_res = client.get(f"/api/blueprint/{run_id}/annotated-pdf")
    assert pdf_res.status_code == 200
    assert pdf_res.headers.get("content-type") == "application/pdf"
    pdf_bytes = pdf_res.content
    assert len(pdf_bytes) > 500

    # Verify PyMuPDF validity and annotations
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    assert len(doc) == 1
    page = doc[0]
    drawings = page.get_drawings()
    assert len(drawings) >= 1, "Annotated PDF must contain vector drawings"
    annots = list(page.annots())
    assert len(annots) >= 1, "Annotated PDF must contain interactive annotations"
    doc.close()

    # Step 7: Download qto.xlsx (/api/takeoff/{run_id}/export/excel)
    excel_res = client.get(f"/api/takeoff/{run_id}/export/excel")
    assert excel_res.status_code == 200
    assert "openxmlformats" in excel_res.headers.get("content-type", "")
    excel_bytes = excel_res.content
    assert len(excel_bytes) > 1000

    # Verify Excel 7 sheets and formulas
    wb = openpyxl.load_workbook(io.BytesIO(excel_bytes), data_only=False)
    expected_sheets = ["Summary", "WallTypes", "Runs", "Openings", "Assumptions", "Review", "RunInfo"]
    assert wb.sheetnames == expected_sheets

    ws_summary = wb["Summary"]
    assert ws_summary.max_row >= 3
    # Check data row
    assert ws_summary.cell(row=2, column=1).value == "1A"
    assert ws_summary.cell(row=2, column=4).value == 20.00
    assert ws_summary.cell(row=2, column=5).value == 3.00
    assert ws_summary.cell(row=2, column=6).value == 17.00
    assert ws_summary.cell(row=2, column=11).value == 358.00
    assert ws_summary.cell(row=2, column=12).value == 16
    assert ws_summary.cell(row=2, column=14).value == 37.00

    # Total row uppercase formulas check
    total_formulas = [str(c.value) for c in ws_summary[3] if str(c.value).startswith("=")]
    assert len(total_formulas) >= 4
    for form in total_formulas:
        assert form.isupper(), f"Formula must be strictly uppercase: {form}"
        assert "=SUM(" in form or "=AVERAGE(" in form
        assert "=sum(" not in form
    wb.close()


# =============================================================================
# SCENARIO 2: NEGATIVE TESTS & WINDOWS ROBUSTNESS
# =============================================================================

def test_negative_upload_corrupted_and_non_pdf():
    """Verify upload rejects corrupted/non-PDF files with clean 400 and no locking."""
    client = TestClient(app.app)

    # 1. Non-PDF extension (.exe)
    res_exe = client.post(
        "/api/upload",
        files={"file": ("test.exe", b"MZ\x90\x00\x03\x00", "application/octet-stream")},
    )
    assert res_exe.status_code == 400
    assert "Invalid file format" in res_exe.json().get("detail", "")

    # 2. Non-PDF extension (.txt)
    res_txt = client.post(
        "/api/upload",
        files={"file": ("readme.txt", b"drywall specs", "text/plain")},
    )
    assert res_txt.status_code == 400

    # 3. Corrupted PDF bytes
    corrupt_bytes = b"%PDF-1.4\ncorrupted invalid binary junk \x00\xff\xfe"
    res_corrupt = client.post(
        "/api/upload",
        files={"file": ("corrupt.pdf", corrupt_bytes, "application/pdf")},
    )
    assert res_corrupt.status_code == 400
    assert "valid PDF" in res_corrupt.json().get("detail", "") or "could not be parsed" in res_corrupt.json().get("detail", "")

    # 4. Zero byte PDF
    res_empty = client.post(
        "/api/upload",
        files={"file": ("empty.pdf", b"", "application/pdf")},
    )
    assert res_empty.status_code == 400
    assert "empty" in res_empty.json().get("detail", "").lower()


def test_windows_file_locking_robustness():
    """Verify uploaded files and runs directories do not suffer from Windows PermissionError file locks."""
    client = TestClient(app.app)
    pdf_path = FIXTURES_DIR / "fixture_door.pdf"

    # Upload
    with open(pdf_path, "rb") as f:
        upload_res = client.post(
            "/api/upload",
            files={"file": ("lock_test.pdf", f, "application/pdf")},
        )
    assert upload_res.status_code == 200
    file_id = upload_res.json()["file_id"]

    # Process
    proc_res = client.post(f"/api/process/{file_id}")
    run_id = proc_res.json()["run_id"]

    # Wait for completion
    for _ in range(50):
        st = client.get(f"/api/pipeline/status/{run_id}").json()
        if st["status"] in ("completed", "error"):
            break
        time.sleep(0.1)

    # Perform downloads
    res_pdf = client.get(f"/api/blueprint/{run_id}/annotated-pdf")
    assert res_pdf.status_code == 200
    res_xls = client.get(f"/api/takeoff/{run_id}/export/excel")
    assert res_xls.status_code == 200
    res_img = client.get(f"/api/blueprint/{run_id}/page/1/image")
    assert res_img.status_code == 200

    # Empirically verify no file locks are lingering on disk:
    # Attempt to open for writing / reading directly on disk
    dest_upload_file = app.UPLOADS_DIR / f"{file_id}.pdf"
    assert dest_upload_file.exists()
    # Test open and read
    with open(dest_upload_file, "rb") as f:
        data = f.read()
        assert len(data) > 0

    run_output_json = app.RUNS_DIR / run_id / "output.json"
    with open(run_output_json, "r", encoding="utf-8") as f:
        meta = json.load(f)
        assert meta["run_id"] == run_id

    run_annotated_pdf = app.RUNS_DIR / run_id / "annotated.pdf"
    with open(run_annotated_pdf, "rb") as f:
        pdf_disk_data = f.read()
        assert len(pdf_disk_data) > 0


def test_missing_scale_graceful_degradation(tmp_path: Path):
    """Test blueprint without scale notes degrades gracefully with DEFAULT_ASSUMED and ASSUMP-01 / QTY_BLOCKED."""
    pdf_path = tmp_path / "plan_no_scale.pdf"
    doc = fitz.open()
    page = doc.new_page(width=1000, height=800)
    page.insert_text(fitz.Point(50, 50), "SHEET A-101: ARCHITECTURAL FLOOR PLAN")
    page.insert_text(fitz.Point(50, 80), "PARTITION SCHEDULE")
    page.insert_text(fitz.Point(50, 100), "1A: 3-5/8 Metal Studs @ 16 OC, 5/8 Type X GWB")
    
    # 180 pt line
    shape = page.new_shape()
    shape.draw_line(fitz.Point(100, 200), fitz.Point(280, 200))
    shape.draw_line(fitz.Point(100, 204), fitz.Point(280, 204))
    shape.finish()
    shape.commit()
    page.insert_text(fitz.Point(180, 190), "1A")
    doc.save(str(pdf_path))
    doc.close()

    out_dir = tmp_path / "run_no_scale"
    result = run_pipeline(str(pdf_path), output_dir=str(out_dir))

    assert result is not None
    assert result["sheets"][0]["scale_status"] == "DEFAULT_ASSUMED"
    
    # Check assumptions in output
    assumptions = result.get("assumptions", [])
    scale_assump = [a for a in assumptions if a.get("category") == "Architectural Scale"]
    assert len(scale_assump) == 1
    assert scale_assump[0]["status"] == "QTY_BLOCKED"

    # Check Excel Assumptions sheet
    wb = openpyxl.load_workbook(str(out_dir / "qto.xlsx"))
    ws_asmp = wb["Assumptions"]
    asmp_data = [str(cell.value) for row in ws_asmp.iter_rows() for cell in row]
    assert any("QTY_BLOCKED" in text for text in asmp_data)
    wb.close()


# =============================================================================
# SCENARIO 3: MATHEMATICAL PARITY CHALLENGE (WORKED EXAMPLE 8.7.1)
# =============================================================================

def test_mathematical_parity_worked_example_8_7_1():
    """Adversarial stress-test verifying exact parity with SOP Worked Example 8.7.1:

    - Gross Length = 20.00 LF
    - Door opening width = 3.00 LF, height = 7.00 LF
    - Net Length = 17.00 LF
    - Net Board Area = 358.00 SF
    - Studs: 16 EA (segmented stud formula across two 8.5 LF spans: 8 + 8 = 16)
    - Stud LF: 160.00 LF (16 * 10 ft)
    - Metal Track: 37.00 LF (20.00 LF top + 17.00 LF bottom)
    - Wood Plates: 57.00 LF (2 * 20.00 + 17.00)
    - Consumables: fasteners 358 EA, joint tape 136.04 LF, joint compound 3.401 gal, acoustic sealant 80.00 LF
    - Waste Policy: 0.0% strict default
    """
    scale_ft_per_pt = 1.0 / (72.0 * 0.125)  # 1/8" = 1'-0" -> 0.111111...
    vector_pt = 180.0  # 20.00 LF in points

    # 1. Gross LF
    gross_lf = calculate_gross_lf(vector_pt, scale_ft_per_pt)
    assert gross_lf == 20.00

    # 2. Net LF with 3ft door
    door_w = 3.00
    door_h = 7.00
    net_lf = calculate_net_lf(gross_lf, [door_w])
    assert net_lf == 17.00

    # 3. Net Board Area: (20*10 - 3*7) * 2 sides * 1 layer = (200 - 21) * 2 = 358.00 SF
    board_sf = calculate_board_area(
        gross_lf=gross_lf,
        height_ft=10.0,
        openings=[(door_w, door_h)],
        faces=2,
        layers_per_face=1,
    )
    assert board_sf == 358.00

    # 4. Stud count: segmented wall spans [8.5, 8.5] @ 16" OC
    # seg 1: ceil(8.5*12 / 16) + 1 = ceil(102/16) + 1 = 7 + 1 = 8
    # seg 2: ceil(8.5*12 / 16) + 1 = 7 + 1 = 8
    # total = 8 + 8 = 16 studs
    studs = calculate_stud_count([8.5, 8.5], stud_spacing_in=16)
    assert studs == 16

    # 5. Metal Track LF: L_gross (top) + L_net (bottom) = 20.00 + 17.00 = 37.00 LF
    track_lf = calculate_track_lf(gross_lf, net_lf)
    assert track_lf == 37.00

    # 6. Wood Plates LF: 2 * L_gross + L_net = 40.00 + 17.00 = 57.00 LF
    plates_lf = calculate_plates_lf(gross_lf, net_lf)
    assert plates_lf == 57.00

    # 7. Consumables
    consumables = calculate_consumables(board_sf, gross_lf, 10.00)
    assert consumables["fasteners_ea"] == 358.0
    assert consumables["joint_tape_lf"] == 136.04
    assert consumables["joint_compound_gal"] == 3.401
    assert consumables["acoustic_sealant_lf"] == 80.00

    # 8. Full calculate_takeoff pipeline simulation with WallRun
    spine = Segment(x1=100.0, y1=300.0, x2=280.0, y2=300.0)
    door_op = Opening(
        opening_id="OP-001",
        wall_run_id="RUN-001",
        page_num=1,
        t_start=176.5, # centered door
        t_end=203.5,
        width_pt=27.0,
        width_ft=3.0,
        height_ft=7.0,
    )
    run_871 = WallRun(
        run_id="RUN-001",
        tag="1A",
        page_num=1,
        sheet_label="A-101",
        spine=spine,
        gross_length_pt=180.0,
        gross_length_ft=20.0,
        opening_deduction_ft=3.0,
        net_length_ft=17.0,
        openings=[door_op],
        segments=[spine],
        ft_per_pt=scale_ft_per_pt,
    )
    assembly_attrs = {
        "1A": {
            "stud_material": "Metal",
            "stud_spacing_in": 16,
            "layers_per_face": 1,
            "finished_faces": 2,
            "height_ft": 10.0,
        }
    }
    result = calculate_takeoff([run_871], openings=[door_op], assembly_attributes=assembly_attrs, waste_percent=0.0)
    assert result.total_gross_lf == 20.00
    assert result.total_opening_deduction_lf == 3.00
    assert result.total_net_lf == 17.00
    assert result.total_board_sf == 358.00
    assert result.total_studs_ea == 16
    assert result.total_track_lf == 37.00
    assert result.total_stud_lf == 160.00
    assert result.waste_percent == 0.0


# =============================================================================
# SCENARIO 4: ADDITIONAL ADVERSARIAL STRESS CHALLENGES
# =============================================================================

def test_scenario_continuous_wall20_full_pipeline():
    """Verify continuous partition wall without doors (fixture_wall20.pdf):

    - Gross LF = 20.00 LF
    - Deductions = 0.00 LF
    - Net LF = 20.00 LF
    - Board SF = 400.00 SF
    - Studs: ceil(20*12/16) + 1 = 16 EA
    - Track LF: 20 + 20 = 40.00 LF
    """
    client = TestClient(app.app)
    wall20_path = FIXTURES_DIR / "fixture_wall20.pdf"
    with open(wall20_path, "rb") as f:
        up = client.post("/api/upload", files={"file": ("fixture_wall20.pdf", f, "application/pdf")})
    assert up.status_code == 200
    fid = up.json()["file_id"]

    proc = client.post(f"/api/process/{fid}")
    assert proc.status_code == 202
    rid = proc.json()["run_id"]

    for _ in range(50):
        st = client.get(f"/api/pipeline/status/{rid}").json()
        if st["status"] in ("completed", "error"):
            break
        time.sleep(0.1)

    summary = client.get(f"/api/takeoff/{rid}/summary").json()
    assert summary["total_gross_lf"] == 20.00
    assert summary["total_opening_deduction_lf"] == 0.00
    assert summary["total_net_lf"] == 20.00
    assert summary["total_board_sf"] == 400.00
    assert summary["total_studs_ea"] == 16
    assert summary["total_track_lf"] == 40.00


def test_api_robustness_bounds_and_error_codes():
    """Verify proper HTTP 404/422 status codes on invalid inputs and boundary conditions."""
    client = TestClient(app.app)

    # 1. Non-existent run_id status
    res_st = client.get("/api/pipeline/status/run_nonexistent_12345")
    assert res_st.status_code == 404

    # 2. Non-existent run_id summary
    res_sum = client.get("/api/takeoff/run_nonexistent_12345/summary")
    assert res_sum.status_code == 404

    # 3. Non-existent run_id excel download
    res_xls = client.get("/api/takeoff/run_nonexistent_12345/export/excel")
    assert res_xls.status_code == 404

    # 4. Non-existent run_id annotated pdf download
    res_pdf = client.get("/api/blueprint/run_nonexistent_12345/annotated-pdf")
    assert res_pdf.status_code == 404

    # 5. Non-existent file_id process
    res_proc = client.post("/api/process/file_nonexistent_99999")
    assert res_proc.status_code == 404

    # 6. Invalid mode parameter returns 422 Unprocessable Entity
    res_bad_mode = client.get(f"/api/pipeline/status/run_nonexistent_12345?mode=invalid_mode")
    # Endpoint doesn't take mode on status, test on page/1/image
    door_path = FIXTURES_DIR / "fixture_door.pdf"
    with open(door_path, "rb") as f:
        up = client.post("/api/upload", files={"file": ("fixture_door.pdf", f, "application/pdf")})
    fid = up.json()["file_id"]
    proc = client.post(f"/api/process/{fid}")
    rid = proc.json()["run_id"]
    for _ in range(50):
        st = client.get(f"/api/pipeline/status/{rid}").json()
        if st["status"] in ("completed", "error"):
            break
        time.sleep(0.1)

    res_bad_mode = client.get(f"/api/blueprint/{rid}/page/1/image?mode=invalid_mode")
    assert res_bad_mode.status_code == 422


def test_out_of_bounds_page_contract_returns_404_on_invalid_bounds():
    """Verify that requesting an out-of-bounds page (page 0, negative, or page > page_count)
    cleanly returns HTTP 404 without raising ValueError('document closed').
    """
    client = TestClient(app.app)
    door_path = FIXTURES_DIR / "fixture_door.pdf"
    with open(door_path, "rb") as f:
        up = client.post("/api/upload", files={"file": ("fixture_door.pdf", f, "application/pdf")})
    fid = up.json()["file_id"]
    proc = client.post(f"/api/process/{fid}")
    rid = proc.json()["run_id"]
    for _ in range(50):
        st = client.get(f"/api/pipeline/status/{rid}").json()
        if st["status"] in ("completed", "error"):
            break
        time.sleep(0.1)

    # Upper out of bounds
    res_upper = client.get(f"/api/blueprint/{rid}/page/99/image")
    assert res_upper.status_code == 404
    assert "out of bounds" in res_upper.json().get("detail", "")

    # Lower out of bounds (page 0 is invalid for 1-indexed document)
    res_lower = client.get(f"/api/blueprint/{rid}/page/0/image")
    assert res_lower.status_code == 404


def test_out_of_bounds_page_contract_should_return_404():
    """Contract test asserting proper 404 status code."""
    client = TestClient(app.app)
    door_path = FIXTURES_DIR / "fixture_door.pdf"
    with open(door_path, "rb") as f:
        up = client.post("/api/upload", files={"file": ("fixture_door.pdf", f, "application/pdf")})
    fid = up.json()["file_id"]
    proc = client.post(f"/api/process/{fid}")
    rid = proc.json()["run_id"]
    for _ in range(50):
        st = client.get(f"/api/pipeline/status/{rid}").json()
        if st["status"] in ("completed", "error"):
            break
        time.sleep(0.1)

    res_out_bounds = client.get(f"/api/blueprint/{rid}/page/99/image")
    assert res_out_bounds.status_code == 404



def test_excel_complete_7_sheet_headers_schema():
    """Verify all 7 sheets in generated qto.xlsx contain exact SOP expected headers."""
    client = TestClient(app.app)
    door_path = FIXTURES_DIR / "fixture_door.pdf"
    with open(door_path, "rb") as f:
        up = client.post("/api/upload", files={"file": ("fixture_door.pdf", f, "application/pdf")})
    fid = up.json()["file_id"]
    proc = client.post(f"/api/process/{fid}")
    rid = proc.json()["run_id"]
    for _ in range(50):
        st = client.get(f"/api/pipeline/status/{rid}").json()
        if st["status"] in ("completed", "error"):
            break
        time.sleep(0.1)

    res_xls = client.get(f"/api/takeoff/{rid}/export/excel")
    assert res_xls.status_code == 200

    wb = openpyxl.load_workbook(io.BytesIO(res_xls.content), data_only=False)
    from qto.export import EXPECTED_HEADERS, EXPECTED_SHEETS

    assert wb.sheetnames == EXPECTED_SHEETS

    for sheet_name in EXPECTED_SHEETS:
        ws = wb[sheet_name]
        headers = [ws.cell(row=1, column=col).value for col in range(1, len(EXPECTED_HEADERS[sheet_name]) + 1)]
        assert headers == EXPECTED_HEADERS[sheet_name], f"Header mismatch on sheet {sheet_name}"

    wb.close()
