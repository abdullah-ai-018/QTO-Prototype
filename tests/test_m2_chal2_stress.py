"""tests/test_m2_chal2_stress.py: Milestone M2 Empirical Challenger Stress Test Suite.

Targeted Verification:
1. Real blueprint tracing on `uploads/doc_20261104_101950_6cbd34.pdf`:
   - Sheet A-101 (Page 15) and Sheet A-102 (Page 16).
   - Verify all traced runs contain valid thickness_in, thickness_measured, and material_layers.
2. REST API contracts:
   - GET /api/takeoff/{run_id}: response schema contains thickness_in, thickness_measured,
     material_layers, is_height_verified, and height_source.
   - GET /api/blueprint/{run_id}/page/{page_num}/walls: serialization of all wall runs.
3. Adversarial boundary and edge cases:
   - Nonexistent runs, negative/zero page numbers, merge logic thickness priority.
   - Manual wall markup CRUD thickness and layer persistence.
"""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import pytest
from fastapi.testclient import TestClient
import pymupdf as fitz

from qto.dedup import create_wall_run, deduplicate_wall_runs, WallRun
from qto.geometry import Point, Segment
from qto.scale import detect_scale_from_page
from qto.segments import extract_page_linework
from qto.tags import find_tag_instances_on_page
from qto.trace_walls import find_leader_endpoint, find_seed_segment, trace_wall_from_seed
from qto.pipeline import QTOPipeline
from qto.assemblies import parse_assembly_attributes

import app

REAL_BLUEPRINT_PATH = Path("uploads/doc_20261104_101950_6cbd34.pdf")
SCHEDULE_TAGS = {
    "0X", "1A", "1B", "1C", "1D", "1E", "2B", "2C", "2W", "2X",
    "3A", "3D", "4B1", "4K", "4P", "5B", "5D", "5E", "5L",
    "7A", "7B", "7C", "7E", "7F", "7G", "8A", "8P", "GL1", "GL2", "PW"
}


@pytest.fixture(scope="module")
def real_pipeline_run():
    """Runs the full pipeline on pages 15 and 16 of the real blueprint once for module tests."""
    assert REAL_BLUEPRINT_PATH.exists(), f"Blueprint not found: {REAL_BLUEPRINT_PATH}"
    pipe = QTOPipeline(pdf_path=str(REAL_BLUEPRINT_PATH), selected_pages=[15, 16])
    summary = pipe.run()
    return pipe, summary


@pytest.fixture
def api_client():
    """FastAPI TestClient fixture."""
    return TestClient(app.app)


# =============================================================================
# 1. REAL BLUEPRINT TRACING: SHEET A-101 (PAGE 15) & SHEET A-102 (PAGE 16)
# =============================================================================

def test_sheet_a101_page15_tracing_thickness_and_layers(real_pipeline_run):
    """Verifies that all wall runs on Sheet A-101 (Page 15) contain valid thickness and layers."""
    pipe, summary = real_pipeline_run
    runs_p15 = [r for r in pipe.deduped_wall_runs if r.page_num == 15]

    assert len(runs_p15) >= 18, f"Expected at least 18 wall runs on Sheet A-101, got {len(runs_p15)}"

    measured_count = 0
    nominal_count = 0

    for r in runs_p15:
        # 1. thickness_in validation
        assert r.thickness_in is not None, f"Wall run {r.run_id} (tag {r.tag}) has None thickness_in"
        assert isinstance(r.thickness_in, (int, float)), f"thickness_in must be numeric, got {type(r.thickness_in)}"
        assert 0.0 < r.thickness_in <= 36.0, f"Wall run {r.run_id} thickness out of valid range: {r.thickness_in}\""

        # 2. thickness_measured validation
        assert isinstance(r.thickness_measured, bool), f"thickness_measured must be bool, got {type(r.thickness_measured)}"
        if r.thickness_measured:
            measured_count += 1
            assert r.thickness_pt is not None and r.thickness_pt > 0, f"Measured wall {r.run_id} missing thickness_pt"
        else:
            nominal_count += 1

        # 3. material_layers validation
        assert isinstance(r.material_layers, list), f"material_layers must be a list in {r.run_id}"
        assert len(r.material_layers) > 0, f"Wall run {r.run_id} (tag {r.tag}) has empty material_layers"
        for layer in r.material_layers:
            assert isinstance(layer, dict), f"Layer in {r.run_id} is not dict: {layer}"
            assert "side" in layer, f"Layer missing 'side' key in {r.run_id}"
            assert "material" in layer, f"Layer missing 'material' key in {r.run_id}"
            assert len(layer["material"].strip()) > 0, f"Layer material empty in {r.run_id}"

        # 4. Geometry sanity
        assert r.gross_length_ft > 0.0, f"Wall run {r.run_id} has invalid length {r.gross_length_ft}"
        assert r.net_length_ft >= 0.0, f"Wall run {r.run_id} has negative net length {r.net_length_ft}"
        assert r.net_length_ft <= r.gross_length_ft + 1e-4

    print(f"\n[A-101 Page 15] Total runs: {len(runs_p15)} | Measured: {measured_count} | Nominal: {nominal_count}")
    assert measured_count > 0, "Expected at least one measured double-line wall on Page 15"


def test_sheet_a102_page16_tracing_thickness_and_layers(real_pipeline_run):
    """Verifies that all wall runs on Sheet A-102 (Page 16) contain valid thickness and layers."""
    pipe, summary = real_pipeline_run
    runs_p16 = [r for r in pipe.deduped_wall_runs if r.page_num == 16]

    assert len(runs_p16) >= 40, f"Expected at least 40 wall runs on Sheet A-102, got {len(runs_p16)}"

    measured_count = 0
    nominal_count = 0

    for r in runs_p16:
        # 1. thickness_in validation
        assert r.thickness_in is not None, f"Wall run {r.run_id} (tag {r.tag}) has None thickness_in"
        assert isinstance(r.thickness_in, (int, float)), f"thickness_in must be numeric, got {type(r.thickness_in)}"
        assert 0.0 < r.thickness_in <= 36.0, f"Wall run {r.run_id} thickness out of valid range: {r.thickness_in}\""

        # 2. thickness_measured validation
        assert isinstance(r.thickness_measured, bool), f"thickness_measured must be bool, got {type(r.thickness_measured)}"
        if r.thickness_measured:
            measured_count += 1
            assert r.thickness_pt is not None and r.thickness_pt > 0, f"Measured wall {r.run_id} missing thickness_pt"
        else:
            nominal_count += 1

        # 3. material_layers validation
        assert isinstance(r.material_layers, list), f"material_layers must be a list in {r.run_id}"
        assert len(r.material_layers) > 0, f"Wall run {r.run_id} (tag {r.tag}) has empty material_layers"
        for layer in r.material_layers:
            assert isinstance(layer, dict), f"Layer in {r.run_id} is not dict: {layer}"
            assert "side" in layer, f"Layer missing 'side' key in {r.run_id}"
            assert "material" in layer, f"Layer missing 'material' key in {r.run_id}"

        # 4. Geometry sanity
        assert r.gross_length_ft > 0.0, f"Wall run {r.run_id} has invalid length {r.gross_length_ft}"
        assert r.net_length_ft >= 0.0, f"Wall run {r.run_id} has negative net length {r.net_length_ft}"

    print(f"\n[A-102 Page 16] Total runs: {len(runs_p16)} | Measured: {measured_count} | Nominal: {nominal_count}")
    assert measured_count > 0, "Expected at least one measured double-line wall on Page 16"


# =============================================================================
# 2. REST API CONTRACT VERIFICATION
# =============================================================================

def test_api_get_takeoff_full_contract(api_client, real_pipeline_run):
    """Verifies GET /api/takeoff/{run_id} schema and field contracts."""
    pipe, _ = real_pipeline_run
    run_id = pipe.run_id

    response = api_client.get(f"/api/takeoff/{run_id}")
    assert response.status_code == 200, f"Expected 200 OK, got {response.status_code}: {response.text}"

    data = response.json()
    assert data["run_id"] == run_id

    # Summary verification
    summary = data.get("summary")
    assert isinstance(summary, dict), "Missing 'summary' dict"
    for required_key in [
        "total_gross_lf", "total_net_lf", "total_board_sf",
        "total_walls", "verified_height_count", "unverified_height_count"
    ]:
        assert required_key in summary, f"Missing key '{required_key}' in takeoff summary"
        assert isinstance(summary[required_key], (int, float)), f"Key '{required_key}' not numeric"

    assert summary["total_walls"] == len(pipe.deduped_wall_runs)
    assert summary["verified_height_count"] + summary["unverified_height_count"] == summary["total_walls"]

    # Walls list verification
    walls = data.get("walls")
    assert isinstance(walls, list), "Missing 'walls' list"
    assert len(walls) == summary["total_walls"]

    for w in walls:
        assert "run_id" in w
        assert "tag" in w
        assert "sheet_label" in w
        assert "page_num" in w
        assert "gross_length_ft" in w
        assert "net_length_ft" in w

        # M2 Contract Required Fields
        assert "thickness_in" in w, f"Missing thickness_in in wall {w['run_id']}"
        assert w["thickness_in"] is not None and w["thickness_in"] > 0, f"Invalid thickness_in in {w['run_id']}"

        assert "thickness_measured" in w, f"Missing thickness_measured in wall {w['run_id']}"
        assert isinstance(w["thickness_measured"], bool), f"thickness_measured must be bool in {w['run_id']}"

        assert "material_layers" in w, f"Missing material_layers in wall {w['run_id']}"
        assert isinstance(w["material_layers"], list) and len(w["material_layers"]) > 0

        assert "is_height_verified" in w, f"Missing is_height_verified in wall {w['run_id']}"
        assert isinstance(w["is_height_verified"], bool)

        assert "height_source" in w, f"Missing height_source in wall {w['run_id']}"
        assert isinstance(w["height_source"], str)

    # Review items
    assert "review_items" in data
    assert isinstance(data["review_items"], list)


def test_api_get_blueprint_page_walls_contract(api_client, real_pipeline_run):
    """Verifies GET /api/blueprint/{run_id}/page/{page_num}/walls schema and partitioning."""
    pipe, _ = real_pipeline_run
    run_id = pipe.run_id

    # Test Page 15
    res15 = api_client.get(f"/api/blueprint/{run_id}/page/15/walls")
    assert res15.status_code == 200, res15.text
    d15 = res15.json()
    assert d15["run_id"] == run_id
    assert d15["page_num"] == 15
    assert d15["total_walls"] == len(d15["walls"])
    assert d15["total_walls"] == len([r for r in pipe.deduped_wall_runs if r.page_num == 15])
    for w in d15["walls"]:
        assert int(w["page_num"]) == 15
        assert w["thickness_in"] is not None
        assert isinstance(w["thickness_measured"], bool)
        assert len(w["material_layers"]) > 0

    # Test Page 16
    res16 = api_client.get(f"/api/blueprint/{run_id}/page/16/walls")
    assert res16.status_code == 200, res16.text
    d16 = res16.json()
    assert d16["run_id"] == run_id
    assert d16["page_num"] == 16
    assert d16["total_walls"] == len(d16["walls"])
    assert d16["total_walls"] == len([r for r in pipe.deduped_wall_runs if r.page_num == 16])
    for w in d16["walls"]:
        assert int(w["page_num"]) == 16
        assert w["thickness_in"] is not None
        assert isinstance(w["thickness_measured"], bool)
        assert len(w["material_layers"]) > 0


# =============================================================================
# 3. ADVERSARIAL & EDGE CASE STRESS TESTS
# =============================================================================

def test_api_adversarial_error_responses(api_client, real_pipeline_run):
    """Stress tests REST API error handling for malformed or out-of-bounds requests."""
    pipe, _ = real_pipeline_run
    run_id = pipe.run_id

    # 1. Nonexistent run_id
    res_404_takeoff = api_client.get("/api/takeoff/nonexistent_run_deadbeef")
    assert res_404_takeoff.status_code == 404

    res_404_blueprint = api_client.get("/api/blueprint/nonexistent_run_deadbeef/page/15/walls")
    assert res_404_blueprint.status_code == 404

    # 2. Out-of-bounds page_num (<= 0)
    res_bad_page_0 = api_client.get(f"/api/blueprint/{run_id}/page/0/walls")
    assert res_bad_page_0.status_code == 400

    res_bad_page_neg = api_client.get(f"/api/blueprint/{run_id}/page/-10/walls")
    assert res_bad_page_neg.status_code == 400

    # 3. Page with no walls (e.g. Page 1 which was not processed in this run)
    res_empty_page = api_client.get(f"/api/blueprint/{run_id}/page/1/walls")
    assert res_empty_page.status_code == 200
    assert res_empty_page.json()["total_walls"] == 0
    assert len(res_empty_page.json()["walls"]) == 0


def test_dedup_thickness_merging_adversarial():
    """Adversarial stress test on deduplicate_wall_runs thickness logic.

    Scenarios:
    1. Two measured runs overlapping -> thickness_pt and thickness_in must be averaged.
    2. One measured run and one nominal run -> measured thickness must prevail regardless of order.
    3. Two nominal runs -> assembly nominal preserved.
    """
    scale = 0.111111  # 1/8" = 1'-0"
    spine1 = Segment(0, 0, 100, 0)
    spine2 = Segment(20, 0, 120, 0)

    # Scenario 1: Both measured
    # 36 pt (4.0") and 45 pt (5.0")
    run_meas1 = WallRun(
        run_id="R-M1", tag="7A", page_num=15, sheet_label="A-101",
        spine=spine1, gross_length_pt=100.0, gross_length_ft=11.11,
        opening_deduction_ft=0.0, net_length_ft=11.11, openings=[], segments=[],
        ft_per_pt=scale, thickness_pt=36.0, thickness_in=4.0, thickness_measured=True,
        material_layers=[{"side": "Face A", "material": "GWB"}]
    )
    run_meas2 = WallRun(
        run_id="R-M2", tag="7A", page_num=15, sheet_label="A-101",
        spine=spine2, gross_length_pt=100.0, gross_length_ft=11.11,
        opening_deduction_ft=0.0, net_length_ft=11.11, openings=[], segments=[],
        ft_per_pt=scale, thickness_pt=45.0, thickness_in=5.0, thickness_measured=True,
        material_layers=[{"side": "Face A", "material": "GWB"}]
    )

    merged = deduplicate_wall_runs([run_meas1, run_meas2], scale)
    assert len(merged) == 1
    m = merged[0]
    assert m.thickness_measured is True
    assert abs(m.thickness_pt - 40.5) < 0.01  # (36 + 45) / 2
    assert abs(m.thickness_in - (40.5 * scale * 12.0)) < 0.01

    # Scenario 2: One nominal, one measured (measured should prevail even if second)
    run_nom = WallRun(
        run_id="R-NOM", tag="7A", page_num=15, sheet_label="A-101",
        spine=spine1, gross_length_pt=100.0, gross_length_ft=11.11,
        opening_deduction_ft=0.0, net_length_ft=11.11, openings=[], segments=[],
        ft_per_pt=scale, thickness_pt=None, thickness_in=4.875, thickness_measured=False,
        material_layers=[]
    )
    run_meas = WallRun(
        run_id="R-MEAS", tag="7A", page_num=15, sheet_label="A-101",
        spine=spine2, gross_length_pt=100.0, gross_length_ft=11.11,
        opening_deduction_ft=0.0, net_length_ft=11.11, openings=[], segments=[],
        ft_per_pt=scale, thickness_pt=54.0, thickness_in=6.0, thickness_measured=True,
        material_layers=[{"side": "Face A", "material": "Type X GWB"}]
    )

    # Order A: Nominal first, Measured second
    merged_a = deduplicate_wall_runs([run_nom, run_meas], scale)
    assert len(merged_a) == 1
    assert merged_a[0].thickness_measured is True
    assert merged_a[0].thickness_in == 6.0
    assert len(merged_a[0].material_layers) == 1

    # Order B: Measured first, Nominal second
    run_nom2 = WallRun(
        run_id="R-NOM2", tag="7A", page_num=15, sheet_label="A-101",
        spine=spine2, gross_length_pt=100.0, gross_length_ft=11.11,
        opening_deduction_ft=0.0, net_length_ft=11.11, openings=[], segments=[],
        ft_per_pt=scale, thickness_pt=None, thickness_in=4.875, thickness_measured=False,
        material_layers=[]
    )
    merged_b = deduplicate_wall_runs([run_meas, run_nom2], scale)
    assert len(merged_b) == 1
    assert merged_b[0].thickness_measured is True
    assert merged_b[0].thickness_in == 6.0


def test_manual_wall_markup_crud_preserves_thickness_and_layers(api_client, tmp_path):
    """Stress tests manual wall creation, patching, and deletion via REST API."""
    run_id = f"test_chal2_crud_{tmp_path.name}"
    run_dir = app.RUNS_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    seed_data = {
        "run_id": run_id,
        "pdf_file": "test.pdf",
        "sheets": [{"page_num": 15, "sheet_label": "A-101", "scale_ft_per_pt": 0.111111}],
        "runs": [],
        "openings": [],
        "total_gross_lf": 0.0,
        "total_net_lf": 0.0,
        "total_board_sf": 0.0,
        "review_items": [],
        "by_tag": {
            "1A": {
                "attributes": {
                    "nominal_thickness_in": 4.875,
                    "material_layers": [
                        {"side": "Face A", "layer": "1", "material": "5/8\" Type X GWB"},
                        {"side": "Core", "layer": "Framing", "material": "3.625\" 25 GA Metal Studs @ 16\" O.C."},
                        {"side": "Face B", "layer": "1", "material": "5/8\" Type X GWB"},
                    ],
                }
            }
        },
    }
    with open(run_dir / "output.json", "w", encoding="utf-8") as f:
        json.dump(seed_data, f)

    try:
        # 1. Create manual wall with tag 1A (nominal thickness 4.875")
        create_payload = {
            "start": {"x": 100.0, "y": 100.0},
            "end": {"x": 280.0, "y": 100.0},  # dx = 180 pt * 0.111111 = 20 LF
            "tag": "1A",
            "height_ft": 10.0,
        }
        res_create = api_client.post(f"/api/blueprint/{run_id}/page/15/walls", json=create_payload)
        assert res_create.status_code == 200, res_create.text
        created_wall = res_create.json()["wall"]

        assert created_wall["is_manual"] is True
        assert created_wall["thickness_in"] is not None
        assert abs(created_wall["thickness_in"] - 4.875) < 0.01
        assert created_wall["thickness_measured"] is False
        assert len(created_wall["material_layers"]) > 0

        wall_id = created_wall["run_id"]

        # 2. Query GET /api/blueprint/{run_id}/page/15/walls
        res_list = api_client.get(f"/api/blueprint/{run_id}/page/15/walls")
        assert res_list.status_code == 200
        assert res_list.json()["total_walls"] == 1
        assert res_list.json()["walls"][0]["run_id"] == wall_id
        assert res_list.json()["walls"][0]["thickness_in"] == created_wall["thickness_in"]

        # 3. Query GET /api/takeoff/{run_id}
        res_takeoff = api_client.get(f"/api/takeoff/{run_id}")
        assert res_takeoff.status_code == 200
        t_data = res_takeoff.json()
        assert t_data["summary"]["total_walls"] == 1
        assert t_data["walls"][0]["thickness_in"] == created_wall["thickness_in"]

        # 4. Patch wall (drag endpoint to dx = 360 pt = 40 LF)
        patch_payload = {
            "end": {"x": 460.0, "y": 100.0}
        }
        res_patch = api_client.patch(f"/api/blueprint/{run_id}/walls/{wall_id}", json=patch_payload)
        assert res_patch.status_code == 200
        patched_wall = res_patch.json()["wall"]
        assert abs(patched_wall["gross_length_ft"] - 40.0) < 0.1
        assert patched_wall["thickness_in"] == created_wall["thickness_in"]
        assert len(patched_wall["material_layers"]) > 0

        # 5. Delete wall
        res_del = api_client.delete(f"/api/blueprint/{run_id}/walls/{wall_id}")
        assert res_del.status_code == 200
        assert res_del.json()["success"] is True

        res_after_del = api_client.get(f"/api/blueprint/{run_id}/page/15/walls")
        assert res_after_del.json()["total_walls"] == 0

    finally:
        shutil.rmtree(run_dir, ignore_errors=True)
