"""Deterministic parsing of raw OCR tokens into structured blueprint
annotations: room-name labels, dimension strings, drawing scale, and
grid reference bubbles.
"""

import re
from dataclasses import dataclass

from app.ocr.paddle_engine import OcrToken

_DIMENSION_RE = re.compile(r"""^\d{1,3}'(-\d{1,2}(\.\d+)?")?$|^\d{1,3}'-\d{1,2}"$|^\d+(\.\d+)?\s?(ft|'|sf|sq\s?ft)$""", re.IGNORECASE)
_SCALE_RE = re.compile(
    r"""(\d+/\d+|\d+)\s*"?\s*=\s*(\d+)\s*'-?0?"?|\b1\s*:\s*\d+\b|\bSCALE\b""",
    re.IGNORECASE,
)
_GRID_REF_RE = re.compile(r"^[A-Z]\.?\d{1,2}$|^\d{1,2}$")

# --- Trade-tag callouts (material/finish/type codes an estimator marks up per trade) ---
_FLOOR_TAG_RE = re.compile(r"^(CPT|VCT|CT|LVT|WD|EPX)-?\d{1,3}$", re.IGNORECASE)
_WALL_TYPE_RE = re.compile(r"^(WT?\d{1,2}|TYPE\s?[A-Z])$", re.IGNORECASE)
_FIRE_RATING_RE = re.compile(r"^\d\s?-?\s?HR$", re.IGNORECASE)
_PAINT_TAG_RE = re.compile(r"^PT?-?\d{1,3}$", re.IGNORECASE)
_PAINT_FINISH_KEYWORDS = {"EGGSHELL", "SEMI-GLOSS", "SEMI GLOSS", "SATIN", "FLAT", "PRIMER"}
_ROOF_KEYWORDS = {"VENT", "SKYLIGHT", "RIDGE", "HIP", "VALLEY", "FLASHING", "CHIMNEY", "GUTTER", "DOWNSPOUT", "SLOPE"}
_ROOF_SLOPE_RE = re.compile(r"^\d{1,2}\s?[:/]\s?12$")
_ROOF_PERCENT_SLOPE_RE = re.compile(r"^\d{1,3}\s?%$")
_SHEET_REF_RE = re.compile(r"\b(SEE\s+([A-Z]-?\d{3,4})|DETAIL\s+\d+/[A-Z]-?\d{3,4}|SECTION\s+[A-Z]-[A-Z])\b", re.IGNORECASE)
_SYMBOL_RE = re.compile(r"^(EJ|RD|FD|SD|AD|CL|CENTERLINE|BREAKLINE|EXPANSION\s+JOINT|ROOF\s+DRAIN|FLOOR\s+DRAIN)$", re.IGNORECASE)

_ROOM_KEYWORDS = {
    "office", "lobby", "conference", "restroom", "bathroom", "kitchen", "break",
    "storage", "closet", "corridor", "hall", "hallway", "stair", "elevator",
    "mechanical", "electrical", "server", "reception", "lounge", "room",
    "suite", "vestibule", "utility", "janitor",
    # Residential & Architectural labels
    "bedroom", "living", "dining", "garage", "deck", "porch", "patio", "entry",
    "foyer", "bath", "master", "wc", "toilet", "cathedral", "terrace", "balcony",
    "laundry", "pantry", "mudroom", "den", "study", "nook", "attic", "basement",
    # Common architectural abbreviations that appear as printed room labels
    # on real drawings but aren't full words, so they need to be listed
    # explicitly rather than relying on the (removed) "looks like a caption"
    # fallback below.
    "pwdr", "lndry", "ldry",
}

# Text that clearly isn't a room label even though it might contain a keyword —
# ceiling heights, drawing notes, contractor disclaimers, specifications, equipment/hardware notes, and legend text.
_ANNOTATION_RE = re.compile(
    r"\b(PANEL|INTERCOM|HARDWARE|STRIKE|FIXTURE|EQUIPMENT|SWITCH|RECEPTACLE|OUTLET|DIFFUSER|GRILLE|THERMOSTAT|KEYPAD|JUNCTION|TRANSFORMER|CONDUIT|BREAKER|CLG|CEILING|CLNG|AFF|HT|ENSURE|CONTRACTOR|VERIFY|SPECIFICATION|SPECIFICATIONS|WARRANTY|SHALL|DRAWINGS|NOTES?|LEGEND|SCHEDULE|ALL TRADES|DIMENSIONS?)\b",
    re.IGNORECASE,
)


@dataclass
class RoomLabel:
    text: str
    centroid_px: tuple[float, float]
    confidence: float


@dataclass
class DimensionLabel:
    text: str
    feet: float | None
    centroid_px: tuple[float, float]
    confidence: float


@dataclass
class ScaleLabel:
    text: str
    ratio: float | None  # e.g. 1/96 for 1/8"=1'-0"
    centroid_px: tuple[float, float]
    confidence: float


@dataclass
class TradeTagLabel:
    text: str
    trade: str  # matches a TradeKey value: "flooring" | "drywall" | "painting" | "roofing"
    tag_type: str  # short category, e.g. "floor_finish", "wall_type", "paint_finish", "roof_note"
    centroid_px: tuple[float, float]
    confidence: float


def _centroid(bbox_px: list[tuple[float, float]]) -> tuple[float, float]:
    xs = [p[0] for p in bbox_px]
    ys = [p[1] for p in bbox_px]
    return (sum(xs) / len(xs), sum(ys) / len(ys))


def _parse_dimension_feet(text: str) -> float | None:
    match = re.match(r"^(\d+)'-(\d+)(?:\.(\d+))?\"?$", text)
    if match:
        feet, inches = int(match.group(1)), int(match.group(2))
        return round(feet + inches / 12, 2)
    match = re.match(r"^(\d+)'$", text)
    if match:
        return float(match.group(1))
    match = re.match(r"^(\d+(?:\.\d+)?)\s?(?:ft|sf|sq\s?ft)$", text, re.IGNORECASE)
    if match:
        return float(match.group(1))
    return None


# A metric ratio scale is written either "1:100" or "1/100". The slash form
# collides with the imperial fraction form ("1/4\" = 1'-0\""), and the two
# are told apart by the "=": an imperial scale always states what the
# fraction equals, a ratio never does. The denominator bound is a second
# guard, measured against the scales actually in use: architectural
# imperial denominators are 2/4/8/16 (1/16"=1'-0" being the finest in
# normal use), while metric ratios start at 1:20 and run to 1:500. Nothing
# real sits between 16 and 20, so the split cannot misread either form.
_MIN_SLASH_RATIO_DENOMINATOR = 20


def _parse_scale_ratio(text: str) -> float | None:
    """Paper-inches per real-world-inch for a printed scale note, or None
    when the text does not actually state a scale.
    """
    clean_text = text.strip()

    # Strip common leading scale label prefixes
    clean_text = re.sub(r"^(?:PLAN\s+)?(?:ORIGINAL\s+)?SCALE\s*[:=\-]?\s*", "", clean_text, flags=re.IGNORECASE).strip()

    # 1. Colon Ratio Match (e.g. 1:50 or 1:100 or 1:25 or 1:200 or 1:500)
    colon_ratio = re.search(r"\b1\s*:\s*(\d+)\b", clean_text)
    if colon_ratio:
        denominator = float(colon_ratio.group(1))
        if denominator >= 10:
            return 1.0 / denominator

    # 2. Whole inches with fractional inches (e.g. 1-1/2" = 1'-0" or 1 1/2" = 1'-0" or 3" = 1'-0")
    mixed_match = re.search(r"(\d+)\s*[- ]\s*(\d+)\s*/\s*(\d+)\s*\"?\s*[:=]\s*(\d+)", clean_text)
    if mixed_match:
        whole = float(mixed_match.group(1))
        num = float(mixed_match.group(2))
        den = float(mixed_match.group(3))
        feet = float(mixed_match.group(4))
        if den > 0 and feet > 0:
            inch_val = whole + (num / den)
            return inch_val / (12.0 * feet)

    # 3. Fractional Match with equals (e.g. 1/4" = 1'-0", 1/8"=1'-0", 3/16" = 1', 1/16" = 1'-0", 3/32" = 1'-0")
    has_equals = "=" in clean_text
    frac_match = re.search(r"(\d+)\s*/\s*(\d+)", clean_text)

    if frac_match and has_equals:
        numerator, denominator = int(frac_match.group(1)), int(frac_match.group(2))
        if denominator <= 0:
            return None
        inch_fraction = numerator / denominator
        right_side = clean_text.split("=")[1]
        feet_match = re.search(r"(\d+)", right_side)
        feet = float(feet_match.group(1)) if feet_match else 1.0
        return inch_fraction / (12.0 * feet) if feet > 0 else None

    # 4. Ratio written with a slash and no "=" (e.g. "SC 1/100").
    if frac_match and not has_equals:
        numerator, denominator = int(frac_match.group(1)), int(frac_match.group(2))
        if numerator == 1 and denominator >= _MIN_SLASH_RATIO_DENOMINATOR:
            return 1.0 / float(denominator)
        return None

    # 5. Whole Number Match (e.g. 1" = 10'-0" or 1" = 20' or 1" = 30' or 1" = 40' or 1" = 50')
    inch_match = re.search(r"(\d+)\s*\"?\s*[:=]\s*(\d+)", clean_text)
    if inch_match:
        inches = float(inch_match.group(1))
        feet = float(inch_match.group(2))
        return inches / (12.0 * feet) if feet > 0 else None

    return None


def _classify_trade_tag(text: str) -> tuple[str, str] | None:
    """Match a token against per-trade callout patterns. Returns
    (trade, tag_type) for the first trade whose pattern matches, or None.
    """
    upper = text.strip().upper()

    if _FLOOR_TAG_RE.match(upper):
        return ("flooring", "floor_finish")

    if _WALL_TYPE_RE.match(upper) or _FIRE_RATING_RE.match(upper):
        return ("drywall", "wall_type")

    if _PAINT_TAG_RE.match(upper) or upper in _PAINT_FINISH_KEYWORDS:
        return ("painting", "paint_finish")

    if upper in _ROOF_KEYWORDS or _ROOF_SLOPE_RE.match(upper) or _ROOF_PERCENT_SLOPE_RE.match(upper):
        return ("roofing", "roof_note")

    if _SYMBOL_RE.match(upper):
        return ("drywall", "symbol_callout")

    return None


# A room name that's more than one printed word ("Pool Office", "Emergency
# Exit") arrives from OCR as separate single-word tokens with no relation
# between them. Testing each word against _ROOM_KEYWORDS independently
# means a qualifier that isn't itself a room word ("Pool") is silently
# dropped whenever its neighbor ("Office") is — verified on a real sheet:
# every "Pool Office" on the drawing became a bare "Office" in the room
# list, because "pool" never matched the keyword set on its own. Merging
# adjacent same-line candidates into one phrase before the keyword test
# means the room keeps the drafter's actual name instead of a hard-coded
# substring inside it.
#
# Threshold picked from the real gap between "Pool" and "Office" on that
# sheet: 11px between them against a 44px token height (ratio 0.25) — a
# same-line, same-label pair sits far closer together than the gap to an
# unrelated neighboring label, so this stays well clear of both without
# being tuned to the exact figure.
_ROOM_LABEL_MERGE_GAP_RATIO = 0.6

# Two tokens are only "the same printed line" if they're close to the same
# text size and vertically centered on each other — verified necessary on
# a real residential plan, where an unrelated door-symbol annotation
# ("BARN DR", misread as "BAN VR") sat in the gap between two genuinely
# different rooms' labels ("M. BATH" and "M. BEDROOM") and bridged them
# into one nonsense phrase. That annotation's OCR box was 95px tall against
# the room labels' 34px — nothing at real room-label scale is ever that
# size-mismatched, so gating on size ratio rejects the bridge outright
# without needing to special-case door symbols specifically.
_ROOM_LABEL_MAX_HEIGHT_RATIO = 1.6
_ROOM_LABEL_MAX_CENTER_OFFSET_RATIO = 0.35


def _merge_adjacent_room_candidates(
    candidates: list[tuple[str, tuple[float, float, float, float], float]],
) -> list[tuple[str, tuple[float, float], float]]:
    """Merge same-line, closely-spaced, similar-size candidate tokens into
    phrases.

    Each candidate is (text, (x0, y0, x1, y1), confidence). Returns
    (merged_text, centroid_px, min_confidence) per phrase, left to right.

    Deliberately does not grow a merged phrase's own bounding box out to
    absorb an outlier neighbor's height before testing the *next* token —
    every candidate is compared against its immediate neighbor's own box,
    so one already-rejected tall annotation can never widen the "same
    line" window for the word after it.
    """
    remaining = sorted(candidates, key=lambda c: (c[1][1], c[1][0]))
    phrases: list[tuple[str, tuple[float, float], float]] = []

    while remaining:
        text, (x0, y0, x1, y1), conf = remaining.pop(0)
        phrase_words = [text]
        phrase_conf = conf
        bx0, by0, bx1, by1 = x0, y0, x1, y1

        merged_any = True
        while merged_any:
            merged_any = False
            height = by1 - by0
            y_center = (by0 + by1) / 2
            for i, (ctext, (cx0, cy0, cx1, cy1), cconf) in enumerate(remaining):
                c_height = cy1 - cy0
                if height <= 0 or c_height <= 0:
                    continue
                size_ratio = max(height, c_height) / min(height, c_height)
                if size_ratio > _ROOM_LABEL_MAX_HEIGHT_RATIO:
                    continue

                min_height = min(height, c_height)
                c_center = (cy0 + cy1) / 2
                if abs(y_center - c_center) > min_height * _ROOM_LABEL_MAX_CENTER_OFFSET_RATIO:
                    continue

                gap = cx0 - bx1
                if not (0 <= gap <= min_height * _ROOM_LABEL_MERGE_GAP_RATIO):
                    continue

                phrase_words.append(ctext)
                phrase_conf = min(phrase_conf, cconf)
                bx0, by0, bx1, by1 = min(bx0, cx0), min(by0, cy0), max(bx1, cx1), max(by1, cy1)
                remaining.pop(i)
                merged_any = True
                break

        phrases.append((" ".join(phrase_words), ((bx0 + bx1) / 2, (by0 + by1) / 2), phrase_conf))

    return phrases


def classify_tokens(tokens: list[OcrToken]) -> dict[str, list]:
    """Bucket raw OCR tokens into room labels, dimensions, scale
    annotations, trade-tag callouts, and grid references using
    deterministic pattern rules.
    """
    rooms: list[RoomLabel] = []
    dimensions: list[DimensionLabel] = []
    scales: list[ScaleLabel] = []
    grid_refs: list[str] = []
    trade_tags: list[TradeTagLabel] = []
    room_candidates: list[tuple[str, tuple[float, float, float, float], float]] = []

    for token in tokens:
        text = token.text.strip()
        if not text:
            continue
        centroid = _centroid(token.bbox_px)

        if _SCALE_RE.search(text):
            scales.append(ScaleLabel(text=text, ratio=_parse_scale_ratio(text), centroid_px=centroid, confidence=token.confidence))
            continue

        if _DIMENSION_RE.match(text):
            dimensions.append(
                DimensionLabel(text=text, feet=_parse_dimension_feet(text), centroid_px=centroid, confidence=token.confidence)
            )
            continue

        trade_match = _classify_trade_tag(text)
        if trade_match:
            trade, tag_type = trade_match
            trade_tags.append(
                TradeTagLabel(text=text, trade=trade, tag_type=tag_type, centroid_px=centroid, confidence=token.confidence)
            )
            continue

        if _GRID_REF_RE.match(text) and len(text) <= 3:
            grid_refs.append(text)
            continue

        sheet_ref = _SHEET_REF_RE.search(text)
        if sheet_ref:
            grid_refs.append(f"REF:{sheet_ref.group(0)}")
            continue

        if _ANNOTATION_RE.search(text):
            continue

        alpha_only = re.sub(r"[^a-zA-Z ]", "", text).strip()
        if len(alpha_only) >= 3:
            xs = [p[0] for p in token.bbox_px]
            ys = [p[1] for p in token.bbox_px]
            room_candidates.append((text, (min(xs), min(ys), max(xs), max(ys)), token.confidence))

    # A token is a room label only if its merged phrase actually names a
    # room — substring match against a known room-word/abbreviation list.
    #
    # This used to also accept ANY short (<=3 word) all-caps text as a room
    # name, on the theory that room labels are usually printed that way. So
    # is almost every other short architectural callout: appliance tags
    # ("MICRO", "TRASH", "FARM SNK"), ceiling heights, fixture notes. Those
    # got assigned as the "name" of whatever polygon happened to be
    # nearest, which is exactly what produced room lists full of "Micro",
    # "Trash", "Farm Snk".
    for phrase_text, phrase_centroid, phrase_conf in _merge_adjacent_room_candidates(room_candidates):
        if _ANNOTATION_RE.search(phrase_text) or len(phrase_text.split()) > 4:
            continue
        lowered = phrase_text.lower()
        if any(keyword in lowered for keyword in _ROOM_KEYWORDS):
            rooms.append(RoomLabel(text=phrase_text.title(), centroid_px=phrase_centroid, confidence=phrase_conf))

    return {"rooms": rooms, "dimensions": dimensions, "scales": scales, "grid_refs": grid_refs, "trade_tags": trade_tags}
