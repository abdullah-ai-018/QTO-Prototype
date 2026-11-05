"""Phase 4 Test Suite: End-to-End PDF -> Canonical Drawing -> DrawingToBIMAdapter -> BIMRoofingEngine.
Verifies that native PDF vector extraction feeds the existing IFC BIMRoofingEngine
with 100% provenance back to PDF page and vector IDs, with zero synthetic heuristics.
"""
import os
import pytest

from app.bim.models import DataProvenanceStatus, QTOEligibilityStatus
from app.pdf.canonical_pipeline import CanonicalDrawingBuilder
from app.pdf.drawing_to_bim import DrawingToBIMAdapter
from app.pdf.models import ScaleStatus
from app.trades.roofing_bim import BIMRoofingEngine

PDF_PATH = os.path.join(
    os.path.dirname(__file__),
    "../storage/uploads/FATIMA-AHMED-CONSTRUCTION-DRAWINGS-PORTFOLIO_f1c89f17b33d.pdf",
)


@pytest.fixture
def canonical_drawing():
    """Builds CanonicalDrawingDocument for Sheet A2.1 (Page 11)."""
    if not os.path.exists(PDF_PATH):
        pytest.skip(f"Target real PDF not found at {PDF_PATH}")
    builder = CanonicalDrawingBuilder()
    doc = builder.build_document(PDF_PATH, target_page_num=11)
    return doc


def test_drawing_to_bim_adapter_structure(canonical_drawing):
    """Verifies that DrawingToBIMAdapter converts CanonicalDrawingDocument to CanonicalBIMModel."""
    adapter = DrawingToBIMAdapter()
    bim_model = adapter.adapt_to_bim_model(canonical_drawing)

    assert bim_model.source_hash == canonical_drawing.source_hash
    assert len(bim_model.roofs) == 2
    assert bim_model.project.schema_version == "PDF_VECTOR_DRAWING"

    lower_roof, upper_roof = bim_model.roofs[0], bim_model.roofs[1]
    assert lower_roof.name == "Lower Roof Plane"
    assert upper_roof.name == "Upper Roof Plane"
    assert lower_roof.source_type == "PDF_VECTOR"
    assert upper_roof.source_type == "PDF_VECTOR"

    # Provenance back to PDF source
    for rf in [lower_roof, upper_roof]:
        assert "PDF_Source" in rf.source_psets
        pdf_meta = rf.source_psets["PDF_Source"]
        assert pdf_meta["page_number"] == 11
        assert pdf_meta["sheet_number"] == "A2.1"
        assert pdf_meta["source_hash"] == canonical_drawing.source_hash
        assert pdf_meta["scale_string"] == "1:50"
        assert len(pdf_meta["raw_boundary_points_pdf"]) == 4


def test_existing_bim_roofing_engine_executes_on_pdf_model(canonical_drawing):
    """CRITICAL ARCHITECTURAL GATE: PDF feeds the EXACT SAME BIMRoofingEngine as IFC."""
    adapter = DrawingToBIMAdapter()
    bim_model = adapter.adapt_to_bim_model(canonical_drawing)

    # Execute existing BIMRoofingEngine
    engine = BIMRoofingEngine(default_waste_factor=0.0)
    summary = engine.calculate(bim_model)

    assert summary.total_elements_evaluated == 2
    assert summary.eligible_elements_count == 2
    assert summary.review_elements_count == 0
    assert summary.blocked_elements_count == 0
    assert summary.verified_slope_count == 2

    # Plan Area: 3,988.20 SF
    assert pytest.approx(summary.total_plan_area_sqft, rel=1e-3) == 3988.20

    # True Surface Area: 4,043.20 SF
    assert pytest.approx(summary.total_true_surface_area_sqft, rel=1e-3) == 4043.20

    # Line Items Produced by BIMRoofingEngine
    assert len(summary.line_items) == 2
    item1 = summary.line_items[0]
    assert item1.trade == "ROOFING"
    assert item1.category == "ROOFING_SURFACE"
    assert item1.item_code == "ROOF-QTO-SURFACE-SF"
    assert pytest.approx(item1.quantity, rel=1e-3) == 2578.68
    assert item1.provenance.pitch_ratio == "2:12"
    assert item1.provenance.slope_provenance == DataProvenanceStatus.VERIFIED_EXPLICIT
    assert item1.provenance.geometry_provenance == DataProvenanceStatus.DERIVED_GEOMETRIC
    assert "2543.6 Plan SF × 1.01379 Pitch Mult = 2578.7 True Surface SF" in item1.provenance.formula

    item2 = summary.line_items[1]
    assert item2.trade == "ROOFING"
    assert item2.category == "ROOFING_SURFACE"
    assert pytest.approx(item2.quantity, rel=1e-3) == 1464.52


def test_missing_scale_blocks_qto_in_bim_model(canonical_drawing):
    """Constraint 5: When scale is unresolved, CanonicalRoof eligibility is REVIEW_REQUIRED."""
    # Modify drawing page to simulate unresolved scale
    page_copy = canonical_drawing.pages[0].model_copy(deep=True)
    page_copy.scale_evidence.scale_status = ScaleStatus.SCALE_UNRESOLVED
    unresolved_doc = canonical_drawing.model_copy(update={"pages": [page_copy]})

    adapter = DrawingToBIMAdapter()
    bim_model = adapter.adapt_to_bim_model(unresolved_doc)

    for rf in bim_model.roofs:
        assert rf.qto_eligibility == QTOEligibilityStatus.REVIEW_REQUIRED
        assert any("SCALE_UNRESOLVED" in reason for reason in rf.review_reasons)

    # Engine reflects REVIEW status
    engine = BIMRoofingEngine()
    summary = engine.calculate(bim_model)
    assert summary.review_elements_count == 2
    assert summary.eligible_elements_count == 0
