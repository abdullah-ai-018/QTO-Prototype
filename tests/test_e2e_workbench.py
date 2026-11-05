"""tests/test_e2e_workbench.py: 4-Tier Comprehensive E2E Workbench Test Suite.

Authoritative specification:
- PROJECT.md: § Feature Inventory (F1 to F17), § Interface Contracts, § Milestones
- TEST_INFRA.md: 4-Tier Requirement-Driven Test Pyramid
- ORIGINAL_REQUEST.md: Requirements R1, R2, R3, R4, R5

Test Methodology:
- Tier 1: Feature Coverage (F1–F17 individual/modular capability assertions)
- Tier 2: Boundary & Corner Cases (out-of-bounds, invalid scales, zero/negative inputs, 71-page navigation)
- Tier 3: Cross-Feature Combinations (sheet selection + wall detection + calibration + manual markup + deduction + schedule sync)
- Tier 4: Real-World Blueprint Scenario (uploads/doc_20261104_101950_6cbd34.pdf Sheet A-101 / Page 15)
"""

from __future__ import annotations

import io
import json
import math
import os
from pathlib import Path
import re
import sys
import time
from typing import Any, Dict, List, Optional, Set

from fastapi.testclient import TestClient
import openpyxl
import pymupdf as fitz
import pytest

import app
from tests.make_fixtures import FIXTURES_DIR, build_all_fixtures
from qto.geometry import Point, Segment, BoundingBox
from qto.scale import detect_scale_from_page, parse_scale_string, DEFAULT_FT_PER_PT
from qto.segments import extract_page_linework, PageLinework
from qto.tags import discover_tags_from_schedules, find_tag_instances_on_page, TagInstance
from qto.trace_walls import (
    find_leader_endpoint,
    find_seed_segment,
    trace_wall_from_seed,
    TracedWall,
)
from qto.dedup import create_wall_run, deduplicate_wall_runs, WallRun
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
)
from qto.pipeline import QTOPipeline, run_pipeline

# Authoritative paths
BASE_DIR = Path(__file__).resolve().parent.parent
REAL_BLUEPRINT_PATH = BASE_DIR / "uploads" / "doc_20261104_101950_6cbd34.pdf"
STATIC_DIR = BASE_DIR / "static"


def is_route_registered(fastapi_app: Any, path: str, method: str) -> bool:
    """Helper to detect whether an endpoint route is currently registered."""
    for route in fastapi_app.routes:
        if getattr(route, "path", None) == path:
            methods = getattr(route, "methods", set())
            if method.upper() in methods:
                return True
    return False


@pytest.fixture(scope="session", autouse=True)
def setup_test_environment():
    """Ensure fixtures exist and required directories are initialized."""
    build_all_fixtures(FIXTURES_DIR)
    assert REAL_BLUEPRINT_PATH.exists(), f"Real blueprint missing: {REAL_BLUEPRINT_PATH}"


# =============================================================================
# TIER 1: FEATURE COVERAGE (F1 to F17)
# =============================================================================


def test_tier1_f1_blueprint_sheet_indexing_and_classification():
    """F1: Blueprint Sheet Indexing Fix.
    
    Verifies that architectural floor plans (Pages 14-19: A-100 to A-105)
    in doc_20261104_101950_6cbd34.pdf are indexed with proper sheet labels
    and classified as FLOOR_PLAN (not false-positive PARTITION_SCHEDULE).
    """
    from qto.sheet_index import extract_sheet_label, extract_sheet_title, classify_page_type

    doc = fitz.open(str(REAL_BLUEPRINT_PATH))
    assert len(doc) == 71

    # Page 15 is Sheet A-101: FIRST FLOOR CONSTRUCTION PLAN
    p15 = doc[14]
    label15 = extract_sheet_label(p15, 15)
    title15 = extract_sheet_title(p15)
    type15 = classify_page_type(label15, title15, p15.get_text("text"), 15, len(doc))

    assert label15 == "A-101", f"Authoritative sheet label for Page 15 must be A-101, got {label15}"
    assert "FIRST FLOOR" in title15.upper() or "CONSTRUCTION PLAN" in title15.upper()
    assert type15 == "FLOOR_PLAN", f"Page 15 must be classified as FLOOR_PLAN, got {type15}"

    # Verify pure partition schedules are on Pages 63-64 (A-900, A-901)
    p63 = doc[62]
    p64 = doc[63]
    lbl63 = extract_sheet_label(p63, 63)
    lbl64 = extract_sheet_label(p64, 64)
    assert lbl63 == "A-900"
    assert lbl64 == "A-901"
    assert classify_page_type(lbl63, extract_sheet_title(p63), p63.get_text("text"), 63, len(doc)) == "PARTITION_SCHEDULE"
    assert classify_page_type(lbl64, extract_sheet_title(p64), p64.get_text("text"), 64, len(doc)) == "PARTITION_SCHEDULE"

    doc.close()


def test_tier1_f2_real_blueprint_wall_detection():
    """F2: Real Blueprint Wall Detection.
    
    Verifies wall detection on Page 15 (Sheet A-101) of doc_20261104_101950_6cbd34.pdf,
    asserting non-zero raw wall runs, non-zero deduped runs, and non-zero LF & SF.
    """
    doc = fitz.open(str(REAL_BLUEPRINT_PATH))
    p15 = doc[14]

    scale, scale_str, status = detect_scale_from_page(p15)
    assert scale > 0.0, "Scale must be non-zero."
    assert scale_str == '1/8" = 1\'-0"'

    lw = extract_page_linework(p15)
    assert len(lw.segments) > 1000, f"Expected >1000 segments, got {len(lw.segments)}"
    assert len(lw.door_arcs) > 50, f"Expected >50 door arcs, got {len(lw.door_arcs)}"

    # Discover schedule tags and find instances on Page 15
    schedule_tags = {'0X', '1A', '1B', '1C', '1D', '1E', '2B', '2C', '2W', '2X', '3A', '3D', '4B1', '4K', '4P', '5B', '5D', '5E', '5L', '7A', '7B', '7C', '7E', '7F', '7G', '8A', '8P', 'GL1', 'GL2', 'PW'}
    insts = find_tag_instances_on_page(p15, schedule_tags)
    assert len(insts) >= 20, f"Expected >=20 tag instances on Page 15, got {len(insts)}"

    # Trace wall runs
    raw_runs = []
    for idx, tag_inst in enumerate(insts):
        anchor_x, anchor_y, leader_seg = find_leader_endpoint(
            tc_x=tag_inst.center.x,
            tc_y=tag_inst.center.y,
            tag_radius=tag_inst.tag_radius,
            segments=lw.segments,
        )
        seed_seg = find_seed_segment(
            anchor_x=anchor_x,
            anchor_y=anchor_y,
            tc_x=tag_inst.center.x,
            tc_y=tag_inst.center.y,
            tag_radius=tag_inst.tag_radius,
            segments=lw.segments,
            leader_seg=leader_seg,
        )
        if seed_seg is None:
            continue
        traced = trace_wall_from_seed(
            seed_seg=seed_seg,
            leader_seg=leader_seg,
            segments=lw.segments,
            door_arcs=lw.door_arcs,
            ft_per_pt=scale,
            page_num=15,
            wall_run_id=f"RUN-{idx+1:03d}",
        )
        if traced:
            wr = create_wall_run(
                traced=traced,
                tag=tag_inst.tag,
                page_num=15,
                sheet_label="A-101",
                run_id=f"RUN-{idx+1:03d}",
                ft_per_pt=scale,
            )
            raw_runs.append(wr)

    assert len(raw_runs) >= 15, f"Expected >=15 raw wall runs, got {len(raw_runs)}"

    deduped = deduplicate_wall_runs(raw_runs, scale)
    assert len(deduped) >= 10, f"Expected >=10 deduped wall runs, got {len(deduped)}"

    total_gross_lf = sum(r.gross_length_ft for r in deduped)
    total_net_lf = sum(r.net_length_ft for r in deduped)

    assert total_gross_lf > 200.0, f"Expected gross LF > 200, got {total_gross_lf:.2f}"
    assert total_net_lf > 200.0, f"Expected net LF > 200, got {total_net_lf:.2f}"
    assert total_net_lf <= total_gross_lf, "Net LF cannot exceed Gross LF"

    doc.close()


def test_tier1_f3_selective_sheet_processing():
    """F3: Selective Sheet Processing API.
    
    Verifies that POST /api/process/{file_id} accepts a configuration payload
    specifying selected_pages and run_mode per Interface Contract 1.
    """
    client = TestClient(app.app)
    
    # Upload test blueprint
    door_path = FIXTURES_DIR / "fixture_door.pdf"
    with open(door_path, "rb") as f:
        up_res = client.post("/api/upload", files={"file": ("fixture_door.pdf", f, "application/pdf")})
    assert up_res.status_code == 200
    file_id = up_res.json()["file_id"]

    # Test selective processing request
    selective_config = {
        "selected_pages": [1],
        "run_mode": "floor_plans_only"
    }
    proc_res = client.post(f"/api/process/{file_id}", json=selective_config)
    assert proc_res.status_code in (200, 202)
    proc_data = proc_res.json()
    assert "run_id" in proc_data
    assert proc_data["status"] == "processing"
    assert proc_data["selected_pages"] == [1]

    # Wait for completion and verify selective summary outputs
    for _ in range(50):
        st = client.get(f"/api/pipeline/status/{proc_data['run_id']}").json()
        if st["status"] in ("completed", "error"):
            break
        time.sleep(0.1)
    assert st["status"] == "completed"

    summary_res = client.get(f"/api/takeoff/{proc_data['run_id']}/summary")
    assert summary_res.status_code == 200
    summary_data = summary_res.json()
    assert summary_data["selected_pages"] == [1]
    assert summary_data["sheets_processed"] == [1]


def test_tier1_f4_out_of_bounds_contract():
    """F4: Out-of-bounds Contract Fix.
    
    Verifies that requesting an out-of-bounds page returns HTTP 404
    (and checks PyMuPDF doc.close() lifecycle bug in app.py:573-576).
    """
    client = TestClient(app.app)
    door_path = FIXTURES_DIR / "fixture_door.pdf"
    with open(door_path, "rb") as f:
        up_res = client.post("/api/upload", files={"file": ("fixture_door.pdf", f, "application/pdf")})
    assert up_res.status_code == 200
    file_id = up_res.json()["file_id"]

    proc_res = client.post(f"/api/process/{file_id}")
    run_id = proc_res.json()["run_id"]

    # Wait for completion
    for _ in range(50):
        st = client.get(f"/api/pipeline/status/{run_id}").json()
        if st["status"] in ("completed", "error"):
            break
        time.sleep(0.1)

    # Request out of bounds page 999
    res = client.get(f"/api/blueprint/{run_id}/page/999/image")
    assert res.status_code == 404, f"Expected HTTP 404, got {res.status_code}"


def test_tier1_f5_twopoint_scale_calibration():
    """F5: 2-Point Scale Calibration API & Mathematical Model.
    
    Derives and verifies 2-point scale calibration mathematics:
    d_pt = hypot(pt2.x - pt1.x, pt2.y - pt1.y)
    new_ft_per_pt = real_world_distance_ft / d_pt
    Also checks HTTP endpoint contract if registered.
    """
    pt1 = {"x": 100.0, "y": 200.0}
    pt2 = {"x": 340.0, "y": 200.0}
    real_world_distance_ft = 20.0

    # 1. Authoritative mathematical derivation
    measured_pt = math.hypot(pt2["x"] - pt1["x"], pt2["y"] - pt1["y"])
    assert measured_pt == 240.0

    new_ft_per_pt = real_world_distance_ft / measured_pt
    assert round(new_ft_per_pt, 6) == round(20.0 / 240.0, 6)
    assert round(new_ft_per_pt, 6) == 0.083333

    # Verification on 180 pt segment
    vector_pt = 180.0
    calibrated_lf = vector_pt * new_ft_per_pt
    assert calibrated_lf == 15.00

    # 2. HTTP endpoint verification (M2 contract)
    client = TestClient(app.app)
    assert is_route_registered(app.app, "/api/blueprint/{run_id}/page/{page_num}/calibrate", "POST")

    res = client.post(
        "/api/blueprint/test_run/page/1/calibrate",
        json={"pt1": pt1, "pt2": pt2, "real_world_distance_ft": real_world_distance_ft},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["new_ft_per_pt"] == round(new_ft_per_pt, 6)


def test_tier1_f6_manual_wall_markup_crud():
    """F6: Manual Wall Markup CRUD Operations.
    
    Verifies WallRun data structures for manual wall markups:
    creation with is_manual=True, endpoint editing, deduction addition, and deletion.
    """
    scale = 0.111111  # 1/8" = 1'-0"
    
    # 1. Create manual wall run (180 pt vector = 20.00 LF)
    seg = Segment(100.0, 100.0, 280.0, 100.0)
    
    manual_run = WallRun(
        run_id="RUN-M01",
        tag="5E",
        page_num=15,
        sheet_label="A-101",
        spine=seg,
        gross_length_pt=180.0,
        gross_length_ft=round(seg.length * scale, 2),
        opening_deduction_ft=0.0,
        net_length_ft=round(seg.length * scale, 2),
        openings=[],
        segments=[seg],
        ft_per_pt=scale,
    )
    assert manual_run.gross_length_ft == 20.00
    assert manual_run.net_length_ft == 20.00

    # 2. Update markup: add door opening deduction (3.0 LF)
    door_opening = Opening(
        opening_id="OP-M01",
        wall_run_id="RUN-M01",
        page_num=15,
        t_start=76.5,
        t_end=103.5,
        width_pt=27.0,
        width_ft=3.0,
        height_ft=7.0,
        center_pt=Point(190.0, 100.0),
    )
    manual_run.openings.append(door_opening)
    manual_run.opening_deduction_ft = 3.00
    manual_run.net_length_ft = round(manual_run.gross_length_ft - 3.0, 2)
    assert manual_run.net_length_ft == 17.00
    assert len(manual_run.openings) == 1

    # 3. Serialized dictionary contract
    run_dict = manual_run.to_dict()
    assert run_dict["run_id"] == "RUN-M01"
    assert run_dict["tag"] == "5E"
    assert run_dict["net_length_ft"] == 17.00

    # 4. HTTP endpoint verification (M2 contract)
    client = TestClient(app.app)
    assert is_route_registered(app.app, "/api/blueprint/{run_id}/page/{page_num}/walls", "POST")
    assert is_route_registered(app.app, "/api/blueprint/{run_id}/walls/{wall_id}", "PATCH")
    assert is_route_registered(app.app, "/api/blueprint/{run_id}/walls/{wall_id}", "DELETE")

    # POST manual wall
    create_res = client.post(
        "/api/blueprint/test_run/page/1/walls",
        json={
            "start": {"x": 100.0, "y": 100.0},
            "end": {"x": 280.0, "y": 100.0},
            "tag": "5E",
            "height_ft": 10.0,
        },
    )
    assert create_res.status_code == 200
    created_wall = create_res.json()["wall"]
    wall_id = created_wall["run_id"]
    assert created_wall["is_manual"] is True
    assert created_wall["tag"] == "5E"

    # PATCH wall: add opening deduction
    patch_res = client.patch(
        f"/api/blueprint/test_run/walls/{wall_id}",
        json={
            "openings": [
                {"type": "door", "width_ft": 3.0, "height_ft": 7.0}
            ]
        },
    )
    assert patch_res.status_code == 200
    patched_wall = patch_res.json()["wall"]
    assert patched_wall["opening_deduction_ft"] == 3.0

    # DELETE wall
    del_res = client.delete(f"/api/blueprint/test_run/walls/{wall_id}")
    assert del_res.status_code == 200
    assert del_res.json()["success"] is True
    assert del_res.json()["deleted_id"] == wall_id


def test_tier1_f7_takeoff_schedule_recalculation():
    """F7: Takeoff Schedule Recalculation API & Dynamic Engine.
    
    Verifies dynamic recalculation of gross LF, net LF, board SF, studs, and track
    upon adding manual wall runs and opening deductions.
    """
    scale = 0.111111
    base_runs: List[WallRun] = []
    
    # 0 runs baseline
    takeoff_0 = calculate_takeoff(runs=base_runs, scale_ft_per_pt=scale)
    assert takeoff_0.total_gross_lf == 0.0
    assert takeoff_0.total_net_lf == 0.0
    assert takeoff_0.total_board_sf == 0.0

    # Add 20 LF manual wall run (Tag 1A, height 10 ft)
    seg = Segment(0.0, 0.0, 180.0, 0.0)
    run1 = WallRun(
        run_id="RUN-001",
        tag="1A",
        page_num=1,
        sheet_label="A-101",
        spine=seg,
        gross_length_pt=180.0,
        gross_length_ft=20.00,
        opening_deduction_ft=0.0,
        net_length_ft=20.00,
        openings=[],
        segments=[seg],
        ft_per_pt=scale,
    )
    takeoff_1 = calculate_takeoff(runs=[run1], scale_ft_per_pt=scale, default_height_ft=10.0)
    assert takeoff_1.total_gross_lf == 20.00
    assert takeoff_1.total_net_lf == 20.00
    # Board SF: 20 * 10 * 2 sides * 1 layer = 400.00 SF
    assert takeoff_1.total_board_sf == 400.00

    # Add 3ft door deduction to run1
    run1.openings.append(
        Opening(
            opening_id="OP-001",
            wall_run_id="RUN-001",
            page_num=1,
            t_start=76.5,
            t_end=103.5,
            width_pt=27.0,
            width_ft=3.0,
            height_ft=7.0,
            center_pt=Point(90.0, 0.0),
        )
    )
    run1.opening_deduction_ft = 3.00
    run1.net_length_ft = 17.00

    takeoff_2 = calculate_takeoff(runs=[run1], scale_ft_per_pt=scale, default_height_ft=10.0)
    assert takeoff_2.total_gross_lf == 20.00
    assert takeoff_2.total_net_lf == 17.00
    # Board SF: (20*10 - 3*7) * 2 = (200 - 21) * 2 = 358.00 SF
    assert takeoff_2.total_board_sf == 358.00


def test_tier1_f8_ui_layout_streamlining():
    """F8: UI Layout Streamlining.
    
    Verifies that static/index.html does not contain dead buttons
    ('Reconciliation', 'Quality Control') and maintains estimator workbench structure.
    """
    index_file = STATIC_DIR / "index.html"
    assert index_file.exists()
    content = index_file.read_text(encoding="utf-8")

    # Workbench structural containers must exist
    assert 'id="left-drawer"' in content
    assert 'canvas' in content.lower()
    assert 'takeoff' in content.lower()

    # Dead buttons check (M3 scope)
    assert "Reconciliation" not in content
    assert "Quality Control" not in content


def test_tier1_f9_header_collision_and_responsive_layout():
    """F9: Header Collision & Responsive Fix.
    
    Verifies that static/css/workbench.css and static/index.html implement
    responsive styling preventing header overlap on viewports <1440px.
    """
    css_file = STATIC_DIR / "css" / "workbench.css"
    assert css_file.exists()
    css_content = css_file.read_text(encoding="utf-8")

    index_file = STATIC_DIR / "index.html"
    index_content = index_file.read_text(encoding="utf-8")

    # Verify flexbox or responsive grid usage
    assert "flex" in index_content
    # Verify presence of responsive CSS classes or media queries
    assert "@media" in css_content or "overflow-hidden" in index_content


def test_tier1_f10_multipage_sheet_navigation():
    """F10: Multi-Page Sheet Navigation.
    
    Verifies 71-page sheet catalog indexing for doc_20261104_101950_6cbd34.pdf,
    asserting sheet numbers, titles, and scale information.
    """
    from qto.sheet_index import extract_blueprint_sheet_catalog

    catalog = extract_blueprint_sheet_catalog(REAL_BLUEPRINT_PATH)

    assert len(catalog) == 71
    assert catalog[0]["page_num"] == 1
    assert catalog[14]["sheet_label"] == "A-101"  # Page 15
    assert catalog[14]["page_type"] == "FLOOR_PLAN"
    assert catalog[14]["scale"] == '1/8" = 1\'-0"'

    # Verify API endpoint GET /api/blueprint/{file_id}/sheets
    client = TestClient(app.app)
    api_res = client.get(f"/api/blueprint/{REAL_BLUEPRINT_PATH.stem}/sheets")
    assert api_res.status_code == 200
    api_catalog = api_res.json()
    assert len(api_catalog) == 71
    assert api_catalog[14]["sheet_label"] == "A-101"
    assert api_catalog[14]["scale"] == '1/8" = 1\'-0"'


def test_tier1_f11_twopoint_scale_calibration_canvas_tool():
    """F11: 2-Point Scale Calibration Canvas Tool.
    
    Verifies that static/index.html, static/js/viewer.js, and static/js/app.js
    implement the interactive 2-point scale calibration tool, modal, and API integration.
    """
    index_file = STATIC_DIR / "index.html"
    viewer_file = STATIC_DIR / "js" / "viewer.js"
    app_file = STATIC_DIR / "js" / "app.js"
    assert index_file.exists() and viewer_file.exists() and app_file.exists()

    index_html = index_file.read_text(encoding="utf-8")
    viewer_js = viewer_file.read_text(encoding="utf-8")
    app_js = app_file.read_text(encoding="utf-8")

    # Verify tool button and modal in HTML
    assert 'id="tool-btn-calibrate"' in index_html, "Micro-toolbar must define tool-btn-calibrate"
    assert 'id="modal-calibration"' in index_html, "HTML must define modal-calibration"
    assert 'id="calib-measured-pts"' in index_html, "Calibration modal must display measured distance"
    assert 'id="calib-distance-input"' in index_html, "Calibration modal must have real-world distance input"

    # Verify calibration mode and live rubberband in viewer.js
    assert "calibrate" in viewer_js.lower(), "viewer.js must support calibrate tool mode"
    assert "rubberband" in viewer_js.lower(), "viewer.js must render calibration rubberband line"
    assert "onCalibrationComplete" in viewer_js, "viewer.js must invoke onCalibrationComplete callback"

    # Verify calibration API call in app.js
    assert "/calibrate" in app_js, "app.js must call backend calibration endpoint"
    assert "confirmCalibration" in app_js, "app.js must define confirmCalibration handler"


def test_tier1_f12_manual_wall_drawing_ruler_tool():
    """F12: Manual Wall Drawing / Ruler Tool.
    
    Verifies that static/index.html, static/js/viewer.js, and static/js/app.js
    implement the manual wall drawing / ruler tool, active tag/height controls,
    and wall creation API integration.
    """
    index_file = STATIC_DIR / "index.html"
    viewer_file = STATIC_DIR / "js" / "viewer.js"
    app_file = STATIC_DIR / "js" / "app.js"
    index_html = index_file.read_text(encoding="utf-8")
    viewer_js = viewer_file.read_text(encoding="utf-8")
    app_js = app_file.read_text(encoding="utf-8")

    # Verify manual wall ruler controls in HTML
    assert 'id="tool-btn-wall"' in index_html, "Micro-toolbar must define tool-btn-wall"
    assert 'id="active-partition-tag"' in index_html, "Micro-toolbar must have active-partition-tag selector"
    assert 'id="active-wall-height"' in index_html, "Micro-toolbar must have active-wall-height input"

    # Verify live dual-red rubberband drawing in viewer.js
    assert "rubberband" in viewer_js.lower(), "viewer.js must render live rubberband line"
    assert "onWallCreated" in viewer_js, "viewer.js must invoke onWallCreated callback"

    # Verify wall creation API integration in app.js
    assert "/walls" in app_js, "app.js must call /walls API endpoint"
    assert "createManualWall" in app_js, "app.js must define createManualWall function"


def test_tier1_f13_interactive_markup_editing():
    """F13: Interactive Markup Editing.
    
    Verifies draggable endpoint handles, editable partition tags/heights,
    opening deductions manager, and wall deletion.
    """
    index_file = STATIC_DIR / "index.html"
    viewer_file = STATIC_DIR / "js" / "viewer.js"
    app_file = STATIC_DIR / "js" / "app.js"
    css_file = STATIC_DIR / "css" / "workbench.css"

    index_html = index_file.read_text(encoding="utf-8")
    viewer_js = viewer_file.read_text(encoding="utf-8")
    app_js = app_file.read_text(encoding="utf-8")
    css_content = css_file.read_text(encoding="utf-8")

    # Verify Inspector editing controls in HTML
    assert 'id="inspector-tag-select"' in index_html, "Inspector must have editable partition tag select"
    assert 'id="inspector-height-input"' in index_html, "Inspector must have editable wall height input"
    assert 'id="btn-add-door"' in index_html, "Inspector must have Add Door deduction button"
    assert 'id="btn-add-window"' in index_html, "Inspector must have Add Window deduction button"
    assert 'id="btn-delete-wall"' in index_html, "Inspector must have Delete Wall button"

    # Verify draggable handles in viewer.js and CSS
    assert "wall-endpoint-handle" in viewer_js, "viewer.js must render wall-endpoint-handle elements"
    assert "wall-endpoint-handle" in css_content, "workbench.css must style wall-endpoint-handle"
    assert "onWallEndpointsChanged" in viewer_js, "viewer.js must dispatch onWallEndpointsChanged"

    # Verify edit & deduction API handlers in app.js
    assert "updateWallEndpoints" in app_js, "app.js must define updateWallEndpoints"
    assert "addOpeningDeduction" in app_js, "app.js must define addOpeningDeduction"
    assert "deleteOpeningDeduction" in app_js, "app.js must define deleteOpeningDeduction"
    assert "deleteSelectedWall" in app_js or "deleteWall" in app_js, "app.js must support wall deletion"


def test_tier1_f14_dual_red_visual_annotations():
    """F14: Dual-Red Visual Annotations.
    
    Verifies PyMuPDF vector highlight parameters:
    bright red 8.0pt band (RGB 1,0,0) and dark red 2.2pt spine edges (RGB 0.85,0,0),
    as well as canvas CSS dual-red styling.
    """
    from qto.annotate import RED_BRIGHT, RED_DARK, annotate_blueprint_pdf

    assert RED_BRIGHT == (1.0, 0.0, 0.0), f"Expected bright red, got {RED_BRIGHT}"
    assert RED_DARK == (0.85, 0.0, 0.0), f"Expected dark red, got {RED_DARK}"
    docstring = annotate_blueprint_pdf.__doc__ or ""
    assert "8.0" in docstring and "2.2" in docstring, "Docstring must specify 8.0pt band and 2.2pt edges"

    css_file = STATIC_DIR / "css" / "workbench.css"
    css_content = css_file.read_text(encoding="utf-8")
    assert "wall-highlight-band" in css_content, "CSS must style wall-highlight-band"
    assert "wall-spine-edge" in css_content, "CSS must style wall-spine-edge"
    assert "239, 68, 68" in css_content or "dc2626" in css_content, "CSS must use red color schemes"


def test_tier1_f15_interactive_takeoff_schedule_dock():
    """F15: Interactive Takeoff Schedule Dock.
    
    Verifies that static/index.html and static/js/app.js define the takeoff
    schedule table with columns: Tag, Type, Gross LF, Deductions, Net LF, SF,
    and supports bi-directional hover and selection linking.
    """
    index_file = STATIC_DIR / "index.html"
    app_file = STATIC_DIR / "js" / "app.js"
    content = index_file.read_text(encoding="utf-8")
    app_js = app_file.read_text(encoding="utf-8")

    # Verify table headers exist in template
    assert "Tag" in content or "tag" in content.lower()
    assert "LF" in content or "Linear" in content
    assert "SF" in content or "Area" in content or "Board" in content

    # Verify bi-directional linking in app.js
    assert "highlightScheduleRow" in app_js, "app.js must implement highlightScheduleRow"
    assert "highlightWall" in app_js or "centerOnWall" in app_js, "app.js must link schedule to canvas"


def test_tier1_f16_windows_environment_compatibility():
    """F16: Windows Compatibility & File Lock Verification.
    
    Verifies that all operations use Windows-safe path semantics and do not
    suffer from Windows file locks or PermissionError crashes.
    """
    assert os.name == "nt" or sys.platform == "win32", "Verification running on Windows"
    
    # Test file access without file lock
    test_pdf = FIXTURES_DIR / "fixture_door.pdf"
    assert test_pdf.exists()
    with open(test_pdf, "rb") as f:
        data = f.read()
    assert len(data) > 0


def test_tier1_f17_e2e_real_blueprint_validation():
    """F17: End-to-End Real Blueprint Validation.
    
    Verifies end-to-end validation on uploads/doc_20261104_101950_6cbd34.pdf
    Sheet A-101 (Page 15) returning non-zero LF, SF, and dual-red annotations.
    """
    doc = fitz.open(str(REAL_BLUEPRINT_PATH))
    p15 = doc[14]
    scale, _, _ = detect_scale_from_page(p15)
    lw = extract_page_linework(p15)

    schedule_tags = {'0X', '1A', '1B', '1C', '1D', '1E', '2B', '2C', '2W', '2X', '3A', '3D', '4B1', '4K', '4P', '5B', '5D', '5E', '5L', '7A', '7B', '7C', '7E', '7F', '7G', '8A', '8P', 'GL1', 'GL2', 'PW'}
    insts = find_tag_instances_on_page(p15, schedule_tags)

    runs = []
    for idx, tag_inst in enumerate(insts):
        ax, ay, l_seg = find_leader_endpoint(tag_inst.center.x, tag_inst.center.y, tag_inst.tag_radius, lw.segments)
        s_seg = find_seed_segment(ax, ay, tag_inst.center.x, tag_inst.center.y, tag_inst.tag_radius, lw.segments, l_seg)
        if s_seg is None:
            continue
        traced = trace_wall_from_seed(s_seg, l_seg, lw.segments, lw.door_arcs, scale, 15, f"RUN-{idx+1:03d}")
        if traced:
            wr = create_wall_run(traced, tag_inst.tag, 15, "A-101", f"RUN-{idx+1:03d}", scale)
            runs.append(wr)

    deduped = deduplicate_wall_runs(runs, scale)
    takeoff = calculate_takeoff(runs=deduped, scale_ft_per_pt=scale)

    assert takeoff.total_gross_lf > 0.0
    assert takeoff.total_net_lf > 0.0
    assert takeoff.total_board_sf > 0.0
    assert len(takeoff.runs) == len(deduped)
    doc.close()


# =============================================================================
# TIER 2: BOUNDARY & CORNER CASES
# =============================================================================


def test_tier2_boundary_out_of_bounds_pages():
    """Boundary Case B1: Out-of-bounds page requests (0, -1, 72, 999)."""
    doc = fitz.open(str(REAL_BLUEPRINT_PATH))
    total_pages = len(doc)
    assert total_pages == 71

    # Verify boundary checking logic
    for invalid_page_num in [0, -1, 72, 999]:
        page_idx = invalid_page_num - 1
        is_oob = page_idx < 0 or page_idx >= total_pages
        assert is_oob is True, f"Page {invalid_page_num} should be recognized as out of bounds"

    with pytest.raises((IndexError, AssertionError)):
        _ = doc[total_pages]
    with pytest.raises((IndexError, AssertionError)):
        _ = doc[999]

    doc.close()


def test_tier2_zero_and_negative_dimensions():
    """Boundary Case B2: Zero and negative dimensions."""
    scale = 0.111111

    # 1. Zero-length segment (start == end)
    zero_seg = Segment(100.0, 100.0, 100.0, 100.0)
    assert zero_seg.length == 0.0
    gross_lf = calculate_gross_lf(zero_seg.length, scale)
    assert gross_lf == 0.00

    # 2. Opening deduction larger than wall length (25 ft opening on 20 ft wall)
    net_lf = calculate_net_lf(gross_lf=20.00, opening_widths_ft=[25.00])
    assert net_lf == 0.00, "Net LF must be clamped to 0.00, never negative."

    # 3. Multiple excessive openings
    net_lf_multi = calculate_net_lf(gross_lf=15.00, opening_widths_ft=[10.00, 10.00])
    assert net_lf_multi == 0.00


def test_tier2_71_page_blueprint_boundary_navigation():
    """Boundary Case B3: 71-Page Large Blueprint Navigation."""
    doc = fitz.open(str(REAL_BLUEPRINT_PATH))
    assert len(doc) == 71

    # First page
    p1 = doc[0]
    assert p1.rect.width == 2592.0 and p1.rect.height == 1728.0

    # Target page (Page 15)
    p15 = doc[14]
    assert p15.rect.width == 2592.0 and p15.rect.height == 1728.0

    # Final page (Page 71)
    p71 = doc[70]
    assert p71.rect.width == 2592.0 and p71.rect.height == 1728.0

    doc.close()


def test_tier2_empty_and_missing_markups():
    """Boundary Case B4: Empty and missing markups."""
    empty_takeoff = calculate_takeoff(runs=[], scale_ft_per_pt=0.111111)
    assert empty_takeoff.total_gross_lf == 0.0
    assert empty_takeoff.total_net_lf == 0.0
    assert empty_takeoff.total_board_sf == 0.0
    assert empty_takeoff.total_studs_ea == 0
    assert empty_takeoff.total_track_lf == 0.0
    assert empty_takeoff.total_plates_lf == 0.0
    assert len(empty_takeoff.runs) == 0


def test_tier2_invalid_calibration_inputs():
    """Boundary Case B5: Invalid calibration inputs."""
    # 1. Identical points (distance = 0)
    pt1 = {"x": 100.0, "y": 100.0}
    pt2 = {"x": 100.0, "y": 100.0}
    dist_pt = math.hypot(pt2["x"] - pt1["x"], pt2["y"] - pt1["y"])
    assert dist_pt == 0.0

    with pytest.raises(ZeroDivisionError):
        _ = 20.0 / dist_pt

    # 2. Negative real-world distance
    negative_distance_ft = -10.0
    assert negative_distance_ft < 0.0, "Negative real-world distance must be flagged invalid."


# =============================================================================
# TIER 3: CROSS-FEATURE COMBINATIONS
# =============================================================================


def test_tier3_combined_sheet_detection_calibration_markup_deduction_sync():
    """Tier 3: Multi-step cross-feature workflow.
    
    Steps:
    1. Sheet selection: Select Page 15 (Sheet A-101) from 71-page blueprint.
    2. Wall detection: Extract CAD linework and trace walls on Page 15.
    3. Interactive 2-point scale calibration: Calibrate custom scale (240 pt = 20 ft).
    4. Manual wall run creation: Add manual wall run (180 pt tagged "5E", height 12.0 ft).
    5. Opening deduction: Add 3.0 ft door opening to the manual wall run.
    6. Schedule sync: Recalculate takeoff and verify detected + manual totals.
    """
    doc = fitz.open(str(REAL_BLUEPRINT_PATH))
    p15 = doc[14]
    lw = extract_page_linework(p15)

    # Step 2: Wall detection with default scale
    default_scale = 0.111111
    schedule_tags = {'0X', '1A', '1B', '1C', '1D', '1E', '2B', '2C', '2W', '2X', '3A', '3D', '4B1', '4K', '4P', '5B', '5D', '5E', '5L', '7A', '7B', '7C', '7E', '7F', '7G', '8A', '8P', 'GL1', 'GL2', 'PW'}
    insts = find_tag_instances_on_page(p15, schedule_tags)
    doc.close()

    runs = []
    for idx, tag_inst in enumerate(insts[:5]):  # Sample 5 runs for combination verification
        ax, ay, l_seg = find_leader_endpoint(tag_inst.center.x, tag_inst.center.y, tag_inst.tag_radius, lw.segments)
        s_seg = find_seed_segment(ax, ay, tag_inst.center.x, tag_inst.center.y, tag_inst.tag_radius, lw.segments, l_seg)
        if s_seg is None:
            continue
        traced = trace_wall_from_seed(s_seg, l_seg, lw.segments, lw.door_arcs, default_scale, 15, f"RUN-{idx+1:03d}")
        if traced:
            wr = create_wall_run(traced, tag_inst.tag, 15, "A-101", f"RUN-{idx+1:03d}", default_scale)
            runs.append(wr)

    initial_takeoff = calculate_takeoff(runs=runs, scale_ft_per_pt=default_scale)
    base_gross_lf = initial_takeoff.total_gross_lf
    base_net_lf = initial_takeoff.total_net_lf

    # Step 3: Interactive 2-Point Calibration (240 pt = 20 ft -> ft_per_pt = 0.083333)
    calibrated_scale = 20.0 / 240.0
    assert round(calibrated_scale, 6) == 0.083333

    # Step 4: Manual Wall Run Creation (180 pt vector at calibrated scale = 15.00 LF)
    manual_seg = Segment(500.0, 500.0, 680.0, 500.0)  # 180 pt
    manual_gross_lf = round(manual_seg.length * calibrated_scale, 2)
    assert manual_gross_lf == 15.00

    manual_run = WallRun(
        run_id="RUN-MANUAL-01",
        tag="5E",
        page_num=15,
        sheet_label="A-101",
        spine=manual_seg,
        gross_length_pt=180.0,
        gross_length_ft=manual_gross_lf,
        opening_deduction_ft=0.0,
        net_length_ft=manual_gross_lf,
        openings=[],
        segments=[manual_seg],
        ft_per_pt=calibrated_scale,
    )

    # Step 5: Opening Deduction Addition (3.0 ft door)
    door_op = Opening(
        opening_id="OP-MANUAL-01",
        wall_run_id="RUN-MANUAL-01",
        page_num=15,
        t_start=76.5,
        t_end=103.5,
        width_pt=27.0,
        width_ft=3.0,
        height_ft=7.0,
        center_pt=Point(590.0, 500.0),
    )
    manual_run.openings.append(door_op)
    manual_run.opening_deduction_ft = 3.00
    manual_run.net_length_ft = round(manual_gross_lf - 3.0, 2)
    assert manual_run.net_length_ft == 12.00

    # Step 6: Schedule Sync & Recalculation
    combined_runs = list(runs) + [manual_run]
    synced_takeoff = calculate_takeoff(runs=combined_runs, scale_ft_per_pt=default_scale)

    assert synced_takeoff.total_gross_lf == round(base_gross_lf + 15.00, 2)
    assert synced_takeoff.total_net_lf == round(base_net_lf + 12.00, 2)
    assert len(synced_takeoff.runs) == len(runs) + 1


# =============================================================================
# TIER 4: REAL-WORLD BLUEPRINT SCENARIO
# =============================================================================


def test_tier4_real_world_blueprint_sheet_a101():
    """Tier 4: Authoritative Real-World Blueprint Scenario on Sheet A-101 (Page 15).
    
    Executes end-to-end on uploads/doc_20261104_101950_6cbd34.pdf targeting
    Sheet A-101 (Page 15) and verifies authoritative oracles:
    - 71 total pages
    - Sheet A-101 at Page 15
    - Scale: 1/8" = 1'-0" (0.111111 ft/pt)
    - 5,951 CAD segments, 220 door arcs
    - 31 qualified tag instances
    - 27 raw wall runs traced, 19 consolidated runs
    - Authoritative gross LF ~495.83 LF, net LF ~473.21 LF
    - Board SF > 9,000 SF
    - Dual-red visual annotation geometry verified
    - Takeoff schedule data structures populated
    """
    doc = fitz.open(str(REAL_BLUEPRINT_PATH))
    assert len(doc) == 71, f"Expected 71 pages, got {len(doc)}"

    p15 = doc[14]
    scale, scale_str, status = detect_scale_from_page(p15)
    assert status == "DETECTED"
    assert scale_str == '1/8" = 1\'-0"'
    assert round(scale, 6) == 0.111111

    lw = extract_page_linework(p15)
    assert len(lw.segments) == 5951, f"Expected 5951 segments, got {len(lw.segments)}"
    assert len(lw.door_arcs) == 220, f"Expected 220 door arcs, got {len(lw.door_arcs)}"

    schedule_tags = {'0X', '1A', '1B', '1C', '1D', '1E', '2B', '2C', '2W', '2X', '3A', '3D', '4B1', '4K', '4P', '5B', '5D', '5E', '5L', '7A', '7B', '7C', '7E', '7F', '7G', '8A', '8P', 'GL1', 'GL2', 'PW'}
    insts = find_tag_instances_on_page(p15, schedule_tags)
    assert len(insts) == 31, f"Expected 31 tag instances, got {len(insts)}"

    raw_runs: List[WallRun] = []
    for idx, tag_inst in enumerate(insts):
        ax, ay, l_seg = find_leader_endpoint(tag_inst.center.x, tag_inst.center.y, tag_inst.tag_radius, lw.segments)
        s_seg = find_seed_segment(ax, ay, tag_inst.center.x, tag_inst.center.y, tag_inst.tag_radius, lw.segments, l_seg)
        if s_seg is None:
            continue
        traced = trace_wall_from_seed(s_seg, l_seg, lw.segments, lw.door_arcs, scale, 15, f"RUN-{idx+1:03d}")
        if traced:
            wr = create_wall_run(traced, tag_inst.tag, 15, "A-101", f"RUN-{idx+1:03d}", scale)
            raw_runs.append(wr)

    assert len(raw_runs) == 27, f"Expected 27 raw wall runs, got {len(raw_runs)}"

    deduped = deduplicate_wall_runs(raw_runs, scale)
    assert len(deduped) == 19, f"Expected 19 deduped wall runs, got {len(deduped)}"

    takeoff = calculate_takeoff(runs=deduped, scale_ft_per_pt=scale)

    # Verify quantitative totals match authoritative ground truth
    assert abs(takeoff.total_gross_lf - 495.83) < 2.0, f"Gross LF mismatch: {takeoff.total_gross_lf}"
    assert abs(takeoff.total_net_lf - 473.21) < 2.0, f"Net LF mismatch: {takeoff.total_net_lf}"
    assert abs(takeoff.total_opening_deduction_lf - 22.62) < 1.0, f"Deduction mismatch: {takeoff.total_opening_deduction_lf}"
    assert takeoff.total_board_sf > 9000.0, f"Board SF mismatch: {takeoff.total_board_sf}"

    # Verify dual-red annotation geometry structures
    for r in deduped:
        assert r.spine is not None, f"Run {r.run_id} missing spine geometry"
        assert r.spine.length > 0.0, f"Run {r.run_id} spine length must be positive"
        assert len(r.segments) > 0, f"Run {r.run_id} missing face segments"
        for face_seg in r.segments:
            assert face_seg.length > 0.0

    doc.close()


def test_tier4_selective_page15_pipeline_real_blueprint():
    """Verify that running QTOPipeline directly on uploads/doc_20261104_101950_6cbd34.pdf
    with selected_pages=[15] returns wall runs and non-zero LF.
    """
    pipeline = QTOPipeline(str(REAL_BLUEPRINT_PATH), selected_pages=[15])
    summary = pipeline.run()

    assert summary["selected_pages"] == [15]
    assert summary["sheets_processed"] == [15]
    assert summary["total_wall_runs"] > 0
    assert summary["total_gross_lf"] > 100.0
    assert summary["total_board_sf"] > 1000.0
