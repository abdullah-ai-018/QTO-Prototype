"""PDF Document Type & Capability Detector.
Analyzes native PDF streams using PyMuPDF (fitz) without rasterization.
Distinguishes VECTOR PDF, SCANNED/RASTER PDF, and HYBRID PDF.
Computes cryptographic SHA-256 source hash for 100% auditable provenance.
"""
from __future__ import annotations

import hashlib
import os
from typing import Optional
import fitz  # PyMuPDF

from app.pdf.models import (
    PDFDocumentCapabilities,
    PDFPageCapabilities,
    PDFType,
)


class PDFTypeDetector:
    """Inspects native PDF content streams and classifies documents based on vector vs. raster content."""

    # Decision thresholds for engineering-grade architectural blueprints
    MIN_VECTOR_PATHS_FOR_VECTOR_PAGE = 15
    MIN_DRAWING_COMMANDS_FOR_VECTOR_PAGE = 30
    MIN_TEXT_CHARS_FOR_NATIVE_TEXT = 20

    @classmethod
    def compute_sha256(cls, file_path: str) -> str:
        """Computes SHA-256 digest of the PDF file in 64KB chunks."""
        hasher = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                hasher.update(chunk)
        return hasher.hexdigest()

    def inspect_document(self, file_path: str) -> PDFDocumentCapabilities:
        """Thoroughly inspects a PDF document and returns complete capability and type classification."""
        if not os.path.isfile(file_path):
            raise FileNotFoundError(f"PDF file not found at: {file_path}")

        file_size = os.path.getsize(file_path)
        source_hash = self.compute_sha256(file_path)
        file_name = os.path.basename(file_path)

        try:
            doc = fitz.open(file_path)
        except Exception as exc:
            raise ValueError(f"Failed to open PDF document with PyMuPDF: {exc}") from exc

        page_caps: list[PDFPageCapabilities] = []
        total_vectors = 0
        total_commands = 0
        total_chars = 0
        total_images = 0

        vector_page_count = 0
        scanned_page_count = 0
        hybrid_page_count = 0

        try:
            for page_idx, page in enumerate(doc):
                cap = self.inspect_page(page, page_idx + 1)
                page_caps.append(cap)

                total_vectors += cap.vector_path_count
                total_commands += cap.drawing_command_count
                total_chars += cap.text_char_count
                total_images += cap.image_count

                if cap.page_pdf_type == PDFType.VECTOR_PDF:
                    vector_page_count += 1
                elif cap.page_pdf_type == PDFType.SCANNED_PDF:
                    scanned_page_count += 1
                else:
                    hybrid_page_count += 1
        finally:
            doc.close()

        total_pages = len(page_caps)

        # Document-level classification
        if total_pages == 0:
            doc_type = PDFType.SCANNED_PDF
            is_supported = False
            notes = ["Document has 0 pages."]
        elif vector_page_count == total_pages:
            doc_type = PDFType.VECTOR_PDF
            is_supported = True
            notes = [
                f"100% Native Vector PDF: All {total_pages} pages contain native vector linework and searchable text.",
                f"Total vector paths: {total_vectors}, drawing commands: {total_commands}, text characters: {total_chars}.",
            ]
        elif scanned_page_count == total_pages:
            doc_type = PDFType.SCANNED_PDF
            is_supported = False
            notes = [
                f"Scanned / Raster PDF: All {total_pages} pages consist of raster images with zero native vectors.",
                "Native vector QTO pipeline is blocked. Requires OCR / vision reconstruction with REVIEW_REQUIRED.",
            ]
        elif vector_page_count > 0 and scanned_page_count == 0:
            # Mixture of pure vector and hybrid
            doc_type = PDFType.HYBRID_PDF
            is_supported = True
            notes = [
                f"Hybrid Vector PDF: {vector_page_count} vector pages, {hybrid_page_count} hybrid pages.",
                "Native vector geometry available for primary takeoff. Raster underlays detected.",
            ]
        elif vector_page_count > 0 and scanned_page_count > 0:
            doc_type = PDFType.HYBRID_PDF
            is_supported = True
            notes = [
                f"Mixed Sheet Set: {vector_page_count} vector pages, {scanned_page_count} scanned sheets.",
                "Vector pages are eligible for native takeoff; scanned sheets require estimator review.",
            ]
        else:
            doc_type = PDFType.SCANNED_PDF
            is_supported = False
            notes = [
                "Document contains primarily raster image data with minimal or zero native vector primitives.",
                "Marked REVIEW_REQUIRED.",
            ]

        return PDFDocumentCapabilities(
            file_path=file_path,
            file_name=file_name,
            file_size_bytes=file_size,
            source_hash=source_hash,
            page_count=total_pages,
            pdf_type=doc_type,
            total_vector_paths=total_vectors,
            total_drawing_commands=total_commands,
            total_text_chars=total_chars,
            total_images=total_images,
            is_vector_supported=is_supported,
            readiness_notes=notes,
            pages=page_caps,
        )

    def inspect_page(self, page: fitz.Page, page_number: int) -> PDFPageCapabilities:
        """Analyzes a single PDF page's native vector paths, text dictionary, and image list."""
        rect = page.rect
        width_pt = float(rect.width)
        height_pt = float(rect.height)
        rotation = int(page.rotation)

        # 1. Native Vector Drawing Paths
        try:
            drawings = page.get_drawings()
        except Exception:
            drawings = []

        vector_path_count = len(drawings)
        drawing_command_count = 0
        for d in drawings:
            items = d.get("items", [])
            drawing_command_count += len(items)

        # 2. Native Text Extraction
        try:
            text_dict = page.get_text("dict")
        except Exception:
            text_dict = {}

        text_char_count = 0
        text_word_count = 0
        text_block_count = 0

        blocks = text_dict.get("blocks", [])
        for block in blocks:
            # Block type 0 is text, type 1 is image
            if block.get("type") == 0:
                text_block_count += 1
                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        txt = span.get("text", "")
                        text_char_count += len(txt)
                        text_word_count += len(txt.split())

        # 3. Embedded Raster Images
        try:
            image_list = page.get_images(full=True)
            image_count = len(image_list)
        except Exception:
            image_count = 0

        has_native_vectors = vector_path_count > 0
        has_native_text = text_char_count > 0
        has_raster_images = image_count > 0
        is_vector_dense = (
            vector_path_count >= self.MIN_VECTOR_PATHS_FOR_VECTOR_PAGE
            or drawing_command_count >= self.MIN_DRAWING_COMMANDS_FOR_VECTOR_PAGE
        )

        # Classification logic for this individual page
        if has_native_vectors and not has_raster_images:
            page_type = PDFType.VECTOR_PDF
            confidence = 1.0
        elif is_vector_dense and has_raster_images:
            # Check if vector density is very high (typical CAD title block / logo might be a small image)
            if vector_path_count >= 100 or drawing_command_count >= 200:
                page_type = PDFType.VECTOR_PDF
                confidence = 0.95
            else:
                page_type = PDFType.HYBRID_PDF
                confidence = 0.90
        elif not has_native_vectors and has_raster_images:
            page_type = PDFType.SCANNED_PDF
            confidence = 0.98
        elif not has_native_vectors and not has_raster_images and has_native_text:
            # Text-only document (e.g. specification sheet)
            page_type = PDFType.VECTOR_PDF
            confidence = 0.90
        else:
            page_type = PDFType.SCANNED_PDF
            confidence = 0.70

        return PDFPageCapabilities(
            page_number=page_number,
            width_pt=width_pt,
            height_pt=height_pt,
            rotation=rotation,
            vector_path_count=vector_path_count,
            drawing_command_count=drawing_command_count,
            text_char_count=text_char_count,
            text_word_count=text_word_count,
            text_block_count=text_block_count,
            image_count=image_count,
            page_pdf_type=page_type,
            has_native_vectors=has_native_vectors,
            has_native_text=has_native_text,
            has_raster_images=has_raster_images,
            confidence=confidence,
        )
