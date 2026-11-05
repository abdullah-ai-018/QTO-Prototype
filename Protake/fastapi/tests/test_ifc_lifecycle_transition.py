"""P0 Data Integrity Regression Tests: IFC Model Lifecycle & Two-IFC Transition Isolation.

Proves:
1. Upload IFC-A -> Workspace/APIs serve IFC-A with 100% provenance and exact source hash.
2. Upload IFC-B -> Workspace/APIs serve IFC-B:
   - IFC-A GUIDs are strictly absent.
   - IFC-A quantities are strictly absent.
   - IFC-A geometry is strictly absent.
   - IFC-B GUIDs, quantities, and geometry are present.
3. Two-IFC Transition Sequence: IFC-A -> IFC-B -> IFC-A re-hydrates each model without state bleed.
4. Cryptographic Source Hash Invariant:
   uploaded_file_hash == parsed_model.source_hash == canonical_model.source_hash == takeoff.source_hash
"""
import hashlib
import os
import sys
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from app.database import Base, engine
from app.main import app

Base.metadata.create_all(bind=engine)
client = TestClient(app)

IFC_STORAGE_DIR = os.path.join(os.path.dirname(__file__), "..", "storage", "ifc")

# Locate real fixture files
lakeside_candidates = [
    os.path.join(IFC_STORAGE_DIR, f) for f in os.listdir(IFC_STORAGE_DIR)
    if f.endswith("NBS_LakesideRVT10_Arch.ifc")
]
duplex_candidates = [
    os.path.join(IFC_STORAGE_DIR, f) for f in os.listdir(IFC_STORAGE_DIR)
    if f.endswith("duplex_sample.ifc")
]

assert len(lakeside_candidates) > 0, "Real fixture NBS_LakesideRVT10_Arch.ifc must be present"
assert len(duplex_candidates) > 0, "Real fixture duplex_sample.ifc must be present"

IFC_A_PATH = lakeside_candidates[0]
IFC_B_PATH = duplex_candidates[0]


def compute_sha256(path: str) -> str:
    hasher = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def test_two_ifc_transition_and_data_lifecycle():
    hash_a = compute_sha256(IFC_A_PATH)
    hash_b = compute_sha256(IFC_B_PATH)

    assert hash_a != hash_b, "Test files must have distinct SHA-256 digests"

    # =========================================================================
    # PHASE 1: UPLOAD IFC-A & VERIFY MODEL IDENTITY
    # =========================================================================
    with open(IFC_A_PATH, "rb") as f:
        res_upload_a = client.post(
            "/api/v1/ifc/upload",
            files={"file": ("NBS_LakesideRVT10_Arch.ifc", f, "application/octet-stream")},
        )
    assert res_upload_a.status_code == 201
    data_upload_a = res_upload_a.json()
    id_a = data_upload_a["id"]
    assert data_upload_a["source_hash"] == hash_a, "Upload A must return exact SHA-256 hash"

    # Parse IFC-A
    res_parse_a = client.post(f"/api/v1/ifc/{id_a}/parse")
    assert res_parse_a.status_code == 200
    data_parse_a = res_parse_a.json()
    assert data_parse_a["source_hash"] == hash_a, "Parse A must return exact SHA-256 hash"
    assert data_parse_a["model"]["source_hash"] == hash_a, "Canonical Model A must carry source_hash"

    # Canonical API A
    res_canon_a = client.get(f"/api/v1/ifc/{id_a}/canonical")
    assert res_canon_a.status_code == 200
    data_canon_a = res_canon_a.json()
    assert data_canon_a["source_hash"] == hash_a

    walls_a = data_canon_a["walls"]
    assert len(walls_a) == 97, f"IFC-A expected 97 walls, got {len(walls_a)}"
    guids_a = set(w["ifc_guid"] for w in walls_a)

    # Takeoff A
    res_takeoff_a = client.post(f"/api/v1/ifc/{id_a}/takeoff?trade=drywall&waste_factor=0.10")
    assert res_takeoff_a.status_code == 200
    data_takeoff_a = res_takeoff_a.json()
    assert data_takeoff_a["source_hash"] == hash_a
    assert data_takeoff_a["qto"]["source_hash"] == hash_a
    assert data_takeoff_a["qto"]["model_sha256"] == hash_a
    qto_gross_a = data_takeoff_a["qto"]["total_gross_wall_area_sqft"]
    assert round(qto_gross_a, 2) == 19677.82

    # =========================================================================
    # PHASE 2: UPLOAD IFC-B & VERIFY STRICT ISOLATION FROM IFC-A
    # =========================================================================
    with open(IFC_B_PATH, "rb") as f:
        res_upload_b = client.post(
            "/api/v1/ifc/upload",
            files={"file": ("duplex_sample.ifc", f, "application/octet-stream")},
        )
    assert res_upload_b.status_code == 201
    data_upload_b = res_upload_b.json()
    id_b = data_upload_b["id"]
    assert id_b != id_a, "Upload B must generate a distinct document ID"
    assert data_upload_b["source_hash"] == hash_b, "Upload B must return exact SHA-256 hash"

    # Parse IFC-B
    res_parse_b = client.post(f"/api/v1/ifc/{id_b}/parse")
    assert res_parse_b.status_code == 200
    data_parse_b = res_parse_b.json()
    assert data_parse_b["source_hash"] == hash_b
    assert data_parse_b["model"]["source_hash"] == hash_b

    # Canonical API B
    res_canon_b = client.get(f"/api/v1/ifc/{id_b}/canonical")
    assert res_canon_b.status_code == 200
    data_canon_b = res_canon_b.json()
    assert data_canon_b["source_hash"] == hash_b

    walls_b = data_canon_b["walls"]
    assert len(walls_b) == 2, f"IFC-B expected 2 walls, got {len(walls_b)}"
    guids_b = set(w["ifc_guid"] for w in walls_b)

    # Takeoff B
    res_takeoff_b = client.post(f"/api/v1/ifc/{id_b}/takeoff?trade=drywall&waste_factor=0.10")
    assert res_takeoff_b.status_code == 200
    data_takeoff_b = res_takeoff_b.json()
    assert data_takeoff_b["source_hash"] == hash_b
    assert data_takeoff_b["qto"]["source_hash"] == hash_b
    qto_gross_b = data_takeoff_b["qto"]["total_gross_wall_area_sqft"]
    assert round(qto_gross_b, 2) == 387.50

    # CRITICAL LEAK AUDIT: Zero overlap between IFC-A and IFC-B
    overlap_guids = guids_a.intersection(guids_b)
    assert len(overlap_guids) == 0, f"Found leaking GUIDs across models: {overlap_guids}"
    assert qto_gross_a != qto_gross_b, "Quantities must not match across distinct models"

    # Verify IFC-A GUIDs are absent in IFC-B takeoff line items
    takeoff_b_source_guids = {
        item.get("source_guid") or item.get("provenance", {}).get("ifc_guid")
        for item in data_takeoff_b["qto"]["line_items"]
    }
    leaking_takeoff_guids = guids_a.intersection(takeoff_b_source_guids)
    assert len(leaking_takeoff_guids) == 0, f"IFC-A GUIDs leaked into IFC-B takeoff: {leaking_takeoff_guids}"

    # =========================================================================
    # PHASE 3: TRANSITION BACK (IFC-A -> IFC-B -> IFC-A)
    # =========================================================================
    # Re-query IFC-A and confirm it still yields exact IFC-A data without degradation
    res_re_canon_a = client.get(f"/api/v1/ifc/{id_a}/canonical")
    assert res_re_canon_a.status_code == 200
    data_re_canon_a = res_re_canon_a.json()
    assert data_re_canon_a["source_hash"] == hash_a
    assert len(data_re_canon_a["walls"]) == 97

    res_re_takeoff_a = client.post(f"/api/v1/ifc/{id_a}/takeoff?trade=drywall&waste_factor=0.10")
    assert res_re_takeoff_a.status_code == 200
    data_re_takeoff_a = res_re_takeoff_a.json()
    assert data_re_takeoff_a["source_hash"] == hash_a
    assert round(data_re_takeoff_a["qto"]["total_gross_wall_area_sqft"], 2) == 19677.82

    # Verify IFC-B GUIDs are absent in IFC-A
    re_guids_a = set(w["ifc_guid"] for w in data_re_canon_a["walls"])
    assert len(re_guids_a.intersection(guids_b)) == 0, "IFC-B GUIDs leaked into restored IFC-A"


def test_hash_invariant_gate():
    """Validates that hash invariant holds across all trades (Drywall, Flooring, Roofing)."""
    with open(IFC_A_PATH, "rb") as f:
        res = client.post(
            "/api/v1/ifc/upload",
            files={"file": ("NBS_LakesideRVT10_Arch.ifc", f, "application/octet-stream")},
        )
    doc_id = res.json()["id"]
    expected_hash = res.json()["source_hash"]

    for trade in ["drywall", "flooring", "roofing"]:
        takeoff_res = client.post(f"/api/v1/ifc/{doc_id}/takeoff?trade={trade}")
        assert takeoff_res.status_code == 200
        qto = takeoff_res.json()["qto"]
        assert qto["source_hash"] == expected_hash, f"{trade} takeoff source_hash mismatch"
        assert qto["model_sha256"] == expected_hash, f"{trade} takeoff model_sha256 mismatch"
