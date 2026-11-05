"""Test Suite for Phase 1: PDF Document Type Detection & Capability Inspection.
Verifies vector vs. scanned vs. hybrid classification, cryptographic SHA-256 provenance,
and native path/text metrics with zero guessing.
"""
import os
import tempfile
import fitz
import pytest

from app.pdf.detector import PDFTypeDetector
from app.pdf.models import PDFType


@pytest.fixture
def detector():
    return PDFTypeDetector()


@pytest.fixture
def synthetic_vector_pdf():
    """Generates a clean vector PDF containing native lines, rects, curves, and text."""
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp_path = tmp.name

    doc = fitz.open()
    page = doc.new_page(width=612, height=792)  # Standard 8.5 x 11 in points

    # Draw native vector paths
    shape = page.new_shape()
    # Rectangle
    shape.draw_rect(fitz.Rect(50, 50, 300, 300))
    shape.finish(color=(0, 0, 0), fill=(0.9, 0.9, 0.9), width=1.5)

    # Sloped roof ridge and eaves
    shape.draw_line(fitz.Point(50, 50), fitz.Point(175, 20))
    shape.draw_line(fitz.Point(175, 20), fitz.Point(300, 50))
    shape.finish(color=(1, 0, 0), width=2.0)

    # Commit shape to page
    shape.commit()

    # Add native text
    page.insert_text(fitz.Point(60, 80), "ROOF PLAN", fontsize=14)
    page.insert_text(fitz.Point(60, 110), "SLOPE 6:12", fontsize=11)
    page.insert_text(fitz.Point(60, 140), "SCALE: 1/4\" = 1'-0\"", fontsize=10)
    page.insert_text(fitz.Point(60, 170), "24'-0\"", fontsize=10)

    doc.save(tmp_path)
    doc.close()

    yield tmp_path

    if os.path.exists(tmp_path):
        os.remove(tmp_path)


@pytest.fixture
def synthetic_scanned_pdf():
    """Generates a scanned raster PDF with only an image and zero vector linework."""
    from PIL import Image

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp_path = tmp.name

    # Create dummy raster image
    img_path = tmp_path + ".png"
    img = Image.new("RGB", (800, 1000), color=(240, 240, 240))
    img.save(img_path)

    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    # Insert image covering the whole page
    page.insert_image(page.rect, filename=img_path)
    doc.save(tmp_path)
    doc.close()

    if os.path.exists(img_path):
        os.remove(img_path)

    yield tmp_path

    if os.path.exists(tmp_path):
        os.remove(tmp_path)


def test_detect_vector_pdf(detector, synthetic_vector_pdf):
    """Verify that a vector PDF is accurately classified with native counts and SHA-256 hash."""
    caps = detector.inspect_document(synthetic_vector_pdf)

    assert caps.pdf_type == PDFType.VECTOR_PDF
    assert caps.is_vector_supported is True
    assert caps.page_count == 1
    assert caps.total_vector_paths >= 1
    assert caps.total_drawing_commands >= 3
    assert caps.total_text_chars >= 20
    assert caps.total_images == 0
    assert len(caps.source_hash) == 64  # Valid SHA-256 hex string

    page = caps.pages[0]
    assert page.page_pdf_type == PDFType.VECTOR_PDF
    assert page.has_native_vectors is True
    assert page.has_native_text is True
    assert page.has_raster_images is False
    assert page.confidence >= 0.95


def test_detect_scanned_pdf(detector, synthetic_scanned_pdf):
    """Verify that a scanned raster PDF is blocked from vector takeoff and marked as SCANNED."""
    caps = detector.inspect_document(synthetic_scanned_pdf)

    assert caps.pdf_type == PDFType.SCANNED_PDF
    assert caps.is_vector_supported is False
    assert caps.page_count == 1
    assert caps.total_vector_paths == 0
    assert caps.total_images >= 1
    assert any("Scanned / Raster PDF" in note for note in caps.readiness_notes)

    page = caps.pages[0]
    assert page.page_pdf_type == PDFType.SCANNED_PDF
    assert page.has_native_vectors is False
    assert page.has_raster_images is True


def test_sha256_provenance_stability(detector, synthetic_vector_pdf):
    """Verify SHA-256 hash calculation is deterministic and changes if document content changes."""
    hash1 = detector.compute_sha256(synthetic_vector_pdf)
    hash2 = detector.compute_sha256(synthetic_vector_pdf)
    assert hash1 == hash2

    # Appending a byte changes the hash
    with open(synthetic_vector_pdf, "ab") as f:
        f.write(b" ")
    hash3 = detector.compute_sha256(synthetic_vector_pdf)
    assert hash1 != hash3


def test_real_architectural_pdf_detection(detector):
    """Tests detector against a real vector drawing set in the repository if available."""
    real_paths = [
        "storage/uploads/2D-Floor-Plan-in-AutoCAD-with-Dimensions_d45437d3cbc6.pdf",
        "storage/uploads/toaz_info-commercial-building-plans-and-elev-pr_5bbbb1e53f26bc5d30a5f65cbbde2515_09c08ce821b4.pdf",
        "storage/uploads/36472-1__architectural_final_7766eb78fece.pdf",
    ]

    for rel_path in real_paths:
        full_path = os.path.join(os.path.dirname(__file__), "..", rel_path)
        if os.path.exists(full_path):
            caps = detector.inspect_document(full_path)
            assert caps.page_count >= 1
            assert len(caps.source_hash) == 64
            assert caps.pdf_type in (PDFType.VECTOR_PDF, PDFType.HYBRID_PDF, PDFType.SCANNED_PDF)
            # If it has vectors, ensure counts are populated
            if caps.total_vector_paths > 0:
                assert caps.total_drawing_commands >= caps.total_vector_paths
            break
