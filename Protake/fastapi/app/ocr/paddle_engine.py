"""PaddleOCR wrapper.

The model is heavy (downloads detection + recognition weights on first
use) so it is imported and instantiated lazily, once, on first real
request — never at module import time. If PaddleOCR/paddlepaddle isn't
installed or fails to load, callers get a clear `OcrUnavailableError`
instead of the whole API failing to boot.
"""

import concurrent.futures
from dataclasses import dataclass
from functools import lru_cache

from app.config import get_settings

settings = get_settings()

# PaddleOCR inference cost scales with pixel count, not drawing detail —
# text recognition doesn't need the full 300 DPI / up-to-6000px geometry
# raster. Downscaling to this before inference cuts CPU inference time
# dramatically on large sheets without meaningfully hurting recognition.
OCR_MAX_LONG_EDGE_PX = 1600

# Hard ceiling on a single OCR call. PaddleOCR releases the GIL during
# inference, so a background thread lets the caller give up and move on
# to the next page instead of hanging the whole blueprint forever if a
# page is pathologically slow (or the model call stalls).
#
# Measured directly against a real 2400x1328 sheet (downscaled to
# OCR_MAX_LONG_EDGE_PX before inference): CPU inference took ~82s. The
# previous 60s ceiling was below that on ordinary hardware, so OCR timed
# out on essentially every real upload — silently returning zero tokens
# every time, in production, while direct test scripts (run without this
# wrapper, or with a much longer shell-level timeout) always looked fine.
# That meant text-masking, scale auto-detection, and room naming were
# never actually running against real uploads despite testing clean.
# 180s leaves real margin above the measured worst case rather than
# matching it, since a loaded background worker will be slower still.
OCR_TIMEOUT_SECONDS = 180

_ocr_executor = concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix="ocr")


class OcrUnavailableError(RuntimeError):
    pass


class OcrTimeoutError(RuntimeError):
    pass


@dataclass
class OcrToken:
    text: str
    confidence: float
    bbox_px: list[tuple[float, float]]  # 4 corner points


@lru_cache(maxsize=1)
def _get_ocr_engine():
    try:
        from paddleocr import PaddleOCR
    except ImportError as exc:  # pragma: no cover - exercised only without the dep installed
        raise OcrUnavailableError(
            "paddleocr is not installed. Run `pip install paddleocr paddlepaddle` to enable OCR."
        ) from exc

    try:
        # Blueprint pages are already-upright rasterized PDF pages, so the
        # document-orientation/unwarping/textline-orientation sub-models
        # are unnecessary overhead — skip them. `enable_mkldnn=False` works
        # around a paddlepaddle oneDNN/PIR CPU-inference bug
        # (ConvertPirAttribute2RuntimeAttribute not supported for the
        # PP-OCRv6 detection model's array-of-doubles attributes) seen on
        # this platform; pure-CPU inference is slower but correct.
        return PaddleOCR(
            lang=settings.ocr_lang,
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,
            enable_mkldnn=False,
        )
    except Exception as exc:  # pragma: no cover - environment-dependent
        raise OcrUnavailableError(f"Failed to initialize PaddleOCR: {exc}") from exc


def _run_paddle_ocr_inference(image_path: str) -> list[OcrToken]:
    """Downscale to OCR_MAX_LONG_EDGE_PX before inference (speed), then
    scale recognized token boxes back up to the original image's pixel
    space so callers can keep comparing them against full-res geometry.
    """
    import cv2

    engine = _get_ocr_engine()

    original = cv2.imread(image_path, cv2.IMREAD_COLOR)
    if original is None:
        raise OcrUnavailableError(f"Could not read image for OCR: {image_path}")

    h, w = original.shape[:2]
    long_edge = max(h, w)
    scale = 1.0
    ocr_input = image_path
    if long_edge > OCR_MAX_LONG_EDGE_PX:
        scale = OCR_MAX_LONG_EDGE_PX / long_edge
        resized = cv2.resize(original, (max(1, round(w * scale)), max(1, round(h * scale))), interpolation=cv2.INTER_AREA)
        ocr_input = resized

    results = engine.predict(ocr_input)
    inv_scale = 1.0 / scale

    tokens: list[OcrToken] = []
    for page_result in results or []:
        texts = page_result.get("rec_texts") or []
        scores = page_result.get("rec_scores") or []
        polys = page_result.get("rec_polys") or page_result.get("dt_polys") or []

        for text, score, poly in zip(texts, scores, polys):
            text = (text or "").strip()
            if not text:
                continue
            tokens.append(
                OcrToken(
                    text=text,
                    confidence=float(score),
                    bbox_px=[(float(x) * inv_scale, float(y) * inv_scale) for x, y in poly],
                )
            )
    return tokens


def _run_paddle_ocr_with_timeout(image_path: str) -> list[OcrToken]:
    future = _ocr_executor.submit(_run_paddle_ocr_inference, image_path)
    return future.result(timeout=OCR_TIMEOUT_SECONDS)


def run_ocr(
    image_path: str, pdf_path: str | None = None, page_number: int | None = None
) -> list[OcrToken]:
    """Run OCR over a rasterized page image and return every recognized
    text token with its confidence and pixel-space bounding polygon.

    `pdf_path`/`page_number` (both required together) let this skip
    PaddleOCR entirely for a genuine PDF source: the ORIGINAL PDF's own
    text layer is read directly (native PyMuPDF word extraction — no ML
    model, ~0.01s) instead of re-reading text out of pixels.

    This used to be attempted against `image_path` — the *rasterized PNG*
    render of the page — which has no text layer at all (verified: 0 words
    from the PNG vs 653 words from the real PDF page on the same sheet),
    so this fast path silently returned nothing on every real call and
    every PDF upload paid full PaddleOCR cost (measured 82-180+s/page on a
    dense sheet) for text that was sitting right there in the source file.
    """
    if not settings.ocr_enabled:
        return []

    tokens: list[OcrToken] = []

    # Method 1: Instant PyMuPDF word extraction from the ORIGINAL PDF
    # (0.01s, zero model loading) — only possible when the upload actually
    # was a PDF (pdf_path/page_number given). An image-only upload (a scan,
    # a photo, a screenshot) has no such source and falls through to
    # PaddleOCR below, same as before this existed.
    if pdf_path and page_number:
        try:
            import cv2
            import fitz  # type: ignore # noqa: F401

            raster = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
            doc = fitz.open(pdf_path)
            src_page = doc[page_number - 1]
            page_w_pt, page_h_pt = src_page.rect.width, src_page.rect.height
            if raster is not None and page_w_pt > 0 and page_h_pt > 0:
                img_h, img_w = raster.shape[:2]
                scale_x, scale_y = img_w / page_w_pt, img_h / page_h_pt
                for x0, y0, x1, y1, text, *_ in src_page.get_text("words"):
                    text = text.strip()
                    if not text:
                        continue
                    px0, py0, px1, py1 = x0 * scale_x, y0 * scale_y, x1 * scale_x, y1 * scale_y
                    tokens.append(
                        OcrToken(
                            text=text,
                            confidence=0.95,
                            bbox_px=[(px0, py0), (px1, py0), (px1, py1), (px0, py1)],
                        )
                    )
            if tokens:
                return tokens
        except Exception:
            tokens = []

    # Method 2: Heavy PaddleOCR (downloads & initializes deep learning weights if needed)
    try:
        tokens = _run_paddle_ocr_with_timeout(image_path)
        if tokens:
            return tokens
    except concurrent.futures.TimeoutError:
        print(f"[Protake OCR] PaddleOCR timed out after {OCR_TIMEOUT_SECONDS}s on {image_path} — skipping OCR for this page")
    except Exception as exc:
        print(f"[Protake OCR] PaddleOCR notice: {exc}")

    # Method 3: PyTesseract (if installed)
    try:
        import pytesseract  # type: ignore # noqa: F401
        from PIL import Image
        img = Image.open(image_path)
        data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
        n_boxes = len(data.get("text", []))
        for i in range(n_boxes):
            text = str(data["text"][i]).strip()
            conf = float(data["conf"][i]) if "conf" in data else 80.0
            if text and conf > 20:
                x, y, w, h = data["left"][i], data["top"][i], data["width"][i], data["height"][i]
                tokens.append(
                    OcrToken(
                        text=text,
                        confidence=conf / 100.0,
                        bbox_px=[(float(x), float(y)), (float(x + w), float(y)), (float(x + w), float(y + h)), (float(x), float(y + h))],
                    )
                )
    except Exception:
        pass

    return tokens
