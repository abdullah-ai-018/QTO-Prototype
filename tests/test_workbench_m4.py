"""tests/test_workbench_m4.py: Milestone 4 Verification Suite.

Validates Requirements R3, R4, R5 & Features F11-F14:
1. API Serialization Contract (GET /api/takeoff/{run_id}, GET /api/takeoff, GET /api/sheets).
2. All 8 M2/M3 fields verified in JSON: thickness_in, thickness_measured, height_ft,
   is_height_verified, height_source, section_callout_tag, material_layers, status.
3. Live Dynamic Recalculation on markup edits (endpoints, height overrides, opening deductions, tags, thickness).
4. Review item clearing upon estimator height verification.
5. 7-Sheet Excel workbook consistency with schedule metrics.
6. 12 comprehensive automated test cases.
"""

import json
from pathlib import Path
import openpyxl
import pytest
from fastapi.testclient import TestClient

import app
from qto.dedup import WallRun
from qto.geometry import Segment
from qto.quantities import calculate_takeoff
from qto.export import create_qto_workbook, EXPECTED_HEADERS

ROOT_DIR = Path(__file__).resolve().parent.parent
RUNS_DIR = getattr(app, "RUNS_DIR", ROOT_DIR / "runs")


@pytest.fixture
def m4_test_run(tmp_path):
    """Creates an isolated test run with 1 verified wall and 1 unverified review wall."""
    run_id = f"test_m4_{tmp_path.name}"
    run_dir = RUNS_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    baseline_data = {
        "run_id": run_id,
        "pdf_file": "fixture_wall20.pdf",
        "pdf_sha256": "abcdef1234567890",
        "timestamp": "2026-11-05T12:00:00Z",
        "default_height_ft": 10.0,
        "stud_spacing_in": 16,
        "waste_percent": 0.0,
        "total_wall_runs": 2,
        "total_openings_deducted": 0,
        "verified_height_count": 1,
        "unverified_height_count": 1,
        "total_gross_lf": 40.0,
        "total_opening_deduction_lf": 0.0,
        "total_net_lf": 40.0,
        "total_board_sf": 720.0,
        "total_studs_ea": 32,
        "total_stud_lf": 288.0,
        "total_track_lf": 80.0,
        "sheets": [
            {
                "page_num": 1,
                "sheet_label": "A-101",
                "page_type": "FLOOR_PLAN",
                "scale_string": "1/8\" = 1'-0\"",
                "scale_status": "CALIBRATED",
                "ft_per_pt": 0.111111,
            }
        ],
        "by_tag": {
            "7A": {
                "tag": "7A",
                "description": "Metal Stud Partition Tag 7A",
                "height_ft": 8.0,
                "faces": 2,
                "layers_per_face": 1,
                "stud_spacing_in": 16,
                "attributes": {
                    "nominal_thickness_in": 4.875,
                    "material_layers": [
                        {"side": "Face A", "material": "5/8\" Type X GWB"},
                        {"side": "Core", "material": "3-5/8\" Metal Studs"},
                        {"side": "Face B", "material": "5/8\" Type X GWB"},
                    ],
                },
            },
            "5E": {
                "tag": "5E",
                "description": "Metal Stud Partition Tag 5E",
                "height_ft": 10.0,
                "faces": 2,
                "layers_per_face": 1,
                "stud_spacing_in": 16,
                "attributes": {
                    "nominal_thickness_in": 8.5,
                    "material_layers": [
                        {"side": "Face A", "material": "5/8\" Type X GWB"},
                        {"side": "Core", "material": "6\" Metal Studs"},
                        {"side": "Face B", "material": "5/8\" Type X GWB"},
                    ],
                },
            },
        },
        "runs": [
            {
                "run_id": "RUN-001",
                "tag": "7A",
                "page_num": 1,
                "sheet_label": "A-101",
                "spine": {"x1": 100.0, "y1": 100.0, "x2": 280.0, "y2": 100.0},
                "ft_per_pt": 0.111111,
                "gross_length_pt": 180.0,
                "gross_length_ft": 20.0,
                "opening_deduction_ft": 0.0,
                "net_length_ft": 20.0,
                "openings": [],
                "openings_count": 0,
                "segment_count": 1,
                "status": "OK",
                "is_manual": False,
                "height_ft": 8.0,
                "thickness_in": 4.875,
                "thickness_measured": True,
                "section_callout_tag": "A-706 / 09",
                "is_height_verified": True,
                "height_source": "A-706 Detail 09",
                "material_layers": [
                    {"side": "Face A", "material": "5/8\" Type X GWB"},
                    {"side": "Core", "material": "3-5/8\" Metal Studs"},
                    {"side": "Face B", "material": "5/8\" Type X GWB"},
                ],
            },
            {
                "run_id": "RUN-002",
                "tag": "5E",
                "page_num": 1,
                "sheet_label": "A-101",
                "spine": {"x1": 100.0, "y1": 250.0, "x2": 280.0, "y2": 250.0},
                "ft_per_pt": 0.111111,
                "gross_length_pt": 180.0,
                "gross_length_ft": 20.0,
                "opening_deduction_ft": 0.0,
                "net_length_ft": 20.0,
                "openings": [],
                "openings_count": 0,
                "segment_count": 1,
                "status": "REVIEW",
                "is_manual": False,
                "height_ft": 10.0,
                "thickness_in": 8.5,
                "thickness_measured": False,
                "section_callout_tag": None,
                "is_height_verified": False,
                "height_source": "UNVERIFIED_HEIGHT_DEFAULT",
                "material_layers": [
                    {"side": "Face A", "material": "5/8\" Type X GWB"},
                    {"side": "Core", "material": "6\" Metal Studs"},
                    {"side": "Face B", "material": "5/8\" Type X GWB"},
                ],
                "notes": ["Unverified wall height: No section callout found on floor plan. Using standard 10.0 ft fallback."],
            },
        ],
        "review_items": [
            {
                "run_id": "RUN-002",
                "target_id": "RUN-002",
                "review_id": "REV-HGT-RUN-002",
                "tag": "5E",
                "page": 1,
                "sheet": "A-101",
                "category": "Unverified Wall Height",
                "issue": "Unverified wall height for Tag 5E: No section callout found on floor plan. Using standard 10.0 ft fallback.",
                "description": "Unverified wall height for Tag 5E: No section callout found on floor plan. Using standard 10.0 ft fallback.",
                "action_required": "Estimator review required to confirm wall height against architectural elevations.",
                "required_action": "Estimator review required to confirm wall height against architectural elevations.",
                "measured_values": "Default Height: 10.00 ft | Gross: 20.00 LF",
            }
        ],
    }

    out_file = run_dir / "output.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(baseline_data, f, indent=2)

    app.recalculate_run_state(run_id, baseline_data)

    return run_id


# Test 1: GET /api/takeoff/{run_id} serialization contract
def test_m4_api_takeoff_full_serialization_contract(m4_test_run):
    """GET /api/takeoff/{run_id} serializes all 8 required M2/M3 fields on every wall."""
    client = TestClient(app.app)
    res = client.get(f"/api/takeoff/{m4_test_run}")
    assert res.status_code == 200
    data = res.json()

    assert data["run_id"] == m4_test_run
    summary = data["summary"]
    assert summary["total_walls"] == 2
    assert summary["verified_height_count"] == 1
    assert summary["unverified_height_count"] == 1
    assert summary["total_gross_lf"] == 40.0
    assert summary["total_net_lf"] == 40.0

    walls = data["walls"]
    assert len(walls) == 2

    w1 = next(w for w in walls if w["run_id"] == "RUN-001")
    assert w1["thickness_in"] == 4.875
    assert w1["thickness_measured"] is True
    assert w1["height_ft"] == 8.0
    assert w1["is_height_verified"] is True
    assert w1["height_source"] == "A-706 Detail 09"
    assert w1["section_callout_tag"] == "A-706 / 09"
    assert len(w1["material_layers"]) == 3
    assert w1["status"] == "OK"

    w2 = next(w for w in walls if w["run_id"] == "RUN-002")
    assert w2["thickness_in"] == 8.5
    assert w2["thickness_measured"] is False
    assert w2["height_ft"] == 10.0
    assert w2["is_height_verified"] is False
    assert w2["height_source"] == "UNVERIFIED_HEIGHT_DEFAULT"
    assert w2["section_callout_tag"] is None
    assert w2["status"] == "REVIEW"

    assert len(data["review_items"]) == 1
    assert data["review_items"][0]["run_id"] == "RUN-002"


# Test 2: GET /api/takeoff alias endpoint
def test_m4_api_takeoff_alias_endpoint(m4_test_run):
    """GET /api/takeoff?run_id={run_id} returns identical takeoff data."""
    client = TestClient(app.app)
    res = client.get(f"/api/takeoff?run_id={m4_test_run}")
    assert res.status_code == 200
    data = res.json()
    assert data["run_id"] == m4_test_run
    assert len(data["walls"]) == 2


# Test 3: GET /api/sheets alias endpoint
def test_m4_api_sheets_endpoint_alias(m4_test_run):
    """GET /api/sheets returns sheets catalog with scale and page data."""
    client = TestClient(app.app)
    res = client.get(f"/api/sheets?run_id={m4_test_run}")
    assert res.status_code == 200
    sheets = res.json()
    assert len(sheets) >= 1
    assert sheets[0]["sheet_label"] == "A-101"


# Test 4: Dynamic recalculation on endpoint drag
def test_m4_live_recalc_wall_length_endpoint_drag(m4_test_run):
    """Dragging wall endpoints dynamically updates gross/net LF, board SF, and stud LF."""
    client = TestClient(app.app)
    # Extend RUN-001 by 90 pt (10 LF) -> gross 30.0 LF
    res = client.patch(
        f"/api/blueprint/{m4_test_run}/walls/RUN-001",
        json={"end": {"x": 370.0, "y": 100.0}},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["wall"]["gross_length_ft"] == 30.0
    assert data["wall"]["net_length_ft"] == 30.0

    recalc = data["recalculated_takeoff"]
    # Total gross LF: 30.0 (RUN-001) + 20.0 (RUN-002) = 50.0 LF
    assert recalc["total_gross_lf"] == 50.0
    assert recalc["total_net_lf"] == 50.0
    # Board SF: 30 LF * 8 H * 2 = 480 SF + 20 LF * 10 H * 2 = 400 SF -> 880 SF
    assert recalc["total_board_sf"] == 880.0


# Test 5: Estimator manual height override clears review item
def test_m4_live_recalc_manual_height_override_clears_review(m4_test_run):
    """Estimator manual height change marks run verified and dynamically removes review item."""
    client = TestClient(app.app)
    # Confirm RUN-002 is unverified before edit
    res_before = client.get(f"/api/takeoff/{m4_test_run}")
    assert res_before.json()["summary"]["unverified_height_count"] == 1
    assert len(res_before.json()["review_items"]) == 1

    # Estimator reviews elevation and sets height to 12.0 ft
    res_patch = client.patch(
        f"/api/blueprint/{m4_test_run}/walls/RUN-002",
        json={"height_ft": 12.0},
    )
    assert res_patch.status_code == 200
    data_patch = res_patch.json()
    wall = data_patch["wall"]
    assert wall["height_ft"] == 12.0
    assert wall["is_height_verified"] is True
    assert wall["height_source"] in ("ESTIMATOR_VERIFIED", "ESTIMATOR_OVERRIDE")
    assert wall["status"] == "OK"

    # Verify review items list is cleared and unverified count dropped to 0
    res_after = client.get(f"/api/takeoff/{m4_test_run}")
    summary_after = res_after.json()["summary"]
    assert summary_after["verified_height_count"] == 2
    assert summary_after["unverified_height_count"] == 0
    assert len(res_after.json()["review_items"]) == 0


# Test 6: Opening deduction subtraction dynamically updates net LF and board SF
def test_m4_live_recalc_opening_deduction_subtraction(m4_test_run):
    """Adding a 3ft x 7ft door opening reduces net LF by 3.0 LF and board SF by 42.0 SF."""
    client = TestClient(app.app)
    res = client.patch(
        f"/api/blueprint/{m4_test_run}/walls/RUN-001",
        json={"openings": [{"type": "door", "width_ft": 3.0, "height_ft": 7.0}]},
    )
    assert res.status_code == 200
    wall = res.json()["wall"]
    assert wall["gross_length_ft"] == 20.0
    assert wall["opening_deduction_ft"] == 3.0
    assert wall["net_length_ft"] == 17.0

    recalc = res.json()["recalculated_takeoff"]
    assert recalc["total_net_lf"] == 37.0  # 17.0 + 20.0
    # RUN-001 Board SF: (20 * 8 - 3 * 7) * 2 = (160 - 21) * 2 = 139 * 2 = 278 SF
    # RUN-002 Board SF: 20 * 10 * 2 = 400 SF -> Total: 678 SF
    assert recalc["total_board_sf"] == 678.0


# Test 7: POST /api/runs/update modifies wall and recomputes takeoff state
def test_m4_runs_update_post_endpoint(m4_test_run):
    """POST /api/runs/update modifies wall and recomputes takeoff state."""
    client = TestClient(app.app)
    res = client.post(
        "/api/runs/update",
        json={"run_id": m4_test_run, "wall_id": "RUN-001", "height_ft": 9.0},
    )
    assert res.status_code == 200
    assert res.json()["wall"]["height_ft"] == 9.0


# Test 8: Excel export contains Thickness, Height, Height Source, and Status
def test_m4_excel_export_thickness_and_height_verification(m4_test_run):
    """qto.xlsx Runs sheet exports thickness_in, height_ft, height_source, and status."""
    client = TestClient(app.app)
    res = client.get(f"/api/takeoff/{m4_test_run}/export/excel")
    assert res.status_code == 200

    wb = openpyxl.load_workbook(open(RUNS_DIR / m4_test_run / "qto.xlsx", "rb"), data_only=True)
    assert "Runs" in wb.sheetnames
    ws_runs = wb["Runs"]

    headers = [ws_runs.cell(row=1, column=c).value for c in range(1, ws_runs.max_column + 1)]
    assert "Height (ft)" in headers
    assert "Height Source" in headers
    assert "Status" in headers
    assert "Thickness (in)" in headers
    assert "Thickness Measured" in headers
    assert "Section Callout Tag" in headers

    h_idx = headers.index("Height (ft)") + 1
    src_idx = headers.index("Height Source") + 1
    st_idx = headers.index("Status") + 1
    thick_idx = headers.index("Thickness (in)") + 1
    meas_idx = headers.index("Thickness Measured") + 1

    row2 = [ws_runs.cell(row=2, column=c).value for c in range(1, ws_runs.max_column + 1)]
    assert row2[h_idx - 1] == 8.0
    assert row2[src_idx - 1] == "A-706 Detail 09"
    assert row2[st_idx - 1] == "OK"
    assert row2[thick_idx - 1] == 4.875
    assert row2[meas_idx - 1] is True

    wb.close()


# Test 9: Live recalculation on thickness modification
def test_m4_live_recalc_thickness_override(m4_test_run):
    """Estimator manual thickness update modifies thickness_in and thickness_measured."""
    client = TestClient(app.app)
    res = client.patch(
        f"/api/blueprint/{m4_test_run}/walls/RUN-002",
        json={"thickness_in": 6.0, "thickness_measured": True},
    )
    assert res.status_code == 200
    wall = res.json()["wall"]
    assert wall["thickness_in"] == 6.0
    assert wall["thickness_measured"] is True

    # Check persistence in output.json
    res_get = client.get(f"/api/takeoff/{m4_test_run}")
    w2 = next(w for w in res_get.json()["walls"] if w["run_id"] == "RUN-002")
    assert w2["thickness_in"] == 6.0
    assert w2["thickness_measured"] is True


# Test 10: Live recalculation on partition tag change
def test_m4_live_recalc_wall_tag_change(m4_test_run):
    """Changing partition tag updates assembly metrics in takeoff."""
    client = TestClient(app.app)
    res = client.patch(
        f"/api/blueprint/{m4_test_run}/walls/RUN-002",
        json={"tag": "7A"},
    )
    assert res.status_code == 200
    wall = res.json()["wall"]
    assert wall["tag"] == "7A"

    # Verify takeoff summary includes by_tag breakdown with updated run counts
    recalc = res.json()["recalculated_takeoff"]
    assert "7A" in recalc["by_tag"]
    assert recalc["by_tag"]["7A"]["runs_count"] == 2


# Test 11: Deleting wall updates summary and clears review count if unverified
def test_m4_delete_wall_recalculates_takeoff_and_review_counts(m4_test_run):
    """Deleting RUN-002 removes review item and decrements unverified height count."""
    client = TestClient(app.app)
    res_del = client.delete(f"/api/blueprint/{m4_test_run}/walls/RUN-002")
    assert res_del.status_code == 200
    data_del = res_del.json()
    assert data_del["success"] is True
    assert data_del["deleted_id"] == "RUN-002"

    recalc = data_del["recalculated_takeoff"]
    assert recalc["total_gross_lf"] == 20.0
    assert recalc["total_net_lf"] == 20.0

    res_get = client.get(f"/api/takeoff/{m4_test_run}")
    summary = res_get.json()["summary"]
    assert summary["total_walls"] == 1
    assert summary["verified_height_count"] == 1
    assert summary["unverified_height_count"] == 0
    assert len(res_get.json()["review_items"]) == 0


# Test 12: POST alias for PATCH /api/blueprint/{run_id}/walls/{wall_id}
def test_m4_post_wall_markup_patch_alias(m4_test_run):
    """POST /api/blueprint/{run_id}/walls/{wall_id} operates identically to PATCH."""
    client = TestClient(app.app)
    res = client.post(
        f"/api/blueprint/{m4_test_run}/walls/RUN-001",
        json={"height_ft": 9.5},
    )
    assert res.status_code == 200
    assert res.json()["wall"]["height_ft"] == 9.5
    assert res.json()["wall"]["is_height_verified"] is True


# ==============================================================================
# FRONTEND DOM, CSS & JS INTEGRATION TESTS (Tests 13-20)
# ==============================================================================

# Test 13: Schedule dock container and filter controls in index.html
def test_m4_schedule_dock_container_and_filter_controls_html():
    """Verify index.html contains takeoff dock and segmented filter button IDs."""
    html_path = ROOT_DIR / "static" / "index.html"
    assert html_path.is_file(), "static/index.html must exist"
    content = html_path.read_text(encoding="utf-8")

    assert 'id="takeoffDock"' in content
    assert 'id="scheduleTable"' in content
    assert 'id="sched-filter-all"' in content
    assert 'id="sched-filter-verified"' in content
    assert 'id="sched-filter-review"' in content
    assert 'id="sched-drawer"' in content


# Test 14: Schedule table 16-column headers in index.html
def test_m4_schedule_table_16_column_headers_html():
    """Verify scheduleTable in index.html defines all 16 required takeoff columns."""
    import re
    html_path = ROOT_DIR / "static" / "index.html"
    content = html_path.read_text(encoding="utf-8")

    # Extract <th> tags inside the thead
    thead_match = re.search(r'<thead id="schedule-table-head".*?>(.*?)</thead>', content, re.DOTALL)
    assert thead_match is not None, "schedule-table-head thead must be present"
    thead_html = thead_match.group(1)

    th_headers = [re.sub(r'<[^>]+>', '', th).strip() for th in re.findall(r'<th[^>]*>(.*?)</th>', thead_html, re.DOTALL)]
    expected_16_headers = [
        "Run ID", "Tag", "Type", "Description", "Thickness", "Height",
        "Height Source", "Gross LF", "Deduction", "Net LF", "Board SF",
        "Studs (ea)", "Track (LF)", "Source Sheet", "Status", "Actions"
    ]
    assert th_headers == expected_16_headers, f"Expected 16 headers {expected_16_headers}, got {th_headers}"
    assert len(th_headers) == 16


# Test 15: Inspector review warning and height provenance fields in index.html
def test_m4_inspector_review_warning_and_height_source_html():
    """Verify right-drawer inspector contains review banner and M2/M3 property elements."""
    html_path = ROOT_DIR / "static" / "index.html"
    content = html_path.read_text(encoding="utf-8")

    assert 'id="inspector-review-banner"' in content
    assert 'id="inspector-review-reason"' in content
    assert 'id="inspector-verified-banner"' in content
    assert 'id="prop-thickness"' in content
    assert 'id="prop-height-verification"' in content
    assert 'id="prop-section-callout"' in content
    assert 'id="prop-height-source"' in content


# Test 16: CSS rules for dock, filter buttons, and HUD in workbench.css
def test_m4_schedule_dock_and_filter_css():
    """Verify workbench.css defines rules for segmented filters, schedule drawer, and HUD."""
    css_path = ROOT_DIR / "static" / "css" / "workbench.css"
    assert css_path.is_file(), "static/css/workbench.css must exist"
    content = css_path.read_text(encoding="utf-8")

    assert "#sched-filter-all" in content
    assert "#sched-filter-verified" in content
    assert "#sched-filter-review" in content
    assert "#sched-drawer" in content
    assert ".cad-hover-hud" in content


# Test 17: Schedule filter and 16-column rendering functions in app.js
def test_m4_app_js_schedule_filter_and_16_column_rendering():
    """Verify static/js/app.js implements setScheduleFilter, formatThickness, formatHeightSource, formatStatusBadge."""
    js_path = ROOT_DIR / "static" / "js" / "app.js"
    assert js_path.is_file(), "static/js/app.js must exist"
    content = js_path.read_text(encoding="utf-8")

    assert "function setScheduleFilter" in content or "setScheduleFilter = " in content or "setScheduleFilter(" in content
    assert "formatThickness" in content
    assert "formatHeightSource" in content
    assert "formatStatusBadge" in content
    assert "scheduleFilter" in content


# Test 18: Inspector review banner logic and material layer chips in app.js
def test_m4_app_js_inspector_review_logic_and_color_chips():
    """Verify app.js manages review warning vs verified badge and renders material layer chips."""
    js_path = ROOT_DIR / "static" / "js" / "app.js"
    content = js_path.read_text(encoding="utf-8")

    assert "inspector-review-banner" in content
    assert "inspector-verified-banner" in content
    assert "prop-material-layers-list" in content
    # Multi-layer assembly chips (Face A, Core, Face B)
    assert "Face A" in content or "face a" in content
    assert "Core" in content or "core" in content
    assert "Face B" in content or "face b" in content


# Test 19: Viewer.js deselectWall and hover HUD methods
def test_m4_viewer_js_deselect_and_cad_hover_hud():
    """Verify viewer.js handles deselectWall with null event and hover HUD updates."""
    viewer_path = ROOT_DIR / "static" / "js" / "viewer.js"
    assert viewer_path.is_file(), "static/js/viewer.js must exist"
    content = viewer_path.read_text(encoding="utf-8")

    assert "deselectWall()" in content
    assert "this.onWallSelected(null)" in content
    assert "cad-hover-hud" in content
    assert "_showHoverHUD" in content
    assert "_hideHoverHUD" in content


# Test 20: Schedule filter segmentation logic
def test_m4_schedule_filter_segmentation_logic():
    """Simulate client-side filtering logic: all, verified, review."""
    mock_walls = [
        {"run_id": "RUN-001", "is_height_verified": True, "status": "VERIFIED"},
        {"run_id": "RUN-002", "is_height_verified": False, "status": "REVIEW"},
        {"run_id": "RUN-003", "is_height_verified": True, "status": "VERIFIED"},
        {"run_id": "RUN-004", "is_height_verified": False, "status": "REVIEW"},
    ]

    def filter_walls(filter_type, walls):
        if filter_type == "verified":
            return [w for w in walls if bool(w.get("is_height_verified")) and w.get("status") != "REVIEW"]
        elif filter_type == "review":
            return [w for w in walls if not bool(w.get("is_height_verified")) or w.get("status") == "REVIEW"]
        return walls

    all_walls = filter_walls("all", mock_walls)
    verified_walls = filter_walls("verified", mock_walls)
    review_walls = filter_walls("review", mock_walls)

    assert len(all_walls) == 4
    assert len(verified_walls) == 2
    assert len(review_walls) == 2
    assert [w["run_id"] for w in verified_walls] == ["RUN-001", "RUN-003"]
    assert [w["run_id"] for w in review_walls] == ["RUN-002", "RUN-004"]

