"""Test Suite for Phase 2: Native Vector & Content Extraction, Semantic Reconstruction,
Scale Validation, and Ground-Truth Reconciliation on Real Architectural Roof Plan.
"""
import os
import fitz
import pytest

from app.bim.models import DataProvenanceStatus, QTOEligibilityStatus
from app.pdf.content_extractor import PDFContentExtractor
from app.pdf.vector_extractor import PDFVectorExtractor
from app.pdf.scale_validator import ScaleValidator
from app.pdf.roof_classifier import RoofVectorClassifier
from app.pdf.roof_topology import RoofTopologyReconstructor
from app.pdf.models import (
    PDFType,
    ScaleStatus,
    SemanticContentType,
)

PDF_PATH = os.path.join(
    os.path.dirname(__file__),
    "../storage/uploads/FATIMA-AHMED-CONSTRUCTION-DRAWINGS-PORTFOLIO_f1c89f17b33d.pdf",
)


@pytest.fixture
def target_roof_page():
    """Opens Sheet A2.1 (Page 11, 0-indexed 10) of the target architectural set."""
    if not os.path.exists(PDF_PATH):
        pytest.skip(f"Target real PDF not found at {PDF_PATH}")
    doc = fitz.open(PDF_PATH)
    page = doc[10]  # Page 11
    yield page
    doc.close()


def test_native_text_and_semantic_extraction(target_roof_page):
    """Question 1: Decodes content, extracts explicit titles, slopes, labels, dimensions."""
    extractor = PDFContentExtractor()
    text_objects = extractor.extract_page_content(target_roof_page, page_number=11)

    assert len(text_objects) > 50

    # 1. Sheet Title & Number
    titles = [t.text for t in text_objects if t.semantic_type == SemanticContentType.DRAWING_TITLE]
    assert any("ROOF PLAN" in t.upper() for t in titles)

    # 2. Explicit Slope Annotations
    slopes = [t.text for t in text_objects if t.semantic_type == SemanticContentType.SLOPE_ANNOTATION]
    assert any("2: 12" in s or "2:12" in s for s in slopes)
    for s in slopes:
        assert "SLOPE" in s.upper()

    # 3. Explicit Roof Facet Labels
    roof_labels = [t.text for t in text_objects if t.semantic_type == SemanticContentType.ROOF_LABEL]
    assert any("LOWER ROOF" in l.upper() for l in roof_labels)
    assert any("UPPER ROOF" in l.upper() for l in roof_labels)
    assert any("LINE OF UPPER ROOF" in l.upper() for l in roof_labels)

    # 4. Verified Dimensions
    dim_texts = [t.text for t in text_objects if t.semantic_type == SemanticContentType.DIMENSION_TEXT]
    assert any("17652 mm" in d for d in dim_texts)
    assert any("13388 mm" in d for d in dim_texts)
    assert any("10024 mm" in d for d in dim_texts)

    # 5. Provenance verification
    for t in text_objects:
        assert t.source == "PDF_NATIVE_TEXT"
        assert t.provenance == DataProvenanceStatus.VERIFIED_EXPLICIT
        assert len(t.bbox_pdf) == 4
        assert len(t.origin_pdf) == 2


def test_native_vector_extraction_and_coordinate_fidelity(target_roof_page):
    """Question 1 & Coordinate Preservation: Extracts raw vector linework without rasterization."""
    extractor = PDFVectorExtractor()
    vectors = extractor.extract_page_vectors(target_roof_page, page_number=11)

    assert len(vectors) >= 1000

    # Ensure coordinates are strictly PDF points, not pixels or raster coordinates
    for v in vectors:
        assert v.source == "PDF_VECTOR"
        assert v.provenance == DataProvenanceStatus.VERIFIED_EXPLICIT
        assert len(v.source_points_pdf) >= 2
        assert len(v.normalized_points) == len(v.source_points_pdf)
        assert len(v.transformed_points_ft) == 0  # Unpopulated before scale validation
        assert v.transform_metadata.applied_snapping_tolerance_pt == 0.0


def test_scale_validation_and_dimension_corroboration(target_roof_page):
    """Question 2: Validates scale (1:50) and corroborates with dimension vector distance."""
    content_extractor = PDFContentExtractor()
    vector_extractor = PDFVectorExtractor()

    text_objects = content_extractor.extract_page_content(target_roof_page, page_number=11)
    geometry_objects = vector_extractor.extract_page_vectors(target_roof_page, page_number=11)

    scale_validator = ScaleValidator()
    evidence = scale_validator.validate_page_scale(text_objects, geometry_objects)

    assert evidence.scale_status == ScaleStatus.VERIFIED_EXPLICIT
    assert evidence.scale_string == "1:50"
    assert evidence.ratio == 50.0
    # Expected ft per point at 1:50: 50 / 864 = 0.05787037...
    assert pytest.approx(evidence.ft_per_pt, rel=1e-5) == 50.0 / 864.0
    assert evidence.provenance == DataProvenanceStatus.VERIFIED_EXPLICIT
    # Confirm dimension cross-check note was generated
    assert any("Dimension cross-check verified" in note for note in evidence.notes)


def test_roof_vector_classification(target_roof_page):
    """Question 1: Categorizes vectors into semantic structural roles."""
    content_extractor = PDFContentExtractor()
    vector_extractor = PDFVectorExtractor()

    text_objects = content_extractor.extract_page_content(target_roof_page, page_number=11)
    geometry_objects = vector_extractor.extract_page_vectors(target_roof_page, page_number=11)

    classifier = RoofVectorClassifier()
    classified = classifier.classify_page_vectors(
        geometry_objects,
        text_objects,
        page_width=target_roof_page.rect.width,
        page_height=target_roof_page.rect.height,
    )

    assert len(classified.roof_boundaries) >= 2
    assert len(classified.standing_seams) > 50
    assert len(classified.title_block_lines) > 10


def test_roof_topology_and_ground_truth_reconciliation(target_roof_page):
    """Questions 3, 4, 5 & Validation Matrix: Reconstructs roof planes and compares QTO to ground truth."""
    content_extractor = PDFContentExtractor()
    vector_extractor = PDFVectorExtractor()
    scale_validator = ScaleValidator()
    classifier = RoofVectorClassifier()
    topology_reconstructor = RoofTopologyReconstructor()

    text_objects = content_extractor.extract_page_content(target_roof_page, page_number=11)
    geometry_objects = vector_extractor.extract_page_vectors(target_roof_page, page_number=11)
    scale_evidence = scale_validator.validate_page_scale(text_objects, geometry_objects)
    classified = classifier.classify_page_vectors(
        geometry_objects,
        text_objects,
        page_width=target_roof_page.rect.width,
        page_height=target_roof_page.rect.height,
    )

    summary = topology_reconstructor.reconstruct_sheet_roof(
        classified, text_objects, scale_evidence, page_number=11
    )

    assert summary.sheet_number == "A2.1"
    assert len(summary.planes) == 2

    plane1, plane2 = summary.planes[0], summary.planes[1]
    assert plane1.name == "Lower Roof Plane"
    assert plane2.name == "Upper Roof Plane"

    # Plan Area Ground Truth check:
    # Lower: 17.652m x 13.388m = 236.325 m² = 2,543.78 SF
    # Upper: 10.024m x 13.388m = 134.201 m² = 1,444.53 SF
    # Total Ground Truth: 3,988.31 SF (370.53 m²)
    assert pytest.approx(summary.total_plan_area_sqft, rel=1e-3) == 3988.20
    assert pytest.approx(plane1.plan_area_sqft, rel=1e-3) == 2543.60
    assert pytest.approx(plane2.plan_area_sqft, rel=1e-3) == 1444.60

    # Slope check:
    assert plane1.pitch_ratio == "2:12"
    assert plane2.pitch_ratio == "2:12"
    expected_mult = (1.0 + (2.0 / 12.0) ** 2) ** 0.5
    assert pytest.approx(plane1.pitch_multiplier, rel=1e-4) == expected_mult
    assert plane1.slope_provenance == DataProvenanceStatus.VERIFIED_EXPLICIT

    # True Surface Area check:
    # 3988.20 * 1.01379 = 4043.20 SF
    assert pytest.approx(summary.total_true_surface_area_sqft, rel=1e-3) == 4043.20

    # Validation Matrix check:
    assert len(summary.validation_matrix) == 10
    for item in summary.validation_matrix:
        assert item.status == "PASS", f"Failed validation item: {item.feature_name} - {item.notes}"


def test_missing_scale_blocks_qto():
    """Constraint 5: Missing scale results in SCALE_UNRESOLVED and blocks accurate QTO."""
    scale_validator = ScaleValidator()
    # Empty texts and geometries
    evidence = scale_validator.validate_page_scale([], [])
    assert evidence.scale_status == ScaleStatus.SCALE_UNRESOLVED
    assert evidence.provenance == DataProvenanceStatus.UNKNOWN_UNRESOLVED
    assert evidence.ft_per_pt is None
    assert any("strictly blocked" in note for note in evidence.notes)
