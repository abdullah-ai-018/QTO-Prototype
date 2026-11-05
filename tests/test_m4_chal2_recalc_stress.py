"""tests/test_m4_chal2_recalc_stress.py: Milestone 4 Dynamic Recalculation Adversarial Stress Suite.

Challenger: m4_it1_chal2 (Empirical Challenger - critic, specialist)
Milestone: M4 (Takeoff Schedule Dock, UI Inspector & Workbench Integration — R3, R4, R5, F11-F14)

Battery of Adversarial Challenges:
1. Dynamic State Transition & Review Item Clearing:
   - POST /api/runs/update transitions wall from REVIEW to OK.
   - Decrements unverified_height_count, increments verified_height_count.
   - Dynamically removes verified wall from review_items list while preserving unrelated review items.
   - POST /api/blueprint/{run_id}/walls/{wall_id} route equivalence.
2. Reverse Transition Stress:
   - Setting is_height_verified=False explicitly transitions wall from OK to REVIEW.
   - Increments unverified_height_count and regenerates review item.
3. Input Validation Boundary Conditions (HTTP 422 & HTTP 400):
   - Zero height (height_ft = 0.0) -> HTTP 422.
   - Negative height (height_ft = -5.0) -> HTTP 422.
   - Non-numeric height (height_ft = "invalid") -> HTTP 422.
   - Zero/negative thickness (thickness_in <= 0) -> HTTP 422.
   - Verification that 422 errors do not corrupt or alter run state on disk.
4. Non-Existent Entity Handling (HTTP 404):
   - Non-existent run_id on POST /api/runs/update -> HTTP 404.
   - Non-existent wall_id on POST /api/runs/update -> HTTP 404.
   - Non-existent run_id on POST /api/blueprint/{run_id}/walls/{wall_id} -> HTTP 404.
   - Non-existent wall_id on POST /api/blueprint/{run_id}/walls/{wall_id} -> HTTP 404.
   - Non-existent wall_id on DELETE /api/blueprint/{run_id}/walls/{wall_id} -> HTTP 404.
5. Opening Deduction Recalculation Stress:
   - Multiple openings deduction (doors + windows) with exact mathematical net LF & board SF.
   - Opening deduction exceeding gross length clamps net LF and board SF to >= 0.0.
   - Zero and negative opening dimensions return HTTP 400.
6. Synchronized Selection/Deselection Architecture:
   - Contract verification of viewer.js deselectWall() calling onWallSelected(null).
   - Contract verification of app.js handling null wall by resetting inspector and clearing row highlights.
   - Contract verification of selection triggering inspector population and row highlight.
7. Rapid Sequential Mutating Pipeline Stress:
   - Chain of height, tag, thickness, opening, and endpoint edits.
   - Verification that output.json and qto.xlsx remain in complete mathematical agreement.
"""

import json
from pathlib import Path
import openpyxl
import pytest
from fastapi.testclient import TestClient

import app

ROOT_DIR = Path(__file__).resolve().parent.parent
RUNS_DIR = getattr(app, "RUNS_DIR", ROOT_DIR / "runs")


@pytest.fixture
def chal2_stress_run(tmp_path):
    """Creates an isolated test run with 1 verified wall and 2 unverified review walls."""
    run_id = f"test_chal2_{tmp_path.name}"
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
        "total_wall_runs": 3,
        "total_openings_deducted": 0,
        "verified_height_count": 1,
        "unverified_height_count": 2,
        "total_gross_lf": 60.0,
        "total_opening_deduction_lf": 0.0,
        "total_net_lf": 60.0,
        "total_board_sf": 1120.0,
        "total_studs_ea": 48,
        "total_stud_lf": 448.0,
        "total_track_lf": 120.0,
        "sheets": [
            {
                "page_num": 1,
                "sheet_label": "A-101",
                "page_type": "FLOOR_PLAN",
                "scale_string": '1/8" = 1\'-0"',
                "scale_status": "CALIBRATED",
                "ft_per_pt": 0.111111,
            }
        ],
        "by_tag": {
            "7A": {
                "tag": "7A",
                "description": "Partition Tag 7A",
                "height_ft": 8.0,
                "faces": 2,
                "layers_per_face": 1,
                "stud_spacing_in": 16,
                "attributes": {
                    "nominal_thickness_in": 4.875,
                    "material_layers": [
                        {"side": "Face A", "material": '5/8" Type X GWB'},
                        {"side": "Core", "material": '3-5/8" Metal Studs'},
                        {"side": "Face B", "material": '5/8" Type X GWB'},
                    ],
                },
            },
            "5E": {
                "tag": "5E",
                "description": "Partition Tag 5E",
                "height_ft": 10.0,
                "faces": 2,
                "layers_per_face": 1,
                "stud_spacing_in": 16,
                "attributes": {
                    "nominal_thickness_in": 8.5,
                    "material_layers": [
                        {"side": "Face A", "material": '5/8" Type X GWB'},
                        {"side": "Core", "material": '6" Metal Studs'},
                        {"side": "Face B", "material": '5/8" Type X GWB'},
                    ],
                },
            },
            "3C": {
                "tag": "3C",
                "description": "Partition Tag 3C",
                "height_ft": 10.0,
                "faces": 2,
                "layers_per_face": 1,
                "stud_spacing_in": 16,
                "attributes": {
                    "nominal_thickness_in": 5.0,
                    "material_layers": [
                        {"side": "Face A", "material": '1/2" Regular GWB'},
                        {"side": "Core", "material": '3-5/8" Metal Studs'},
                        {"side": "Face B", "material": '1/2" Regular GWB'},
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
                    {"side": "Face A", "material": '5/8" Type X GWB'},
                    {"side": "Core", "material": '3-5/8" Metal Studs'},
                    {"side": "Face B", "material": '5/8" Type X GWB'},
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
                    {"side": "Face A", "material": '5/8" Type X GWB'},
                    {"side": "Core", "material": '6" Metal Studs'},
                    {"side": "Face B", "material": '5/8" Type X GWB'},
                ],
                "notes": ["Unverified wall height for Tag 5E: No section callout found on floor plan."],
            },
            {
                "run_id": "RUN-003",
                "tag": "3C",
                "page_num": 1,
                "sheet_label": "A-101",
                "spine": {"x1": 100.0, "y1": 400.0, "x2": 280.0, "y2": 400.0},
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
                "thickness_in": 5.0,
                "thickness_measured": False,
                "section_callout_tag": None,
                "is_height_verified": False,
                "height_source": "UNVERIFIED_HEIGHT_DEFAULT",
                "material_layers": [
                    {"side": "Face A", "material": '1/2" Regular GWB'},
                    {"side": "Core", "material": '3-5/8" Metal Studs'},
                    {"side": "Face B", "material": '1/2" Regular GWB'},
                ],
                "notes": ["Unverified wall height for Tag 3C: No section callout found on floor plan."],
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
                "issue": "Unverified wall height for Tag 5E: No section callout found on floor plan.",
                "description": "Unverified wall height for Tag 5E: No section callout found on floor plan.",
                "action_required": "Estimator review required.",
                "required_action": "Estimator review required.",
                "measured_values": "Default Height: 10.00 ft | Gross: 20.00 LF",
            },
            {
                "run_id": "RUN-003",
                "target_id": "RUN-003",
                "review_id": "REV-HGT-RUN-003",
                "tag": "3C",
                "page": 1,
                "sheet": "A-101",
                "category": "Unverified Wall Height",
                "issue": "Unverified wall height for Tag 3C: No section callout found on floor plan.",
                "description": "Unverified wall height for Tag 3C: No section callout found on floor plan.",
                "action_required": "Estimator review required.",
                "required_action": "Estimator review required.",
                "measured_values": "Default Height: 10.00 ft | Gross: 20.00 LF",
            },
        ],
    }

    out_file = run_dir / "output.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(baseline_data, f, indent=2)

    app.recalculate_run_state(run_id, baseline_data)
    return run_id


# ==============================================================================
# 1. Dynamic State Transition & Review Item Clearing Tests
# ==============================================================================

def test_chal2_post_runs_update_transitions_review_to_ok_and_decrements_count(chal2_stress_run):
    """POST /api/runs/update transitions status to OK, decrements unverified count, and removes review item."""
    client = TestClient(app.app)

    # 1. Verify baseline state before update
    res_before = client.get(f"/api/takeoff/{chal2_stress_run}")
    assert res_before.status_code == 200
    summary_before = res_before.json()["summary"]
    assert summary_before["total_walls"] == 3
    assert summary_before["verified_height_count"] == 1
    assert summary_before["unverified_height_count"] == 2
    assert len(res_before.json()["review_items"]) == 2

    # 2. Update RUN-002 height via POST /api/runs/update
    res_update = client.post(
        "/api/runs/update",
        json={"run_id": chal2_stress_run, "wall_id": "RUN-002", "height_ft": 14.5},
    )
    assert res_update.status_code == 200
    data_update = res_update.json()

    # Wall object assertions
    wall = data_update["wall"]
    assert wall["run_id"] == "RUN-002"
    assert wall["height_ft"] == 14.5
    assert wall["is_height_verified"] is True
    assert wall["is_manual"] is True
    assert wall["height_source"] == "ESTIMATOR_VERIFIED"
    assert wall["status"] == "OK"

    # Recalculated takeoff summary assertions
    recalc = data_update["recalculated_takeoff"]
    assert recalc["verified_height_count"] == 2
    assert recalc["unverified_height_count"] == 1
    assert recalc["review_items_count"] == 1
    # Ensure remaining review item belongs exclusively to RUN-003
    assert len(recalc["review_items"]) == 1
    assert recalc["review_items"][0]["run_id"] == "RUN-003"

    # 3. Verify GET /api/takeoff persistence
    res_after = client.get(f"/api/takeoff/{chal2_stress_run}")
    data_after = res_after.json()
    assert data_after["summary"]["verified_height_count"] == 2
    assert data_after["summary"]["unverified_height_count"] == 1
    assert len(data_after["review_items"]) == 1
    assert data_after["review_items"][0]["run_id"] == "RUN-003"


def test_chal2_post_blueprint_walls_route_equivalence(chal2_stress_run):
    """POST /api/blueprint/{run_id}/walls/{wall_id} produces identical recalculations to /api/runs/update."""
    client = TestClient(app.app)

    # Update RUN-003 height via POST /api/blueprint/{run_id}/walls/{wall_id}
    res_post = client.post(
        f"/api/blueprint/{chal2_stress_run}/walls/RUN-003",
        json={"height_ft": 11.25},
    )
    assert res_post.status_code == 200
    data = res_post.json()

    wall = data["wall"]
    assert wall["run_id"] == "RUN-003"
    assert wall["height_ft"] == 11.25
    assert wall["is_height_verified"] is True
    assert wall["status"] == "OK"

    recalc = data["recalculated_takeoff"]
    assert recalc["verified_height_count"] == 2
    assert recalc["unverified_height_count"] == 1
    # Only RUN-002 should remain in review items
    assert len(recalc["review_items"]) == 1
    assert recalc["review_items"][0]["run_id"] == "RUN-002"


def test_chal2_sequential_clearing_all_review_items(chal2_stress_run):
    """Sequentially updating all unverified walls completely drains review_items to zero."""
    client = TestClient(app.app)

    # 1. Update RUN-002
    res1 = client.post(
        "/api/runs/update",
        json={"run_id": chal2_stress_run, "wall_id": "RUN-002", "height_ft": 9.0},
    )
    assert res1.status_code == 200
    assert res1.json()["recalculated_takeoff"]["unverified_height_count"] == 1

    # 2. Update RUN-003
    res2 = client.post(
        f"/api/blueprint/{chal2_stress_run}/walls/RUN-003",
        json={"height_ft": 10.0},
    )
    assert res2.status_code == 200
    recalc2 = res2.json()["recalculated_takeoff"]
    assert recalc2["verified_height_count"] == 3
    assert recalc2["unverified_height_count"] == 0
    assert recalc2["review_items_count"] == 0
    assert len(recalc2["review_items"]) == 0

    # 3. Verify Excel workbook state
    wb = openpyxl.load_workbook(open(RUNS_DIR / chal2_stress_run / "qto.xlsx", "rb"), data_only=True)
    ws_runs = wb["Runs"]
    headers = [ws_runs.cell(row=1, column=c).value for c in range(1, ws_runs.max_column + 1)]
    status_idx = headers.index("Status") + 1
    height_idx = headers.index("Height (ft)") + 1

    # Every wall row (rows 2, 3, 4) must now be OK
    for r in range(2, 5):
        assert ws_runs.cell(row=r, column=status_idx).value == "OK"
        assert ws_runs.cell(row=r, column=height_idx).value in (8.0, 9.0, 10.0)

    # Check Review Items sheet in workbook
    if "Review Items" in wb.sheetnames:
        ws_rev = wb["Review Items"]
        # Max row should be 1 (header only)
        assert ws_rev.max_row <= 1
    wb.close()


# ==============================================================================
# 2. Reverse State Transition Stress
# ==============================================================================

def test_chal2_reverse_transition_marking_wall_unverified(chal2_stress_run):
    """Explicitly setting is_height_verified=False transitions wall back to REVIEW and regenerates review item."""
    client = TestClient(app.app)

    # RUN-001 was originally verified (status OK). Estimator revokes verification.
    res = client.post(
        "/api/runs/update",
        json={"run_id": chal2_stress_run, "wall_id": "RUN-001", "is_height_verified": False},
    )
    assert res.status_code == 200
    wall = res.json()["wall"]
    assert wall["is_height_verified"] is False
    assert wall["status"] == "REVIEW"

    recalc = res.json()["recalculated_takeoff"]
    assert recalc["verified_height_count"] == 0
    assert recalc["unverified_height_count"] == 3
    assert recalc["review_items_count"] == 3

    # Ensure RUN-001 is now listed in review_items
    run_ids_in_review = [item["run_id"] for item in recalc["review_items"]]
    assert "RUN-001" in run_ids_in_review


# ==============================================================================
# 3. Input Validation Boundary Conditions (HTTP 422 & HTTP 400)
# ==============================================================================

@pytest.mark.parametrize("invalid_height", [0, 0.0, -0.001, -5.0, -100.0])
def test_chal2_height_validation_non_positive_returns_400_or_422(chal2_stress_run, invalid_height):
    """Zero or negative height values must be rejected with HTTP 400 (custom validation) or HTTP 422 (Pydantic)."""
    client = TestClient(app.app)

    # Test via POST /api/runs/update
    res1 = client.post(
        "/api/runs/update",
        json={"run_id": chal2_stress_run, "wall_id": "RUN-001", "height_ft": invalid_height},
    )
    assert res1.status_code in (400, 422), f"Expected 400 or 422 for height {invalid_height}, got {res1.status_code}"
    assert "positive" in str(res1.json().get("detail", "")).lower()

    # Test via POST /api/blueprint/{run_id}/walls/{wall_id}
    res2 = client.post(
        f"/api/blueprint/{chal2_stress_run}/walls/RUN-001",
        json={"height_ft": invalid_height},
    )
    assert res2.status_code in (400, 422), f"Expected 400 or 422 for height {invalid_height}, got {res2.status_code}"
    assert "positive" in str(res2.json().get("detail", "")).lower()


def test_chal2_height_validation_type_error_returns_422(chal2_stress_run):
    """Non-numeric string height must fail Pydantic validation with HTTP 422."""
    client = TestClient(app.app)
    res = client.post(
        "/api/runs/update",
        json={"run_id": chal2_stress_run, "wall_id": "RUN-001", "height_ft": "not_a_number"},
    )
    assert res.status_code == 422


@pytest.mark.parametrize("invalid_thick", [0, 0.0, -1.0, -4.875])
def test_chal2_thickness_validation_non_positive_returns_422(chal2_stress_run, invalid_thick):
    """Zero or negative thickness must fail validation with HTTP 422."""
    client = TestClient(app.app)
    res = client.post(
        "/api/runs/update",
        json={"run_id": chal2_stress_run, "wall_id": "RUN-001", "thickness_in": invalid_thick},
    )
    assert res.status_code == 422


def test_chal2_validation_failure_does_not_corrupt_disk_state(chal2_stress_run):
    """Validation errors must reject cleanly without mutating output.json."""
    client = TestClient(app.app)

    out_file = RUNS_DIR / chal2_stress_run / "output.json"
    with open(out_file, "r", encoding="utf-8") as f:
        data_before = json.load(f)

    # Attempt invalid update
    client.post(
        "/api/runs/update",
        json={"run_id": chal2_stress_run, "wall_id": "RUN-002", "height_ft": -10.0},
    )

    with open(out_file, "r", encoding="utf-8") as f:
        data_after = json.load(f)

    assert data_before["runs"] == data_after["runs"]
    assert data_before["total_board_sf"] == data_after["total_board_sf"]


# ==============================================================================
# 4. Non-Existent Entity Handling (HTTP 404)
# ==============================================================================

def test_chal2_non_existent_run_id_returns_404(chal2_stress_run):
    """Non-existent run_id returns HTTP 404 on all update endpoints."""
    client = TestClient(app.app)
    ghost_run = "non_existent_run_99999999"

    # POST /api/runs/update
    res1 = client.post(
        "/api/runs/update",
        json={"run_id": ghost_run, "wall_id": "RUN-001", "height_ft": 10.0},
    )
    assert res1.status_code == 404

    # POST /api/blueprint/{run_id}/walls/{wall_id}
    res2 = client.post(
        f"/api/blueprint/{ghost_run}/walls/RUN-001",
        json={"height_ft": 10.0},
    )
    assert res2.status_code == 404

    # GET /api/takeoff/{run_id}
    res3 = client.get(f"/api/takeoff/{ghost_run}")
    assert res3.status_code == 404


def test_chal2_non_existent_wall_id_returns_404(chal2_stress_run):
    """Non-existent wall_id returns HTTP 404 on update and delete."""
    client = TestClient(app.app)
    ghost_wall = "GHOST-WALL-XYZ"

    # POST /api/runs/update
    res1 = client.post(
        "/api/runs/update",
        json={"run_id": chal2_stress_run, "wall_id": ghost_wall, "height_ft": 10.0},
    )
    assert res1.status_code == 404

    # POST /api/blueprint/{run_id}/walls/{wall_id}
    res2 = client.post(
        f"/api/blueprint/{chal2_stress_run}/walls/{ghost_wall}",
        json={"height_ft": 10.0},
    )
    assert res2.status_code == 404

    # DELETE /api/blueprint/{run_id}/walls/{wall_id}
    res3 = client.delete(f"/api/blueprint/{chal2_stress_run}/walls/{ghost_wall}")
    assert res3.status_code == 404


# ==============================================================================
# 5. Opening Deduction Recalculation Stress
# ==============================================================================

def test_chal2_multi_opening_deduction_exact_mathematics(chal2_stress_run):
    """Multi-opening deductions recalculate net LF and board SF with mathematical precision."""
    client = TestClient(app.app)

    # RUN-001: Gross LF = 20.0, Height = 8.0, Tag = 7A (2 faces, 1 layer)
    # Gross SF = 20.0 * 8.0 * 2 = 320.0 SF
    # Add Door: 3.0 LF x 7.0 H = 21.0 SF * 2 faces = 42.0 SF deduction
    # Add Window: 5.0 LF x 4.0 H = 20.0 SF * 2 faces = 40.0 SF deduction
    # Total deduction LF = 8.0 LF -> Net LF = 12.0 LF
    # Total deduction SF = 82.0 SF -> Net Board SF for RUN-001 = 320.0 - 82.0 = 238.0 SF
    res = client.patch(
        f"/api/blueprint/{chal2_stress_run}/walls/RUN-001",
        json={
            "openings": [
                {"type": "door", "width_ft": 3.0, "height_ft": 7.0},
                {"type": "window", "width_ft": 5.0, "height_ft": 4.0},
            ]
        },
    )
    assert res.status_code == 200
    data = res.json()
    wall = data["wall"]
    assert wall["gross_length_ft"] == 20.0
    assert wall["opening_deduction_ft"] == 8.0
    assert wall["net_length_ft"] == 12.0
    assert len(wall["openings"]) == 2

    recalc = data["recalculated_takeoff"]
    # Total gross LF: 20 + 20 + 20 = 60.0 LF
    # Total net LF: 12 + 20 + 20 = 52.0 LF
    assert recalc["total_gross_lf"] == 60.0
    assert recalc["total_opening_deduction_lf"] == 8.0
    assert recalc["total_net_lf"] == 52.0

    # RUN-001 Board SF = 238.0 SF
    # RUN-002 Board SF = 20 * 10 * 2 = 400.0 SF
    # RUN-003 Board SF = 20 * 10 * 2 = 400.0 SF
    # Total board SF = 238.0 + 400.0 + 400.0 = 1038.0 SF
    assert recalc["total_board_sf"] == 1038.0


def test_chal2_opening_deduction_exceeding_gross_clamps_to_zero(chal2_stress_run):
    """Opening deduction wider than wall clamps net linear footage to 0.0 LF without crashing."""
    client = TestClient(app.app)

    # RUN-001 gross LF is 20.0. Inject a massive opening of 25.0 LF.
    res = client.patch(
        f"/api/blueprint/{chal2_stress_run}/walls/RUN-001",
        json={"openings": [{"type": "door", "width_ft": 25.0, "height_ft": 8.0}]},
    )
    assert res.status_code == 200
    wall = res.json()["wall"]
    assert wall["net_length_ft"] == 0.0

    recalc = res.json()["recalculated_takeoff"]
    assert recalc["total_net_lf"] == 40.0  # 0.0 + 20.0 + 20.0


@pytest.mark.parametrize("bad_w, bad_h", [(0, 7.0), (-1.0, 7.0), (3.0, 0), (3.0, -2.0)])
def test_chal2_opening_invalid_dimensions_returns_400(chal2_stress_run, bad_w, bad_h):
    """Openings with non-positive width or height return HTTP 400."""
    client = TestClient(app.app)
    res = client.patch(
        f"/api/blueprint/{chal2_stress_run}/walls/RUN-001",
        json={"openings": [{"type": "door", "width_ft": bad_w, "height_ft": bad_h}]},
    )
    assert res.status_code == 400


# ==============================================================================
# 6. Synchronized Selection and Deselection Architecture Tests
# ==============================================================================

def test_chal2_synchronized_selection_architecture_contracts():
    """Validates viewer.js and app.js contract integration for selection and deselection handling."""
    viewer_js_path = ROOT_DIR / "static" / "js" / "viewer.js"
    app_js_path = ROOT_DIR / "static" / "js" / "app.js"
    index_html_path = ROOT_DIR / "static" / "index.html"

    assert viewer_js_path.exists()
    assert app_js_path.exists()
    assert index_html_path.exists()

    viewer_js = viewer_js_path.read_text(encoding="utf-8")
    app_js = app_js_path.read_text(encoding="utf-8")
    index_html = index_html_path.read_text(encoding="utf-8")

    # Contract 1: viewer.js must notify caller with null on deselectWall()
    assert "deselectWall()" in viewer_js
    assert "this.onWallSelected(null)" in viewer_js

    # Contract 2: app.js onWallSelected callback handles both truthy wall and null wall
    assert "onWallSelected: (wall) =>" in app_js
    assert "resetInspector();" in app_js
    assert "highlightScheduleRow(null, false);" in app_js
    assert "populateInspector(wall);" in app_js
    assert "highlightScheduleRow(wall.run_id, true);" in app_js

    # Contract 3: index.html contains required CAD HUD and Inspector Banner structures
    assert 'id="cad-hover-hud"' in index_html
    assert 'id="inspector-review-banner"' in index_html
    assert 'id="inspector-verified-banner"' in index_html
    assert 'id="takeoffDock"' in index_html
    assert 'id="scheduleTable"' in index_html


# ==============================================================================
# 7. Rapid Sequential Mutating Pipeline Stress
# ==============================================================================

def test_chal2_rapid_sequential_mutations_pipeline_consistency(chal2_stress_run):
    """Rapid sequence of diverse mutations (height, tag, thickness, openings, endpoints) preserves integrity."""
    client = TestClient(app.app)

    # 1. Update height on RUN-002 (transitions to OK, decrements unverified)
    r1 = client.post(
        "/api/runs/update",
        json={"run_id": chal2_stress_run, "wall_id": "RUN-002", "height_ft": 12.0},
    )
    assert r1.status_code == 200
    assert r1.json()["wall"]["status"] == "OK"

    # 2. Update tag on RUN-002 from 5E to 7A
    r2 = client.post(
        f"/api/blueprint/{chal2_stress_run}/walls/RUN-002",
        json={"tag": "7A"},
    )
    assert r2.status_code == 200
    assert r2.json()["wall"]["tag"] == "7A"
    assert r2.json()["recalculated_takeoff"]["by_tag"]["7A"]["runs_count"] == 2

    # 3. Update thickness on RUN-002
    r3 = client.post(
        "/api/runs/update",
        json={"run_id": chal2_stress_run, "wall_id": "RUN-002", "thickness_in": 6.5, "thickness_measured": True},
    )
    assert r3.status_code == 200
    assert r3.json()["wall"]["thickness_in"] == 6.5
    assert r3.json()["wall"]["thickness_measured"] is True

    # 4. Add door opening on RUN-002
    r4 = client.patch(
        f"/api/blueprint/{chal2_stress_run}/walls/RUN-002",
        json={"openings": [{"type": "door", "width_ft": 4.0, "height_ft": 7.0}]},
    )
    assert r4.status_code == 200
    assert r4.json()["wall"]["net_length_ft"] == 16.0

    # 5. Drag endpoints of RUN-001 to extend by 90 pt (10 LF) -> gross 30.0 LF
    r5 = client.patch(
        f"/api/blueprint/{chal2_stress_run}/walls/RUN-001",
        json={"end": {"x": 370.0, "y": 100.0}},
    )
    assert r5.status_code == 200
    assert r5.json()["wall"]["gross_length_ft"] == 30.0

    # Final verification of disk persistence and Excel generation
    res_final = client.get(f"/api/takeoff/{chal2_stress_run}")
    assert res_final.status_code == 200
    final_data = res_final.json()

    # Total gross LF: 30 (RUN-001) + 20 (RUN-002) + 20 (RUN-003) = 70.0 LF
    # Total deduction LF: 4.0 LF
    # Total net LF: 66.0 LF
    summary = final_data["summary"]
    assert summary["total_gross_lf"] == 70.0
    assert summary["total_net_lf"] == 66.0
    assert summary["verified_height_count"] == 2
    assert summary["unverified_height_count"] == 1

    # Check Excel matches
    res_excel = client.get(f"/api/takeoff/{chal2_stress_run}/export/excel")
    assert res_excel.status_code == 200

    wb = openpyxl.load_workbook(open(RUNS_DIR / chal2_stress_run / "qto.xlsx", "rb"), data_only=True)
    ws_runs = wb["Runs"]
    headers = [ws_runs.cell(row=1, column=c).value for c in range(1, ws_runs.max_column + 1)]
    run_id_col = headers.index("Wall Run ID") + 1
    thick_col = headers.index("Thickness (in)") + 1
    net_col = headers.index("Net LF") + 1

    # Find RUN-002 row
    r002_row = None
    for r in range(2, ws_runs.max_row + 1):
        if ws_runs.cell(row=r, column=run_id_col).value == "RUN-002":
            r002_row = r
            break
    assert r002_row is not None
    assert ws_runs.cell(row=r002_row, column=thick_col).value == 6.5
    assert ws_runs.cell(row=r002_row, column=net_col).value == 16.0
    wb.close()
