"""API Integration Tests for IFC Upload, Parse, Takeoff, and Export Endpoints."""
import io
import os
import sys
import tempfile
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from app.database import Base, engine
from app.main import app
from test_ifc_reader_and_normalizer import create_sample_test_ifc

# Ensure all tables exist in database
Base.metadata.create_all(bind=engine)

client = TestClient(app)


def test_ifc_full_api_workflow():
    """End-to-end integration test through FastAPI endpoints."""
    with tempfile.TemporaryDirectory() as tmpdir:
        sample_path = os.path.join(tmpdir, "duplex_sample.ifc")
        create_sample_test_ifc(sample_path)

        with open(sample_path, "rb") as f:
            file_bytes = f.read()

        # 1. Upload IFC
        response = client.post(
            "/api/v1/ifc/upload",
            files={"file": ("duplex_sample.ifc", file_bytes, "application/octet-stream")},
        )
        assert response.status_code == 201
        upload_data = response.json()
        doc_id = upload_data["id"]
        assert upload_data["status"] == "VALIDATED"
        assert upload_data["schema"] == "IFC4"

        # 2. Get Document Details
        res_get = client.get(f"/api/v1/ifc/{doc_id}")
        assert res_get.status_code == 200
        assert res_get.json()["filename"] == "duplex_sample.ifc"

        # 3. Parse and Normalize
        res_parse = client.post(f"/api/v1/ifc/{doc_id}/parse")
        assert res_parse.status_code == 200
        parse_data = res_parse.json()
        assert parse_data["status"] == "PARSED"
        assert parse_data["canonical_summary"]["total_walls"] == 2
        assert parse_data["canonical_summary"]["drywall_eligible_walls"] == 1

        # 4. Get Canonical Model
        res_canon = client.get(f"/api/v1/ifc/{doc_id}/canonical")
        assert res_canon.status_code == 200
        canon_data = res_canon.json()
        assert len(canon_data["walls"]) == 2
        wall1 = next(w for w in canon_data["walls"] if "W-101" in w["name"])
        wall1_guid = wall1["ifc_guid"]

        # 5. Calculate Takeoff
        res_takeoff = client.post(f"/api/v1/ifc/{doc_id}/takeoff?waste_factor=0.10")
        assert res_takeoff.status_code == 200
        qto_data = res_takeoff.json()
        assert qto_data["status"] == "TAKEOFF_COMPLETED"
        assert qto_data["qto"]["eligible_walls_count"] == 1
        assert qto_data["qto"]["excluded_walls_count"] == 1
        assert qto_data["qto"]["total_drywall_sheets_4x8"] > 0

        # 6. Inspect Wall Element with QTO Audit
        res_elem = client.get(f"/api/v1/ifc/{doc_id}/elements/{wall1_guid}")
        assert res_elem.status_code == 200
        elem_data = res_elem.json()
        assert elem_data["element_type"] == "WALL"
        assert elem_data["wall"]["ifc_guid"] == wall1_guid
        assert elem_data["qto_audit"]["source_guid"] == wall1_guid
        assert elem_data["qto_audit"]["provenance"]["status"] == "CONFIRMED"

        # 7. Export Excel BOQ
        res_export = client.get(f"/api/v1/ifc/{doc_id}/export/excel")
        assert res_export.status_code == 200
        assert "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" in res_export.headers["content-type"]
        assert len(res_export.content) > 1000  # Valid binary Excel payload
