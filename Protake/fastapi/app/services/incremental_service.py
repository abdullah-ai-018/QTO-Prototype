"""Incremental Processing Service: Reprocesses only specified single page numbers
(e.g. Sheet A-103) upon drawing revision updates instead of reprocessing the entire PDF.
"""

from sqlalchemy.orm import Session
from app.models.page import Page
from app.repositories.page_repository import PageRepository
from app.services.analysis_service import AnalysisService


def reprocess_single_page(db: Session, page_id: int) -> dict[str, str | int | bool]:
    page = PageRepository(db).get_or_404(page_id)

    analysis = AnalysisService(db)

    # 1. Recompute Geometry Analysis for this single sheet
    analysis._recompute_geometry(page)

    # 2. Run OCR & AI Validation pass
    analysis.run_ocr(page)
    analysis.run_ai_validation(page)

    return {
        "page_id": page.id,
        "page_number": page.page_number,
        "sheet_code": page.sheet_code or f"Page-{page.page_number}",
        "reprocessed": True,
        "status": "Incremental reprocessing completed successfully.",
    }
