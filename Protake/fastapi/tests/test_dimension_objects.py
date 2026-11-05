"""Test Suite: Structured Architectural Dimension Objects.
Validates extraction of dimensions with nominal values, units, witness lines, and real-world lengths.
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


def test_dimensions_extracted(canonical_doc: CanonicalDrawingDocument):
    page = canonical_doc.pages[0]
    dims = page.dimension_objects
    assert len(dims) >= 2, f"Expected at least 2 dimensions, found {len(dims)}"


def test_major_building_dimensions(canonical_doc: CanonicalDrawingDocument):
    page = canonical_doc.pages[0]
    dim_texts = [d.dimension_text for d in page.dimension_objects]
    # Check that major dimensions like 17652 or 13388 are captured
    assert any("17652" in t for t in dim_texts) or any("13388" in t for t in dim_texts)

    d_17652 = next((d for d in page.dimension_objects if "17652" in d.dimension_text), None)
    if d_17652:
        assert d_17652.unit in ("mm", "unknown")
        assert d_17652.measured_value == 17652.0
        # 17652 mm / 304.8 = 57.913 ft
        assert abs(d_17652.nominal_length_ft - (17652.0 / 304.8)) < 0.1
        assert d_17652.start_pt is not None
        assert d_17652.end_pt is not None


def test_dimension_coordinate_transformation(canonical_doc: CanonicalDrawingDocument):
    page = canonical_doc.pages[0]
    for dim in page.dimension_objects:
        assert len(dim.start_pt) == 2
        assert len(dim.end_pt) == 2
        if dim.start_pt_ft and dim.end_pt_ft:
            assert len(dim.start_pt_ft) == 2
            assert len(dim.end_pt_ft) == 2
            assert dim.is_calibrated is True


def test_dimension_association_status(canonical_doc: CanonicalDrawingDocument):
    page = canonical_doc.pages[0]
    for dim in page.dimension_objects:
        assert dim.association_status in ("VERIFIED_EXPLICIT", "REVIEW_REQUIRED")
