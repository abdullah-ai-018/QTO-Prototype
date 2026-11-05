"""End-to-end OCR pipeline for a single page: run PaddleOCR, classify
tokens, and cross-validate against the geometry engine's output.
"""

from dataclasses import dataclass

from app.geometry.engine import GeometryResult
from app.ocr.paddle_engine import OcrToken, run_ocr
from app.ocr.parsers import ScaleLabel, TradeTagLabel, classify_tokens
from app.ocr.validator import OcrValidationResult, validate


@dataclass
class OcrPipelineResult:
    room_name_overrides: dict[int, str]
    dimension_flags: list[dict]
    detected_scale: ScaleLabel | None
    grid_refs: list[str]
    trade_tags: list[TradeTagLabel]
    token_count: int


def run_ocr_pipeline(
    image_path: str,
    geometry: GeometryResult,
    scale_ft_per_px: float,
    image_w: int,
    image_h: int,
    tokens: list[OcrToken] | None = None,
    pdf_path: str | None = None,
    page_number: int | None = None,
) -> OcrPipelineResult:
    """If `tokens` is omitted, OCR is run fresh on `image_path` — but
    callers that already ran OCR once for this page (e.g. for scale
    detection) should pass those tokens through to avoid paying the
    (slow) OCR inference cost twice per page.

    `pdf_path`/`page_number`, when this is a genuine PDF source, let the
    fresh-OCR path read the PDF's own text layer directly instead of
    running PaddleOCR against the rasterized page image — see
    paddle_engine.run_ocr's docstring for why that matters.
    """
    if tokens is None:
        tokens = run_ocr(image_path, pdf_path=pdf_path, page_number=page_number)
    classified = classify_tokens(tokens)
    validation: OcrValidationResult = validate(geometry, classified, scale_ft_per_px, image_w, image_h)

    best_scale = max(classified["scales"], key=lambda s: s.confidence, default=None)

    return OcrPipelineResult(
        room_name_overrides=validation.room_name_overrides,
        dimension_flags=validation.dimension_flags,
        detected_scale=best_scale,
        grid_refs=classified["grid_refs"],
        trade_tags=classified["trade_tags"],
        token_count=len(tokens),
    )
