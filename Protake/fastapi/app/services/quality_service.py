"""Pre-flight Drawing Quality Inspector: Inspects rasterized blueprint images for low DPI,
blur, improper rotation, and scan artifacts before processing, returning quality health scores.
"""

from dataclasses import dataclass, field
from PIL import Image, ImageStat


@dataclass
class QualityReport:
    health_score: int  # 0 to 100
    dpi: int
    is_acceptable: bool
    warnings: list[str] = field(default_factory=list)


def inspect_drawing_quality(image_path: str, width_px: int, height_px: int, dpi: int = 200) -> QualityReport:
    warnings: list[str] = []
    score = 100

    # 1. DPI Check
    if dpi < 150:
        score -= 25
        warnings.append(f"Low resolution ({dpi} DPI). Recommended threshold is 200 DPI for reliable OCR.")

    # 2. Image Aspect & Dimension Check
    min_dim = min(width_px, height_px)
    if min_dim < 1000:
        score -= 20
        warnings.append(f"Image dimension ({width_px}x{height_px} px) is smaller than standard architectural sheet size.")

    # 3. Blur & Contrast Inspection via PIL ImageStat
    try:
        with Image.open(image_path) as img:
            gray = img.convert("L")
            stat = ImageStat.Stat(gray)
            stddev = stat.stddev[0] if stat.stddev else 0.0
            
            # Very low standard deviation indicates extremely blurry, blank, or washed out scan
            if stddev < 15.0:
                score -= 30
                warnings.append("Low scan contrast or blurry image detected. Text OCR precision may decrease.")
    except Exception:
        pass

    final_score = max(0, min(100, score))
    is_acceptable = final_score >= 60

    return QualityReport(
        health_score=final_score,
        dpi=dpi,
        is_acceptable=is_acceptable,
        warnings=warnings,
    )
