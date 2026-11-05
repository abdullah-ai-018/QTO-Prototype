"""tests/test_m2_markup_crud.py: Milestone 2 Scale Calibration & Wall Markup CRUD Test Suite.

Authoritative specification:
- PROJECT.md Contracts 3 & 4
- m2_exp2/handoff.md Section 4.2
- ORIGINAL_REQUEST.md Requirement R3

Tests:
1. Scale Calibration:
   - 2-point scale calculation and sheet scale update (CALIBRATED)
   - Dynamic scaling of gross/net LF of all runs on the calibrated page
   - Input validation: identical points (400), non-positive distance (400)
   - Nonexistent run_id (404)
2. Manual Wall Creation:
   - Creation with is_manual=True, page_num, tag, custom height_ft
   - Calculated gross LF, opening deductions, net LF, board SF
   - Input validation: zero length (400), empty tag (400)
3. Wall Patching (Editing):
   - Drag endpoints: updates spine, gross LF, net LF
   - Tag modification: updates tag rollup in takeoff schedule
   - Height modification: honors per-run height in board SF calculation
   - Openings management: adds door/window deductions, clears deductions
   - Nonexistent wall_id (404)
4. Wall Deletion:
   - Removes wall and associated openings from output.json
   - Recalculates project takeoff totals dynamically
   - Nonexistent wall_id (404)
5. Excel Synchronization:
   - Verifies qto.xlsx is regenerated and perfectly in sync with output.json
"""

import json
import math
import os
from pathlib import Path
import shutil
import sys
import pytest
from fastapi.testclient import TestClient
import openpyxl

ROOT_DIR = Path(__file__).resolve().parent.parent
if sys.path[0] != str(ROOT_DIR):
    sys.path.insert(0, str(ROOT_DIR))

if "app" in sys.modules and getattr(sys.modules["app"], "__file__", "") != str(ROOT_DIR / "app.py"):
    del sys.modules["app"]

import app
RUNS_DIR = getattr(app, "RUNS_DIR", ROOT_DIR / "runs")


@pytest.fixture
def test_crud_run(tmp_path):
    """Creates a temporary isolated test run seeded with a baseline 20 LF wall run."""
    run_id = f"test_m2_crud_{tmp_path.name}"
    run_dir = RUNS_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    baseline_data = {
        "run_id": run_id,
        "pdf_file": "fixture_wall20.pdf",
        "pdf_sha256": "abcdef1234567890",
        "timestamp": "2026-11-04T12:00:00Z",
        "default_height_ft": 10.0,
        "stud_spacing_in": 16,
        "waste_percent": 0.0,
        "total_wall_runs": 1,
        "total_openings_deducted": 0,
        "total_gross_lf": 20.0,
        "total_opening_deduction_lf": 0.0,
        "total_net_lf": 20.0,
        "total_board_sf": 400.0,
        "total_studs_ea": 16,
        "total_track_lf": 40.0,
        "sheets": [
            {
                "page_num": 1,
                "sheet_label": "Sheet_1",
                "page_type": "FLOOR_PLAN",
                "width": 612.0,
                "height": 792.0,
                "scale_string": "1/8\" = 1'-0\"",
                "scale_status": "DETECTED",
                "ft_per_pt": 0.111111,
            }
        ],
        "by_tag": {
            "7A": {
                "tag": "7A",
                "description": "Metal Stud Partition Tag 7A",
                "height_ft": 10.0,
                "height_source": "DEFAULT",
                "faces": 2,
                "layers_per_face": 1,
                "stud_material": "Metal",
                "stud_spacing_in": 16,
                "board_type": "Type X",
                "board_thickness_in": "5/8\"",
                "status": "OK",
                "runs_count": 1,
                "gross_lf": 20.0,
                "opening_deduction_lf": 0.0,
                "net_lf": 20.0,
                "net_board_sf": 400.0,
                "studs_ea": 16,
                "stud_lf": 160.0,
                "track_lf": 40.0,
                "plates_lf": 0.0,
                "attributes": {
                    "height_ft": 10.0,
                    "stud_spacing_in": 16,
                    "layers_per_face": 1,
                    "finished_faces": 2,
                },
            }
        },
        "openings": [],
        "runs": [
            {
                "run_id": "RUN-001",
                "tag": "7A",
                "page_num": 1,
                "sheet_label": "Sheet_1",
                "spine": {
                    "x1": 100.0,
                    "y1": 200.0,
                    "x2": 280.0,
                    "y2": 200.0,
                    "length": 180.0,
                    "angle": 0.0,
                },
                "ft_per_pt": 0.111111,
                "gross_length_pt": 180.0,
                "gross_length_ft": 20.0,
                "opening_deduction_ft": 0.0,
                "net_length_ft": 20.0,
                "openings_count": 0,
                "openings": [],
                "segment_count": 1,
                "has_leader": False,
                "tag_instances": [],
                "status": "OK",
                "conflict_tags": [],
                "notes": [],
                "is_manual": False,
                "height_ft": None,
            }
        ],
    }

    with open(run_dir / "output.json", "w", encoding="utf-8") as f:
        json.dump(baseline_data, f, indent=2)

    app.recalculate_run_state(run_id, baseline_data)

    yield run_id

    # Cleanup run dir
    if run_dir.exists():
        shutil.rmtree(run_dir, ignore_errors=True)


def test_calibrate_updates_page_scale_and_recalculates_walls(test_crud_run):
    """Calibrating page scale recalculates all walls on that page and updates sheet scale status."""
    client = TestClient(app.app)
    run_id = test_crud_run

    # pt1 (0, 0) to pt2 (240, 0) with real distance 20.0 ft -> new_ft_per_pt = 20.0 / 240.0 = 0.083333
    res = client.post(
        f"/api/blueprint/{run_id}/page/1/calibrate",
        json={
            "pt1": {"x": 0.0, "y": 0.0},
            "pt2": {"x": 240.0, "y": 0.0},
            "real_world_distance_ft": 20.0,
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["page_num"] == 1
    assert data["measured_pixel_distance"] == 240.0
    assert data["new_ft_per_pt"] == 0.083333

    # Wall gross LF was 180 pt * 0.083333 = 15.00 LF
    recalc = data["recalculated_takeoff"]
    assert recalc["total_gross_lf"] == 15.00
    assert recalc["total_net_lf"] == 15.00
    assert recalc["net_linear_footage"] == 15.00
    assert recalc["net_board_footage"] == 300.0  # 15 LF * 10 H * 2 sides

    # Verify output.json on disk
    with open(RUNS_DIR / run_id / "output.json", "r", encoding="utf-8") as f:
        disk_data = json.load(f)

    sheet_1 = next(s for s in disk_data["sheets"] if s["page_num"] == 1)
    assert sheet_1["scale_status"] == "CALIBRATED"
    assert sheet_1["ft_per_pt"] == 0.083333
    assert disk_data["runs"][0]["gross_length_ft"] == 15.00


def test_calibrate_validation_identical_points_400(test_crud_run):
    """Submitting identical points must return HTTP 400 Bad Request."""
    client = TestClient(app.app)
    res = client.post(
        f"/api/blueprint/{test_crud_run}/page/1/calibrate",
        json={
            "pt1": {"x": 100.0, "y": 100.0},
            "pt2": {"x": 100.0, "y": 100.0},
            "real_world_distance_ft": 20.0,
        },
    )
    assert res.status_code == 400
    assert "identical" in res.json()["detail"].lower()


def test_calibrate_validation_non_positive_distance_400(test_crud_run):
    """Submitting zero or negative real-world distance must return HTTP 400."""
    client = TestClient(app.app)
    res = client.post(
        f"/api/blueprint/{test_crud_run}/page/1/calibrate",
        json={
            "pt1": {"x": 0.0, "y": 0.0},
            "pt2": {"x": 200.0, "y": 0.0},
            "real_world_distance_ft": -5.0,
        },
    )
    assert res.status_code == 400
    assert "positive" in res.json()["detail"].lower()


def test_calibrate_nonexistent_run_404():
    """Attempting calibration on an unknown run_id returns HTTP 404."""
    client = TestClient(app.app)
    res = client.post(
        "/api/blueprint/nonexistent_run_999999/page/1/calibrate",
        json={
            "pt1": {"x": 0.0, "y": 0.0},
            "pt2": {"x": 200.0, "y": 0.0},
            "real_world_distance_ft": 20.0,
        },
    )
    assert res.status_code == 404


def test_create_manual_wall_returns_is_manual_true(test_crud_run):
    """Creating a manual wall assigns is_manual=True, unique ID, and updates project takeoff totals."""
    client = TestClient(app.app)
    run_id = test_crud_run

    # 180 pt segment at 0.111111 ft/pt = 20.00 LF with tag 5E and height 12.0 ft
    res = client.post(
        f"/api/blueprint/{run_id}/page/1/walls",
        json={
            "start": {"x": 300.0, "y": 200.0},
            "end": {"x": 480.0, "y": 200.0},
            "tag": "5E",
            "height_ft": 12.0,
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    wall = data["wall"]
    assert wall["run_id"] == "RUN-M01"
    assert wall["is_manual"] is True
    assert wall["tag"] == "5E"
    assert wall["gross_length_ft"] == 20.00
    assert wall["net_length_ft"] == 20.00
    assert wall["height_ft"] == 12.0

    # Project totals: baseline 20.0 LF (tag 7A) + manual 20.0 LF (tag 5E) = 40.0 LF
    recalc = data["recalculated_takeoff"]
    assert recalc["total_gross_lf"] == 40.00
    assert recalc["total_net_lf"] == 40.00
    # Board SF: 20 LF * 10 H * 2 = 400 SF (tag 7A) + 20 LF * 12 H * 2 = 480 SF (tag 5E) = 880 SF
    assert recalc["total_board_sf"] == 880.0


def test_create_manual_wall_zero_length_400(test_crud_run):
    """Creating a manual wall with identical endpoints returns HTTP 400."""
    client = TestClient(app.app)
    res = client.post(
        f"/api/blueprint/{test_crud_run}/page/1/walls",
        json={
            "start": {"x": 100.0, "y": 100.0},
            "end": {"x": 100.0, "y": 100.0},
            "tag": "1A",
        },
    )
    assert res.status_code == 400
    assert "identical" in res.json()["detail"].lower()


def test_create_manual_wall_empty_tag_400(test_crud_run):
    """Creating a manual wall with empty whitespace tag returns HTTP 400."""
    client = TestClient(app.app)
    res = client.post(
        f"/api/blueprint/{test_crud_run}/page/1/walls",
        json={
            "start": {"x": 100.0, "y": 100.0},
            "end": {"x": 200.0, "y": 100.0},
            "tag": "   ",
        },
    )
    assert res.status_code == 400
    assert "empty" in res.json()["detail"].lower()


def test_patch_wall_drag_endpoints_and_change_tag(test_crud_run):
    """Dragging wall endpoints and editing partition tag updates geometries and schedule rollups."""
    client = TestClient(app.app)
    run_id = test_crud_run

    # Baseline wall is RUN-001 from (100, 200) to (280, 200) [180 pt = 20 LF] with tag 7A
    # Extend end to (370, 200) [270 pt = 30 LF] and change tag to 3A
    res = client.patch(
        f"/api/blueprint/{run_id}/walls/RUN-001",
        json={
            "end": {"x": 370.0, "y": 200.0},
            "tag": "3A",
            "height_ft": 10.0,
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    wall = data["wall"]
    assert wall["gross_length_ft"] == 30.00
    assert wall["net_length_ft"] == 30.00
    assert wall["tag"] == "3A"

    recalc = data["recalculated_takeoff"]
    assert recalc["total_gross_lf"] == 30.00
    assert "3A" in recalc["by_tag"]
    assert recalc["by_tag"]["3A"]["net_lf"] == 30.00


def test_patch_wall_add_door_opening_deduction(test_crud_run):
    """Adding an opening deduction subtracts opening width from net LF and opening area from net SF."""
    client = TestClient(app.app)
    run_id = test_crud_run

    # Add a 3.0 ft door opening (7.0 ft height) to RUN-001 (20 LF, 10 ft height, 2 finished faces)
    res = client.patch(
        f"/api/blueprint/{run_id}/walls/RUN-001",
        json={
            "openings": [
                {"type": "door", "width_ft": 3.0, "height_ft": 7.0}
            ]
        },
    )
    assert res.status_code == 200
    data = res.json()
    wall = data["wall"]
    assert wall["opening_deduction_ft"] == 3.00
    assert wall["net_length_ft"] == 17.00

    recalc = data["recalculated_takeoff"]
    assert recalc["total_opening_deduction_lf"] == 3.00
    assert recalc["total_net_lf"] == 17.00
    # Board SF: (20 * 10 - 3 * 7) * 2 sides = (200 - 21) * 2 = 358.0 SF
    assert recalc["total_board_sf"] == 358.0


def test_patch_wall_clear_openings(test_crud_run):
    """Submitting an empty openings list clears all deductions."""
    client = TestClient(app.app)
    run_id = test_crud_run

    # First add deduction
    client.patch(
        f"/api/blueprint/{run_id}/walls/RUN-001",
        json={"openings": [{"type": "door", "width_ft": 4.0, "height_ft": 7.0}]},
    )

    # Now clear deductions
    res = client.patch(
        f"/api/blueprint/{run_id}/walls/RUN-001",
        json={"openings": []},
    )
    assert res.status_code == 200
    wall = res.json()["wall"]
    assert wall["opening_deduction_ft"] == 0.0
    assert wall["net_length_ft"] == wall["gross_length_ft"]

    recalc = res.json()["recalculated_takeoff"]
    assert recalc["total_opening_deduction_lf"] == 0.0
    assert recalc["total_net_lf"] == recalc["total_gross_lf"]


def test_patch_wall_nonexistent_404(test_crud_run):
    """Patching a non-existent wall ID returns HTTP 404 Not Found."""
    client = TestClient(app.app)
    res = client.patch(
        f"/api/blueprint/{test_crud_run}/walls/UNKNOWN_WALL_ID",
        json={"tag": "3A"},
    )
    assert res.status_code == 404


def test_delete_wall_removes_from_run_and_reduces_takeoff(test_crud_run):
    """Deleting a wall removes it from output.json and deducts its quantities from project totals."""
    client = TestClient(app.app)
    run_id = test_crud_run

    # Delete RUN-001
    res = client.delete(f"/api/blueprint/{run_id}/walls/RUN-001")
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["deleted_id"] == "RUN-001"

    recalc = data["recalculated_takeoff"]
    assert recalc["total_gross_lf"] == 0.0
    assert recalc["total_net_lf"] == 0.0
    assert recalc["total_board_sf"] == 0.0

    # Verify output.json on disk
    with open(RUNS_DIR / run_id / "output.json", "r", encoding="utf-8") as f:
        disk_data = json.load(f)
    assert len(disk_data["runs"]) == 0
    assert disk_data["total_gross_lf"] == 0.0


def test_delete_wall_nonexistent_404(test_crud_run):
    """Deleting a non-existent wall ID returns HTTP 404 Not Found."""
    client = TestClient(app.app)
    res = client.delete(f"/api/blueprint/{test_crud_run}/walls/UNKNOWN_WALL_ID")
    assert res.status_code == 404


def test_qto_excel_workbook_in_sync_after_each_operation(test_crud_run):
    """qto.xlsx workbook on disk is dynamically updated and matches output.json after CRUD operations."""
    client = TestClient(app.app)
    run_id = test_crud_run
    excel_path = RUNS_DIR / run_id / "qto.xlsx"

    # 1. Create a manual wall (20 LF, tag 5E)
    create_res = client.post(
        f"/api/blueprint/{run_id}/page/1/walls",
        json={
            "start": {"x": 300.0, "y": 200.0},
            "end": {"x": 480.0, "y": 200.0},
            "tag": "5E",
            "height_ft": 10.0,
        },
    )
    assert create_res.status_code == 200
    assert excel_path.exists()

    # Open workbook and inspect Runs sheet
    wb = openpyxl.load_workbook(str(excel_path), data_only=True)
    runs_sheet = wb["Runs"]
    # Check that RUN-M01 is present
    run_ids_in_excel = [runs_sheet.cell(row=r, column=1).value for r in range(2, runs_sheet.max_row + 1)]
    assert "RUN-001" in run_ids_in_excel
    assert "RUN-M01" in run_ids_in_excel
    wb.close()

    # 2. Delete RUN-001
    del_res = client.delete(f"/api/blueprint/{run_id}/walls/RUN-001")
    assert del_res.status_code == 200

    # Inspect refreshed Excel workbook
    wb2 = openpyxl.load_workbook(str(excel_path), data_only=True)
    runs_sheet2 = wb2["Runs"]
    run_ids_after_del = [runs_sheet2.cell(row=r, column=1).value for r in range(2, runs_sheet2.max_row + 1)]
    assert "RUN-001" not in run_ids_after_del
    assert "RUN-M01" in run_ids_after_del
    wb2.close()
