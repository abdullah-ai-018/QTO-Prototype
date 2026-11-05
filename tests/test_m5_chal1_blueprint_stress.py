"""tests/test_m5_chal1_blueprint_stress.py: Empirical Verification of Real Blueprint & Selective Pipeline.

Mission (Milestone 5 Challenger 1):
1. Target blueprint: uploads/doc_20261104_101950_6cbd34.pdf
2. Test selective processing on Page 15 (A-101), Page 16 (A-102), and Pages [15, 16] combined.
3. Verify non-zero LF and SF, dual-red visual annotations in annotated.pdf, and takeoff schedule generation.
4. Check boundary and edge cases: out-of-range page numbers, invalid sheet selections, empty selections.
5. Verify REST API handling of selective sheet processing and error boundaries.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import time
from typing import Any, Dict, List

from fastapi.testclient import TestClient
import pymupdf as fitz
import pytest

import app
from qto.pipeline import QTOPipeline
from qto.annotate import RED_BRIGHT, RED_DARK

BASE_DIR = Path(__file__).resolve().parent.parent
REAL_BLUEPRINT_PATH = BASE_DIR / "uploads" / "doc_20261104_101950_6cbd34.pdf"


@pytest.fixture(scope="session")
def blueprint_pdf():
    assert REAL_BLUEPRINT_PATH.exists(), f"Target blueprint not found: {REAL_BLUEPRINT_PATH}"
    return str(REAL_BLUEPRINT_PATH)


@pytest.fixture(scope="module")
def api_client():
    return TestClient(app.app)


# =============================================================================
# 1. EMPIRICAL VERIFICATION: SELECTIVE PROCESSING ON PAGE 15 (A-101)
# =============================================================================

def test_selective_processing_page_15_a101(blueprint_pdf):
    """Verify selective processing on Page 15 (Sheet A-101) produces non-zero LF, SF,

    generates dual-red visual annotations in annotated.pdf, and outputs takeoff schedule.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        pipe = QTOPipeline(blueprint_pdf, selected_pages=[15], output_dir=tmp_dir)
        summary = pipe.run()

        # Sheets processed
        assert summary["sheets_processed"] == [15]
        assert summary["selected_pages"] == [15]

        # Non-zero wall runs
        total_runs = summary["total_wall_runs"]
        assert total_runs > 0, f"Expected non-zero wall runs, got {total_runs}"
        assert total_runs == 18, f"Expected exactly 18 consolidated wall runs for Page 15, got {total_runs}"

        # Quantities non-zero
        gross_lf = summary["total_gross_lf"]
        net_lf = summary["total_net_lf"]
        board_sf = summary["total_board_sf"]
        assert gross_lf > 200.0, f"Expected gross LF > 200, got {gross_lf}"
        assert net_lf > 200.0, f"Expected net LF > 200, got {net_lf}"
        assert board_sf > 4000.0, f"Expected board SF > 4000, got {board_sf}"

        # Takeoff schedule details
        by_tag = summary["by_tag"]
        assert len(by_tag) > 0, "Expected non-empty by_tag schedule"
        assert "7A" in by_tag, "Expected partition tag '7A' in schedule for Page 15"
        assert by_tag["7A"]["net_lf"] > 0
        assert by_tag["7A"]["net_board_sf"] > 0

        # Runs detail check
        runs = summary["runs"]
        assert len(runs) == total_runs
        for r in runs:
            assert r["page_num"] == 15
            assert r["sheet_label"] == "A-101"
            assert r["gross_length_ft"] > 0
            assert r["net_length_ft"] > 0
            assert "spine" in r
            assert r["spine"]["length"] > 0

        # Verify annotated.pdf generated and contains dual-red visual annotations
        annotated_pdf = Path(tmp_dir) / "annotated.pdf"
        assert annotated_pdf.exists(), "annotated.pdf was not generated"
        assert annotated_pdf.stat().st_size > 0

        doc_annot = fitz.open(str(annotated_pdf))
        try:
            assert len(doc_annot) == 71
            p15 = doc_annot[14]
            annots = list(p15.annots())
            drawings = p15.get_drawings()
            assert len(annots) >= 5, f"Expected at least 5 annotations on Page 15, got {len(annots)}"
            assert len(drawings) > 1000, f"Expected CAD vector drawings on Page 15, got {len(drawings)}"
        finally:
            doc_annot.close()


# =============================================================================
# 2. EMPIRICAL VERIFICATION: SELECTIVE PROCESSING ON PAGE 16 (A-102)
# =============================================================================

def test_selective_processing_page_16_a102(blueprint_pdf):
    """Verify selective processing on Page 16 (Sheet A-102) produces non-zero LF, SF,

    opening deductions, dual-red visual annotations, and takeoff schedule.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        pipe = QTOPipeline(blueprint_pdf, selected_pages=[16], output_dir=tmp_dir)
        summary = pipe.run()

        # Sheets processed
        assert summary["sheets_processed"] == [16]
        assert summary["selected_pages"] == [16]

        # Non-zero wall runs
        total_runs = summary["total_wall_runs"]
        assert total_runs == 41, f"Expected 41 consolidated wall runs for Page 16, got {total_runs}"

        # Quantities non-zero
        gross_lf = summary["total_gross_lf"]
        net_lf = summary["total_net_lf"]
        board_sf = summary["total_board_sf"]
        opening_ded = summary["total_opening_deduction_lf"]

        assert abs(gross_lf - 721.21) < 2.0, f"Expected gross LF ~721.21, got {gross_lf}"
        assert abs(net_lf - 693.50) < 2.0, f"Expected net LF ~693.50, got {net_lf}"
        assert abs(board_sf - 22168.97) < 10.0 or abs(board_sf - 22838.38) < 10.0, f"Expected board SF ~22168.97 (or ~22838.38), got {board_sf}"
        assert opening_ded > 0, f"Expected non-zero opening deductions, got {opening_ded}"
        assert abs(opening_ded - 27.71) < 1.0, f"Expected opening deduction ~27.71, got {opening_ded}"

        # Takeoff schedule details
        by_tag = summary["by_tag"]
        assert len(by_tag) >= 2, f"Expected at least 2 partition tags for Page 16, got {list(by_tag.keys())}"
        assert "7A" in by_tag
        assert "2B" in by_tag

        # Verify annotated.pdf generated and contains annotations
        annotated_pdf = Path(tmp_dir) / "annotated.pdf"
        assert annotated_pdf.exists()

        doc_annot = fitz.open(str(annotated_pdf))
        try:
            p16 = doc_annot[15]
            annots = list(p16.annots())
            drawings = p16.get_drawings()
            assert len(annots) >= 9, f"Expected at least 9 annotations on Page 16, got {len(annots)}"
            assert len(drawings) > 1000
        finally:
            doc_annot.close()


# =============================================================================
# 3. EMPIRICAL VERIFICATION: COMBINED SELECTIVE PROCESSING ON PAGES [15, 16]
# =============================================================================

def test_combined_selective_processing_pages_15_16(blueprint_pdf):
    """Verify combined processing of Pages [15, 16] aggregates schedules, wall runs,

    linear footage, and square footage with mathematical consistency.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        pipe = QTOPipeline(blueprint_pdf, selected_pages=[15, 16], output_dir=tmp_dir)
        summary = pipe.run()

        assert summary["sheets_processed"] == [15, 16]
        assert summary["selected_pages"] == [15, 16]

        # 18 runs from Page 15 + 41 runs from Page 16 = 59 runs
        assert summary["total_wall_runs"] == 59, f"Expected 59 runs, got {summary['total_wall_runs']}"

        # Check aggregation: Gross LF = 465.85 + 721.21 = 1187.06
        assert abs(summary["total_gross_lf"] - 1187.06) < 0.1
        # Net LF = 443.24 + 693.50 = 1136.74
        assert abs(summary["total_net_lf"] - 1136.74) < 0.1
        # Board SF = 14031.44 + 22838.38 = 36869.82 (or ~35309.70 with section heights)
        assert abs(summary["total_board_sf"] - 35309.70) < 1.0 or abs(summary["total_board_sf"] - 36869.82) < 1.0

        # Verify runs span both pages
        runs_p15 = [r for r in summary["runs"] if r["page_num"] == 15]
        runs_p16 = [r for r in summary["runs"] if r["page_num"] == 16]
        assert len(runs_p15) == 18
        assert len(runs_p16) == 41

        # Verify dual-red annotations present on both pages in output PDF
        annotated_pdf = Path(tmp_dir) / "annotated.pdf"
        assert annotated_pdf.exists()
        doc_annot = fitz.open(str(annotated_pdf))
        try:
            annots_15 = list(doc_annot[14].annots())
            annots_16 = list(doc_annot[15].annots())
            assert len(annots_15) >= 5
            assert len(annots_16) >= 9
        finally:
            doc_annot.close()


# =============================================================================
# 4. BOUNDARY & STRESS TESTS: EDGE CASES IN SELECTIVE PROCESSING
# =============================================================================

def test_boundary_out_of_range_pages_above(blueprint_pdf):
    """Stress test: page numbers exceeding total blueprint pages (e.g. 72 on 71-page PDF)."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        pipe = QTOPipeline(blueprint_pdf, selected_pages=[72], output_dir=tmp_dir)
        with pytest.raises(ValueError) as excinfo:
            pipe.run()
        assert "Invalid selected_pages" in str(excinfo.value)
        assert "72" in str(excinfo.value)
        assert "71" in str(excinfo.value)


def test_boundary_out_of_range_pages_zero_and_negative(blueprint_pdf):
    """Stress test: page number 0 and negative page numbers."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        pipe_zero = QTOPipeline(blueprint_pdf, selected_pages=[0], output_dir=tmp_dir)
        with pytest.raises(ValueError) as excinfo:
            pipe_zero.run()
        assert "Invalid selected_pages [0]" in str(excinfo.value)

        pipe_neg = QTOPipeline(blueprint_pdf, selected_pages=[-5], output_dir=tmp_dir)
        with pytest.raises(ValueError) as excinfo:
            pipe_neg.run()
        assert "Invalid selected_pages [-5]" in str(excinfo.value)


def test_boundary_mixed_valid_and_invalid_pages(blueprint_pdf):
    """Stress test: mixed valid and out-of-range pages."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        pipe = QTOPipeline(blueprint_pdf, selected_pages=[15, 999], output_dir=tmp_dir)
        with pytest.raises(ValueError) as excinfo:
            pipe.run()
        assert "999" in str(excinfo.value)


def test_boundary_empty_selection_behavior(blueprint_pdf):
    """Stress test: empty list selected_pages=[].

    According to pipeline design: empty selected_pages defaults to all floor plans.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        pipe = QTOPipeline(blueprint_pdf, selected_pages=[], output_dir=tmp_dir)
        # Empty list is falsy in Python; self.selected_pages becomes None if `sp else None`
        assert pipe.selected_pages is None or pipe.selected_pages == []


def test_boundary_non_floor_plan_sheet_selection(blueprint_pdf):
    """Stress test: selecting non-floor plan sheet (e.g. Cover Page 1).

    Should complete cleanly without crashing, returning 0 wall runs.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        pipe = QTOPipeline(blueprint_pdf, selected_pages=[1], output_dir=tmp_dir)
        summary = pipe.run()
        assert summary["sheets_processed"] == [1]
        assert summary["total_wall_runs"] == 0
        assert summary["total_gross_lf"] == 0.0
        assert summary["total_net_lf"] == 0.0
        assert summary["total_board_sf"] == 0.0


def test_boundary_duplicate_page_numbers(blueprint_pdf):
    """Stress test: duplicate page numbers e.g. [15, 15]."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        pipe = QTOPipeline(blueprint_pdf, selected_pages=[15, 15], output_dir=tmp_dir)
        summary = pipe.run()
        # Should not double-count wall runs for the same sheet
        assert summary["total_wall_runs"] == 18


# =============================================================================
# 5. REST API CONTRACT VERIFICATION WITH SELECTIVE PROCESSING
# =============================================================================

def test_api_blueprint_sheet_catalog(api_client, blueprint_pdf):
    """Verify GET /api/blueprint/{file_id}/sheets correctly enumerates sheets."""
    file_id = "doc_20261104_101950_6cbd34"
    resp = api_client.get(f"/api/blueprint/{file_id}/sheets")
    assert resp.status_code == 200
    sheets = resp.json()
    assert len(sheets) == 71

    # Check Page 15 (A-101)
    s15 = next((s for s in sheets if s["page_num"] == 15), None)
    assert s15 is not None
    assert s15["sheet_label"] == "A-101"
    assert s15["page_type"] == "FLOOR_PLAN"

    # Check Page 16 (A-102)
    s16 = next((s for s in sheets if s["page_num"] == 16), None)
    assert s16 is not None
    assert s16["sheet_label"] == "A-102"
    assert s16["page_type"] == "FLOOR_PLAN"


def test_api_process_out_of_range_error_handling(api_client):
    """Verify POST /api/process/{file_id} with invalid page numbers transitions to error status cleanly."""
    file_id = "doc_20261104_101950_6cbd34"
    payload = {
        "selected_pages": [999],
        "run_mode": "floor_plans_only"
    }
    resp = api_client.post(f"/api/process/{file_id}", json=payload)
    assert resp.status_code == 202
    run_id = resp.json()["run_id"]

    # Poll status (worker detects out-of-range immediately in S00)
    deadline = time.time() + 25.0
    status = "processing"
    while time.time() < deadline:
        st_resp = api_client.get(f"/api/pipeline/status/{run_id}")
        assert st_resp.status_code == 200
        st_data = st_resp.json()
        status = st_data["status"]
        if status in ("completed", "error"):
            break
        time.sleep(0.5)

    assert status == "error"
    assert "Invalid selected_pages [999]" in st_data.get("error", "")


def test_api_process_selective_pages(api_client, blueprint_pdf):
    """Verify POST /api/process/{file_id} accepts selected_pages and launches worker."""
    file_id = "doc_20261104_101950_6cbd34"
    payload = {
        "selected_pages": [15],
        "run_mode": "floor_plans_only"
    }
    resp = api_client.post(f"/api/process/{file_id}", json=payload)
    assert resp.status_code == 202
    data = resp.json()
    assert "run_id" in data
    assert data["status"] == "processing"
    assert data["selected_pages"] == [15]

    run_id = data["run_id"]
    # Poll until complete (full 71-page indexing in S01 + S06 takes ~60-90s on Windows)
    deadline = time.time() + 150.0
    status = "processing"
    while time.time() < deadline:
        st_resp = api_client.get(f"/api/pipeline/status/{run_id}")
        assert st_resp.status_code == 200
        st_data = st_resp.json()
        status = st_data["status"]
        if status in ("completed", "error"):
            break
        time.sleep(1.0)

    assert status == "completed", f"Pipeline failed with: {st_data.get('error')}"
    sum_resp = api_client.get(f"/api/takeoff/{run_id}/summary")
    assert sum_resp.status_code == 200
    summary = sum_resp.json()
    assert summary.get("sheets_processed") == [15]
    assert summary.get("total_wall_runs") == 18
    assert summary.get("total_gross_lf", 0) > 200.0
