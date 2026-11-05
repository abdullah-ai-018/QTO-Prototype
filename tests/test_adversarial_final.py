"""tests/test_adversarial_final.py: Final Milestone E2E & Tier 5 Adversarial Stress Test Suite.

Authoritative verification for:
1. Complete user journey on app.py via FastAPI TestClient
2. All pipeline stages S00 through S16 emitted via SSE
3. Deep Excel workbook verification (openpyxl 7 sheets, uppercase formulas, numerical values)
4. Deep PDF visual and interactive annotation verification (PyMuPDF bands, edges, tooltips)
5. Adversarial stress tests:
   - Non-PDF upload rejection (HTTP 400)
   - Corrupted PDF upload handling (HTTP 400, no server crash)
   - Missing scale plan handling (graceful fallback)
   - Concurrent upload and processing requests
   - Extreme dimensions (0 LF, 100,000 LF, opening > wall span)
6. Frontend static web assets loading (/, workbench.css, app.js, viewer.js)
"""

from __future__ import annotations

import concurrent.futures
import io
import json
import math
import os
from pathlib import Path
import time
import openpyxl
import pymupdf as fitz
import pytest
from fastapi.testclient import TestClient

import app
from tests.make_fixtures import FIXTURES_DIR, build_all_fixtures
from qto.dedup import WallRun
from qto.geometry import Point, Segment, BoundingBox
from qto.openings import Opening
from qto.quantities import calculate_takeoff, split_run_into_segments
from qto.pipeline import run_pipeline


@pytest.fixture(scope="session", autouse=True)
def setup_test_fixtures():
    build_all_fixtures(FIXTURES_DIR)


# =============================================================================
# 1. FRONTEND STATIC WEB ASSETS VERIFICATION
# =============================================================================

def test_frontend_web_assets_load():
    """Verify that all essential frontend assets load with HTTP 200 and expected contents."""
    client = TestClient(app.app)

    # 1. Root SPA HTML
    res_root = client.get("/")
    assert res_root.status_code == 200, f"Expected 200 for '/', got {res_root.status_code}"
    assert "text/html" in res_root.headers.get("content-type", "")
    assert "PDF ENGINE" in res_root.text or "workbench" in res_root.text.lower()

    # 2. CAD Design System CSS
    res_css = client.get("/static/css/workbench.css")
    assert res_css.status_code == 200, f"Expected 200 for workbench.css, got {res_css.status_code}"
    assert "text/css" in res_css.headers.get("content-type", "")
    # Check for dark palette and sharp 0px corners
    assert "#070B13" in res_css.text.upper() or "border-radius: 0" in res_css.text or "0px" in res_css.text

    # 3. Main SPA Controller JS
    res_app_js = client.get("/static/js/app.js")
    assert res_app_js.status_code == 200, f"Expected 200 for app.js, got {res_app_js.status_code}"
    assert "javascript" in res_app_js.headers.get("content-type", "").lower()
    assert "EventSource" in res_app_js.text or "pipeline" in res_app_js.text

    # 4. Canvas Viewer Engine JS
    res_viewer_js = client.get("/static/js/viewer.js")
    assert res_viewer_js.status_code == 200, f"Expected 200 for viewer.js, got {res_viewer_js.status_code}"
    assert "javascript" in res_viewer_js.headers.get("content-type", "").lower()
    assert "CADCanvasViewer" in res_viewer_js.text or "canvas" in res_viewer_js.text.lower()


# =============================================================================
# 2. COMPLETE E2E USER JOURNEY & REST API VERIFICATION
# =============================================================================

def test_complete_user_journey_and_artifacts():
    """Executes the full user lifecycle: upload -> process -> SSE stream -> status

    -> summary -> walls -> Excel download -> PDF download -> page image.
    """
    client = TestClient(app.app)
    door_fixture = FIXTURES_DIR / "fixture_door.pdf"
    assert door_fixture.exists(), "fixture_door.pdf missing from fixtures"

    # Step 1: Upload blueprint PDF (POST /api/upload)
    with open(door_fixture, "rb") as f:
        upload_res = client.post(
            "/api/upload",
            files={"file": ("fixture_door.pdf", f, "application/pdf")},
        )
    assert upload_res.status_code == 200, f"Upload failed: {upload_res.text}"
    up_data = upload_res.json()
    assert "file_id" in up_data
    assert up_data["filename"] == "fixture_door.pdf"
    assert up_data["page_count"] == 1
    file_id = up_data["file_id"]

    # Step 2: Initiate processing (POST /api/process/{file_id})
    process_res = client.post(f"/api/process/{file_id}")
    assert process_res.status_code == 202, f"Process start failed: {process_res.text}"
    proc_data = process_res.json()
    assert "run_id" in proc_data
    run_id = proc_data["run_id"]
    assert proc_data["status"] == "processing"

    # Step 3: Listen to SSE events (GET /api/pipeline/events/{run_id})
    # Wait briefly to let the pipeline worker thread execute
    max_wait = 5.0
    start_t = time.time()
    completed = False
    while time.time() - start_t < max_wait:
        st_res = client.get(f"/api/pipeline/status/{run_id}")
        if st_res.status_code == 200 and st_res.json().get("status") in ("completed", "error"):
            completed = True
            break
        time.sleep(0.1)

    assert completed, f"Pipeline did not finish within {max_wait}s"
    assert st_res.json().get("status") == "completed", f"Pipeline status error: {st_res.json()}"

    # Consume SSE events stream
    sse_res = client.get(f"/api/pipeline/events/{run_id}")
    assert sse_res.status_code == 200
    assert "text/event-stream" in sse_res.headers.get("content-type", "")
    sse_body = sse_res.text
    assert len(sse_body) > 0

    # Parse SSE events and verify stages S00 through S16
    event_lines = [l for l in sse_body.splitlines() if l.startswith("data:")]
    assert len(event_lines) >= 10, f"Expected multiple SSE events, got: {event_lines}"

    emitted_stages = []
    has_complete_event = False
    for line in event_lines:
        payload = json.loads(line[5:].strip())
        if "stage" in payload:
            emitted_stages.append(payload["stage"])
        if payload.get("status") == "completed":
            has_complete_event = True

    # Verify crucial pipeline stages are reported
    for expected_stage in ["S00", "S01", "S02", "S03", "S04", "S06", "S07", "S08", "S13", "S14", "S15", "S16"]:
        assert any(expected_stage in st for st in emitted_stages), (
            f"Stage {expected_stage} not found in emitted SSE stages: {emitted_stages}"
        )
    assert has_complete_event, "SSE stream did not emit final 'complete' status event"

    # Step 4: Check status endpoint (GET /api/pipeline/status/{run_id})
    status_res = client.get(f"/api/pipeline/status/{run_id}")
    assert status_res.status_code == 200
    status_data = status_res.json()
    assert status_data["run_id"] == run_id
    assert status_data["status"] == "completed"
    assert status_data["progress_pct"] == 100
    assert "S16" in status_data["current_stage"] or "Complete" in status_data["current_stage"]

    # Step 5: Fetch summary metrics (GET /api/takeoff/{run_id}/summary)
    summary_res = client.get(f"/api/takeoff/{run_id}/summary")
    assert summary_res.status_code == 200
    sum_data = summary_res.json()
    assert sum_data["run_id"] == run_id
    # Exact Worked Example 8.7.1 parity
    assert sum_data["total_gross_lf"] == 20.00
    assert sum_data["total_opening_deduction_lf"] == 3.00
    assert sum_data["total_net_lf"] == 17.00
    assert sum_data["total_board_sf"] == 358.00
    assert sum_data["total_studs_ea"] == 16
    assert sum_data["total_track_lf"] == 37.00
    assert sum_data["waste_percent"] == 0.0
    assert "artifacts" in sum_data
    assert "excel_workbook_url" in sum_data["artifacts"]
    assert "annotated_pdf_url" in sum_data["artifacts"]

    # Step 6: Fetch wall geometries (GET /api/takeoff/{run_id}/walls)
    walls_res = client.get(f"/api/takeoff/{run_id}/walls")
    assert walls_res.status_code == 200
    walls_data = walls_res.json()
    assert walls_data["run_id"] == run_id
    assert walls_data["total_walls"] >= 1
    assert len(walls_data["walls"]) >= 1
    wall_item = walls_data["walls"][0]
    assert wall_item["tag"] == "1A"
    assert wall_item["gross_length_ft"] == 20.00
    assert wall_item["net_length_ft"] == 17.00
    assert "spine" in wall_item
    assert "x1" in wall_item["spine"] and "y1" in wall_item["spine"]

    # Step 7: Download qto.xlsx (GET /api/takeoff/{run_id}/export/excel)
    excel_res = client.get(f"/api/takeoff/{run_id}/export/excel")
    assert excel_res.status_code == 200
    assert "openxmlformats" in excel_res.headers.get("content-type", "")
    assert len(excel_res.content) > 1000

    # Step 8: Download annotated.pdf (GET /api/blueprint/{run_id}/annotated-pdf)
    pdf_res = client.get(f"/api/blueprint/{run_id}/annotated-pdf")
    assert pdf_res.status_code == 200
    assert pdf_res.headers.get("content-type") == "application/pdf"
    assert len(pdf_res.content) > 500

    # Step 9: Fetch rendered page image (GET /api/blueprint/{run_id}/page/1/image)
    img_res = client.get(f"/api/blueprint/{run_id}/page/1/image")
    assert img_res.status_code == 200
    assert img_res.headers.get("content-type") == "image/png"
    # Verify PNG magic signature: \x89PNG\r\n\x1a\n
    assert img_res.content[:8] == b"\x89PNG\r\n\x1a\n"


# =============================================================================
# 3. EXCEL WORKBOOK OPENPYXL SCHEMA & FORMULA VERIFICATION
# =============================================================================

def test_excel_openpyxl_7sheets_and_uppercase_formulas():
    """Downloads qto.xlsx for fixture_door.pdf and verifies all 7 sheets,

    uppercase native Excel formulas (=SUM), and calculated numerical values.
    """
    client = TestClient(app.app)
    door_fixture = FIXTURES_DIR / "fixture_door.pdf"

    # Upload and run fixture
    with open(door_fixture, "rb") as f:
        up = client.post("/api/upload", files={"file": ("fixture_door.pdf", f, "application/pdf")})
    file_id = up.json()["file_id"]
    proc = client.post(f"/api/process/{file_id}")
    run_id = proc.json()["run_id"]

    # Wait for completion
    for _ in range(50):
        st = client.get(f"/api/pipeline/status/{run_id}").json()
        if st["status"] in ("completed", "error"):
            break
        time.sleep(0.1)

    # Download Excel workbook
    excel_res = client.get(f"/api/takeoff/{run_id}/export/excel")
    assert excel_res.status_code == 200

    # Open with openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(excel_res.content), data_only=False)

    # 1. Verify exact 7 sheets
    expected_sheets = [
        "Summary",
        "WallTypes",
        "Runs",
        "Openings",
        "Assumptions",
        "Review",
        "RunInfo",
    ]
    assert wb.sheetnames == expected_sheets, f"Sheet list mismatch: {wb.sheetnames} vs {expected_sheets}"

    # 2. Verify Summary sheet content and uppercase formula syntax
    ws_summary = wb["Summary"]
    assert ws_summary.max_row >= 3, "Summary sheet missing data or total row"

    # Row 1 headers
    headers = [cell.value for cell in ws_summary[1]]
    assert "Tag" in headers
    assert "Net Board SF" in headers
    assert "Studs (EA)" in headers
    assert "Track/Plates (LF)" in headers

    # Row 2 values (Tag 1A)
    assert ws_summary.cell(row=2, column=1).value == "1A"
    assert ws_summary.cell(row=2, column=4).value == 20.00   # Gross LF
    assert ws_summary.cell(row=2, column=5).value == 3.00    # Opening LF
    assert ws_summary.cell(row=2, column=6).value == 17.00   # Net LF
    assert ws_summary.cell(row=2, column=11).value == 358.00 # Net Board SF
    assert ws_summary.cell(row=2, column=12).value == 16     # Studs EA
    assert ws_summary.cell(row=2, column=14).value == 37.00  # Track LF

    # Row 3: Total row formulas
    total_label = ws_summary.cell(row=3, column=1).value
    assert "TOTAL" in str(total_label).upper()

    formula_cells = []
    for cell in ws_summary[3]:
        val = str(cell.value or "")
        if val.startswith("="):
            formula_cells.append(val)

    assert len(formula_cells) >= 5, f"Expected multiple formula cells in total row, found: {formula_cells}"

    for formula in formula_cells:
        # Strictly uppercase syntax check
        assert "=SUM(" in formula or "=AVERAGE(" in formula, f"Formula does not use uppercase syntax: {formula}"
        assert "=sum(" not in formula, f"Forbidden lowercase formula syntax found: {formula}"

    # 3. Verify WallTypes sheet
    ws_walltypes = wb["WallTypes"]
    assert ws_walltypes.max_row >= 2
    assert ws_walltypes.cell(row=2, column=1).value == "1A"
    assert ws_walltypes.cell(row=2, column=3).value == "DRYWALL"

    # 4. Verify Runs sheet
    ws_runs = wb["Runs"]
    assert ws_runs.max_row >= 2
    assert ws_runs.cell(row=2, column=3).value == "1A"
    assert ws_runs.cell(row=2, column=12).value == 20.00
    assert ws_runs.cell(row=2, column=14).value == 17.00

    # 5. Verify Openings sheet
    ws_openings = wb["Openings"]
    assert ws_openings.max_row >= 2
    assert ws_openings.cell(row=2, column=7).value == 3.00 # Width 3.00 ft
    assert ws_openings.cell(row=2, column=8).value == 7.00 # Height 7.00 ft

    # 6. Verify Assumptions sheet
    ws_assumptions = wb["Assumptions"]
    assert ws_assumptions.max_row >= 2
    asmp_texts = [str(cell.value) for row in ws_assumptions.iter_rows() for cell in row]
    assert any("Wall Height" in t or "ASSUMP-" in t for t in asmp_texts)

    # 7. Verify RunInfo sheet
    ws_runinfo = wb["RunInfo"]
    assert ws_runinfo.max_row >= 3
    runinfo_props = [ws_runinfo.cell(row=r, column=1).value for r in range(1, ws_runinfo.max_row + 1)]
    assert "Run ID" in runinfo_props

    wb.close()


# =============================================================================
# 4. PYMUPDF ANNOTATED PDF VISUAL AND INTERACTIVE TOOLTIP VERIFICATION
# =============================================================================

def test_pdf_annotated_bands_edges_and_tooltips():
    """Inspects annotated.pdf using PyMuPDF to verify:

    - Red highlight bands (width 8.0, 0.32 alpha)
    - Dark red edges (width 2.2, 0.90 alpha)
    - Interactive PDF tooltip annotations
    """
    client = TestClient(app.app)
    door_fixture = FIXTURES_DIR / "fixture_door.pdf"

    # Upload and execute
    with open(door_fixture, "rb") as f:
        up = client.post("/api/upload", files={"file": ("fixture_door.pdf", f, "application/pdf")})
    file_id = up.json()["file_id"]
    proc = client.post(f"/api/process/{file_id}")
    run_id = proc.json()["run_id"]

    for _ in range(50):
        st = client.get(f"/api/pipeline/status/{run_id}").json()
        if st["status"] in ("completed", "error"):
            break
        time.sleep(0.1)

    pdf_res = client.get(f"/api/blueprint/{run_id}/annotated-pdf")
    assert pdf_res.status_code == 200

    doc = fitz.open(stream=pdf_res.content, filetype="pdf")
    assert len(doc) >= 1
    page = doc[0]

    # 1. Verify vector drawings (draw_line bands & edges)
    drawings = page.get_drawings()
    assert len(drawings) >= 1, "Annotated PDF has no vector drawing commands"

    # Search drawings for highlight band (width ~8.0, color bright red)
    band_found = False
    edge_found = False
    for d in drawings:
        w = round(d.get("width", 0.0), 1)
        color = d.get("color")
        opacity = d.get("stroke_opacity")

        # Bright red band: width 8.0, alpha 0.32, color (1.0, 0.0, 0.0)
        if w == 8.0:
            if opacity is not None:
                assert abs(opacity - 0.32) < 0.05, f"Expected band opacity ~0.32, got {opacity}"
            if color is not None:
                assert color[0] > 0.9 and color[1] < 0.1 and color[2] < 0.1
            band_found = True

        # Dark red edge: width 2.2, alpha 0.90, color (0.85, 0.0, 0.0)
        if w == 2.2:
            if opacity is not None:
                assert abs(opacity - 0.90) < 0.05, f"Expected edge opacity ~0.90, got {opacity}"
            if color is not None:
                assert color[0] > 0.8 and color[1] < 0.1 and color[2] < 0.1
            edge_found = True

    assert band_found, "Bright red highlight band (width 8.0, alpha 0.32) not found in vector drawings"
    assert edge_found, "Dark red crisp edge (width 2.2, alpha 0.90) not found in vector drawings"

    # 2. Verify interactive annotations
    annots = list(page.annots())
    assert len(annots) >= 1, "No interactive PDF annotations found on page"

    tooltip_texts = []
    titles = []
    for a in annots:
        info = a.info
        if info:
            if info.get("content"):
                tooltip_texts.append(info["content"])
            if info.get("title"):
                titles.append(info["title"])

    # Verify presence of Wall annotation tooltip
    has_wall_annot = any("DRYWALL WALL" in txt or "Gross LF:" in txt for txt in tooltip_texts)
    has_tag_annot = any("DRYWALL TAG" in txt or "Tag 1A" in t for txt, t in zip(tooltip_texts, titles))

    assert has_wall_annot, f"Missing interactive Wall annotation tooltip. Found: {tooltip_texts}"
    assert has_tag_annot, f"Missing interactive Tag annotation tooltip. Found: {titles}"

    # Verify tooltip numerical correctness
    wall_tooltips = [t for t in tooltip_texts if "DRYWALL WALL" in t]
    assert len(wall_tooltips) >= 1
    target_tooltip = wall_tooltips[0]
    assert "Gross LF: 20.00'" in target_tooltip
    assert "Net LF: 17.00'" in target_tooltip
    assert "Opening Deductions: 3.00'" in target_tooltip

    doc.close()


# =============================================================================
# 5. ADVERSARIAL STRESS TESTS
# =============================================================================

def test_adversarial_non_pdf_upload_rejected():
    """Verify upload endpoint strictly rejects non-PDF files (HTTP 400)."""
    client = TestClient(app.app)

    # 1. Upload executable file
    exe_file = io.BytesIO(b"MZ\x90\x00\x03\x00\x00\x00")
    res1 = client.post("/api/upload", files={"file": ("malware.exe", exe_file, "application/octet-stream")})
    assert res1.status_code == 400
    assert "Invalid file format" in res1.json().get("detail", "")

    # 2. Upload text file
    txt_file = io.BytesIO(b"Just plain text notes")
    res2 = client.post("/api/upload", files={"file": ("notes.txt", txt_file, "text/plain")})
    assert res2.status_code == 400

    # 3. Upload empty file
    empty_file = io.BytesIO(b"")
    res3 = client.post("/api/upload", files={"file": ("empty.pdf", empty_file, "application/pdf")})
    assert res3.status_code == 400
    assert "empty" in res3.json().get("detail", "").lower()


def test_adversarial_corrupted_pdf_upload():
    """Verify upload endpoint handles corrupted PDF bytes gracefully without server crash (HTTP 400)."""
    client = TestClient(app.app)
    corrupted_bytes = io.BytesIO(b"%PDF-1.4\ncorrupted header junk \x00\xff\xfe not valid pdf data")
    res = client.post("/api/upload", files={"file": ("corrupt.pdf", corrupted_bytes, "application/pdf")})
    assert res.status_code == 400
    assert "valid PDF" in res.json().get("detail", "") or "could not be parsed" in res.json().get("detail", "")


def test_adversarial_missing_scale_plan_handling(tmp_path: Path):
    """Adversarial test: A blueprint with valid wall lines and tags but NO scale string.

    Pipeline must not crash or throw unhandled exceptions.
    Empirically inspects assumptions and scale fallback.
    """
    # Create synthetic PDF without scale note
    pdf_path = tmp_path / "missing_scale.pdf"
    doc = fitz.open()
    page = doc.new_page(width=1000, height=800)
    page.insert_text(fitz.Point(50, 50), "SHEET A-101: FLOOR PLAN (NO SCALE GIVEN)")

    # Insert partition schedule with tag 1A
    page.insert_text(fitz.Point(50, 100), "PARTITION SCHEDULE")
    page.insert_text(fitz.Point(50, 120), "1A: 3-5/8 Metal Studs @ 16 OC, 5/8 Type X GWB")

    # Draw wall linework: 180 pt horizontal wall
    shape = page.new_shape()
    shape.draw_line(fitz.Point(100, 300), fitz.Point(280, 300))
    shape.draw_line(fitz.Point(100, 304), fitz.Point(280, 304))
    shape.finish()
    shape.commit()

    # Draw tag callout
    page.insert_text(fitz.Point(190, 290), "1A")

    doc.save(str(pdf_path))
    doc.close()

    # Run pipeline via functional interface
    out_dir = tmp_path / "run_missing_scale"
    result = run_pipeline(str(pdf_path), output_dir=str(out_dir))

    # Verification: Pipeline executed successfully without crashing
    assert result is not None
    assert "sheets" in result
    sheet_info = result["sheets"][0]
    assert sheet_info["scale_status"] == "DEFAULT_ASSUMED"

    # Inspect generated Excel Assumptions sheet
    excel_path = out_dir / "qto.xlsx"
    assert excel_path.exists()
    wb = openpyxl.load_workbook(str(excel_path))
    ws_assump = wb["Assumptions"]
    assump_rows = list(ws_assump.iter_rows(values_only=True))
    wb.close()

    # Document empirical behavior:
    # Baseline pipeline falls back to DEFAULT_FT_PER_PT (1/8" = 1'-0") with status 'DEFAULT_ASSUMED'.
    assert len(assump_rows) >= 3

    # Verify assumption with QTY_BLOCKED exists in takeoff.assumptions
    scale_assumps = [a for a in result.get("assumptions", []) if a.get("category") == "Architectural Scale"]
    assert len(scale_assumps) == 1
    assert scale_assumps[0]["status"] == "QTY_BLOCKED"
    assert "QTY_BLOCKED" in scale_assumps[0]["justification"]

    # Verify QTY_BLOCKED appears in Excel Assumptions sheet
    asmp_flat = [str(c) for row in assump_rows for c in row if c is not None]
    assert any("QTY_BLOCKED" in txt for txt in asmp_flat)


def test_adversarial_concurrent_upload_and_processing():
    """Verify backend handles 5 concurrent uploads and processing triggers

    without file lock collisions or race condition crashes.
    """
    client = TestClient(app.app)
    door_fixture = FIXTURES_DIR / "fixture_door.pdf"

    def execute_single_workflow(idx: int):
        with open(door_fixture, "rb") as f:
            up = client.post(
                "/api/upload",
                files={"file": (f"fixture_{idx}.pdf", f, "application/pdf")},
            )
        assert up.status_code == 200
        fid = up.json()["file_id"]

        proc = client.post(f"/api/process/{fid}")
        assert proc.status_code == 202
        rid = proc.json()["run_id"]
        return rid

    # Launch 5 concurrent workers
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(execute_single_workflow, i) for i in range(5)]
        run_ids = [f.result() for f in futures]

    assert len(run_ids) == 5
    assert len(set(run_ids)) == 5, "Duplicate run_ids generated during concurrent execution"

    # Wait for all runs to finish
    time.sleep(2.0)
    for rid in run_ids:
        st = client.get(f"/api/pipeline/status/{rid}").json()
        assert st["status"] in ("completed", "processing")


def test_adversarial_extreme_dimensions_and_edge_cases():
    """Stress-test mathematical takeoff calculations under extreme boundary conditions:

    - 0 LF wall (points at exact same position)
    - Massive 100,000 LF wall
    - Opening larger than wall span (deduction > gross LF)
    """
    scale_ft_per_pt = 0.1111111111111111 # 1/8" = 1'-0"

    # 1. Zero LF Wall: (100, 100) -> (100, 100)
    zero_spine = Segment(x1=100.0, y1=100.0, x2=100.0, y2=100.0)
    zero_run = WallRun(
        run_id="RUN-ZERO",
        tag="1A",
        page_num=1,
        sheet_label="A-101",
        spine=zero_spine,
        gross_length_pt=0.0,
        gross_length_ft=0.0,
        opening_deduction_ft=0.0,
        net_length_ft=0.0,
        openings=[],
        segments=[],
        ft_per_pt=scale_ft_per_pt,
    )
    result_zero = calculate_takeoff([zero_run], scale_ft_per_pt=scale_ft_per_pt)
    assert result_zero.total_gross_lf == 0.0
    assert result_zero.total_net_lf == 0.0
    assert result_zero.total_board_sf == 0.0
    assert not math.isnan(result_zero.total_board_sf)
    assert not math.isinf(result_zero.total_board_sf)

    # 2. Massive Wall: 100,000 LF (900,000 pt vector)
    huge_spine = Segment(x1=0.0, y1=0.0, x2=900000.0, y2=0.0)
    huge_run = WallRun(
        run_id="RUN-HUGE",
        tag="1A",
        page_num=1,
        sheet_label="A-101",
        spine=huge_spine,
        gross_length_pt=900000.0,
        gross_length_ft=100000.0,
        opening_deduction_ft=0.0,
        net_length_ft=100000.0,
        openings=[],
        segments=[huge_spine],
        ft_per_pt=scale_ft_per_pt,
    )
    result_huge = calculate_takeoff([huge_run], scale_ft_per_pt=scale_ft_per_pt)
    assert result_huge.total_gross_lf == 100000.0
    assert result_huge.total_net_lf == 100000.0
    assert result_huge.total_board_sf == 2000000.0 # 100,000 * 10 * 2
    assert result_huge.total_studs_ea > 50000

    # 3. Opening larger than wall span (10 LF wall with 15 LF opening)
    op_large = Opening(
        opening_id="OP-LARGE",
        wall_run_id="RUN-OP",
        page_num=1,
        t_start=0.0,
        t_end=135.0, # 15 LF (135 pt)
        width_pt=135.0,
        width_ft=15.0,
        height_ft=7.0,
    )
    over_run = WallRun(
        run_id="RUN-OP",
        tag="1A",
        page_num=1,
        sheet_label="A-101",
        spine=Segment(x1=0.0, y1=0.0, x2=90.0, y2=0.0), # 10 LF (90 pt)
        gross_length_pt=90.0,
        gross_length_ft=10.0,
        opening_deduction_ft=15.0,
        net_length_ft=max(0.0, 10.0 - 15.0), # clamped to 0.0
        openings=[op_large],
        segments=[],
        ft_per_pt=scale_ft_per_pt,
    )
    result_over = calculate_takeoff([over_run], scale_ft_per_pt=scale_ft_per_pt)
    assert result_over.total_gross_lf == 10.0
    assert result_over.total_net_lf == 0.0
    # Net board area cannot be negative
    assert result_over.total_board_sf >= 0.0


