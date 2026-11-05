"""PDF ingestion: extract page metadata, rasterize pages to PNG at a
fixed working DPI, and generate thumbnails. Backed by PyMuPDF (fitz).
"""

from dataclasses import dataclass

import fitz  # PyMuPDF

from app.geometry.page_classifier import extract_sheet_number_from_page

WORKING_DPI = 300  # Ceiling DPI — used as-is for normal sheet sizes (Letter through ARCH C)
MIN_WORKING_DPI = 200  # Floor DPI — large sheets never drop below this or lines get too thin to detect
MAX_RASTER_LONG_EDGE_PX = 8000  # Pixel budget for the page's longer edge, regardless of physical sheet size
THUMBNAIL_DPI = 44


@dataclass
class RasterizedPage:
    page_number: int  # 1-indexed
    width_px: int
    height_px: int
    dpi: int
    image_path: str
    thumbnail_path: str
    # Real title-block-extracted sheet number (e.g. "A-101"), or None when it
    # genuinely could not be read from this page's own text layer. NEVER a
    # page-index-derived placeholder ("A101" because this was page 1) —
    # callers must render "Not available from source" for None, not guess.
    sheet_code: str | None
    sheet_code_confidence: float
    sheet_name: str


def open_document(pdf_path: str) -> fitz.Document:
    return fitz.open(pdf_path)


def get_page_count(pdf_path: str) -> int:
    with fitz.open(pdf_path) as doc:
        return doc.page_count


def compute_adaptive_dpi(width_pt: float, height_pt: float) -> int:
    """Large architectural sheets (ARCH D/E, ~30-40in on the long edge)
    rasterized at a flat 300 DPI become 8000-10000px wide images — Canny
    + Hough line extraction on one such page alone takes several seconds,
    and a multi-page set can take minutes of synchronous CPU time. This
    caps the *pixel* budget instead of the DPI, so a Letter-size sheet
    still gets full 300 DPI precision while an ARCH D/E sheet is rendered
    at a lower DPI that keeps its pixel count (and processing time) in
    the same ballpark — never below MIN_WORKING_DPI, or wall lines get
    too thin for Hough to pick up reliably.
    
    If the sheet is so large that even rendering at MIN_WORKING_DPI would
    exceed MAX_RASTER_LONG_EDGE_PX, we bypass the floor and use the exact
    DPI that fits the pixel budget to prevent 'Overly large image' crashes.
    """
    long_edge_in = max(width_pt, height_pt) / 72.0
    if long_edge_in <= 0:
        return WORKING_DPI
    dpi = MAX_RASTER_LONG_EDGE_PX / long_edge_in
    if long_edge_in * MIN_WORKING_DPI > MAX_RASTER_LONG_EDGE_PX:
        return int(round(min(WORKING_DPI, dpi)))
    return int(round(min(WORKING_DPI, max(MIN_WORKING_DPI, dpi))))


def rasterize_page(
    pdf_path: str,
    page_index: int,
    image_out_path: str,
    thumbnail_out_path: str,
) -> RasterizedPage:
    """Render one PDF page to a full-resolution PNG and a lightweight
    thumbnail PNG. Returns pixel dimensions and inferred sheet metadata.
    """
    with fitz.open(pdf_path) as doc:
        page = doc.load_page(page_index)

        working_dpi = compute_adaptive_dpi(page.rect.width, page.rect.height)

        matrix = fitz.Matrix(working_dpi / 72, working_dpi / 72)
        pixmap = page.get_pixmap(matrix=matrix, alpha=False)
        pixmap.save(image_out_path)

        thumb_matrix = fitz.Matrix(THUMBNAIL_DPI / 72, THUMBNAIL_DPI / 72)
        thumb_pixmap = page.get_pixmap(matrix=thumb_matrix, alpha=False)
        thumb_pixmap.save(thumbnail_out_path)

        # Real evidence only — no page-index-derived guess ("page 3 -> A103").
        # Sheet title text (not the code) can still be provisionally labeled
        # by position since it's purely descriptive and re-derived properly
        # from full page text later in BlueprintSheetClassifier.
        sheet_name = "Floor Plan" if page_index == 0 else f"Sheet {page_index + 1}"
        sheet_code, sheet_code_confidence = extract_sheet_number_from_page(page)

        return RasterizedPage(
            page_number=page_index + 1,
            width_px=pixmap.width,
            height_px=pixmap.height,
            dpi=working_dpi,
            image_path=image_out_path,
            thumbnail_path=thumbnail_out_path,
            sheet_code=sheet_code,
            sheet_code_confidence=sheet_code_confidence,
            sheet_name=sheet_name,
        )
