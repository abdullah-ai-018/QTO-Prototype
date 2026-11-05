"""Test Suite: Bidirectional Canvas Provenance.
Proves that every rendered canvas object maps to source PDF objects,
and that QTO items trace back to canvas geometry and PDF coordinates.
"""
import os
import pytest
from app.pdf.canonical_pipeline import CanonicalDrawingBuilder
from app.pdf.drawing_to_bim import DrawingToBIMAdapter
from app.pdf.models import CanonicalDrawingDocument, DrawingObjectType
from app.trades.roofing_bim import BIMRoofingEngine

PDF_FIXTURE_PATH = os.path.join(
    "storage", "uploads", "FATIMA-AHMED-CONSTRUCTION-DRAWINGS-PORTFOLIO_f1c89f17b33d.pdf"
)


@pytest.fixture(scope="module")
def pipeline_data():
    builder = CanonicalDrawingBuilder()
    doc = builder.build_document(PDF_FIXTURE_PATH, target_page_num=11)
    adapter = DrawingToBIMAdapter()
    bim = adapter.convert_drawing_to_bim(doc, target_page_num=11)
    engine = BIMRoofingEngine()
    qto = engine.calculate_roofing_qto(bim)
    return {"doc": doc, "bim": bim, "qto": qto}


def test_canvas_object_to_source_pdf_provenance(pipeline_data):
    doc: CanonicalDrawingDocument = pipeline_data["doc"]
    page = doc.pages[0]

    for sem_obj in page.semantic_objects:
        assert sem_obj.id is not None
        assert sem_obj.page_number == 11
        # Must link to either source vector IDs or source text IDs
        assert len(sem_obj.source_vector_ids) > 0 or len(sem_obj.source_text_ids) > 0
        assert sem_obj.provenance.value in ("VERIFIED_EXPLICIT", "DERIVED_GEOMETRIC")
        assert len(sem_obj.source_points_pdf) > 0


def test_qto_line_to_canvas_and_pdf_provenance(pipeline_data):
    doc: CanonicalDrawingDocument = pipeline_data["doc"]
    qto = pipeline_data["qto"]
    page = doc.pages[0]

    # Every item in QTO line items must map back to a CanonicalRoof and PDF vectors
    assert len(qto.line_items) >= 2
    for item in qto.line_items:
        # Find matching roof semantic object
        matched_sem = next(
            (o for o in page.semantic_objects if o.object_type == DrawingObjectType.ROOF and o.label == item.provenance.element_name),
            None,
        )
        assert matched_sem is not None, f"Could not find semantic object matching QTO item '{item.provenance.element_name}'"
        # Validate that matched semantic object has source vector IDs and points
        assert len(matched_sem.source_vector_ids) > 0
        assert len(matched_sem.source_points_pdf) >= 4
        # Validate area reconciliation
        assert abs(matched_sem.properties["plan_area_sqft"] - item.provenance.plan_area_sqft) < 0.05
        assert abs(matched_sem.properties["true_surface_area_sqft"] - item.provenance.true_surface_area_sqft) < 0.05


def test_pdf_geometry_to_qto_mapping(pipeline_data):
    doc: CanonicalDrawingDocument = pipeline_data["doc"]
    page = doc.pages[0]
    roof_objs = [o for o in page.semantic_objects if o.object_type == DrawingObjectType.ROOF]

    for roof in roof_objs:
        assert roof.qto_reference_id is not None
        assert roof.properties.get("status") == "PASS"
