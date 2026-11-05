"""Detail/Section Callout Resolver.

Parses drawing "N/SHEET" detail-bubble callouts (e.g. "3/A401" meaning
"see detail 3 on sheet A401") near a wall, and resolves the referenced
sheet against the drawing set's actual pages — following exactly the same
spatial-text-matching approach as app/geometry/wall_tags.py's wall-tag
resolver.

Resolution is honest by construction: a callout whose sheet doesn't exist
in this drawing set is flagged REFERENCE_UNRESOLVED, never silently
dropped or guessed at.
"""

import re
from typing import Any

# "3/A401", "5/A-502", "12 / A601" — detail number, slash, sheet code, all
# in a single text run. Real drawings sometimes write it this way (e.g. in
# a general note), but a true detail-bubble callout on a floor plan almost
# never does — see the word-pair matcher below for that real-world shape.
DETAIL_CALLOUT_PATTERN = re.compile(
    r"\b(\d{1,3})\s*/\s*([A-Z]{1,3}-?\d{3,4})\b",
    re.IGNORECASE,
)

# A real detail bubble (a circle split by a horizontal line, detail number
# on top, sheet number on the bottom) does NOT produce one text run when a
# PDF's text layer is extracted — it produces two SEPARATE, tightly stacked
# word tokens. Confirmed directly against a real 18-page architectural set:
# raw extracted text reads "...1\nS302\n1\nS302\n1\nS301..." — repeated
# bare-number / sheet-code pairs, never a single "1/S302" run. These two
# patterns identify each half of that pair so they can be matched by
# proximity in extract_detail_callouts_from_text.
_BARE_NUMBER_PATTERN = re.compile(r"^\d{1,3}$")
_SHEET_CODE_TOKEN_PATTERN = re.compile(r"^[A-Z]{1,3}-?\d{1,4}\.?\d{0,2}$", re.IGNORECASE)
# Common short tokens that syntactically match the sheet-code shape but are
# never actually one (unit/abbreviation noise) — excluded to cut down
# obvious false positives from the proximity heuristic below.
_SHEET_CODE_TOKEN_EXCLUDE = {"NO", "OC", "AFF", "GA", "HR", "MIN", "MAX"}
# Real bubbles stack their two halves immediately on top of each other —
# deliberately tight so this doesn't start pairing unrelated nearby numbers
# (room numbers, dimension strings) with unrelated sheet-code-like text.
_WORD_PAIR_MAX_DIST = 0.015


def _is_bare_number(text: str) -> bool:
    return bool(_BARE_NUMBER_PATTERN.match(text.strip()))


def _is_sheet_code_token(text: str) -> bool:
    t = text.strip().upper()
    if t in _SHEET_CODE_TOKEN_EXCLUDE:
        return False
    return bool(_SHEET_CODE_TOKEN_PATTERN.match(t)) and any(c.isdigit() for c in t)

# Same height-annotation shape as app/trades/drywall.py's _resolve_project_height_ft
# HT_PATTERN — kept in sync deliberately so a callout-scoped match and the
# project-wide scan agree on what counts as a height annotation.
_HEIGHT_PATTERN = re.compile(
    r"(\d{1,2})['\-](\d{0,2})\s*\"?\s*(?:AFF|A\.F\.F\.|CLG|CEILING|T\.O\.\s*WALL|T\.O\.\s*PLATE|DECK|CLR)",
    re.IGNORECASE,
)


def normalize_sheet_ref(sheet_ref: str) -> str:
    """Uppercase and strip separators so "A401" / "A-401" / "A 401" all
    resolve to the same key. Used both when indexing detail sheets into
    ProjectBlueprintIndex.detail_sheets and when resolving a callout's
    sheet reference against that index.
    """
    return re.sub(r"[\s\-]", "", sheet_ref.upper())


def extract_detail_callouts_from_text(
    text_items: list[tuple[float, float, float, float, str]],
) -> list[dict[str, Any]]:
    """Extracts all detail-bubble callouts with normalized spatial bounding
    boxes — same output shape as WallTagResolver.extract_wall_tags_from_text
    so the same nearest-match logic pattern applies. Two independent match
    methods, since real drawings use both shapes:
      1. A single text run like "3/A401" (rare on a floor plan itself, but
         does occur in notes).
      2. Two separate, tightly-stacked word tokens — a bare number and a
         sheet code — which is how a real detail-bubble callout actually
         extracts from a PDF's text layer.
    """
    found: list[dict[str, Any]] = []

    # Method 1: single-token "N/SHEET" run.
    for x0, y0, x1, y1, text in text_items:
        match = DETAIL_CALLOUT_PATTERN.search(text.strip())
        if not match:
            continue
        detail_num = match.group(1)
        sheet_ref = match.group(2).upper()
        ref_type = "SECTION_REFERENCE" if (sheet_ref.startswith("S") or "SEC" in sheet_ref) else "DETAIL_REFERENCE"
        found.append({
            "detail_num": detail_num,
            "sheet_ref": sheet_ref,
            "sheet_ref_normalized": normalize_sheet_ref(sheet_ref),
            "callout": f"{detail_num}/{sheet_ref}",
            "reference_type": ref_type,
            "center": ((x0 + x1) / 2.0, (y0 + y1) / 2.0),
            "bbox": (x0, y0, x1, y1),
            "text": text.strip(),
            "match_method": "slash_token",
        })

    # Method 2: adjacent bare-number + sheet-code word pair (the real
    # detail-bubble shape). Each bare number is paired with its single
    # nearest sheet-code-like token, only when that pair is tightly stacked
    # (real bubbles render as two nearly-coincident tokens, not scattered
    # ones) — this keeps the heuristic from pairing unrelated numbers
    # (room numbers, dimension strings) with unrelated sheet-code text
    # elsewhere on a busy sheet.
    numbers = [(x0, y0, x1, y1, text.strip()) for x0, y0, x1, y1, text in text_items if _is_bare_number(text)]
    codes = [(x0, y0, x1, y1, text.strip().upper()) for x0, y0, x1, y1, text in text_items if _is_sheet_code_token(text)]

    for nx0, ny0, nx1, ny1, num_text in numbers:
        ncx, ncy = (nx0 + nx1) / 2.0, (ny0 + ny1) / 2.0
        best_sheet_ref: str | None = None
        best_dist = float("inf")
        for cx0, cy0, cx1, cy1, code_text in codes:
            ccx, ccy = (cx0 + cx1) / 2.0, (cy0 + cy1) / 2.0
            dist = ((ncx - ccx) ** 2 + (ncy - ccy) ** 2) ** 0.5
            if dist < best_dist:
                best_dist = dist
                best_sheet_ref = code_text
        if best_sheet_ref is not None and best_dist <= _WORD_PAIR_MAX_DIST:
            ref_type = "SECTION_REFERENCE" if (best_sheet_ref.startswith("S") or "SEC" in best_sheet_ref) else "DETAIL_REFERENCE"
            found.append({
                "detail_num": num_text,
                "sheet_ref": best_sheet_ref,
                "sheet_ref_normalized": normalize_sheet_ref(best_sheet_ref),
                "callout": f"{num_text}/{best_sheet_ref}",
                "reference_type": ref_type,
                "center": (ncx, ncy),
                "bbox": (nx0, ny0, nx1, ny1),
                "text": f"{num_text} {best_sheet_ref}",
                "match_method": "word_pair",
            })

    return found


def find_nearest_callout(
    wall_loc: tuple[float, float] | tuple[tuple[float, float], tuple[float, float]],
    callouts: list[dict[str, Any]],
    max_dist: float = 0.08,
) -> dict[str, Any] | None:
    """Finds the nearest detail callout to a wall (point or segment),
    within max_dist normalized units. Same perpendicular-distance-to-segment
    logic as WallTagResolver.match_tag_to_wall (app/geometry/wall_tags.py),
    duplicated rather than imported to avoid refactoring that tested,
    already-shipped resolver.
    """
    best_item: dict[str, Any] | None = None
    best_dist = float("inf")

    is_segment = isinstance(wall_loc, tuple) and len(wall_loc) == 2 and isinstance(wall_loc[0], (tuple, list))

    for item in callouts:
        tc = item["center"]
        if is_segment:
            p1, p2 = wall_loc
            dx = p2[0] - p1[0]
            dy = p2[1] - p1[1]
            l2 = dx * dx + dy * dy
            if l2 == 0.0:
                dist = ((tc[0] - p1[0]) ** 2 + (tc[1] - p1[1]) ** 2) ** 0.5
            else:
                t = max(0.0, min(1.0, ((tc[0] - p1[0]) * dx + (tc[1] - p1[1]) * dy) / l2))
                proj_x = p1[0] + t * dx
                proj_y = p1[1] + t * dy
                dist = ((tc[0] - proj_x) ** 2 + (tc[1] - proj_y) ** 2) ** 0.5
        else:
            dist = ((wall_loc[0] - tc[0]) ** 2 + (wall_loc[1] - tc[1]) ** 2) ** 0.5

        if dist < best_dist and dist <= max_dist:
            best_dist = dist
            best_item = item

    return best_item


# ── Engineering-info extraction from a resolved detail/section sheet's text ──
#
# Each pattern mirrors the proven regex shapes already used in
# app/intelligence/schedule_parser.py for tabular partition-schedule rows,
# adapted for free-form detail-sheet prose. Verified directly against real
# architectural legend text (not only synthetic fixtures) — see
# tests/test_detail_callout_resolution.py.

_THICKNESS_PATTERN = re.compile(
    r"(\d{1,2}(?:[\s\-]\d/\d)?)\s*\"\s*(?:WALL|PARTITION)\b", re.IGNORECASE,
)
_STUD_DEPTH_PATTERN = re.compile(
    r"(\d{1,2}(?:[\s\-]\d/\d)?)\s*\"\s*(?:\d{1,2}\s*GA\s+)?(?:GAL'?V\.?\s+)?(?:METAL\s+|STEEL\s+|WOOD\s+)?STUDS?",
    re.IGNORECASE,
)
_STUD_GAUGE_PATTERN = re.compile(r"\b(\d{1,2})\s*GA\b", re.IGNORECASE)
_STUD_SPACING_PATTERN = re.compile(r"@\s*(\d{1,2})\s*\"\s*O\.?\s*C\.?", re.IGNORECASE)
_BOARD_PATTERN = re.compile(
    r"(\d{1,2}/\d{1,2})\s*\"\s*(TYPE\s*X\s*)?GYP\.?\s*(?:BOARD|BD\.?|B\.D\.?)", re.IGNORECASE,
)
_LAYERS_PAREN_PATTERN = re.compile(r"\((\d{1,2})\)\s*LAYER", re.IGNORECASE)
_LAYERS_PLY_PATTERN = re.compile(r"\b(\d{1,2})\s*PLY\b", re.IGNORECASE)
_FIRE_RATING_PATTERN = re.compile(r"(\d{1,2})\s*-?\s*HOUR\s*FIRE\s*RATED|(\d{1,2})\s*HR\.?\s*FIRE", re.IGNORECASE)
_STC_PATTERN = re.compile(r"\bSTC[\s\-]?(\d{2,3})\b", re.IGNORECASE)
_INSULATION_PATTERN = re.compile(r"\bR[\s\-]?(\d{1,3})\b(?=.{0,25}?(?:BATT|INSULATION)|)", re.IGNORECASE)


def _to_fraction_in(text: str) -> float | None:
    """Parses '5/8', '3 5/8', '3-5/8' style dimension text into decimal
    inches. Returns None (never a guess) if the text doesn't parse cleanly.
    """
    t = text.strip()
    try:
        if "/" in t:
            whole = 0.0
            frac_part = t
            m = re.match(r"^(\d+)[\s\-](\d+/\d+)$", t)
            if m:
                whole = float(m.group(1))
                frac_part = m.group(2)
            num, den = frac_part.split("/")
            return round(whole + float(num) / float(den), 3)
        return round(float(t), 3)
    except (ValueError, ZeroDivisionError):
        return None


def extract_engineering_info_from_detail_text(text: str) -> dict[str, Any]:
    """Best-effort, conservative extraction of explicit engineering values
    from a resolved detail/section sheet's own text — thickness, stud
    depth/gauge/spacing, board type, layers, fire rating, acoustic rating,
    insulation. Every field is absent (not defaulted, not guessed) unless a
    clear, explicit textual match is found — per-field, not all-or-nothing.

    Returns a dict of only the fields actually found; each value is a
    plain dict {"value":..., "confidence":...} so a caller can attach
    source/method (which sheet, which extraction step) around it.
    """
    result: dict[str, dict[str, Any]] = {}
    t = text or ""

    m = _THICKNESS_PATTERN.search(t)
    if m:
        val = _to_fraction_in(m.group(1))
        if val is not None:
            result["thickness_in"] = {"value": val, "confidence": 0.90}

    m = _STUD_DEPTH_PATTERN.search(t)
    if m:
        val = _to_fraction_in(m.group(1))
        if val is not None:
            result["stud_depth_in"] = {"value": val, "confidence": 0.90}

    m = _STUD_GAUGE_PATTERN.search(t)
    if m:
        result["stud_gauge"] = {"value": f"{m.group(1)} GA", "confidence": 0.90}

    m = _STUD_SPACING_PATTERN.search(t)
    if m:
        result["stud_spacing_in"] = {"value": float(m.group(1)), "confidence": 0.85}

    m = _BOARD_PATTERN.search(t)
    if m and _to_fraction_in(m.group(1)) is not None:
        type_x = " Type X" if m.group(2) else ""
        result["board_type"] = {"value": f"{m.group(1)}\"{type_x} GWB", "confidence": 0.90}

    m = _LAYERS_PAREN_PATTERN.search(t) or _LAYERS_PLY_PATTERN.search(t)
    if m:
        result["layers"] = {"value": int(m.group(1)), "confidence": 0.85}

    m = _FIRE_RATING_PATTERN.search(t)
    if m:
        hours = m.group(1) or m.group(2)
        result["fire_rating_hr"] = {"value": float(hours), "confidence": 0.90}

    m = _STC_PATTERN.search(t)
    if m:
        result["sound_rating_stc"] = {"value": float(m.group(1)), "confidence": 0.90}

    m = _INSULATION_PATTERN.search(t)
    if m:
        result["insulation"] = {"value": f"R-{m.group(1)}", "confidence": 0.80}

    return result


def resolve_height_from_sheet_text(text: str) -> float | None:
    """Best-effort extraction of a single plausible wall/ceiling height
    (7.5-20 ft) from a resolved detail/section sheet's own text. Returns
    None when nothing extractable is found — callers must treat that as
    "sheet resolved, no height data", not fabricate a value.
    """
    candidates: list[float] = []
    for match in _HEIGHT_PATTERN.finditer(text or ""):
        try:
            ft = float(match.group(1))
            in_str = match.group(2)
            inches = float(in_str) if in_str else 0.0
            ht_ft = ft + inches / 12.0
            if 7.5 <= ht_ft <= 20.0:
                candidates.append(ht_ft)
        except ValueError:
            continue
    return min(candidates) if candidates else None
