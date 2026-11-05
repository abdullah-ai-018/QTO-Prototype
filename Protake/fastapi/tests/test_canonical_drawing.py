"""Test Suite: Canonical Drawing Document Structure & Completeness.
Verifies that native architectural drawing data is faithfully captured in CanonicalDrawingDocument
without inventing synthetic geometry.
"""
import os
import pytest
from app.pdf.canonical_pipeline import CanonicalDrawingBuilder
from app.pdf.models import (
    CanonicalDrawingDocument,
    DrawingObjectType,
    ScaleStatus,
    SemanticClassificationStatus,
)

PDF_FIXTURE_PATH = os.path.join(
    "storage", "uploads", "FATIMA-AHMED-CONSTRUCTION-DRAWINGS-PORTFOLIO_f1c89f17b33d.pdf"
)


@pytest.fixture(scope="module")
def canonical_doc() -> CanonicalDrawingDocument:
    assert os.path.isfile(PDF_FIXTURE_PATH), f"Fixture not found at {PDF_FIXTURE_PATH}"
    builder = CanonicalDrawingBuilder()
    # Sheet A2.1 is Page 11
    doc = builder.build_document(PDF_FIXTURE_PATH, target_page_num=11)
    return doc


def test_canonical_document_metadata(canonical_doc: CanonicalDrawingDocument):
    assert canonical_doc.source_hash is not None
    assert len(canonical_doc.source_hash) == 64  # SHA-256
    assert canonical_doc.pdf_type.value in ("VECTOR_PDF", "HYBRID_PDF")
    assert len(canonical_doc.pages) == 1


def test_sheet_a21_identity_and_scale(canonical_doc: CanonicalDrawingDocument):
    page = canonical_doc.pages[0]
    assert page.page_number == 11
    assert page.sheet_number == "A2.1"
    assert "ROOF PLAN" in page.sheet_title.upper()
    assert page.scale_evidence.scale_status == ScaleStatus.VERIFIED_EXPLICIT
    assert page.scale_evidence.scale_string == "1:50"
    assert page.scale_evidence.ratio == 50.0
    assert abs(page.scale_evidence.ft_per_pt - (50.0 / 864.0)) < 1e-6


def test_text_and_geometry_completeness(canonical_doc: CanonicalDrawingDocument):
    page = canonical_doc.pages[0]
    # Native text extracted without dropping
    assert len(page.text_objects) >= 30
    # Native vector linework extracted
    assert len(page.geometry_objects) >= 500
    # Reconstructed semantic objects
    assert len(page.semantic_objects) >= 100


def test_layers_defined_with_non_zero_counts(canonical_doc: CanonicalDrawingDocument):
    page = canonical_doc.pages[0]
    layer_names = {l.name for l in page.layers}
    assert "Roof" in layer_names
    assert "Dimensions" in layer_names
    assert "Grid" in layer_names
    assert "Title Block" in layer_names
    assert "Hatches" in layer_names

    roof_layer = next(l for l in page.layers if l.name == "Roof")
    assert roof_layer.object_count >= 2

    hatch_layer = next(l for l in page.layers if l.name == "Hatches")
    assert hatch_layer.object_count >= 100


def test_no_synthetic_or_guessed_geometry(canonical_doc: CanonicalDrawingDocument):
    page = canonical_doc.pages[0]
    for sem_obj in page.semantic_objects:
        assert sem_obj.classification_status in (
            SemanticClassificationStatus.SUPPORTED,
            SemanticClassificationStatus.REVIEW_REQUIRED,
            SemanticClassificationStatus.UNKNOWN,
        )
        assert sem_obj.confidence >= 0.0
        # If real-world coordinates populated, scale must be verified
        if sem_obj.transformed_points_ft:
            assert page.scale_evidence.scale_status == ScaleStatus.VERIFIED_EXPLICIT
