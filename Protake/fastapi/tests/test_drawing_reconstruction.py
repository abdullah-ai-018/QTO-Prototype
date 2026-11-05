"""Test Suite: Architectural Drawing Semantic Reconstruction.
Validates segregation into layers, creation of semantic drawing objects,
and fidelity of real-world coordinates.
"""
import os
import pytest
from app.pdf.canonical_pipeline import CanonicalDrawingBuilder
from app.pdf.models import CanonicalDrawingDocument, DrawingObjectType

PDF_FIXTURE_PATH = os.path.join(
    "storage", "uploads", "FATIMA-AHMED-CONSTRUCTION-DRAWINGS-PORTFOLIO_f1c89f17b33d.pdf"
)


@pytest.fixture(scope="module")
def canonical_doc() -> CanonicalDrawingDocument:
    builder = CanonicalDrawingBuilder()
    return builder.build_document(PDF_FIXTURE_PATH, target_page_num=11)


def test_semantic_objects_created(canonical_doc: CanonicalDrawingDocument):
    page = canonical_doc.pages[0]
    objs = page.semantic_objects
    assert len(objs) >= 100, f"Expected >= 100 semantic objects, got {len(objs)}"

    types = {o.object_type for o in objs}
    assert DrawingObjectType.ROOF in types
    assert DrawingObjectType.DIMENSION in types
    assert DrawingObjectType.GRID in types
    assert DrawingObjectType.TITLE_BLOCK in types
    assert DrawingObjectType.HATCH in types


def test_roof_planes_semantic_properties(canonical_doc: CanonicalDrawingDocument):
    page = canonical_doc.pages[0]
    roof_objs = [o for o in page.semantic_objects if o.object_type == DrawingObjectType.ROOF]
    assert len(roof_objs) == 2  # Lower Roof and Upper Roof

    lower = next((r for r in roof_objs if "lower" in r.label.lower()), None)
    upper = next((r for r in roof_objs if "upper" in r.label.lower()), None)

    assert lower is not None
    assert upper is not None

    assert lower.properties.get("slope") == "2:12"
    assert upper.properties.get("slope") == "2:12"
    assert lower.properties.get("plan_area_sqft") > 0
    assert upper.properties.get("plan_area_sqft") > 0
    assert lower.qto_reference_id is not None
    assert upper.qto_reference_id is not None


def test_layer_statistics(canonical_doc: CanonicalDrawingDocument):
    page = canonical_doc.pages[0]
    layers = {l.name: l for l in page.layers}

    assert layers["Roof"].object_count == 2
    assert layers["Dimensions"].object_count >= 2
    assert layers["Hatches"].object_count >= 100
    assert layers["Grid"].object_count >= 5
    assert layers["Title Block"].object_count >= 1


def test_validation_report_reflects_reconstruction(canonical_doc: CanonicalDrawingDocument):
    page = canonical_doc.pages[0]
    val = page.validation_report
    assert val is not None
    assert val.validation_state == "PASS"
    assert val.reconstructed_geometries == len(page.semantic_objects)
    assert val.associated_dimension_count == len(page.dimension_objects)
    assert val.reconciliation_results.get("reconciliation_status") == "RECONCILED_100_PERCENT"
