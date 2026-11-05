"""Test Suite: Text <-> Geometry Relationships.
Validates deterministic links between text, dimensions, and drawing geometry.
"""
import os
import pytest
from app.pdf.canonical_pipeline import CanonicalDrawingBuilder
from app.pdf.models import CanonicalDrawingDocument

PDF_FIXTURE_PATH = os.path.join(
    "storage", "uploads", "FATIMA-AHMED-CONSTRUCTION-DRAWINGS-PORTFOLIO_f1c89f17b33d.pdf"
)


@pytest.fixture(scope="module")
def canonical_doc() -> CanonicalDrawingDocument:
    builder = CanonicalDrawingBuilder()
    return builder.build_document(PDF_FIXTURE_PATH, target_page_num=11)


def test_relationships_extracted(canonical_doc: CanonicalDrawingDocument):
    page = canonical_doc.pages[0]
    rels = page.relationships
    assert len(rels) >= 4, f"Expected at least 4 relationships, got {len(rels)}"


def test_slope_to_roof_plane_association(canonical_doc: CanonicalDrawingDocument):
    page = canonical_doc.pages[0]
    slope_rels = [r for r in page.relationships if r.relationship_type == "SLOPE_TO_ROOF_BOUNDARY"]
    assert len(slope_rels) >= 1
    rel = slope_rels[0]
    assert rel.method in ("SPATIAL_CONTAINMENT", "PROXIMITY")
    assert rel.status == "SUPPORTED"
    assert "ROOF" in rel.target_object_id.upper() or "PLANE" in rel.target_object_id.upper()


def test_dimension_to_line_association(canonical_doc: CanonicalDrawingDocument):
    page = canonical_doc.pages[0]
    dim_rels = [r for r in page.relationships if r.relationship_type == "DIMENSION_TO_LINE"]
    assert len(dim_rels) >= 1
    rel = dim_rels[0]
    assert rel.method in ("ALIGNMENT", "WITNESS_GEOMETRY")
    assert rel.confidence >= 0.90


def test_scale_to_page_association(canonical_doc: CanonicalDrawingDocument):
    page = canonical_doc.pages[0]
    scale_rels = [r for r in page.relationships if r.relationship_type == "SCALE_TO_PAGE"]
    assert len(scale_rels) == 1
    rel = scale_rels[0]
    assert rel.target_object_id == "PAGE-11"
    assert rel.method == "EXPLICIT_SYNTAX"
    assert rel.status == "SUPPORTED"


def test_no_arbitrary_guesses(canonical_doc: CanonicalDrawingDocument):
    page = canonical_doc.pages[0]
    for rel in page.relationships:
        assert rel.status in ("SUPPORTED", "REVIEW_REQUIRED", "UNKNOWN")
        assert rel.provenance.value == "VERIFIED_EXPLICIT"
